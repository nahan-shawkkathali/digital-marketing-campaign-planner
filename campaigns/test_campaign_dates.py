from datetime import date, datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from .forms import CampaignRequestForm
from .models import Campaign
from .test_audit import AuditFixtures


class CampaignDateFormTests(SimpleTestCase):
    def setUp(self):
        self.today = date(2031, 3, 8)
        self.local_date = patch("campaigns.forms.timezone.localdate", return_value=self.today)
        self.local_date.start()
        self.addCleanup(self.local_date.stop)

    def data(self, **changes):
        return {"name": "Dated campaign", "description": "Campaign requirements",
                "start_date": self.today.isoformat(),
                "end_date": (self.today + timedelta(days=1)).isoformat(), **changes}

    def test_today_and_future_start_dates_are_valid(self):
        for offset in (0, 7):
            with self.subTest(offset=offset):
                start = self.today + timedelta(days=offset)
                form = CampaignRequestForm(self.data(start_date=start, end_date=start + timedelta(days=1)))
                self.assertTrue(form.is_valid(), form.errors)

    def test_past_start_date_is_rejected(self):
        form = CampaignRequestForm(self.data(start_date=self.today - timedelta(days=1)))
        self.assertEqual(form.errors["start_date"], ["Start date cannot be in the past."])

    def test_end_date_must_be_strictly_later(self):
        for offset in (-1, 0):
            with self.subTest(offset=offset):
                form = CampaignRequestForm(self.data(end_date=self.today + timedelta(days=offset)))
                self.assertEqual(form.errors["end_date"], ["End date must be after the start date."])
        self.assertTrue(CampaignRequestForm(self.data()).is_valid())

    def test_dates_remain_optional(self):
        for changes in ({"start_date": ""}, {"end_date": ""}, {"start_date": "", "end_date": ""}):
            with self.subTest(changes=changes):
                form = CampaignRequestForm(self.data(**changes))
                self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_date_strings_keep_field_validation(self):
        for field in ("start_date", "end_date"):
            with self.subTest(field=field):
                form = CampaignRequestForm(self.data(**{field: "not-a-date"}))
                self.assertEqual(form.errors[field], ["Enter a valid date."])

    def test_other_field_validation_is_preserved(self):
        form = CampaignRequestForm(self.data(name="", description="", budget="-1", platforms="x" * 256))
        self.assertEqual(set(form.errors), {"name", "description", "budget", "platforms"})
        self.assertEqual(form.errors["budget"], ["Budget cannot be negative."])

    def test_new_form_minimum_uses_local_date(self):
        form = CampaignRequestForm()
        self.assertEqual(form.fields["start_date"].widget.attrs["min"], self.today.isoformat())
        self.assertNotIn("min", form.fields["end_date"].widget.attrs)

    def test_end_minimum_tracks_bound_and_initial_start_dates(self):
        for start, minimum in ((date(2032, 2, 28), "2032-02-29"),
                               (date(2032, 2, 29), "2032-03-01"),
                               (date(2031, 12, 31), "2032-01-01")):
            for bound in (False, True):
                with self.subTest(start=start, bound=bound):
                    form = CampaignRequestForm(self.data(start_date=start)) if bound else CampaignRequestForm(initial={"start_date": start})
                    self.assertEqual(form.fields["end_date"].widget.attrs["min"], minimum)

    def test_missing_invalid_or_maximum_start_does_not_crash_widget_rendering(self):
        for start in ("", "invalid", "9999-12-31"):
            with self.subTest(start=start):
                form = CampaignRequestForm(self.data(start_date=start))
                self.assertNotIn("min", form.fields["end_date"].widget.attrs)
                self.assertIn('type="date"', str(form["start_date"]))

    def test_unsaved_instance_cannot_exempt_a_past_start_date(self):
        past = self.today - timedelta(days=5)
        form = CampaignRequestForm(self.data(start_date=past), instance=Campaign(start_date=past))
        self.assertEqual(form.errors["start_date"], ["Start date cannot be in the past."])

    def test_date_input_values_use_iso_format_in_other_locales(self):
        with translation.override("en-gb"):
            form = CampaignRequestForm(initial={"start_date": self.today, "end_date": self.today + timedelta(days=1)})
            self.assertIn('value="2031-03-08"', str(form["start_date"]))
            self.assertIn('value="2031-03-09"', str(form["end_date"]))

    def test_configured_timezone_controls_today_at_utc_day_boundaries(self):
        self.local_date.stop()
        cases = (
            ("Asia/Kolkata", datetime(2031, 1, 1, 20, tzinfo=datetime_timezone.utc), date(2031, 1, 2)),
            ("America/Los_Angeles", datetime(2031, 1, 2, 2, tzinfo=datetime_timezone.utc), date(2031, 1, 1)),
        )
        for zone, now, today in cases:
            with self.subTest(zone=zone), override_settings(TIME_ZONE=zone), timezone.override(None), patch("django.utils.timezone.now", return_value=now):
                self.assertEqual(CampaignRequestForm().fields["start_date"].widget.attrs["min"], today.isoformat())
                form = CampaignRequestForm(self.data(start_date=today, end_date=today + timedelta(days=1)))
                self.assertTrue(form.is_valid(), form.errors)
                form = CampaignRequestForm(self.data(start_date=today - timedelta(days=1), end_date=today))
                self.assertEqual(form.errors["start_date"], ["Start date cannot be in the past."])


class CampaignDateRequestTests(AuditFixtures):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.start = self.today - timedelta(days=30)
        self.end = self.today - timedelta(days=10)
        Campaign.objects.filter(pk=self.campaign.pk).update(
            start_date=self.start, end_date=self.end, status=Campaign.Status.PENDING,
        )
        self.campaign.refresh_from_db()
        self.client.force_login(self.owner)
        self.edit_url = reverse("client_campaign_edit", args=(self.campaign.pk,))

    def data(self, **changes):
        return {"name": "Dated request", "description": "Updated requirements",
                "start_date": self.start.isoformat(), "end_date": self.end.isoformat(), **changes}

    def test_manual_invalid_new_requests_do_not_create_or_change_records(self):
        before = list(Campaign.objects.values())
        cases = (
            ({"start_date": self.today - timedelta(days=1), "end_date": self.today}, "Start date cannot be in the past."),
            ({"start_date": self.today, "end_date": self.today}, "End date must be after the start date."),
            ({"start_date": self.today, "end_date": self.today - timedelta(days=1)}, "End date must be after the start date."),
        )
        for dates, error in cases:
            with self.subTest(dates=dates):
                response = self.client.post(reverse("campaign_request"), self.data(**dates))
                self.assertContains(response, error)
                self.assertEqual(list(Campaign.objects.values()), before)

    def test_new_requests_accept_today_and_future_dates(self):
        for offset in (0, 7):
            with self.subTest(offset=offset):
                start = self.today + timedelta(days=offset)
                response = self.client.post(reverse("campaign_request"), self.data(
                    name=f"Valid request {offset}", start_date=start, end_date=start + timedelta(days=1),
                ))
                self.assertRedirects(response, reverse("client_campaign_list"))
                saved = Campaign.objects.get(name=f"Valid request {offset}")
                self.assertEqual((saved.start_date, saved.end_date), (start, start + timedelta(days=1)))

    def test_historical_campaigns_remain_viewable_by_existing_roles(self):
        for archived in (False, True):
            Campaign.objects.filter(pk=self.campaign.pk).update(is_archived=archived)
            before = list(Campaign.objects.values())
            for user, page in ((self.owner, "client_campaign_detail"), (self.owner, "client_campaign_report"),
                               (self.staff, "administrator_campaign_detail"), (self.staff, "administrator_campaign_report"),
                               (self.employee_user, "employee_campaign_detail")):
                with self.subTest(archived=archived, page=page):
                    self.client.force_login(user)
                    response = self.client.get(reverse(page, args=(self.campaign.pk,)))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context["campaign"].start_date, self.start)
                    self.assertEqual(response.context["campaign"].end_date, self.end)
            self.assertEqual(list(Campaign.objects.values()), before)

    def test_pending_edit_accepts_unchanged_historical_dates(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.context["form"].fields["start_date"].widget.attrs["min"], self.start.isoformat())
        self.assertEqual(response.context["form"].fields["end_date"].widget.attrs["min"], (self.start + timedelta(days=1)).isoformat())
        self.assertContains(response, f'value="{self.start.isoformat()}"')
        response = self.client.post(self.edit_url, self.data())
        self.assertRedirects(response, reverse("client_campaign_detail", args=(self.campaign.pk,)))
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.start_date, self.campaign.end_date), (self.start, self.end))
        self.assertEqual(self.campaign.description, "Updated requirements")
        self.assertEqual(self.campaign.status, Campaign.Status.PENDING)

    def test_changed_historical_start_dates_are_rejected_without_saving(self):
        before = list(Campaign.objects.values())
        for offset in (-1, 1):
            with self.subTest(offset=offset):
                response = self.client.post(self.edit_url, self.data(start_date=self.start + timedelta(days=offset)))
                self.assertContains(response, "Start date cannot be in the past.")
                self.assertEqual(response.context["form"].fields["start_date"].widget.attrs["min"], self.today.isoformat())
                self.assertEqual(list(Campaign.objects.values()), before)

    def test_historical_start_can_be_changed_to_today_or_future(self):
        for offset in (0, 5):
            with self.subTest(offset=offset):
                start = self.today + timedelta(days=offset)
                response = self.client.post(self.edit_url, self.data(start_date=start, end_date=start + timedelta(days=1)))
                self.assertRedirects(response, reverse("client_campaign_detail", args=(self.campaign.pk,)))
                self.campaign.refresh_from_db()
                self.assertEqual((self.campaign.start_date, self.campaign.end_date), (start, start + timedelta(days=1)))

    def test_unchanged_historical_start_still_requires_later_end(self):
        before = list(Campaign.objects.values())
        for offset in (-1, 0):
            with self.subTest(offset=offset):
                response = self.client.post(self.edit_url, self.data(end_date=self.start + timedelta(days=offset)))
                self.assertContains(response, "End date must be after the start date.")
                self.assertNotIn("start_date", response.context["form"].errors)
                self.assertEqual(list(Campaign.objects.values()), before)

    def test_edit_with_previously_blank_start_cannot_add_a_past_date(self):
        Campaign.objects.filter(pk=self.campaign.pk).update(start_date=None)
        response = self.client.post(self.edit_url, self.data())
        self.assertContains(response, "Start date cannot be in the past.")
        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.start_date)
