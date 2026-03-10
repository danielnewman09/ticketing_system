from django import forms
from .models import OntologyNode, OntologyTriple


class OntologyNodeForm(forms.ModelForm):
    class Meta:
        model = OntologyNode
        fields = ["kind", "name", "qualified_name", "compound_refid", "description"]
        widgets = {
            "kind": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., Calculator"}),
            "qualified_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., myapp::Calculator"}),
            "compound_refid": forms.TextInput(attrs={"class": "form-control", "placeholder": "Link to codebase compound (optional)"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class OntologyTripleForm(forms.ModelForm):
    class Meta:
        model = OntologyTriple
        fields = ["subject", "predicate", "object"]
        widgets = {
            "subject": forms.Select(attrs={"class": "form-select"}),
            "predicate": forms.Select(attrs={"class": "form-select"}),
            "object": forms.Select(attrs={"class": "form-select"}),
        }
