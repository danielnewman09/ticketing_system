from django.db import models
from django import forms
from requirements.models import LowLevelRequirement
from .models import Ticket


class TicketForm(forms.ModelForm):
    link_llrs = forms.ModelMultipleChoiceField(
        queryset=LowLevelRequirement.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Link Low-Level Requirements",
    )

    class Meta:
        model = Ticket
        fields = ["title", "priority", "complexity", "summary", "ticket_type",
                  "components", "languages", "requires_math", "generate_tutorial"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "complexity": forms.Select(attrs={"class": "form-select"}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "ticket_type": forms.Select(attrs={"class": "form-select"}),
            "components": forms.CheckboxSelectMultiple,
            "languages": forms.CheckboxSelectMultiple,
            "requires_math": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "generate_tutorial": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            linked_ids = self.instance.low_level_requirements.values_list("id", flat=True)
            self.fields["link_llrs"].queryset = LowLevelRequirement.objects.filter(
                models.Q(id__in=linked_ids) | ~models.Q(tickets__isnull=False)
            ).distinct().select_related("high_level_requirement")
            self.fields["link_llrs"].initial = linked_ids
        else:
            self.fields["link_llrs"].queryset = LowLevelRequirement.objects.exclude(
                tickets__isnull=False
            ).select_related("high_level_requirement")
