from django import forms
from .models import OntologyNode, OntologyEdge


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


class OntologyEdgeForm(forms.ModelForm):
    class Meta:
        model = OntologyEdge
        fields = ["source", "target", "relationship", "label"]
        widgets = {
            "source": forms.Select(attrs={"class": "form-select"}),
            "target": forms.Select(attrs={"class": "form-select"}),
            "relationship": forms.Select(attrs={"class": "form-select"}),
            "label": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional label"}),
        }
