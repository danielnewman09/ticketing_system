"""Recommendation card rendering for the dependency review page."""

from nicegui import ui

from frontend.theme import STATUS_COLORS

# ---------------------------------------------------------------------------
# Status styling
# ---------------------------------------------------------------------------

_STATUS_BADGE_COLORS = {
    "accepted": "positive",
    "rejected": "grey",
    "rejected_stdlib": "blue-grey",
}

_STATUS_GROUP_STYLES = [
    ("pending", "Pending Review", "text-gray-300"),
    ("accepted", "Accepted", "text-green-400"),
    ("rejected_stdlib", "Using Standard Library", "text-blue-400"),
    ("rejected", "Rejected", "text-gray-500"),
]


def _status_border_style(status: str) -> str:
    """Return inline CSS for the left-border status indicator."""
    if status == "accepted":
        return f"border-left: 3px solid {STATUS_COLORS['accepted']};"
    if status == "rejected_stdlib":
        return f"border-left: 3px solid {STATUS_COLORS['rejected_stdlib']}; opacity: 0.7;"
    if status == "rejected":
        return f"border-left: 3px solid {STATUS_COLORS['rejected']}; opacity: 0.6;"
    return ""


# ---------------------------------------------------------------------------
# Card sub-sections
# ---------------------------------------------------------------------------


def _render_header(rec: dict):
    """Name, stars, license, last-updated badges."""
    with ui.row().classes("items-center gap-3"):
        ui.label(rec["name"]).classes("text-lg font-bold")
        if rec["stars"]:
            ui.badge(f"{rec['stars']} stars", color="grey").classes("text-xs")
        if rec["license"]:
            ui.badge(rec["license"], color="grey").classes("text-xs")
        if rec["last_updated"]:
            ui.label(f"Updated {rec['last_updated'][:10]}").classes("text-xs text-gray-500")


def _render_actions(rec: dict, pending_recs: list[dict] | None, on_accept, on_reject):
    """Accept/Reject buttons when pending, or a status badge otherwise."""
    if pending_recs is not None:
        with ui.row().classes("gap-1"):
            ui.button(
                "Accept", icon="check",
                on_click=lambda _, r=rec, p=pending_recs: on_accept(r["id"], r["name"], p),
            ).props("color=positive size=sm")
            ui.button(
                "Reject", icon="close",
                on_click=lambda _, r=rec: on_reject(r["id"], r["name"]),
            ).props("color=negative size=sm outline")
    else:
        label = "stdlib" if rec["status"] == "rejected_stdlib" else rec["status"]
        ui.badge(label, color=_STATUS_BADGE_COLORS.get(rec["status"], "grey"))


def _render_body(rec: dict):
    """GitHub link, description, pros/cons, relevant HLRs/structures."""
    if rec["github_url"]:
        ui.link(rec["github_url"], rec["github_url"]).classes(
            "text-xs text-blue-400 no-underline"
        )

    if rec["description"]:
        ui.label(rec["description"]).classes("text-sm mt-2")

    if rec["pros"] or rec["cons"]:
        with ui.row().classes("w-full gap-4 mt-3"):
            if rec["pros"]:
                with ui.column().classes("flex-1"):
                    ui.label("Pros").classes("text-xs text-green-400 uppercase tracking-wider mb-1")
                    for pro in rec["pros"]:
                        ui.label(f"+ {pro}").classes("text-xs text-green-300")
            if rec["cons"]:
                with ui.column().classes("flex-1"):
                    ui.label("Cons").classes("text-xs text-red-400 uppercase tracking-wider mb-1")
                    for con in rec["cons"]:
                        ui.label(f"- {con}").classes("text-xs text-red-300")

    hlrs = rec.get("relevant_hlrs", [])
    structs = rec.get("relevant_structures", [])
    if hlrs or structs:
        with ui.row().classes("gap-2 mt-2 flex-wrap"):
            for hlr_id in hlrs:
                ui.link(
                    f"HLR {hlr_id}", f"/hlr/{hlr_id}",
                ).classes("text-xs text-blue-400 no-underline").props("outline")
            for struct in structs:
                ui.badge(struct, color="grey").classes("text-xs font-mono")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_recommendation_card(
    rec: dict, *, pending_recs: list[dict] | None = None, on_accept=None, on_reject=None,
):
    """Render a single recommendation card with optional action buttons."""
    with ui.card().classes("w-full mx-2 mb-3").style(_status_border_style(rec["status"])):
        with ui.row().classes("w-full items-center justify-between"):
            _render_header(rec)
            _render_actions(rec, pending_recs, on_accept, on_reject)
        _render_body(rec)


def render_recs_by_status(
    recs: list[dict], *, on_accept, on_reject, on_use_stdlib,
):
    """Group recommendations by status and render each group."""
    grouped = {}
    for r in recs:
        grouped.setdefault(r["status"], []).append(r)

    for status, heading, color_cls in _STATUS_GROUP_STYLES:
        group = grouped.get(status)
        if not group:
            continue

        if status == "pending":
            with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-2"):
                ui.label(heading).classes(f"text-sm font-semibold {color_cls}")
                ui.button(
                    "Use Standard Library", icon="code",
                    on_click=lambda p=group: on_use_stdlib(p),
                ).props("size=sm outline").classes("text-blue-400 border-blue-400").tooltip(
                    "Reject all pending and use standard library instead"
                )
        else:
            ui.label(heading).classes(f"text-sm font-semibold {color_cls} px-2 mt-4 mb-2")

        for rec in group:
            render_recommendation_card(
                rec,
                pending_recs=group if status == "pending" else None,
                on_accept=on_accept,
                on_reject=on_reject,
            )
