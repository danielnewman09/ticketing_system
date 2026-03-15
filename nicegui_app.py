#!/usr/bin/env python
"""
NiceGUI frontend prototype — requirements dashboard.

Shares Django's ORM and database directly. Run with:
    source .venv/bin/activate
    python nicegui_app.py

Then visit http://127.0.0.1:8081
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from asgiref.sync import sync_to_async
from nicegui import ui

from codebase.models import OntologyNode, OntologyTriple, Predicate
from components.models import Component
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationMethod,
)

# ---------------------------------------------------------------------------
# Theme / shared config
# ---------------------------------------------------------------------------

COLORS = {
    "primary": "#1a1a2e",
    "secondary": "#16213e",
    "accent": "#0f3460",
    "positive": "#10b981",
    "negative": "#ef4444",
    "warning": "#f59e0b",
    "info": "#3b82f6",
}

VERIFICATION_COLORS = {
    "automated": "positive",
    "review": "warning",
    "inspection": "info",
}

KIND_COLORS = {
    "class": "#4a90d9",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
    "method": "#2ecc71",
    "attribute": "#8b6914",
    "module": "#1abc9c",
    "function": "#27ae60",
    "constant": "#7f8c8d",
    "enum_value": "#c0392b",
    "primitive": "#95a5a6",
    "type_alias": "#e67e22",
}


def apply_theme():
    """Apply consistent dark theme."""
    ui.colors(**COLORS)
    ui.dark_mode(True)


# ---------------------------------------------------------------------------
# Shared layout
# ---------------------------------------------------------------------------

def page_layout(title: str = ""):
    """Create the shared page shell with a left drawer nav."""
    with ui.header().classes("items-center justify-between px-6"):
        with ui.row().classes("items-center gap-4"):
            ui.button(
                icon="menu", on_click=lambda: drawer.toggle()
            ).props("flat round color=white")
            ui.link("Ticketing System", "/").classes(
                "text-white text-lg font-bold no-underline"
            )

        # Top nav links for wider screens
        with ui.row().classes("gap-2 hidden md:flex"):
            for label, href in _NAV_ITEMS:
                ui.link(label, href).classes("text-white/80 hover:text-white no-underline text-sm px-2")

    drawer = ui.left_drawer(value=False).classes("bg-[#1a1a2e]").props("width=220 breakpoint=960")
    with drawer:
        ui.label("Navigation").classes("text-white/60 text-xs uppercase tracking-wider px-4 pt-4 pb-2")
        for label, href in _NAV_ITEMS:
            with ui.link(target=href).classes("no-underline"):
                ui.item(label).classes("text-white/90")
        ui.separator().classes("my-2")
        ui.label("Pipeline").classes("text-white/60 text-xs uppercase tracking-wider px-4 pt-2 pb-2")
        for label, href in _PIPELINE_ITEMS:
            with ui.link(target=href).classes("no-underline"):
                ui.item(label).classes("text-white/90")

    return drawer


_NAV_ITEMS = [
    ("Requirements", "/"),
    ("Components", "/components"),
    ("Ontology", "/ontology"),
]

_PIPELINE_ITEMS = [
    ("Run Demo Pipeline", "/pipeline"),
]


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def _stat_card(label: str, value, color: str = "primary"):
    """Compact stat card."""
    with ui.card().classes("p-4 min-w-[140px]"):
        ui.label(str(value)).classes(f"text-3xl font-bold text-{color}")
        ui.label(label).classes("text-xs text-gray-400 uppercase tracking-wider mt-1")


# ---------------------------------------------------------------------------
# Data-fetching functions (run in sync context via sync_to_async)
# ---------------------------------------------------------------------------

def _fetch_requirements_data():
    """Fetch all data needed for the requirements dashboard."""
    hlrs = []
    for hlr in HighLevelRequirement.objects.select_related("component").prefetch_related(
        "low_level_requirements__verifications",
    ).all():
        llrs = []
        for llr in hlr.low_level_requirements.all():
            methods = [v.method for v in llr.verifications.all()]
            llrs.append({
                "id": llr.pk,
                "description": llr.description,
                "methods": methods,
            })
        hlrs.append({
            "id": hlr.pk,
            "description": hlr.description,
            "component": hlr.component.name if hlr.component else None,
            "llrs": llrs,
        })

    unlinked = []
    for llr in LowLevelRequirement.objects.filter(
        high_level_requirement__isnull=True,
    ).prefetch_related("verifications"):
        methods = [v.method for v in llr.verifications.all()]
        unlinked.append({
            "id": llr.pk,
            "description": llr.description,
            "methods": methods,
        })

    return {
        "hlrs": hlrs,
        "unlinked_llrs": unlinked,
        "total_hlrs": HighLevelRequirement.objects.count(),
        "total_llrs": LowLevelRequirement.objects.count(),
        "total_verifications": VerificationMethod.objects.count(),
        "total_nodes": OntologyNode.objects.count(),
        "total_triples": OntologyTriple.objects.count(),
    }


def _fetch_hlr_detail(hlr_id):
    """Fetch all data needed for HLR detail page."""
    try:
        hlr = HighLevelRequirement.objects.select_related("component").prefetch_related(
            "low_level_requirements__verifications",
            "triples__subject",
            "triples__predicate",
            "triples__object",
            "low_level_requirements__triples__subject",
            "low_level_requirements__triples__predicate",
            "low_level_requirements__triples__object",
        ).get(pk=hlr_id)
    except HighLevelRequirement.DoesNotExist:
        return None

    llrs = []
    for llr in hlr.low_level_requirements.all():
        methods = [v.method for v in llr.verifications.all()]
        llrs.append({
            "id": llr.pk,
            "description": llr.description,
            "methods": methods,
        })

    all_triples = set(hlr.triples.all())
    for llr_obj in hlr.low_level_requirements.all():
        all_triples.update(llr_obj.triples.all())
    triples = [
        {
            "subject": t.subject.name,
            "predicate": t.predicate.name,
            "object": t.object.name,
        }
        for t in sorted(all_triples, key=lambda t: t.pk)
    ]

    return {
        "id": hlr.pk,
        "description": hlr.description,
        "component": hlr.component.name if hlr.component else None,
        "llrs": llrs,
        "triples": triples,
    }


def _fetch_llr_detail(llr_id):
    """Fetch all data needed for LLR detail page."""
    try:
        llr = LowLevelRequirement.objects.select_related(
            "high_level_requirement__component",
        ).prefetch_related(
            "verifications__conditions",
            "verifications__actions",
            "components",
            "triples__subject",
            "triples__predicate",
            "triples__object",
        ).get(pk=llr_id)
    except LowLevelRequirement.DoesNotExist:
        return None

    hlr = llr.high_level_requirement
    hlr_data = None
    if hlr:
        hlr_data = {
            "id": hlr.pk,
            "description": hlr.description,
            "component": hlr.component.name if hlr.component else None,
        }

    verifications = []
    for v in llr.verifications.all():
        preconditions = [
            {
                "member_qualified_name": c.member_qualified_name,
                "operator": c.operator,
                "expected_value": c.expected_value,
            }
            for c in v.conditions.filter(phase="pre").order_by("order")
        ]
        postconditions = [
            {
                "member_qualified_name": c.member_qualified_name,
                "operator": c.operator,
                "expected_value": c.expected_value,
            }
            for c in v.conditions.filter(phase="post").order_by("order")
        ]
        actions = [
            {
                "order": a.order,
                "description": a.description,
                "member_qualified_name": a.member_qualified_name,
            }
            for a in v.actions.order_by("order")
        ]
        verifications.append({
            "id": v.pk,
            "method": v.method,
            "test_name": v.test_name,
            "description": v.description,
            "preconditions": preconditions,
            "actions": actions,
            "postconditions": postconditions,
        })

    components = [c.name for c in llr.components.all()]

    triples = [
        {
            "subject": t.subject.name,
            "predicate": t.predicate.name,
            "object": t.object.name,
        }
        for t in llr.triples.all()
    ]

    return {
        "id": llr.pk,
        "description": llr.description,
        "hlr": hlr_data,
        "verifications": verifications,
        "components": components,
        "triples": triples,
    }


def _fetch_components_data():
    """Fetch all data needed for components page."""
    result = []
    for comp in Component.objects.select_related("parent", "language").prefetch_related(
        "high_level_requirements", "ontology_nodes",
    ).all():
        result.append({
            "name": comp.name,
            "language": str(comp.language) if comp.language else None,
            "parent": comp.parent.name if comp.parent else None,
            "hlr_count": comp.high_level_requirements.count(),
            "node_count": comp.ontology_nodes.count(),
        })
    return result


def _fetch_ontology_data():
    """Fetch all data needed for ontology page."""
    nodes = []
    kind_counts = {}
    for n in OntologyNode.objects.select_related("component").all():
        kind_counts[n.kind] = kind_counts.get(n.kind, 0) + 1
        nodes.append({
            "name": n.name,
            "kind": n.kind,
            "qualified_name": n.qualified_name,
            "component": n.component.name if n.component else "-",
        })

    return {
        "nodes": nodes[:200],
        "kind_counts": kind_counts,
        "total_nodes": len(nodes),
        "total_triples": OntologyTriple.objects.count(),
        "total_predicates": Predicate.objects.count(),
    }


# ---------------------------------------------------------------------------
# UI rendering helpers (no DB access — work with plain dicts)
# ---------------------------------------------------------------------------

def _render_hlr_card(hlr):
    """Render a single HLR as an expandable card with its LLR table."""
    llr_count = len(hlr["llrs"])

    with ui.card().classes("w-full mb-2"):
        with ui.row().classes("w-full items-start justify-between"):
            with ui.column().classes("flex-1 gap-0"):
                with ui.row().classes("items-center gap-2"):
                    ui.badge(f"HLR {hlr['id']}", color="blue").props("outline")
                    if hlr["component"]:
                        ui.badge(hlr["component"], color="grey")
                    ui.badge(
                        f"{llr_count} LLR{'s' if llr_count != 1 else ''}",
                        color="green" if llr_count > 0 else "grey",
                    ).classes("text-xs")
                ui.label(hlr["description"]).classes("text-sm mt-1")

            hlr_id = hlr["id"]
            with ui.button(icon="more_vert").props("flat round size=sm"):
                with ui.menu():
                    ui.menu_item("View Details", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}"))
                    ui.menu_item("Add LLR", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}#add-llr"))
                    ui.separator()
                    ui.menu_item("Decompose", on_click=lambda h=hlr_id: ui.notify(f"Would decompose HLR {h}"))

        # Expandable LLR table
        if hlr["llrs"]:
            with ui.expansion("Low-Level Requirements", icon="list").classes("w-full mt-2").props("dense"):
                _render_llr_table(hlr["llrs"])


def _render_llr_table(llrs):
    """Render an LLR table from plain dicts."""
    columns = [
        {"name": "id", "label": "ID", "field": "id", "align": "left", "sortable": True},
        {"name": "description", "label": "Description", "field": "description", "align": "left"},
        {"name": "verification", "label": "Verification", "field": "verification", "align": "left"},
    ]

    rows = []
    for llr in llrs:
        desc = llr["description"]
        rows.append({
            "id": llr["id"],
            "description": desc[:120] + ("..." if len(desc) > 120 else ""),
            "verification": ", ".join(llr["methods"]) if llr["methods"] else "-",
        })

    table = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full")
    table.props("dense flat")
    table.on("row-click", lambda e: ui.navigate.to(f"/llr/{e.args[1]['id']}"))

    # Custom cell rendering for verification badges
    table.add_slot(
        "body-cell-verification",
        """
        <q-td :props="props">
            <template v-for="method in props.value.split(', ')">
                <q-badge v-if="method !== '-'"
                    :color="method === 'automated' ? 'positive' : method === 'review' ? 'warning' : 'info'"
                    :label="method"
                    class="q-mr-xs text-xs"
                />
                <span v-else class="text-grey">-</span>
            </template>
        </q-td>
        """,
    )


def _render_verification_card(v):
    """Render a single verification method as a card with conditions/actions."""
    color = VERIFICATION_COLORS.get(v["method"], "grey")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-2"):
                ui.badge(v["method"], color=color).classes("text-xs")
                if v["test_name"]:
                    ui.label(v["test_name"]).classes("text-sm font-mono text-gray-300")

        if v["description"]:
            ui.label(v["description"]).classes("text-xs text-gray-400 mt-1")

        # Pre-conditions
        if v["preconditions"]:
            ui.separator().classes("my-2")
            ui.label("Pre-conditions").classes("text-xs uppercase tracking-wider text-gray-500 mb-1")
            for c in v["preconditions"]:
                with ui.row().classes("items-center gap-1"):
                    ui.label(c["member_qualified_name"]).classes("text-xs font-mono text-blue-300")
                    ui.label(c["operator"]).classes("text-xs text-gray-500")
                    ui.label(c["expected_value"]).classes("text-xs font-mono text-green-300")

        # Actions
        if v["actions"]:
            ui.separator().classes("my-2")
            ui.label("Actions").classes("text-xs uppercase tracking-wider text-gray-500 mb-1")
            for i, a in enumerate(v["actions"], 1):
                with ui.row().classes("items-center gap-2"):
                    ui.badge(str(i), color="grey").props("rounded").classes("text-xs")
                    ui.label(a["description"]).classes("text-xs")
                    if a["member_qualified_name"]:
                        ui.label(a["member_qualified_name"]).classes("text-xs font-mono text-gray-500")

        # Post-conditions
        if v["postconditions"]:
            ui.separator().classes("my-2")
            ui.label("Post-conditions").classes("text-xs uppercase tracking-wider text-gray-500 mb-1")
            for c in v["postconditions"]:
                with ui.row().classes("items-center gap-1"):
                    ui.label(c["member_qualified_name"]).classes("text-xs font-mono text-blue-300")
                    ui.label(c["operator"]).classes("text-xs text-gray-500")
                    ui.label(c["expected_value"]).classes("text-xs font-mono text-green-300")


def _render_triples_card(triples):
    """Render an ontology triples card from plain dicts."""
    with ui.card().classes("w-full"):
        ui.label("Ontology Triples").classes(
            "text-xs uppercase tracking-wider text-gray-400 mb-2"
        )
        if triples:
            triple_cols = [
                {"name": "subject", "label": "Subject", "field": "subject", "align": "left"},
                {"name": "predicate", "label": "Predicate", "field": "predicate", "align": "left"},
                {"name": "object", "label": "Object", "field": "object", "align": "left"},
            ]
            t = ui.table(columns=triple_cols, rows=triples).classes("w-full")
            t.props("dense flat")
            t.add_slot(
                "body-cell-predicate",
                '<q-td :props="props"><code class="text-cyan-300">{{ props.value }}</code></q-td>',
            )
        else:
            ui.label("No triples linked.").classes("text-sm text-gray-500")


# ---------------------------------------------------------------------------
# Page: Requirements dashboard (main page)
# ---------------------------------------------------------------------------

@ui.page("/")
async def requirements_page():
    apply_theme()
    page_layout("Requirements")

    data = await sync_to_async(_fetch_requirements_data, thread_sensitive=True)()

    # Stats row
    with ui.row().classes("w-full gap-4 flex-wrap px-2 mt-4"):
        _stat_card("HLRs", data["total_hlrs"], "blue-5")
        _stat_card("LLRs", data["total_llrs"], "green-5")
        _stat_card("Verifications", data["total_verifications"], "amber-5")
        _stat_card("Ontology Nodes", data["total_nodes"], "purple-5")
        _stat_card("Triples", data["total_triples"], "cyan-5")

    # Action bar
    with ui.row().classes("w-full items-center justify-between px-2 mt-6 mb-2"):
        ui.label("High-Level Requirements").classes("text-xl font-semibold")
        with ui.row().classes("gap-2"):
            ui.button("+ HLR", icon="add", on_click=lambda: ui.navigate.to("/hlr/new")).props(
                "color=positive size=sm"
            )

    # HLR cards
    for hlr in data["hlrs"]:
        _render_hlr_card(hlr)

    # Unlinked LLRs
    if data["unlinked_llrs"]:
        ui.separator().classes("my-4")
        ui.label("Unlinked LLRs").classes("text-lg font-semibold text-amber-400 px-2 mb-2")
        _render_llr_table(data["unlinked_llrs"])


# ---------------------------------------------------------------------------
# Page: HLR Detail
# ---------------------------------------------------------------------------

@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: int):
    apply_theme()
    page_layout(f"HLR {hlr_id}")

    hlr = await sync_to_async(_fetch_hlr_detail, thread_sensitive=True)(hlr_id)
    if not hlr:
        ui.label("HLR not found").classes("text-xl text-red-400")
        return

    # Breadcrumb
    with ui.row().classes("items-center gap-1 px-2 mt-4"):
        ui.link("Requirements", "/").classes("text-blue-400 text-sm no-underline")
        ui.label("/").classes("text-gray-500 text-sm")
        ui.label(f"HLR {hlr['id']}").classes("text-sm text-gray-300")

    # Header
    with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
        with ui.row().classes("items-center gap-3"):
            ui.label(f"HLR {hlr['id']}").classes("text-2xl font-bold")
            if hlr["component"]:
                ui.badge(hlr["component"], color="grey")
        with ui.row().classes("gap-2"):
            ui.button("Back", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
                "flat size=sm"
            )
            ui.button("Decompose", icon="account_tree", on_click=lambda: ui.notify("Would decompose")).props(
                "color=warning size=sm"
            )

    # Two-column layout
    with ui.row().classes("w-full gap-4 px-2 items-start"):
        # Left column
        with ui.column().classes("flex-1 gap-4"):
            with ui.card().classes("w-full"):
                ui.label("Description").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                ui.label(hlr["description"]).classes("text-sm")

            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label("Low-Level Requirements").classes(
                        "text-xs uppercase tracking-wider text-gray-400"
                    )
                    ui.button(icon="add", on_click=lambda: ui.notify("Would create LLR")).props(
                        "flat round size=xs color=positive"
                    )
                if hlr["llrs"]:
                    _render_llr_table(hlr["llrs"])
                else:
                    ui.label("No low-level requirements yet.").classes("text-sm text-gray-500")

        # Right column
        with ui.column().classes("flex-1 gap-4"):
            _render_triples_card(hlr["triples"])


# ---------------------------------------------------------------------------
# Page: LLR Detail
# ---------------------------------------------------------------------------

@ui.page("/llr/{llr_id}")
async def llr_detail_page(llr_id: int):
    apply_theme()
    page_layout(f"LLR {llr_id}")

    data = await sync_to_async(_fetch_llr_detail, thread_sensitive=True)(llr_id)
    if not data:
        ui.label("LLR not found").classes("text-xl text-red-400")
        return

    hlr = data["hlr"]

    # Breadcrumb
    with ui.row().classes("items-center gap-1 px-2 mt-4"):
        ui.link("Requirements", "/").classes("text-blue-400 text-sm no-underline")
        ui.label("/").classes("text-gray-500 text-sm")
        if hlr:
            ui.link(f"HLR {hlr['id']}", f"/hlr/{hlr['id']}").classes("text-blue-400 text-sm no-underline")
            ui.label("/").classes("text-gray-500 text-sm")
        ui.label(f"LLR {data['id']}").classes("text-sm text-gray-300")

    # Header
    with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
        ui.label(f"LLR {data['id']}").classes("text-2xl font-bold")
        ui.button("Back", icon="arrow_back", on_click=lambda: ui.navigate.to(
            f"/hlr/{hlr['id']}" if hlr else "/"
        )).props("flat size=sm")

    with ui.row().classes("w-full gap-4 px-2 items-start"):
        # Left column
        with ui.column().classes("flex-1 gap-4"):
            with ui.card().classes("w-full"):
                ui.label("Description").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                ui.label(data["description"]).classes("text-sm")

            if hlr:
                with ui.card().classes("w-full"):
                    ui.label("Parent HLR").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(f"HLR {hlr['id']}", color="blue").props("outline")
                        if hlr["component"]:
                            ui.badge(hlr["component"], color="grey")
                    desc = hlr["description"]
                    ui.link(
                        desc[:100] + ("..." if len(desc) > 100 else ""),
                        f"/hlr/{hlr['id']}",
                    ).classes("text-sm no-underline mt-1")

            # Verification cards
            if data["verifications"]:
                for v in data["verifications"]:
                    _render_verification_card(v)
            else:
                with ui.card().classes("w-full"):
                    ui.label("Verifications").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                    ui.label("No verifications defined.").classes("text-sm text-gray-500")

            # Components
            if data["components"]:
                with ui.card().classes("w-full"):
                    ui.label("Components").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                    with ui.row().classes("gap-2"):
                        for name in data["components"]:
                            ui.badge(name, color="grey")

        # Right column
        with ui.column().classes("flex-1 gap-4"):
            _render_triples_card(data["triples"])


# ---------------------------------------------------------------------------
# Page: Components
# ---------------------------------------------------------------------------

@ui.page("/components")
async def components_page():
    apply_theme()
    page_layout("Components")

    components = await sync_to_async(_fetch_components_data, thread_sensitive=True)()

    with ui.row().classes("w-full items-center justify-between px-2 mt-4 mb-4"):
        ui.label("Components").classes("text-xl font-semibold")

    if not components:
        ui.label("No components defined yet.").classes("text-gray-500 px-2")
        return

    with ui.row().classes("w-full gap-4 flex-wrap px-2"):
        for comp in components:
            with ui.card().classes("w-72"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label(comp["name"]).classes("text-lg font-semibold")
                    if comp["language"]:
                        ui.badge(comp["language"], color="grey").classes("text-xs")

                with ui.row().classes("gap-3 mt-2"):
                    with ui.row().classes("items-center gap-1"):
                        ui.icon("description", size="xs").classes("text-gray-500")
                        ui.label(f"{comp['hlr_count']} HLRs").classes("text-xs text-gray-400")
                    with ui.row().classes("items-center gap-1"):
                        ui.icon("hub", size="xs").classes("text-gray-500")
                        ui.label(f"{comp['node_count']} nodes").classes("text-xs text-gray-400")

                if comp["parent"]:
                    ui.label(f"Parent: {comp['parent']}").classes("text-xs text-gray-500 mt-1")


# ---------------------------------------------------------------------------
# Page: Ontology overview
# ---------------------------------------------------------------------------

@ui.page("/ontology")
async def ontology_page():
    apply_theme()
    page_layout("Ontology")

    data = await sync_to_async(_fetch_ontology_data, thread_sensitive=True)()

    with ui.row().classes("w-full items-center justify-between px-2 mt-4 mb-4"):
        ui.label("Ontology").classes("text-xl font-semibold")

    # Stats
    with ui.row().classes("w-full gap-4 flex-wrap px-2 mb-4"):
        _stat_card("Nodes", data["total_nodes"], "purple-5")
        _stat_card("Triples", data["total_triples"], "cyan-5")
        _stat_card("Predicates", data["total_predicates"], "amber-5")

    # Kind breakdown
    with ui.card().classes("w-full mx-2 mb-4"):
        ui.label("Nodes by Kind").classes("text-xs uppercase tracking-wider text-gray-400 mb-3")
        with ui.row().classes("gap-3 flex-wrap"):
            for kind, count in sorted(data["kind_counts"].items(), key=lambda x: -x[1]):
                color = KIND_COLORS.get(kind, "#666")
                with ui.row().classes("items-center gap-1"):
                    ui.html(f'<div style="width:12px;height:12px;border-radius:50%;background:{color}"></div>')
                    ui.label(f"{kind}: {count}").classes("text-sm")

    # Node table
    with ui.card().classes("w-full mx-2"):
        ui.label("All Nodes").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
        columns = [
            {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
            {"name": "kind", "label": "Kind", "field": "kind", "align": "left", "sortable": True},
            {"name": "qualified_name", "label": "Qualified Name", "field": "qualified_name", "align": "left"},
            {"name": "component", "label": "Component", "field": "component", "align": "left"},
        ]
        t = ui.table(columns=columns, rows=data["nodes"]).classes("w-full")
        t.props("dense flat")
        t.add_slot(
            "body-cell-kind",
            """
            <q-td :props="props">
                <q-badge :label="props.value" color="grey" class="text-xs" />
            </q-td>
            """,
        )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Ticketing System",
        port=8081,
        reload=True,
        show=False,
    )
