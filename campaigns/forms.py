from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .models import Campaign, ClientProfile, Deliverable, DeliverableMessage, EmployeeProfile, Task


class BootstrapFormMixin:
    def apply_bootstrap_styles(self):
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class ClientRegistrationForm(BootstrapFormMixin, UserCreationForm):
    email = forms.EmailField(required=True)
    company_name = forms.CharField(label="Company / Business Name", max_length=255, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "company_name", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            with transaction.atomic():
                user.save()
                if self.cleaned_data["company_name"]:
                    ClientProfile.objects.update_or_create(
                        user=user,
                        defaults={"company_name": self.cleaned_data["company_name"]},
                    )
        return user


class ClientLoginForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.apply_bootstrap_styles()


class ClientProfileForm(BootstrapFormMixin, forms.ModelForm):
    email = forms.EmailField(required=True)
    company_name = forms.CharField(label="Company / Business Name", max_length=255, required=False)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "company_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, "client_profile", None) if self.instance.pk else None
        self.initial.setdefault("company_name", profile.company_name if profile else "")
        self.apply_bootstrap_styles()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            with transaction.atomic():
                user.save()
                ClientProfile.objects.update_or_create(
                    user=user,
                    defaults={"company_name": self.cleaned_data["company_name"]},
                )
        return user


class AdministratorLoginForm(ClientLoginForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_staff or user.is_superuser):
            raise forms.ValidationError(
                "Administrator access is limited to staff users.",
                code="not_staff",
            )


class CampaignStatusForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ("status",)
        widgets = {"status": forms.Select(attrs={"class": "form-select"})}

    def clean_status(self):
        if self.instance.is_archived:
            raise forms.ValidationError("Archived campaigns cannot be updated.")
        return self.cleaned_data["status"]

    def save(self, commit=True):
        campaign = super().save(commit=False)
        if campaign.status == Campaign.Status.COMPLETED:
            campaign.progress_percentage = 100
        if commit:
            campaign.save()
        return campaign


class CampaignRequestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Campaign
        fields = (
            "name",
            "description",
            "campaign_type",
            "product_service_name",
            "target_audience",
            "budget",
            "start_date",
            "end_date",
            "platforms",
            "campaign_goal",
        )
        labels = {"platforms": "Platforms", "campaign_goal": "Campaign Goal"}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "campaign_goal": forms.Textarea(attrs={"rows": 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()

    def clean_budget(self):
        budget = self.cleaned_data["budget"]
        if budget is not None and budget < 0:
            raise forms.ValidationError("Budget cannot be negative.")
        return budget

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date cannot be before the start date.")
        return cleaned_data


class EmployeeLoginForm(ClientLoginForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not hasattr(user, "employee_profile"):
            raise forms.ValidationError(
                "This account is not registered as a marketing employee.",
                code="not_employee",
            )


class EmployeeCreationForm(BootstrapFormMixin, UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=False)
    job_title = forms.CharField(max_length=100, required=False)
    phone = forms.CharField(max_length=30, required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "job_title", "phone", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
            EmployeeProfile.objects.create(
                user=user,
                job_title=self.cleaned_data["job_title"],
                phone=self.cleaned_data["phone"],
            )
        return user


class EmployeeProfileForm(BootstrapFormMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=True, max_length=254)

    class Meta:
        model = EmployeeProfile
        fields = ("first_name", "last_name", "email", "job_title", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.instance.user.first_name
        self.fields["last_name"].initial = self.instance.user.last_name
        self.fields["email"].initial = self.instance.user.email
        self.apply_bootstrap_styles()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.user_id).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save(update_fields=("first_name", "last_name", "email"))
            profile.save()
        return profile


class AdministratorEmployeeForm(EmployeeProfileForm):
    is_active = forms.BooleanField(required=False, help_text="Inactive employees cannot sign in.")

    class Meta(EmployeeProfileForm.Meta):
        fields = EmployeeProfileForm.Meta.fields + ("is_active",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].initial = self.instance.user.is_active
        self.fields["is_active"].widget.attrs["class"] = "form-check-input"

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.user.is_active = self.cleaned_data["is_active"]
        if commit:
            profile.user.save(update_fields=("first_name", "last_name", "email", "is_active"))
            profile.save()
        return profile


class CampaignAssignmentForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ("assigned_employee",)
        widgets = {"assigned_employee": forms.Select(attrs={"class": "form-select"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_employee"].queryset = EmployeeProfile.objects.filter(
            user__is_active=True,
        ).select_related("user").order_by("user__first_name", "user__username")

    def clean_assigned_employee(self):
        employee = self.cleaned_data["assigned_employee"]
        if self.instance.is_archived:
            raise forms.ValidationError("Archived campaigns cannot be assigned.")
        if employee and self.instance.status not in (Campaign.Status.APPROVED, Campaign.Status.IN_PROGRESS):
            raise forms.ValidationError("Only approved campaigns can be assigned.")
        return employee


class EmployeeCampaignProgressForm(forms.ModelForm):
    progress_percentage = forms.IntegerField(
        min_value=0, max_value=100,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    status = forms.ChoiceField(
        choices=(
            (Campaign.Status.IN_PROGRESS, Campaign.Status.IN_PROGRESS.label),
            (Campaign.Status.COMPLETED, Campaign.Status.COMPLETED.label),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Campaign
        fields = ("progress_percentage", "status")

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.is_archived:
            raise forms.ValidationError("Archived campaigns cannot be updated.")
        if self.instance.status in (Campaign.Status.PENDING, Campaign.Status.REJECTED):
            raise forms.ValidationError("This campaign must be approved before work can be updated.")
        if cleaned_data.get("status") == Campaign.Status.COMPLETED and "progress_percentage" in cleaned_data:
            cleaned_data["progress_percentage"] = 100
        return cleaned_data


class DeliverableUploadForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Deliverable
        fields = ("title", "description", "uploaded_file")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "uploaded_file": forms.ClearableFileInput(
                attrs={"accept": ".pdf,.docx,.jpg,.jpeg,.png"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()


class DeliverableMessageForm(BootstrapFormMixin, forms.ModelForm):
    body = forms.CharField(label="Message", max_length=5000, widget=forms.Textarea(attrs={"rows": 3}))

    class Meta:
        model = DeliverableMessage
        fields = ("body",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()


class RevisionRequestForm(DeliverableMessageForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].label = "Revision comment"


class AdministratorTaskForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ("title", "description", "due_date", "assigned_employee")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, campaign, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign = campaign
        employees = EmployeeProfile.objects.filter(
            user__is_active=True, pk=campaign.assigned_employee_id,
        )
        self.fields["assigned_employee"].queryset = employees.select_related("user")
        self.fields["assigned_employee"].required = True
        self.apply_bootstrap_styles()

    def clean(self):
        cleaned_data = super().clean()
        if self.campaign.is_archived:
            raise forms.ValidationError("Archived campaigns cannot have new work assigned.")
        if not self.fields["assigned_employee"].queryset.exists():
            raise forms.ValidationError("Assign an active employee to this campaign before creating tasks.")
        return cleaned_data


class EmployeeTaskStatusForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("status",)
        widgets = {"status": forms.Select(attrs={"class": "form-select"})}
