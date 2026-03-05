"""Tests for ticket content indexing: parsing, storage, and querying.

Validates:
- Markdown parsing: title, summary, requirements, acceptance criteria,
  files, references
- Database round-trip: index_single_ticket, index_tickets
- TicketQuerier: search, get, list, create
"""

from pathlib import Path

import pytest

from ticketing_system.tickets import (
    parse_title,
    parse_summary,
    parse_requirements,
    parse_acceptance_criteria,
    parse_files,
    parse_references,
    detect_ticket_type,
    index_single_ticket,
    index_tickets,
    load_tickets,
)
from ticketing_system.requirements import (
    load_high_level_requirements,
    load_low_level_requirements,
)
from ticketing_system.querier import TicketQuerier


# ---------------------------------------------------------------------------
# Sample ticket markdown
# ---------------------------------------------------------------------------

SAMPLE_TICKET = """\
# Feature Ticket: Collision Detection Narrow Phase

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
for convex polytopes. This builds on the broad-phase sweep from ticket 40.

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

## Files

### New Files
- `msd/msd-sim/src/collision/gjk.cpp` — GJK algorithm implementation
- `msd/msd-sim/src/collision/epa.cpp` — EPA algorithm implementation

### Modified Files
- `msd/msd-sim/src/collision/pipeline.cpp` — Integration with collision pipeline

## References
- Ticket 40 — Broad phase sweep and prune
- `msd/msd-sim/src/collision/broad_phase.cpp`

## Dependencies
- Parent ticket 35
- Blocks 60
"""


# ===========================================================================
# Title parsing
# ===========================================================================


def testparse_title_feature_ticket():
    assert parse_title(SAMPLE_TICKET) == "Collision Detection Narrow Phase"


def testparse_title_plain_heading():
    assert parse_title("# My Simple Title\n\nSome text.") == "My Simple Title"


def testparse_title_empty_content():
    assert parse_title("") == "Untitled"


# ===========================================================================
# Summary parsing
# ===========================================================================


def testparse_summary():
    summary = parse_summary(SAMPLE_TICKET)
    assert summary is not None
    assert "GJK" in summary


def testparse_summary_missing():
    assert parse_summary("# No summary here") is None


# ===========================================================================
# Requirements parsing
# ===========================================================================


def testparse_requirements_table_count():
    reqs = parse_requirements(SAMPLE_TICKET)
    assert len(reqs) == 4


def testparse_requirements_table_descriptions():
    reqs = parse_requirements(SAMPLE_TICKET)
    assert "GJK" in reqs[0]["description"]
    assert "EPA" in reqs[1]["description"]


def testparse_requirements_table_verification():
    reqs = parse_requirements(SAMPLE_TICKET)
    methods = [r["verification"] for r in reqs]
    assert methods == ["automated", "automated", "automated", "review"]


def testparse_requirements_legacy_format():
    content = """\
## Requirements

### R1: First Requirement
- Description of the first requirement

### R2: Second Requirement
- Description of the second requirement
"""
    reqs = parse_requirements(content)
    assert len(reqs) == 2
    assert "First Requirement" in reqs[0]["description"]
    assert reqs[0]["verification"] == "review"


def testparse_requirements_empty():
    assert parse_requirements("# No requirements") == []


# ===========================================================================
# Acceptance criteria parsing
# ===========================================================================


def testparse_acceptance_criteria_count():
    criteria = parse_acceptance_criteria(SAMPLE_TICKET)
    assert len(criteria) == 3


def testparse_acceptance_criteria_descriptions():
    criteria = parse_acceptance_criteria(SAMPLE_TICKET)
    descriptions = [c["description"] for c in criteria]
    assert "GJK algorithm correctly determines intersection" in descriptions


def testparse_acceptance_criteria_descriptions_detail():
    criteria = parse_acceptance_criteria(SAMPLE_TICKET)
    assert "EPA" in criteria[1]["description"]
    assert "Performance" in criteria[2]["description"]


def testparse_acceptance_criteria_empty():
    assert parse_acceptance_criteria("# No criteria") == []


# ===========================================================================
# Files parsing
# ===========================================================================


def testparse_files_count():
    files = parse_files(SAMPLE_TICKET)
    assert len(files) >= 3


def testparse_files_change_types():
    files = parse_files(SAMPLE_TICKET)
    types = {f["change_type"] for f in files}
    assert "new" in types
    assert "modified" in types


def testparse_files_empty():
    assert parse_files("# No files") == []


# ===========================================================================
# References parsing
# ===========================================================================


def testparse_references_ticket_refs():
    refs = parse_references(SAMPLE_TICKET)
    ticket_refs = [r for r in refs if r["ref_type"] == "ticket"]
    targets = [r["ref_target"] for r in ticket_refs]
    assert "40" in targets


def testparse_references_parent():
    refs = parse_references(SAMPLE_TICKET)
    parent_refs = [r for r in refs if r["ref_type"] == "parent"]
    assert any(r["ref_target"] == "35" for r in parent_refs)


def testparse_references_empty():
    assert parse_references("# No references") == []


# ===========================================================================
# Ticket type detection
# ===========================================================================


def testdetect_ticket_type_feature():
    assert detect_ticket_type(SAMPLE_TICKET) == "feature"


def testdetect_ticket_type_debug():
    assert detect_ticket_type("# Debug Ticket: Fix crash") == "debug"


# ===========================================================================
# index_single_ticket
# ===========================================================================


def test_index_single_ticket_basic(conn):
    result = index_single_ticket(conn, SAMPLE_TICKET, ticket_id=50)
    conn.commit()

    assert result["id"] == 50
    assert result["title"] == "Collision Detection Narrow Phase"

    row = conn.execute("SELECT * FROM tickets WHERE id = 50").fetchone()
    assert row is not None
    assert row["title"] == "Collision Detection Narrow Phase"


def test_index_single_ticket_stores_requirements(conn):
    index_single_ticket(conn, SAMPLE_TICKET, ticket_id=50)
    conn.commit()

    # 4 low-level requirements created in standalone table
    count = conn.execute("SELECT COUNT(*) FROM low_level_requirements").fetchone()[0]
    assert count == 4

    # Verify requirement content
    reqs = conn.execute(
        "SELECT description, verification FROM low_level_requirements"
    ).fetchall()
    assert any("GJK" in r["description"] for r in reqs)
    assert any(r["verification"] == "automated" for r in reqs)


def test_index_single_ticket_replaces_existing(conn):
    index_single_ticket(conn, SAMPLE_TICKET, ticket_id=50)
    conn.commit()

    updated = SAMPLE_TICKET.replace("Collision Detection Narrow Phase", "Updated Title")
    result = index_single_ticket(conn, updated, ticket_id=50)
    conn.commit()

    assert result["title"] == "Updated Title"
    count = conn.execute("SELECT COUNT(*) FROM tickets WHERE id = 50").fetchone()[0]
    assert count == 1


def test_index_single_ticket_auto_id(conn):
    result = index_single_ticket(conn, SAMPLE_TICKET)
    conn.commit()

    assert result["id"] is not None
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (result["id"],)).fetchone()
    assert row["title"] == "Collision Detection Narrow Phase"


# ===========================================================================
# index_tickets (directory scan)
# ===========================================================================


def test_index_tickets_basic(conn, tmp_path):
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "50_collision_narrow.md").write_text(SAMPLE_TICKET)

    result = index_tickets(conn, str(tmp_path), tickets_dir="tickets")
    assert result["new_count"] == 1
    assert result["total"] == 1


def test_index_tickets_incremental_skips_unchanged(conn, tmp_path):
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "50_collision_narrow.md").write_text(SAMPLE_TICKET)

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
    (tickets_dir / "50_collision_narrow.md").write_text(SAMPLE_TICKET)
    (tickets_dir / "51_physics.md").write_text(
        "# Feature Ticket: Physics Engine\n\n"
        "## Metadata\n- **Priority**: Medium\n- **Target Component(s)**: msd-sim\n\n"
        "## Summary\nPhysics engine for rigid body dynamics.\n"
    )
    index_tickets(conn, str(tmp_path), tickets_dir="tickets")
    return TicketQuerier(conn)


def test_search_tickets(querier_with_tickets):
    results = querier_with_tickets.search("collision")
    assert len(results) >= 1
    assert any(r["id"] == 50 for r in results)


def test_get_ticket_full_detail(querier_with_tickets):
    result = querier_with_tickets.get(50)
    assert "error" not in result
    assert result["title"] == "Collision Detection Narrow Phase"
    assert len(result["requirements"]) == 0  # no HLR linkage from markdown
    assert len(result["acceptance_criteria"]) == 3
    assert len(result["files"]) >= 3
    assert len(result["references"]) >= 2


def test_get_ticket_not_found(querier_with_tickets):
    result = querier_with_tickets.get(9999)
    assert "error" in result


def test_list_tickets_all(querier_with_tickets):
    results = querier_with_tickets.list()
    assert len(results) == 2


def test_list_tickets_filter_priority(querier_with_tickets):
    results = querier_with_tickets.list(priority="High")
    assert len(results) == 1
    assert results[0]["id"] == 50


def test_create_ticket(conn, tmp_path):
    querier = TicketQuerier(conn)
    content = """\
# Feature Ticket: Widget Factory

## Metadata
- **Priority**: Medium

## Summary
Implement a widget factory.

## Acceptance Criteria
- [ ] AC1: Factory creates widgets
"""
    result = querier.create(content, str(tmp_path))
    assert "error" not in result
    assert result["id"] is not None
    assert result["title"] == "Widget Factory"

    # Verify it's queryable
    ticket = querier.get(result["id"])
    assert ticket["title"] == "Widget Factory"


# ===========================================================================
# Calculator fixture tickets (integration test)
# ===========================================================================


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "calculator-cpp"


def test_load_calculator_fixtures(conn):
    """All 5 calculator tickets, 5 high-level and 45 low-level requirements load from JSON."""
    tickets_json = FIXTURES_DIR / "tickets.json"
    llr_json = FIXTURES_DIR / "requirements.json"
    hlr_json = FIXTURES_DIR / "high_level_requirements.json"
    if not tickets_json.exists():
        pytest.skip("Calculator fixtures not found")

    # Load high-level requirements first
    hlr_result = load_high_level_requirements(conn, str(hlr_json))
    assert hlr_result["total"] == 5

    # Load low-level requirements (reference high-level ones)
    llr_result = load_low_level_requirements(conn, str(llr_json))
    assert llr_result["total"] == 45

    # Load tickets (which reference high-level requirements)
    ticket_result = load_tickets(conn, str(tickets_json))
    assert ticket_result["total"] == 5

    # Verify ticket 1 data
    row = conn.execute("SELECT * FROM tickets WHERE id = 1").fetchone()
    assert row["title"] == "CMake Project Configuration with Presets"
    assert row["priority"] == "Critical"

    # Verify acceptance criteria
    ac = conn.execute(
        "SELECT * FROM ticket_acceptance_criteria WHERE ticket_id = 1"
    ).fetchall()
    assert len(ac) == 4

    # Verify files
    files = conn.execute(
        "SELECT * FROM ticket_files WHERE ticket_id = 1"
    ).fetchall()
    assert len(files) == 5

    # Verify references
    refs = conn.execute(
        "SELECT * FROM ticket_references WHERE ticket_id = 1"
    ).fetchall()
    assert len(refs) == 3

    # Verify ticket 1 links to HLR 1 via join table
    links = conn.execute(
        "SELECT * FROM ticket_requirements WHERE ticket_id = 1"
    ).fetchall()
    assert len(links) == 1
    assert links[0]["high_level_requirement_id"] == 1

    # Verify high-level requirement content via join
    hlrs = conn.execute(
        """SELECT hlr.id, hlr.description
           FROM high_level_requirements hlr
           JOIN ticket_requirements tr ON tr.high_level_requirement_id = hlr.id
           WHERE tr.ticket_id = 1"""
    ).fetchall()
    assert len(hlrs) == 1
    assert "CMake" in hlrs[0]["description"]

    # Verify low-level requirements link to high-level requirements
    llr = conn.execute(
        """SELECT llr.id, llr.high_level_requirement_id, hlr.description
           FROM low_level_requirements llr
           JOIN high_level_requirements hlr ON hlr.id = llr.high_level_requirement_id
           WHERE llr.id = 1"""
    ).fetchone()
    assert llr is not None
    assert llr["high_level_requirement_id"] == 1
    assert "CMake" in llr["description"]

    # All 8 low-level requirements with HLR 1
    llr_count = conn.execute(
        "SELECT COUNT(*) FROM low_level_requirements WHERE high_level_requirement_id = 1"
    ).fetchone()[0]
    assert llr_count == 8
