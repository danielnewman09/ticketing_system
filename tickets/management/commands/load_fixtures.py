import json
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand

from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    TicketRequirement,
)
from tickets.models import (
    Component,
    Language,
    Ticket,
    TicketAcceptanceCriteria,
    TicketFile,
    TicketReference,
)


class Command(BaseCommand):
    help = "Load ticket fixture data from JSON files"

    def add_arguments(self, parser):
        default_dir = Path(__file__).resolve().parent.parent.parent / "fixtures" / "calculator-cpp"
        parser.add_argument(
            "--fixtures-dir",
            default=str(default_dir),
            help="Path to the fixtures directory",
        )

    def handle(self, *args, **options):
        fixtures_dir = Path(options["fixtures_dir"])

        hlr_path = fixtures_dir / "high_level_requirements.json"
        llr_path = fixtures_dir / "requirements.json"
        tickets_path = fixtures_dir / "tickets.json"

        # Load high-level requirements
        with open(hlr_path) as f:
            hlrs = json.load(f)
        for hlr in hlrs:
            HighLevelRequirement.objects.update_or_create(
                id=hlr["id"], defaults={"description": hlr["description"]}
            )
        self.stdout.write(f"Loaded {len(hlrs)} high-level requirements")

        # Load low-level requirements
        with open(llr_path) as f:
            llrs = json.load(f)
        for llr in llrs:
            LowLevelRequirement.objects.update_or_create(
                id=llr["id"],
                defaults={
                    "high_level_requirement_id": llr.get("high_level_requirement_id"),
                    "description": llr["description"],
                    "verification": llr["verification"],
                },
            )
        self.stdout.write(f"Loaded {len(llrs)} low-level requirements")

        # Load tickets
        with open(tickets_path) as f:
            tickets = json.load(f)
        for t in tickets:
            # Parse created_date string to datetime
            created_at = None
            if t.get("created_date"):
                created_at = datetime.strptime(t["created_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

            defaults = {
                "title": t["title"],
                "ticket_type": t.get("ticket_type", "feature").lower(),
                "priority": (t.get("priority") or "").lower(),
                "complexity": (t.get("complexity") or "").lower(),
                "author": t.get("author") or "",
                "summary": t.get("summary") or "",
                "parent_id": t.get("parent_id"),
                "requires_math": t.get("requires_math", False),
                "generate_tutorial": t.get("generate_tutorial", False),
            }
            if created_at:
                defaults["created_at"] = created_at

            ticket, _ = Ticket.objects.update_or_create(id=t["id"], defaults=defaults)

            # Components (comma-separated string → M2M)
            ticket.components.clear()
            for name in (t.get("target_components") or "").split(","):
                name = name.strip()
                if name:
                    component, _ = Component.objects.get_or_create(name=name)
                    ticket.components.add(component)

            # Languages (comma-separated string → M2M)
            ticket.languages.clear()
            for name in (t.get("languages") or "C++").split(","):
                name = name.strip()
                if name:
                    language, _ = Language.objects.get_or_create(name=name)
                    ticket.languages.add(language)

            # Acceptance criteria
            ticket.acceptance_criteria.all().delete()
            for ac in t.get("acceptance_criteria", []):
                TicketAcceptanceCriteria.objects.create(
                    ticket=ticket, description=ac["description"]
                )

            # Files
            ticket.files.all().delete()
            for f_entry in t.get("files", []):
                TicketFile.objects.create(
                    ticket=ticket,
                    file_path=f_entry["file_path"],
                    change_type=f_entry["change_type"],
                    description=f_entry.get("description") or "",
                )

            # References
            ticket.references.all().delete()
            for ref in t.get("references", []):
                TicketReference.objects.create(
                    ticket=ticket,
                    ref_type=ref["ref_type"],
                    ref_target=ref["ref_target"],
                )

            # Link ticket to LLRs that belong to its HLRs
            for hlr_id in t.get("high_level_requirement_ids", []):
                llr_ids = LowLevelRequirement.objects.filter(
                    high_level_requirement_id=hlr_id
                ).values_list("id", flat=True)
                for llr_id in llr_ids:
                    TicketRequirement.objects.get_or_create(
                        ticket=ticket, low_level_requirement_id=llr_id
                    )

        self.stdout.write(f"Loaded {len(tickets)} tickets")

        # Generate embeddings for all tickets
        from search.embeddings import upsert_ticket_embedding
        for ticket in Ticket.objects.all():
            upsert_ticket_embedding(ticket.id, ticket.title, ticket.summary)
        self.stdout.write(f"Generated embeddings for {Ticket.objects.count()} tickets")

        self.stdout.write(self.style.SUCCESS("Done!"))
