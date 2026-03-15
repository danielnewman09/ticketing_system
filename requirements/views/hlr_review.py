import json

from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from requirements.models import HighLevelRequirement
from agents.review.review_hlrs import review_hlrs


@require_POST
def hlr_review_start(request):
    """Trigger the HLR review agent and render the proposal page."""
    hlrs = list(HighLevelRequirement.objects.values("id", "description"))
    if not hlrs:
        return redirect("requirement_list")

    result = review_hlrs(hlrs)

    # Build context: original HLRs keyed by ID, and proposals.
    # The agent may omit original_id, so we match non-"add" proposals to
    # originals by position as a fallback.
    originals = {h["id"]: h["description"] for h in hlrs}
    unmatched_originals = list(hlrs)  # ordered queue for positional fallback

    proposals = []
    for p in result.proposals:
        original_id = p.original_id

        # If no original_id but action implies one, match by position
        if original_id is None and p.action in ("keep", "modify", "delete"):
            if unmatched_originals:
                original_id = unmatched_originals.pop(0)["id"]
        elif original_id is not None:
            # Remove from unmatched queue so positional matching stays aligned
            unmatched_originals = [h for h in unmatched_originals if h["id"] != original_id]

        proposals.append({
            "action": p.action,
            "original_id": original_id,
            "original_description": originals.get(original_id, "") if original_id else "",
            "description": p.description,
            "rationale": p.rationale,
        })

    return render(request, "requirements/hlr/review.html", {
        "proposals": proposals,
        "proposals_json": json.dumps(proposals),
        "original_count": len(hlrs),
    })


@require_POST
def hlr_review_apply(request):
    """Apply the user's accepted HLR changes."""
    proposals = json.loads(request.POST.get("proposals_json", "[]"))
    if not proposals:
        return redirect("requirement_list")

    with transaction.atomic():
        for p in proposals:
            action = p.get("action")
            original_id = p.get("original_id")
            description = p.get("description", "").strip()

            if action == "keep" and original_id:
                # No change needed
                continue
            elif action == "modify" and original_id and description:
                hlr = HighLevelRequirement.objects.filter(pk=original_id).first()
                if hlr:
                    hlr.description = description
                    hlr.save(update_fields=["description"])
            elif action == "add" and description:
                HighLevelRequirement.objects.create(description=description)
            elif action == "delete" and original_id:
                HighLevelRequirement.objects.filter(pk=original_id).delete()

    return redirect("requirement_list")
