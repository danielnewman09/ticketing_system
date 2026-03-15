from django import forms
from django.forms import inlineformset_factory
from .models import (
    Component,
    Language,
    BuildSystem,
    TestFramework,
    DependencyManager,
    Dependency,
)

FC = "form-control"
FC_SM = "form-control form-control-sm"


class ComponentForm(forms.ModelForm):
    class Meta:
        model = Component
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": FC}),
        }


class LanguageForm(forms.ModelForm):
    class Meta:
        model = Language
        fields = ["name", "version"]
        widgets = {
            "name": forms.TextInput(attrs={"class": FC}),
            "version": forms.TextInput(
                attrs={"class": FC, "placeholder": "e.g. 3.13"}
            ),
        }


BuildSystemFormSet = inlineformset_factory(
    Language,
    BuildSystem,
    fields=["name", "config_file", "version"],
    extra=1,
    can_delete=True,
    widgets={
        "name": forms.TextInput(attrs={"class": FC_SM}),
        "config_file": forms.TextInput(attrs={"class": FC_SM}),
        "version": forms.TextInput(attrs={"class": FC_SM}),
    },
)

TestFrameworkFormSet = inlineformset_factory(
    Language,
    TestFramework,
    fields=["name", "config_file", "test_discovery_path"],
    extra=1,
    can_delete=True,
    widgets={
        "name": forms.TextInput(attrs={"class": FC_SM}),
        "config_file": forms.TextInput(attrs={"class": FC_SM}),
        "test_discovery_path": forms.TextInput(attrs={"class": FC_SM}),
    },
)

DependencyManagerFormSet = inlineformset_factory(
    Language,
    DependencyManager,
    fields=["name", "manifest_file", "lock_file"],
    extra=1,
    can_delete=True,
    widgets={
        "name": forms.TextInput(attrs={"class": FC_SM}),
        "manifest_file": forms.TextInput(attrs={"class": FC_SM}),
        "lock_file": forms.TextInput(attrs={"class": FC_SM}),
    },
)

DependencyFormSet = inlineformset_factory(
    DependencyManager,
    Dependency,
    fields=["name", "version", "is_dev"],
    extra=1,
    can_delete=True,
    widgets={
        "name": forms.TextInput(attrs={"class": FC_SM}),
        "version": forms.TextInput(
            attrs={"class": FC_SM, "placeholder": "e.g. >=1.0,<2.0"}
        ),
        "is_dev": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    },
)
