"""Mixin for views that provide AI assist context."""

import json

from django.forms.models import model_to_dict


class AiAssistMixin:
    """Add AI assist context to template context.

    Views should implement get_ai_context() to return a dict describing
    the page's data. This gets serialized as JSON and made available to
    the frontend AI assist component.
    """

    def get_ai_context(self):
        """Return a dict describing the data on this page.

        Override in subclasses. Default: serialize the main object for
        DetailViews, or return an empty dict.
        """
        obj = getattr(self, "object", None)
        if obj is not None:
            return {
                "model": obj.__class__.__name__,
                "data": _serialize_instance(obj),
            }
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ai_ctx = self.get_ai_context()
        context["ai_context_json"] = json.dumps(ai_ctx, default=str)
        return context


def _serialize_instance(obj, depth=0):
    """Serialize a model instance to a dict, including key relations."""
    if depth > 1:
        return {"id": obj.pk, "str": str(obj)}

    data = model_to_dict(obj)
    # Convert non-serializable values
    for key, value in list(data.items()):
        if hasattr(value, "pk"):
            data[key] = {"id": value.pk, "str": str(value)}
        elif hasattr(value, "all"):
            # M2M or reverse FK queryset
            data[key] = [{"id": r.pk, "str": str(r)} for r in value.all()[:20]]
    return data
