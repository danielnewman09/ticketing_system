"""AI Assist endpoint — takes page context + user query, returns LLM suggestions."""

import json
import os
import re
from datetime import datetime

from django.apps import apps
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from agents.llm_client import call_text

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "ai_assist")

# Models that AI assist is allowed to modify
_ALLOWED_MODELS = {
    "HighLevelRequirement", "LowLevelRequirement", "VerificationMethod",
    "Ticket", "TicketAcceptanceCriteria", "TicketFile", "TicketReference",
    "Component", "Language",
    "OntologyNode", "OntologyTriple",
}


SYSTEM_PROMPT = """\
You are an AI assistant embedded in a project management and requirements
engineering tool. The user is viewing a page that displays specific data
(provided below as JSON). Based on the user's query, propose concrete
modifications to the data.

## Data model

These are the database models and their writable fields:

- **Ticket**: title, summary, priority (critical/high/medium/low),
  complexity (small/medium/large), ticket_type (feature/bug/task), author
- **TicketAcceptanceCriteria**: ticket (FK id), description
- **TicketFile**: ticket (FK id), file_path, change_type, description
- **HighLevelRequirement**: description, component (FK id)
- **LowLevelRequirement**: high_level_requirement (FK id), description
- **VerificationMethod**: low_level_requirement (FK id),
  method (automated/review/inspection), test_name, description
- **Component**: name, parent (FK id), language (FK id)
- **Language**: name, version
- **OntologyNode**: kind, name, qualified_name, description
- **OntologyTriple**: subject (FK id), predicate (FK id), object (FK id)

Related objects shown as nested arrays in the context (e.g., low_level_requirements
inside a HighLevelRequirement) are SEPARATE records. To add a child, CREATE a new
record of the child model with the parent FK set. Do NOT try to update the parent's
nested array.

## Response format

Respond with a JSON object containing:

- "summary": A brief explanation of what you propose (1-3 sentences).
- "edits": An array of proposed edits. Each edit is an object with:
    - "model": The model name (e.g., "LowLevelRequirement", "Ticket")
    - "id": The primary key of the record to modify (null for new records)
    - "action": One of "create", "update", "delete"
    - "fields": An object mapping field names to new values (for create/update).
      Use only the writable fields listed above. For foreign keys, use the integer ID.
    - "reason": Why this change is needed (1 sentence)

Respond with ONLY the JSON object, no markdown fences or extra text.

## Guidelines

- Only propose changes to data that is shown in the page context.
- Keep modifications minimal and targeted to the user's request.
- For "update" actions, only include fields that should change.
- Preserve existing IDs; do not renumber or reassign foreign keys unless asked.
- To add a related object, use "create" with the FK field set to the parent's ID.
- If the user's request is unclear, propose the most reasonable interpretation
  and explain your reasoning in the summary.
"""


@require_POST
def ai_assist(request):
    """Handle an AI assist request.

    Expects JSON body with:
        - context: dict describing the page data
        - query: str with the user's request
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    page_context = body.get("context", {})
    query = body.get("query", "").strip()

    if not query:
        return JsonResponse({"error": "No query provided"}, status=400)

    user_message = (
        f"## Page context\n\n```json\n{json.dumps(page_context, indent=2)}\n```\n\n"
        f"## User request\n\n{query}"
    )

    # Build log path: logs/ai_assist/<page_name>/<timestamp>.md
    page_name = page_context.get("page", "unknown")
    page_name = re.sub(r"[^a-zA-Z0-9_]", "_", page_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prompt_log_file = os.path.join(LOGS_DIR, page_name, f"{timestamp}.md")

    response_text = call_text(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=4096,
        prompt_log_file=prompt_log_file,
    )

    # Parse the LLM response as JSON
    # Strip markdown fences if the model wraps its output
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]  # remove opening fence
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        return JsonResponse({
            "summary": response_text,
            "edits": [],
            "raw": True,
        })

    return JsonResponse(result)


def _find_model(name):
    """Look up a Django model class by name across all installed apps."""
    if name not in _ALLOWED_MODELS:
        return None
    for app_config in apps.get_app_configs():
        try:
            return app_config.get_model(name)
        except LookupError:
            continue
    return None


@require_POST
def ai_assist_apply(request):
    """Apply a set of proposed edits from AI assist.

    Expects JSON body with:
        - edits: list of edit objects (model, id, action, fields)
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    edits = body.get("edits", [])
    if not edits:
        return JsonResponse({"error": "No edits provided"}, status=400)

    applied = []
    errors = []

    with transaction.atomic():
        for edit in edits:
            model_name = edit.get("model", "")
            Model = _find_model(model_name)
            if Model is None:
                errors.append(f"Unknown or disallowed model: {model_name}")
                continue

            action = edit.get("action")
            pk = edit.get("id")
            fields = edit.get("fields", {})

            try:
                if action == "create":
                    obj = Model(**fields)
                    obj.full_clean()
                    obj.save()
                    applied.append({"model": model_name, "id": obj.pk, "action": "created"})

                elif action == "update" and pk is not None:
                    obj = Model.objects.get(pk=pk)
                    for field, value in fields.items():
                        setattr(obj, field, value)
                    obj.full_clean()
                    obj.save()
                    applied.append({"model": model_name, "id": pk, "action": "updated"})

                elif action == "delete" and pk is not None:
                    Model.objects.filter(pk=pk).delete()
                    applied.append({"model": model_name, "id": pk, "action": "deleted"})

                else:
                    errors.append(f"Invalid action '{action}' for {model_name}")

            except Exception as e:
                errors.append(f"{model_name} {action}: {e}")

    return JsonResponse({"applied": applied, "errors": errors})
