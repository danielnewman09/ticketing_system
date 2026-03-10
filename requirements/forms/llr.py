from django import forms
from django.forms import inlineformset_factory

from requirements.models import (
    LowLevelRequirement,
    VerificationMethod,
    VerificationCondition,
    VerificationAction,
)


class LowLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = LowLevelRequirement
        fields = [
            "high_level_requirement",
            "components",
            "description",
        ]
        widgets = {
            "high_level_requirement": forms.Select(attrs={"class": "form-select"}),
            "components": forms.CheckboxSelectMultiple(),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Describe the low-level requirement"}),
        }
        labels = {
            "high_level_requirement": "Parent HLR",
        }


class VerificationMethodForm(forms.ModelForm):
    class Meta:
        model = VerificationMethod
        fields = ["method", "test_name", "description"]
        widgets = {
            "method": forms.Select(attrs={"class": "form-select"}),
            "test_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., test_press_addition_key"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "What this verification does"}),
        }


class VerificationConditionForm(forms.ModelForm):
    class Meta:
        model = VerificationCondition
        fields = ["phase", "order", "member_qualified_name", "operator", "expected_value", "ontology_node"]
        widgets = {
            "phase": forms.HiddenInput(),
            "order": forms.HiddenInput(),
            "member_qualified_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g., calc::core::Calculator::operation"}),
            "operator": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "expected_value": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g., Operation::Addition"}),
            "ontology_node": forms.Select(attrs={"class": "form-select form-select-sm"}),
        }


class VerificationActionForm(forms.ModelForm):
    class Meta:
        model = VerificationAction
        fields = ["order", "description", "ontology_node", "member_qualified_name"]
        widgets = {
            "order": forms.HiddenInput(),
            "description": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g., Press the + button"}),
            "ontology_node": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "member_qualified_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "e.g., calc::gui::OperatorButton::onClick"}),
        }


VerificationMethodFormSet = inlineformset_factory(
    LowLevelRequirement,
    VerificationMethod,
    form=VerificationMethodForm,
    extra=1,
    can_delete=True,
)

VerificationConditionFormSet = inlineformset_factory(
    VerificationMethod,
    VerificationCondition,
    form=VerificationConditionForm,
    extra=1,
    can_delete=True,
)

VerificationActionFormSet = inlineformset_factory(
    VerificationMethod,
    VerificationAction,
    form=VerificationActionForm,
    extra=1,
    can_delete=True,
)
