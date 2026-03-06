from django import forms
from .models import Component


class ComponentForm(forms.ModelForm):
    class Meta:
        model = Component
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }
