from django import forms
from django.forms import inlineformset_factory
from .models import HighLevelRequirement, LowLevelRequirement, LLRVerification


class HighLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = HighLevelRequirement
        fields = ["actor", "actor_compound_refid", "action", "subject", "subject_compound_refid", "description"]
        widgets = {
            "actor": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., A developer"}),
            "actor_compound_refid": forms.TextInput(attrs={"class": "form-control", "placeholder": "Compound refid (optional)"}),
            "action": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., compiles"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., the codebase"}),
            "subject_compound_refid": forms.TextInput(attrs={"class": "form-control", "placeholder": "Compound refid (optional)"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional additional detail"}),
        }


class LowLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = LowLevelRequirement
        fields = [
            "high_level_requirement",
            "actor", "actor_compound_refid",
            "action",
            "subject", "subject_compound_refid",
            "components",
            "description",
        ]
        widgets = {
            "high_level_requirement": forms.Select(attrs={"class": "form-select"}),
            "actor": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., The end user"}),
            "actor_compound_refid": forms.TextInput(attrs={"class": "form-control", "placeholder": "Compound refid (optional)"}),
            "action": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., presses the + button"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., in the GUI"}),
            "subject_compound_refid": forms.TextInput(attrs={"class": "form-control", "placeholder": "Compound refid (optional)"}),
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
