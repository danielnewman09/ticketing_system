from django import forms
from .models import HighLevelRequirement, LowLevelRequirement


class HighLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = HighLevelRequirement
        fields = ["description"]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class LowLevelRequirementForm(forms.ModelForm):
    class Meta:
        model = LowLevelRequirement
        fields = ["description", "verification", "high_level_requirement"]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "verification": forms.Select(attrs={"class": "form-select"}),
            "high_level_requirement": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "high_level_requirement": "Parent HLR",
        }
