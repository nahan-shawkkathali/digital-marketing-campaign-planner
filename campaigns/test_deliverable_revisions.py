from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils.html import escape

from .models import Campaign, Deliverable, DeliverableMessage
from .test_audit import AuditFixtures


class DeliverableRevisionTests(AuditFixtures):
    comment = "Please make the product image larger and change the headline."

    def discussion_url(self, deliverable=None, campaign=None):
        return reverse("deliverable_discussion", args=((campaign or self.campaign).pk,
                                                        (deliverable or self.deliverable).pk))

    def decision_url(self, decision="request_changes", deliverable=None, campaign=None):
        return reverse("client_deliverable_decision", args=((campaign or self.campaign).pk,
                                                            (deliverable or self.deliverable).pk, decision))

    def revision_url(self, deliverable=None):
        return reverse("employee_deliverable_revision", args=(self.campaign.pk, (deliverable or self.deliverable).pk))

    def request_changes(self, deliverable=None):
        self.client.force_login(self.owner)
        return self.client.post(self.decision_url(deliverable=deliverable), {"body": self.comment})

    def upload_data(self, **overrides):
        return {"title": "Revised Creative", "description": "Updated headline",
                "uploaded_file": SimpleUploadedFile("creative.pdf", b"revised file", content_type="application/pdf"),
                **overrides}

    def upload_revision(self, previous=None):
        self.client.force_login(self.employee_user)
        return self.client.post(self.revision_url(previous), self.upload_data())

    def test_client_requests_changes_with_preserved_sender_comment_and_status(self):
        self.assertRedirects(self.request_changes(), self.discussion_url())
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.CHANGES_REQUESTED)
        message = self.deliverable.messages.get()
        self.assertEqual(message.sender, self.owner)
        self.assertEqual(message.body, self.comment)
        self.assertEqual(message.kind, DeliverableMessage.Kind.CHANGES_REQUESTED)
        self.assertIsNotNone(message.created_at)
        self.client.force_login(self.employee_user)
        response = self.client.get(self.discussion_url())
        self.assertContains(response, self.comment)
        self.assertContains(response, "Changes Requested")
        self.assertContains(response, self.revision_url())

    def test_request_changes_requires_nonblank_comment_and_preserves_pending_on_error(self):
        self.client.force_login(self.owner)
        for data in ({}, {"body": ""}, {"body": " \n\t "}, {"body": "x" * 5001}):
            response = self.client.post(self.decision_url(), data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("body", response.context["revision_form"].errors)
            self.deliverable.refresh_from_db()
            self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.PENDING)
            self.assertFalse(DeliverableMessage.objects.exists())

    def test_other_client_and_mismatched_campaign_cannot_request_changes(self):
        other = Campaign.objects.create(client=self.owner, name="Other", description="Other")
        self.client.force_login(self.other_client)
        self.assertEqual(self.client.post(self.decision_url(), {"body": self.comment}).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.decision_url(campaign=other), {"body": self.comment}).status_code, 404)
        self.assertFalse(DeliverableMessage.objects.exists())

    def test_review_is_post_only_csrf_protected_and_client_only(self):
        self.client.force_login(self.owner)
        for method in ("get", "head", "put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.decision_url()).status_code, 405)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.post(self.decision_url(), {"body": self.comment}).status_code, 403)
        for user in (self.employee_user, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.decision_url(), {"body": self.comment}).status_code, 302)
        self.assertFalse(DeliverableMessage.objects.exists())

    def test_review_history_cannot_be_overwritten_by_repeat_decisions(self):
        self.request_changes()
        for decision in ("approve", "reject", "request_changes"):
            self.client.post(self.decision_url(decision), {"body": "Replace review"})
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.CHANGES_REQUESTED)
        self.assertEqual(list(self.deliverable.messages.values_list("body", flat=True)), [self.comment])

    def test_client_and_employee_discussion_is_chronological_and_sender_is_server_controlled(self):
        self.request_changes()
        for user, body in ((self.employee_user, "Sure, I will update it."), (self.owner, "Thank you.")):
            self.client.force_login(user)
            self.assertRedirects(self.client.post(self.discussion_url(), {
                "body": body, "sender": self.other_client.pk, "kind": "approved", "deliverable": 999999,
            }), self.discussion_url())
        messages = list(self.deliverable.messages.all())
        self.assertEqual([m.sender_id for m in messages], [self.owner.pk, self.employee_user.pk, self.owner.pk])
        self.assertEqual([m.kind for m in messages], ["changes_requested", "comment", "comment"])
        response = self.client.get(self.discussion_url())
        self.assertEqual([m.pk for m in response.context["discussion_messages"]], [m.pk for m in messages])
        html = response.content.decode()
        self.assertLess(html.index(self.comment), html.index("Sure, I will update it."))
        self.assertLess(html.index("Sure, I will update it."), html.index("Thank you."))

    def test_discussion_rejects_empty_messages_and_escapes_text(self):
        self.client.force_login(self.owner)
        for body in ("", " \n ", "x" * 5001):
            response = self.client.post(self.discussion_url(), {"body": body})
            self.assertIn("body", response.context["message_form"].errors)
        self.assertFalse(DeliverableMessage.objects.exists())
        body = '<script>alert("revision")</script>'
        self.client.post(self.discussion_url(), {"body": body})
        response = self.client.get(self.discussion_url())
        self.assertContains(response, escape(body))
        self.assertNotContains(response, body)

    def test_unauthorized_users_cannot_read_or_post_discussion(self):
        self.request_changes()
        for user in (self.other_client, self.other_employee_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.discussion_url()).status_code, 404)
            self.assertEqual(self.client.post(self.discussion_url(), {"body": "Intrusion"}).status_code, 404)
        self.client.logout()
        self.assertRedirects(self.client.get(self.discussion_url()), f'{reverse("login")}?next={self.discussion_url()}')
        self.assertEqual(DeliverableMessage.objects.count(), 1)

    def test_admin_can_view_discussion_but_cannot_participate(self):
        self.request_changes()
        self.client.force_login(self.staff)
        response = self.client.get(self.discussion_url())
        self.assertContains(response, self.comment)
        self.assertNotContains(response, ">Send Message</button>")
        self.assertEqual(self.client.post(self.discussion_url(), {"body": "Admin message"}).status_code, 403)

    def test_discussion_checks_campaign_and_deliverable_pair(self):
        other = Campaign.objects.create(client=self.owner, name="Other", description="Other")
        for user in (self.owner, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.discussion_url(campaign=other)).status_code, 404)
        self.assertEqual(DeliverableMessage.objects.count(), 0)

    def test_discussion_requires_csrf_and_supported_methods(self):
        self.client.force_login(self.owner)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.post(self.discussion_url(), {"body": "Message"}).status_code, 403)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.discussion_url()).status_code, 405)
        self.assertFalse(DeliverableMessage.objects.exists())

    def test_revision_preserves_original_record_file_and_review(self):
        self.deliverable.uploaded_file.save("creative.pdf", SimpleUploadedFile("creative.pdf", b"original file"))
        original_path = self.deliverable.uploaded_file.path
        self.request_changes()
        self.deliverable.refresh_from_db()
        before = Deliverable.objects.filter(pk=self.deliverable.pk).values().get()
        self.upload_revision()
        revision = Deliverable.objects.get(original=self.deliverable)
        self.assertEqual(Deliverable.objects.filter(pk=self.deliverable.pk).values().get(), before)
        self.assertEqual(revision.version, 2)
        self.assertEqual(revision.campaign, self.campaign)
        self.assertEqual(revision.uploaded_by, self.employee)
        self.assertEqual(revision.approval_status, Deliverable.ApprovalStatus.PENDING)
        self.assertNotEqual(revision.uploaded_file.path, original_path)
        self.assertEqual(self.deliverable.uploaded_file.read(), b"original file")
        self.deliverable.uploaded_file.close()
        self.assertEqual(revision.uploaded_file.read(), b"revised file")
        revision.uploaded_file.close()
        self.assertEqual(self.deliverable.messages.get().body, self.comment)

    def test_revision_cannot_forge_version_owner_status_or_original(self):
        self.request_changes()
        self.client.force_login(self.employee_user)
        self.client.post(self.revision_url(), self.upload_data(
            original=999999, campaign=999999, uploaded_by=self.other_employee.pk, version=100,
            approval_status="approved",
        ))
        revision = Deliverable.objects.get(original=self.deliverable)
        self.assertEqual((revision.campaign_id, revision.uploaded_by_id, revision.version, revision.approval_status),
                         (self.campaign.pk, self.employee.pk, 2, "pending"))

    def test_only_current_version_awaiting_changes_can_be_revised(self):
        self.client.force_login(self.employee_user)
        for status in ("pending", "approved"):
            Deliverable.objects.filter(pk=self.deliverable.pk).update(approval_status=status)
            self.assertEqual(self.client.get(self.revision_url()).status_code, 403)
            self.assertEqual(self.client.post(self.revision_url(), self.upload_data()).status_code, 403)
        Deliverable.objects.filter(pk=self.deliverable.pk).update(approval_status="changes_requested")
        self.upload_revision()
        self.assertEqual(self.client.post(self.revision_url(), self.upload_data()).status_code, 403)
        self.assertEqual(Deliverable.objects.count(), 2)

    def test_revised_version_can_be_approved_without_changing_original_review(self):
        self.request_changes()
        self.upload_revision()
        revision = Deliverable.objects.get(original=self.deliverable)
        self.client.force_login(self.owner)
        self.client.post(self.decision_url("approve", revision))
        revision.refresh_from_db()
        self.deliverable.refresh_from_db()
        self.assertEqual(revision.approval_status, Deliverable.ApprovalStatus.APPROVED)
        self.assertEqual(self.deliverable.approval_status, Deliverable.ApprovalStatus.CHANGES_REQUESTED)
        self.assertEqual(revision.messages.get().kind, "approved")
        self.assertEqual(self.client.get(self.revision_url(revision)).status_code, 302)

    def test_multiple_revision_rounds_keep_version_order_current_marker_and_all_messages(self):
        self.request_changes()
        self.upload_revision()
        second = Deliverable.objects.get(original=self.deliverable, version=2)
        self.request_changes(second)
        self.upload_revision(second)
        third = Deliverable.objects.get(original=self.deliverable, version=3)
        self.client.force_login(self.owner)
        self.client.post(self.decision_url("approve", third))
        response = self.client.get(self.discussion_url())
        self.assertEqual([v.version for v in response.context["versions"]], [1, 2, 3])
        self.assertEqual(response.context["current_version"].pk, third.pk)
        self.assertEqual(len(response.context["discussion_messages"]), 3)
        self.assertContains(response, "Current version: 3")
        annotated = list(Deliverable.objects.with_current_version().order_by("version"))
        self.assertEqual([d.is_current for d in annotated], [False, False, True])
        self.assertEqual([d.pk for d in Deliverable.objects.with_current_version().filter(has_newer_version=False)], [third.pk])

    def test_other_employees_clients_and_mismatched_ids_cannot_upload_revisions(self):
        self.request_changes()
        self.client.force_login(self.other_employee_user)
        self.assertEqual(self.client.get(self.revision_url()).status_code, 404)
        self.assertEqual(self.client.post(self.revision_url(), self.upload_data()).status_code, 404)
        other = Campaign.objects.create(client=self.owner, name="Other", description="Other", assigned_employee=self.employee)
        self.client.force_login(self.employee_user)
        url = reverse("employee_deliverable_revision", args=(other.pk, self.deliverable.pk))
        self.assertEqual(self.client.post(url, self.upload_data()).status_code, 404)
        for user in (self.owner, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.revision_url(), self.upload_data()).status_code, 302)
        self.assertEqual(Deliverable.objects.count(), 1)

    def test_revision_requires_csrf_and_valid_file_without_creating_history_on_get(self):
        self.request_changes()
        self.client.force_login(self.employee_user)
        self.assertContains(self.client.get(self.revision_url()), "Upload Revised Version")
        self.assertEqual(Deliverable.objects.count(), 1)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.employee_user)
        self.assertEqual(browser.post(self.revision_url(), self.upload_data()).status_code, 403)
        for upload in (None, SimpleUploadedFile("bad.html", b"bad"), SimpleUploadedFile("empty.pdf", b"")):
            data = self.upload_data()
            if upload is None:
                data.pop("uploaded_file")
            else:
                data["uploaded_file"] = upload
            response = self.client.post(self.revision_url(), data)
            self.assertIn("uploaded_file", response.context["form"].errors)
        self.assertEqual(Deliverable.objects.count(), 1)
        self.assertEqual(list(self.media_root.rglob("*.pdf")), [])

    def test_reassignment_revokes_discussion_revision_and_file_access(self):
        self.request_changes()
        self.client.force_login(self.employee_user)
        self.assertEqual(self.client.get(self.discussion_url()).status_code, 200)
        self.assertEqual(self.client.get(self.revision_url()).status_code, 200)
        Campaign.objects.filter(pk=self.campaign.pk).update(assigned_employee=self.other_employee)
        self.assertEqual(self.client.post(self.discussion_url(), {"body": "Old employee"}).status_code, 404)
        self.assertEqual(self.client.post(self.revision_url(), self.upload_data()).status_code, 404)
        self.assertEqual(self.client.get(self.deliverable.uploaded_file.url).status_code, 404)
        self.client.force_login(self.other_employee_user)
        self.assertContains(self.client.get(self.discussion_url()), self.comment)
        self.assertRedirects(self.client.post(self.discussion_url(), {"body": "New employee"}), self.discussion_url())
        self.client.post(self.revision_url(), self.upload_data())
        self.assertEqual(Deliverable.objects.get(original=self.deliverable).uploaded_by, self.other_employee)

    def test_archived_campaign_preserves_read_only_discussion_and_prevents_revisions(self):
        self.request_changes()
        Campaign.objects.filter(pk=self.campaign.pk).update(is_archived=True)
        for user in (self.owner, self.employee_user, self.staff):
            self.client.force_login(user)
            response = self.client.get(self.discussion_url())
            self.assertContains(response, self.comment)
            self.assertNotContains(response, ">Send Message</button>")
            self.assertNotContains(response, "Upload Revised Version")
            self.assertEqual(self.client.post(self.discussion_url(), {"body": "New work"}).status_code, 403)
        self.client.force_login(self.employee_user)
        self.assertEqual(self.client.post(self.revision_url(), self.upload_data()).status_code, 404)
        self.assertEqual(Deliverable.objects.count(), 1)
        self.assertEqual(DeliverableMessage.objects.count(), 1)

    def test_pending_and_rejected_campaigns_cannot_receive_revisions(self):
        self.request_changes()
        self.client.force_login(self.employee_user)
        for status in (Campaign.Status.PENDING, Campaign.Status.REJECTED):
            Campaign.objects.filter(pk=self.campaign.pk).update(status=status)
            self.assertEqual(self.client.post(self.revision_url(), self.upload_data()).status_code, 403)
        self.assertEqual(Deliverable.objects.count(), 1)

    def test_historical_rejected_deliverables_render_and_can_be_revised_without_rewriting(self):
        Deliverable.objects.filter(pk=self.deliverable.pk).update(approval_status="rejected")
        for user in (self.owner, self.employee_user, self.staff):
            self.client.force_login(user)
            self.assertContains(self.client.get(self.discussion_url()), "Rejected")
        self.upload_revision()
        self.deliverable.refresh_from_db()
        self.assertEqual(self.deliverable.approval_status, "rejected")
        self.assertEqual(Deliverable.objects.get(original=self.deliverable).approval_status, "pending")

    def test_review_ui_offers_approve_and_request_changes_with_required_comment(self):
        self.client.force_login(self.owner)
        for page, args in (("client_campaign_detail", (self.campaign.pk,)), ("client_deliverables", ())):
            response = self.client.get(reverse(page, args=args))
            self.assertContains(response, "Approve")
            self.assertContains(response, "Request Changes")
            self.assertContains(response, 'name="body" rows="3" maxlength="5000" required')
            self.assertNotContains(response, self.decision_url("reject"))
            self.assertContains(response, self.discussion_url())
