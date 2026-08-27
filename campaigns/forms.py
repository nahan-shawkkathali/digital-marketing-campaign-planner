from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Campaign, EmployeeProfile


class BootstrapFormMixin:
    def apply_bootstrap_styles(self):
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class ClientRegistrationForm(BootstrapFormMixin, UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_styles()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ClientLoginForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.apply_bootstrap_styles()


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
    email = forms.EmailField(required=True)

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

    def clean_assigned_employee(self):
        employee = self.cleaned_data["assigned_employee"]
        if employee and self.instance.status != Campaign.Status.APPROVED:
            raise forms.ValidationError("Only approved campaigns can be assigned.")
        return employee


class EmployeeCampaignProgressForm(forms.ModelForm):
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
        widgets = {
            "progress_percentage": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == Campaign.Status.COMPLETED:
            cleaned_data["progress_percentage"] = 100
        return cleaned_data
