from django.db import models


class HighLevelRequirement(models.Model):
    description = models.TextField()
    component = models.ForeignKey(
        "components.Component",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="high_level_requirements",
        help_text="Architectural component this requirement belongs to",
    )
    dependency_context = models.JSONField(
        null=True,
        blank=True,
        help_text="Dependency assessment from the assess_dependencies agent",
    )
    triples = models.ManyToManyField(
        "codebase.OntologyTriple",
        related_name="high_level_requirements",
        blank=True,
        help_text="Ontology triples that express this requirement",
    )

    class Meta:
        app_label = "requirements"
        db_table = "high_level_requirements"

    def __str__(self):
        return self.description[:80] if self.description else f"HLR {self.pk}"

    def to_prompt_text(self, include_llrs=False, include_component=False):
        """Format this HLR as text for LLM prompts.

        Args:
            include_llrs: Include indented child LLRs.
            include_component: Include [Component: ...] tag.
        """
        comp = ""
        if include_component and self.component_id:
            comp = f" [Component: {self.component.name}]"
        line = f"HLR {self.id}{comp}: {self.description}"
        if not include_llrs:
            return line
        lines = [line]
        for llr in self.low_level_requirements.all():
            lines.append(f"  {llr.to_prompt_text()}")
        return "\n".join(lines)


def format_hlr_dict(hlr, include_component=False):
    """Format a single HLR dict as a prompt line.

    Works with dicts from .values() querysets. Supports both
    'component_name' and 'component__name' keys.
    """
    comp = ""
    if include_component:
        comp_name = hlr.get("component_name") or hlr.get("component__name")
        if comp_name:
            comp = f" [Component: {comp_name}]"
    return f"HLR {hlr['id']}{comp}: {hlr['description']}"


def format_hlrs_for_prompt(hlrs, llrs=None, include_component=False):
    """Format HLR/LLR dicts into a text block for agent prompts.

    Works with dicts from .values() querysets. For model instances,
    use HighLevelRequirement.to_prompt_text() instead.

    Args:
        hlrs: List of dicts with 'id' and 'description' keys.
        llrs: Optional list of LLR dicts with 'id', 'hlr_id', 'description'.
        include_component: Include [Component: ...] tag from hlr dicts.
    """
    from .llr import format_llr_dict

    lines = []
    for hlr in hlrs:
        lines.append(format_hlr_dict(hlr, include_component))
        if llrs:
            for llr in [l for l in llrs if l.get("hlr_id") == hlr["id"]]:
                lines.append(f"  {format_llr_dict(llr)}")
    if llrs:
        unlinked = [l for l in llrs if l.get("hlr_id") is None]
        if unlinked:
            lines.append("\nUnlinked LLRs:")
            for llr in unlinked:
                lines.append(f"  {format_llr_dict(llr)}")
    return "\n".join(lines)
