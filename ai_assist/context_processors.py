"""Context processor that passes ai_context_json to all templates."""


def ai_context(request):
    """Make ai_context_json available to all templates.

    The actual value is set by AiAssistMixin.get_context_data().
    This processor just ensures the variable exists (as empty) so the
    base template can reference it without errors on views that don't
    use the mixin.
    """
    return {"ai_context_json": "{}"}
