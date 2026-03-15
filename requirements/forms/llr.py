from django import forms

from requirements.models import LowLevelRequirement


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
