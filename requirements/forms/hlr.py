from django import forms

from requirements.models import HighLevelRequirement


class HighLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = HighLevelRequirement
        fields = ["description"]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Describe the high-level requirement"}),
        }
