"""Mixin for views that provide AI assist context."""

import json


class AiAssistMixin:
    """Add AI assist context to template context.

    Views should implement get_ai_context() to return a dict describing
    the page's data. This gets serialized as JSON and made available to
    the frontend AI assist component.
    """

    def get_ai_context(self):
        """Return a dict describing the data on this page.

        Override in subclasses. Default: use to_prompt_text() on the main
        object for DetailViews, or return an empty dict.
        """
        obj = getattr(self, "object", None)
        if obj is not None and hasattr(obj, "to_prompt_text"):
            return {
                "model": obj.__class__.__name__,
                "context": obj.to_prompt_text(),
            }
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ai_ctx = self.get_ai_context()
        context["ai_context_json"] = json.dumps(ai_ctx, default=str)
        return context
