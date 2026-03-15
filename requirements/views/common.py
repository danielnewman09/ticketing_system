import json

from django.urls import reverse, reverse_lazy
from django.views.generic import ListView

from ai_assist.mixins import AiAssistMixin
from requirements.models import HighLevelRequirement, LowLevelRequirement


class RequirementListView(AiAssistMixin, ListView):
    model = HighLevelRequirement
    template_name = "requirements/requirement_list.html"
    context_object_name = "hlrs"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "component",
        ).prefetch_related(
            "low_level_requirements__components",
            "low_level_requirements__verifications",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unlinked_llrs"] = LowLevelRequirement.objects.filter(
            high_level_requirement__isnull=True
        ).prefetch_related("verifications")
        return context

    def get_ai_context(self):
        hlrs = []
        for hlr in self.get_queryset():
            llrs = []
            for llr in hlr.low_level_requirements.all():
                llrs.append({
                    "id": llr.id,
                    "description": llr.description,
                    "verifications": [v.method for v in llr.verifications.all()],
                })
            hlrs.append({
                "id": hlr.id,
                "description": hlr.description,
                "component": hlr.component.name if hlr.component else None,
                "low_level_requirements": llrs,
            })
        return {"page": "requirements_list", "high_level_requirements": hlrs}


def _build_requirement_graph(req):
    """Build graph data for a single requirement's ontology triples."""
    nodes = []
    edges = []
    seen_node_ids = set()

    for triple in req.triples.select_related("subject", "object", "predicate").all():
        for ont_node in (triple.subject, triple.object):
            node_id = f"node-{ont_node.pk}"
            if node_id not in seen_node_ids:
                seen_node_ids.add(node_id)
                nodes.append({
                    "id": node_id,
                    "name": ont_node.name,
                    "qualified_name": ont_node.qualified_name,
                    "kind": ont_node.kind,
                    "group": "ontology",
                    "compound_refid": ont_node.compound_refid,
                    "description": ont_node.description,
                    "url": reverse("ontology_node_detail", kwargs={"pk": ont_node.pk}),
                })
        edges.append({
            "source": f"node-{triple.subject_id}",
            "target": f"node-{triple.object_id}",
            "predicate": triple.predicate.name,
        })

    return {"nodes": nodes, "edges": edges}
