from django import forms
from django.forms import inlineformset_factory

from requirements.models import LowLevelRequirement, LLRVerification


class LowLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = LowLevelRequirement
        fields = [
            "high_level_requirement",
            "actor",
            "action",
            "subject",
            "components",
            "description",
        ]
        widgets = {
            "high_level_requirement": forms.Select(attrs={"class": "form-select"}),
            "actor": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., The end user"}),
            "action": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., presses the + button"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., in the GUI"}),
            "components": forms.CheckboxSelectMultiple(),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional additional detail"}),
        }
        labels = {
            "high_level_requirement": "Parent HLR",
        }


class LLRVerificationForm(forms.ModelForm):
    class Meta:
        model = LLRVerification
        fields = ["method", "confirmation", "test_name"]
        widgets = {
            "method": forms.Select(attrs={"class": "form-select"}),
            "confirmation": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., operator field populated with ADDITION enum"}),
            "test_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., user_presses_addition_key"}),
        }


LLRVerificationFormSet = inlineformset_factory(
    LowLevelRequirement,
    LLRVerification,
    form=LLRVerificationForm,
    extra=1,
    can_delete=True,
)
