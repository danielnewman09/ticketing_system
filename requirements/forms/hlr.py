from django import forms

from requirements.models import HighLevelRequirement


class HighLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = HighLevelRequirement
        fields = ["actor", "action", "subject", "description"]
        widgets = {
            "actor": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., A developer"}),
            "action": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., compiles"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., the codebase"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional additional detail"}),
        }
