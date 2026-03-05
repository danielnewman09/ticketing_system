"""Tests for ticket content indexing: parsing, storage, and querying.

Validates:
- Markdown parsing: title, summary, requirements, acceptance criteria,
  workflow log, files, references, canonical phase mapping
- Database round-trip: index_single_ticket, index_tickets
- TicketQuerier: search, get, list, create
"""

from pathlib import Path

import pytest

from ticketing_system.indexer import (
    _map_canonical_phase,
    _parse_title,
    _parse_summary,
    _parse_requirements,
    _parse_acceptance_criteria,
    _parse_workflow_log,
    _parse_files,
    _parse_references,
    _detect_ticket_type,
    index_single_ticket,
    index_tickets,
)
from ticketing_system.querier import TicketQuerier


# ---------------------------------------------------------------------------
# Sample ticket markdown
# ---------------------------------------------------------------------------

SAMPLE_TICKET = """\
# Feature Ticket: Collision Detection Narrow Phase

## Status
- [x] Draft
- [x] Ready for Design
- [x] Design Complete — Awaiting Review
- [x] Design Approved — Ready for Prototype
- [ ] Prototype Complete — Awaiting Review
- [ ] Ready for Implementation
- [ ] Implementation Complete — Awaiting Test Writing
- [ ] Test Writing Complete — Awaiting Quality Gate
- [ ] Quality Gate Passed — Awaiting Review
- [ ] Approved — Ready to Merge
- [ ] Merged / Complete

## Metadata
- **Created**: 2025-06-15
- **Author**: Daniel Newman
- **Priority**: High
- **Estimated Complexity**: Large
- **Target Component(s)**: msd-sim, msd-assets
- **Languages**: C++
- **Generate Tutorial**: No
- **Requires Math Design**: Yes

---

## Summary
Implement narrow-phase collision detection using GJK and EPA algorithms
for convex polytopes. This builds on the broad-phase sweep from ticket 0040.

## Requirements

| ID | Requirement | Verification | Test/Proof | Status |
|----|-------------|--------------|------------|--------|
| R1 | GJK algorithm correctly determines intersection for convex polytopes | Automated | `tests/collision/test_gjk.cpp::Intersection` | Draft |
| R2 | EPA provides contact normal and penetration depth within tolerance | Automated | `tests/collision/test_epa.cpp::ContactNormal` | Verified |
| R3 | Performance meets 60fps target for 100 bodies | Automated | `tests/collision/test_perf.cpp::Benchmark100Bodies` | Draft |
| R4 | Algorithm handles degenerate cases (coplanar faces, coincident vertices) | Review | — | Draft |

## Acceptance Criteria
- [x] AC1: GJK algorithm correctly determines intersection
- [ ] AC2: EPA provides contact normal and penetration depth
- [ ] AC3: Performance meets 60fps target for 100 bodies

## Workflow Log

### Design Phase
- **Started**: 2025-06-16T10:00:00Z
- **Completed**: 2025-06-18T14:30:00Z
- **Branch**: 0050-design
- **Artifacts**:
  - `docs/designs/0050_collision_narrow/design.md`
  - `docs/designs/0050_collision_narrow/collision.puml`
- **Notes**: Approved with minor revisions

### Implementation Phase
- **Started**: 2025-06-20T09:00:00Z

## Files

### New Files
- `msd/msd-sim/src/collision/gjk.cpp` — GJK algorithm implementation
- `msd/msd-sim/src/collision/epa.cpp` — EPA algorithm implementation

### Modified Files
- `msd/msd-sim/src/collision/pipeline.cpp` — Integration with collision pipeline

## References
- Ticket 0040 — Broad phase sweep and prune
- `msd/msd-sim/src/collision/broad_phase.cpp`

## Dependencies
- Parent ticket 0035
- Blocks 0060
"""


# ===========================================================================
# Canonical phase mapping
# ===========================================================================


def test_map_canonical_phase_draft():
    assert _map_canonical_phase("Draft") == "draft"


def test_map_canonical_phase_design_complete():
    assert _map_canonical_phase("Design Complete — Awaiting Review") == "design"


def test_map_canonical_phase_design_approved():
    assert _map_canonical_phase("Design Approved — Ready for Prototype") == "design_review"


def test_map_canonical_phase_merged():
    assert _map_canonical_phase("Merged / Complete") == "merged"


def test_map_canonical_phase_unknown_defaults_to_draft():
    assert _map_canonical_phase("Something Unknown") == "draft"


# ===========================================================================
# Title parsing
# ===========================================================================


def test_parse_title_feature_ticket():
    assert _parse_title(SAMPLE_TICKET) == "Collision Detection Narrow Phase"


def test_parse_title_plain_heading():
    assert _parse_title("# My Simple Title\n\nSome text.") == "My Simple Title"


def test_parse_title_empty_content():
    assert _parse_title("") == "Untitled"


# ===========================================================================
# Summary parsing
# ===========================================================================


def test_parse_summary():
    summary = _parse_summary(SAMPLE_TICKET)
    assert summary is not None
    assert "GJK" in summary


def test_parse_summary_missing():
    assert _parse_summary("# No summary here") is None


# ===========================================================================
# Requirements parsing
# ===========================================================================


def test_parse_requirements_table_count():
    reqs = _parse_requirements(SAMPLE_TICKET)
    assert len(reqs) == 4


def test_parse_requirements_table_ids():
    reqs = _parse_requirements(SAMPLE_TICKET)
    ids = [r["requirement_id"] for r in reqs]
    assert ids == ["R1", "R2", "R3", "R4"]


def test_parse_requirements_table_verification_methods():
    reqs = _parse_requirements(SAMPLE_TICKET)
    methods = [r["verification_method"] for r in reqs]
    assert methods == ["automated", "automated", "automated", "review"]


def test_parse_requirements_table_test_links():
    reqs = _parse_requirements(SAMPLE_TICKET)
    r1 = next(r for r in reqs if r["requirement_id"] == "R1")
    assert r1["test_link"] == "tests/collision/test_gjk.cpp::Intersection"
    r4 = next(r for r in reqs if r["requirement_id"] == "R4")
    assert r4["test_link"] is None


def test_parse_requirements_table_status():
    reqs = _parse_requirements(SAMPLE_TICKET)
    r2 = next(r for r in reqs if r["requirement_id"] == "R2")
    assert r2["status"] == "verified"
    r1 = next(r for r in reqs if r["requirement_id"] == "R1")
    assert r1["status"] == "draft"


def test_parse_requirements_legacy_format():
    content = """\
## Requirements

### R1: First Requirement
- Description of the first requirement

### R2: Second Requirement
- Description of the second requirement
"""
    reqs = _parse_requirements(content)
    assert len(reqs) == 2
    assert reqs[0]["requirement_id"] == "R1"
    assert reqs[0]["verification_method"] == "review"
    assert reqs[0]["status"] == "draft"


def test_parse_requirements_empty():
    assert _parse_requirements("# No requirements") == []


# ===========================================================================
# Acceptance criteria parsing
# ===========================================================================


def test_parse_acceptance_criteria_count():
    criteria = _parse_acceptance_criteria(SAMPLE_TICKET)
    assert len(criteria) == 3


def test_parse_acceptance_criteria_ids():
    criteria = _parse_acceptance_criteria(SAMPLE_TICKET)
    ids = [c["criterion_id"] for c in criteria]
    assert "AC1" in ids


def test_parse_acceptance_criteria_met_status():
    criteria = _parse_acceptance_criteria(SAMPLE_TICKET)
    ac1 = next(c for c in criteria if c["criterion_id"] == "AC1")
    ac2 = next(c for c in criteria if c["criterion_id"] == "AC2")
    assert ac1["is_met"] is True
    assert ac2["is_met"] is False


def test_parse_acceptance_criteria_empty():
    assert _parse_acceptance_criteria("# No criteria") == []


# ===========================================================================
# Workflow log parsing
# ===========================================================================


def test_parse_workflow_log_count():
    entries = _parse_workflow_log(SAMPLE_TICKET)
    assert len(entries) == 2


def test_parse_workflow_log_phase_names():
    entries = _parse_workflow_log(SAMPLE_TICKET)
    phases = [e["phase_name"] for e in entries]
    assert "Design" in phases
    assert "Implementation" in phases


def test_parse_workflow_log_artifacts():
    entries = _parse_workflow_log(SAMPLE_TICKET)
    design = next(e for e in entries if e["phase_name"] == "Design")
    assert len(design["artifacts"]) == 2


def test_parse_workflow_log_empty():
    assert _parse_workflow_log("# No log") == []


# ===========================================================================
# Files parsing
# ===========================================================================


def test_parse_files_count():
    files = _parse_files(SAMPLE_TICKET)
    assert len(files) >= 3


def test_parse_files_change_types():
    files = _parse_files(SAMPLE_TICKET)
    types = {f["change_type"] for f in files}
    assert "new" in types
    assert "modified" in types


def test_parse_files_empty():
    assert _parse_files("# No files") == []


# ===========================================================================
# References parsing
# ===========================================================================


def test_parse_references_ticket_refs():
    refs = _parse_references(SAMPLE_TICKET)
    ticket_refs = [r for r in refs if r["ref_type"] == "ticket"]
    targets = [r["ref_target"] for r in ticket_refs]
    assert "0040" in targets


def test_parse_references_parent():
    refs = _parse_references(SAMPLE_TICKET)
    parent_refs = [r for r in refs if r["ref_type"] == "parent"]
    assert any(r["ref_target"] == "0035" for r in parent_refs)


def test_parse_references_empty():
    assert _parse_references("# No references") == []


# ===========================================================================
# Ticket type detection
# ===========================================================================


def test_detect_ticket_type_feature():
    assert _detect_ticket_type(SAMPLE_TICKET) == "feature"


def test_detect_ticket_type_debug():
    assert _detect_ticket_type("# Debug Ticket: Fix crash") == "debug"


# ===========================================================================
# index_single_ticket
# ===========================================================================


def test_index_single_ticket_basic(conn):
    result = index_single_ticket(conn, "0050", SAMPLE_TICKET, "tickets/0050_collision.md")
    conn.commit()

    assert result["ticket_number"] == "0050"
    assert result["title"] == "Collision Detection Narrow Phase"
    assert result["canonical_phase"] == "design_review"

    row = conn.execute("SELECT * FROM tickets WHERE ticket_number = '0050'").fetchone()
    assert row is not None
    assert row["title"] == "Collision Detection Narrow Phase"


def test_index_single_ticket_stores_requirements(conn):
    index_single_ticket(conn, "0050", SAMPLE_TICKET, "tickets/0050_collision.md")
    conn.commit()

    rows = conn.execute(
        "SELECT * FROM ticket_requirements WHERE ticket_number = '0050'"
    ).fetchall()
    assert len(rows) == 4
    r1 = next(r for r in rows if r["requirement_id"] == "R1")
    assert r1["verification_method"] == "automated"
    assert "test_gjk" in r1["test_link"]


def test_index_single_ticket_replaces_existing(conn):
    index_single_ticket(conn, "0050", SAMPLE_TICKET, "tickets/0050_collision.md")
    conn.commit()

    updated = SAMPLE_TICKET.replace("Collision Detection Narrow Phase", "Updated Title")
    result = index_single_ticket(conn, "0050", updated, "tickets/0050_collision.md")
    conn.commit()

    assert result["title"] == "Updated Title"
    count = conn.execute("SELECT COUNT(*) FROM tickets WHERE ticket_number = '0050'").fetchone()[0]
    assert count == 1


# ===========================================================================
# index_tickets (directory scan)
# ===========================================================================


def test_index_tickets_basic(conn, tmp_path):
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "0050_collision_narrow.md").write_text(SAMPLE_TICKET)

    result = index_tickets(conn, str(tmp_path), tickets_dir="tickets")
    assert result["new_count"] == 1
    assert result["total"] == 1


def test_index_tickets_incremental_skips_unchanged(conn, tmp_path):
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "0050_collision_narrow.md").write_text(SAMPLE_TICKET)

    result1 = index_tickets(conn, str(tmp_path), tickets_dir="tickets")
    result2 = index_tickets(conn, str(tmp_path), tickets_dir="tickets")

    assert result1["new_count"] == 1
    assert result2["new_count"] == 0
    assert result2["updated_count"] == 0


def test_index_tickets_missing_dir(conn, tmp_path):
    result = index_tickets(conn, str(tmp_path), tickets_dir="nonexistent")
    assert result["total"] == 0


# ===========================================================================
# TicketQuerier
# ===========================================================================


@pytest.fixture
def querier_with_tickets(conn, tmp_path):
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "0050_collision_narrow.md").write_text(SAMPLE_TICKET)
    (tickets_dir / "0051_physics.md").write_text(
        "# Feature Ticket: Physics Engine\n\n## Status\n- [x] Draft\n\n"
        "## Metadata\n- **Priority**: Medium\n- **Target Component(s)**: msd-sim\n\n"
        "## Summary\nPhysics engine for rigid body dynamics.\n"
    )
    index_tickets(conn, str(tmp_path), tickets_dir="tickets")
    return TicketQuerier(conn)


def test_search_tickets(querier_with_tickets):
    results = querier_with_tickets.search("collision")
    assert len(results) >= 1
    assert any(r["ticket_number"] == "0050" for r in results)


def test_get_ticket_full_detail(querier_with_tickets):
    result = querier_with_tickets.get("0050")
    assert "error" not in result
    assert result["title"] == "Collision Detection Narrow Phase"
    assert len(result["requirements"]) == 4
    assert len(result["acceptance_criteria"]) == 3
    assert len(result["workflow_log"]) == 2
    assert len(result["files"]) >= 3
    assert len(result["references"]) >= 2


def test_get_ticket_not_found(querier_with_tickets):
    result = querier_with_tickets.get("9999")
    assert "error" in result


def test_list_tickets_all(querier_with_tickets):
    results = querier_with_tickets.list()
    assert len(results) == 2


def test_list_tickets_filter_priority(querier_with_tickets):
    results = querier_with_tickets.list(priority="High")
    assert len(results) == 1
    assert results[0]["ticket_number"] == "0050"


def test_create_ticket(conn, tmp_path):
    querier = TicketQuerier(conn)
    content = """\
# Feature Ticket: Widget Factory

## Status
- [x] Draft

## Metadata
- **Priority**: Medium

## Summary
Implement a widget factory.

## Acceptance Criteria
- [ ] AC1: Factory creates widgets
"""
    result = querier.create("0090", content, str(tmp_path))
    assert "error" not in result
    assert result["ticket_number"] == "0090"
    assert result["title"] == "Widget Factory"

    # Verify it's queryable
    ticket = querier.get("0090")
    assert ticket["title"] == "Widget Factory"


# ===========================================================================
# Calculator fixture tickets (integration test)
# ===========================================================================


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "calculator-cpp" / "tickets"


def test_index_calculator_fixtures(conn):
    """All 5 calculator tickets index successfully with requirements."""
    if not FIXTURES_DIR.exists():
        pytest.skip("Calculator fixtures not found")

    result = index_tickets(conn, str(FIXTURES_DIR.parent.parent), tickets_dir="calculator-cpp/tickets")
    assert result["total"] == 5

    # Verify ticket 0001 has requirements
    rows = conn.execute(
        "SELECT * FROM ticket_requirements WHERE ticket_number = '0001'"
    ).fetchall()
    assert len(rows) == 8  # R1-R8

    # Verify requirements have correct verification methods
    r1 = next(r for r in rows if r["requirement_id"] == "R1")
    assert r1["verification_method"] == "automated"
    assert r1["test_link"] is not None
