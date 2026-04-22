# Spec-Driven Development Architecture — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a complete spec-driven development workflow that takes an initial prompt and produces a fully implemented, tested, and verified codebase — benchmarked against a simple calculator application — with full traceability from requirements through design to implementation stored in Neo4j.

**Architecture:** The pipeline extends the existing ticketing system's requirement decomposition, OO design, and verification agents with three new phases: (1) task generation from designs, (2) skeleton/test/implementation agents, and (3) design-code sync hooks. Neo4j serves as the unified graph storing requirements, ontology (design), existing codebase documentation, and implementation metadata. Each phase writes back to Neo4j, keeping design ↔ implementation ↔ verification independently synchronized.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, Neo4j 5.x (Docker), Pydantic, pytest, NiceGUI (existing dashboard), llm-caller (existing agent framework), existing sqlite-vec for semantic search.

---

## Pipeline Overview

The full workflow, given an initial prompt:

```
INITIAL PROMPT
  │
  ▼ [1] HLR Generation
High-Level Requirements
  │
  ▼ [2] Decompose (EXISTING — decompose_hlr.py)
Low-Level Requirements
  │
  ▼ [3] Verification Methods (EXISTING — verify_llr.py)
  │   ← checks existing Neo4j ontology, appends
  ▼ [4] OO Design → Neo4j (EXISTING — design_oo.py + map_to_ontology.py + neo4j_sync.py)
  │   ← checks existing Neo4j codebase docs, appends
  │
  ▼ [5] Task Generation (NEW)
Scoped Tasks (one per design element / verification method cluster)
  │
  ▼ [6] Skeleton Generation (NEW)
Empty class/method stubs matching the OO design
  │
  ▼ [7] Test Writing (NEW)
  │   Tests map 1:1 to verification methods
  │   Each test's name/description references the LLR + verification method
  │
  ▼ [8] Implementation (NEW)
  │   Fill in skeleton with real logic
  │
  ▼ [9] Design-Code Sync Hooks (NEW)
  │   Verify: implemented code matches design schema
  │   Verify: tests cover all verification methods
  │   Update Neo4j: mark design nodes as :IMPLEMENTED
  │
  ▼ [10] Neo4j Metadata Update
Design nodes get "implemented" flag, linked to test files and source files
```

## Phase Breakdown

### Phase A: Infrastructure Bootstrap (Tasks 1-5)
Get Neo4j running, database seeded, environment working. New ORM models for tasks and implementation tracking.

### Phase B: Task Generation Agent (Tasks 6-12)
New agent that produces scoped tasks from the OO design + verification methods.

### Phase C: Skeleton Generator (Tasks 13-18)
Generate empty class/method/attribute stubs from the Neo4j design.

### Phase D: Test Writer Agent (Tasks 19-25)
Write unit tests that directly map to verification methods.

### Phase E: Implementation Agent (Tasks 26-30)
Fill in the implementation from skeleton.

### Phase F: Design-Code Sync Hooks (Tasks 31-37)
Verify code matches design, tests cover verification, update Neo4j.

### Phase G: Calculator Benchmark (Tasks 38-43)
Wire the full pipeline to the calculator HLRs, run end-to-end.

### Phase H: Analysis & Viewability (Tasks 44-48)
Make artifacts viewable, add multi-model LLM analysis.

---

## Phase A: Infrastructure Bootstrap

### Task 1: Start Neo4j Database

**Objective:** Get the Neo4j graph database running via Docker Compose.

**Files:**
- `docker-compose.yml` (no change — already correct)

**Step 1: Start Neo4j**

Run (in this machine — no docker available, so use Neo4j standalone or skip if not available):
```bash
cd ~/ticketing_system && docker compose up -d
```
Expected: Neo4j container starts on ports 7474 (browser) and 7687 (bolt).

---

### Task 2: Create Task ORM Model and Extend OntologyNode

**Objective:** Add Alembic migration for new fields: `implementation_status` on ontology nodes, `task` entity with design/verification links.

**Files:**
- Create: `backend/db/models/tasks.py` (new Task, TaskDesignNode, TaskVerification models)
- Modify: `backend/db/models/ontology.py` (add `implementation_status`, `source_file`, `test_file`, `implemented_at` fields)
- Modify: `backend/db/models/verification.py` (add `task_links` relationship)
- Modify: `backend/db/models/__init__.py` (add Task imports)

**Step 1: Add implementation_status to OntologyNode**

Append to `OntologyNode` class in `backend/db/models/ontology.py` (after `is_intercomponent` field):

```python
    # --- Implementation tracking ---
    implementation_status: Mapped[str] = mapped_column(
        String(20), default="designed", server_default="designed"
    )  # "designed", "scaffolded", "tested", "implemented", "verified"
    source_file: Mapped[str] = mapped_column(String(500), default="", server_default="")
    test_file: Mapped[str] = mapped_column(String(500), default="", server_default="")
    implemented_at: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Task linkage ---
    task_links: Mapped[list["TaskDesignNode"]] = relationship(
        "TaskDesignNode", back_populates="ontology_node",
    )
```

**Step 2: Create Task model** in `backend/db/models/tasks.py`:

```python
"""Task model — scoped work items generated from design + verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.db.models.components import Component
    from backend.db.models.requirements import LowLevelRequirement
    from backend.db.models.ontology import OntologyNode
    from backend.db.models.verification import VerificationMethod


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    # pending, scaffolded, tested, implemented, verified
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    component_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("components.id", ondelete="SET NULL"), nullable=True,
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True,
    )

    component: Mapped[Optional[Component]] = relationship("Component")
    parent: Mapped[Optional[Task]] = relationship(
        "Task", remote_side="Task.id", back_populates="children",
    )
    children: Mapped[list[Task]] = relationship("Task", back_populates="parent")

    # Design elements this task implements
    design_nodes: Mapped[list["TaskDesignNode"]] = relationship(
        "TaskDesignNode", back_populates="task", cascade="all, delete-orphan",
    )
    # Verifications this task covers
    verifications: Mapped[list["TaskVerification"]] = relationship(
        "TaskVerification", back_populates="task", cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"Task {self.id}: {self.title}"


class TaskDesignNode(Base):
    """Links a task to one or more ontology design nodes."""
    __tablename__ = "task_design_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
    )
    ontology_node_id: Mapped[int] = mapped_column(
        ForeignKey("ontology_nodes.id", ondelete="CASCADE"), nullable=False,
    )

    task: Mapped[Task] = relationship("Task", back_populates="design_nodes")
    ontology_node: Mapped["OntologyNode"] = relationship("OntologyNode")


class TaskVerification(Base):
    """Links a task to one or more verification methods it must satisfy."""
    __tablename__ = "task_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
    )
    verification_method_id: Mapped[int] = mapped_column(
        ForeignKey("verification_methods.id", ondelete="CASCADE"), nullable=False,
    )

    task: Mapped[Task] = relationship("Task", back_populates="verifications")
    verification_method: Mapped["VerificationMethod"] = relationship("VerificationMethod")
```

**Step 3: Add reverse relationship** to `VerificationMethod` in `backend/db/models/verification.py` (after the `actions` relationship):

```python
    task_links: Mapped[list["TaskVerification"]] = relationship(
        "TaskVerification", back_populates="verification_method",
    )
```

**Step 4: Add imports** to `backend/db/models/__init__.py`:

```python
from backend.db.models.tasks import Task, TaskDesignNode, TaskVerification
```

**Step 5: Run Alembic migration**

```bash
cd ~/ticketing_system && source .venv/bin/activate
alembic revision --autogenerate -m "add task models and implementation_status"
alembic upgrade head
```

Expected: Migration file created, tables created, no errors.

---

### Task 3: Create Standalone Neo4j Service and Extend Sync

**Objective:** Create a standalone Neo4j driver (not tied to NiceGUI app state), and extend sync for tasks/implementation status/verification nodes.

**Files:**
- Create: `backend/services/neo4j_service.py`
- Modify: `backend/db/neo4j_sync.py` (append task sync, implementation status sync, verification sync)

**Step 1: Create standalone Neo4j service** at `backend/services/neo4j_service.py`:

```python
"""Standalone Neo4j driver management (not tied to NiceGUI app state)."""

import os
from contextlib import contextmanager
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")

_driver = None

def get_driver():
    """Get or create the Neo4j driver singleton."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver

def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

@contextmanager
def get_neo4j_session(database="neo4j"):
    driver = get_driver()
    session = driver.session(database=database)
    try:
        yield session
    finally:
        session.close()

def verify_connection():
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except Exception as e:
        print(f"Neo4j connection failed: {e}")
        return False
```

**Step 2: Add sync functions** to `backend/db/neo4j_sync.py`:

```python
def sync_task(neo4j_session, task):
    """MERGE a Task node in Neo4j with its design/verification links."""
    cypher = """
    MERGE (t:Task {sqlite_id: $tid})
    SET t.title = $title,
        t.description = $description,
        t.status = $status,
        t.component_id = $component_id,
        t.created_at = $created_at,
        t.updated_at = $updated_at
    """
    neo4j_session.run(cypher, {
        "tid": task.id,
        "title": task.title[:300],
        "description": task.description,
        "status": task.status,
        "component_id": task.component_id,
        "created_at": str(task.created_at),
        "updated_at": str(task.updated_at),
    })
    # Link to design nodes
    for td in task.design_nodes:
        node_qname = td.ontology_node.qualified_name
        neo4j_session.run("""
        MATCH (t:Task {sqlite_id: $tid})
        MATCH (d:Design {qualified_name: $qname})
        MERGE (t)-[:IMPLEMENTING]->(d)
        """, {"tid": task.id, "qname": node_qname})
    # Link to verification methods
    for tv in task.verifications:
        vm = tv.verification_method
        neo4j_session.run("""
        MATCH (t:Task {sqlite_id: $tid})
        MERGE (v:Verification {sqlite_id: $vid})
        SET v.method = $method, v.test_name = $test_name
        MERGE (t)-[:COVERS]->(v)
        MERGE (l:LLR {sqlite_id: $llr_id})
        MERGE (l)-[:VERIFIED_BY]->(v)
        """, {"tid": task.id, "vid": vm.id, "method": vm.method,
              "test_name": vm.test_name, "llr_id": vm.low_level_requirement_id})

def sync_implementation_status(neo4j_session, node):
    """Update a Design node's implementation status in Neo4j."""
    neo4j_session.run("""
    MATCH (d:Design {qualified_name: $qname})
    SET d.implementation_status = $status,
        d.source_file = $source_file,
        d.test_file = $test_file
    """, {
        "qname": node.qualified_name,
        "status": node.implementation_status,
        "source_file": node.source_file,
        "test_file": node.test_file,
    })
```

---

### Task 4: Create Pipeline Package and Orchestrator Skeleton

**Objective:** Create the `backend/pipeline/` package with the master orchestrator.

**Files:**
- Create: `backend/pipeline/__init__.py`
- Create: `backend/pipeline/orchestrator.py`
- Create: `backend/pipeline/schemas.py`

**Step 1: Create pipeline schemas** in `backend/pipeline/schemas.py`:

```python
"""Pydantic schemas for pipeline phases."""

from pydantic import BaseModel, Field


class TaskSchema(BaseModel):
    """A scoped work item generated from design + verification."""
    title: str
    description: str
    design_node_qualified_names: list[str] = Field(
        default_factory=list,
        description="OO design nodes this task implements",
    )
    verification_test_names: list[str] = Field(
        default_factory=list,
        description="Verification method test names this task must satisfy",
    )
    source_files: list[str] = Field(
        default_factory=list,
        description="Files this task will create or modify",
    )
    test_files: list[str] = Field(
        default_factory=list,
        description="Test files this task will create",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Other task titles this depends on (by title)",
    )
    estimated_complexity: str = Field(default="medium")  # low, medium, high


class TaskBatchSchema(BaseModel):
    """Complete set of tasks for a component."""
    tasks: list[TaskSchema]
    component_name: str = ""
    dependency_graph: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Edges: (from_task_title, to_task_title)",
    )
```

**Step 2: Create orchestrator skeleton** in `backend/pipeline/orchestrator.py`:

```python
"""
Master orchestrator for the spec-driven development pipeline.

Given an initial prompt, runs the full pipeline:
  HLR → Decomposition → Verification → Design → Tasks →
  Skeleton → Tests → Implementation → Sync Hooks → Neo4j update
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

log = logging.getLogger("pipeline.orchestrator")


@dataclass
class PipelineResult:
    """Aggregated results from a full pipeline run."""
    hlrs_created: int = 0
    llrs_created: int = 0
    verifications_created: int = 0
    design_nodes: int = 0
    design_triples: int = 0
    tasks_created: int = 0
    skeleton_files: list[str] = field(default_factory=list)
    tests_created: int = 0
    implementations_created: int = 0
    sync_issues: list[str] = field(default_factory=list)
    neo4j_synced: bool = False
    benchmark_metrics: dict = field(default_factory=dict)


def run_pipeline(
    initial_prompt: str,
    session: Session,
    model: str = "",
    language: str = "python",
    workspace_dir: str = "",
    dry_run: bool = False,
) -> PipelineResult:
    """Run the full spec-driven development pipeline.

    Each phase calls the corresponding agent module and records results.
    Neo4j is updated incrementally after each phase.
    """
    result = PipelineResult()
    log.info("Pipeline started: %s", initial_prompt[:100])

    # Phase 1-4 use existing agents (decompose, design_oo, verify_llr)
    # Phase 5-9 use new agents (implemented in later tasks)

    return result
```

---

### Task 5: Create Calculator Benchmark Seed Script

**Objective:** Create a script that seeds the calculator benchmark HLRs into the database.

**Files:**
- Create: `scripts/04_benchmark_calculator.py`

```python
#!/usr/bin/env python
"""
Benchmark: Simple Calculator Application.

Seeds HLRs for a calculator and runs them through the full pipeline.

Usage:
    source .venv/bin/activate
    python scripts/04_benchmark_calculator.py [--dry-run] [--model MODEL]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from backend.db import init_db, get_session, get_or_create
from backend.db.models import Component, HighLevelRequirement, Language

CALCULATOR_HLRS = [
    "The calculator application provides a GUI with a numeric display and buttons "
    "for digits 0-9, operators (+, -, *, /), clear, and equals. Display shows current "
    "input and result.",

    "The calculator performs addition, subtraction, multiplication, and division with "
    "proper input validation. Division by zero raises an error. Invalid expressions "
    "are rejected. Results are returned immediately.",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()

    with get_session() as session:
        existing = session.query(HighLevelRequirement).filter(
            HighLevelRequirement.description.like("%calculator%")
        ).count()
        if existing >= len(CALCULATOR_HLRS):
            print(f"Already seeded: {existing} calculator HLRs")
            return

        lang, _ = get_or_create(session, Language, name="Python",
                                  defaults={"version": "3.11"})
        comp, created = get_or_create(
            session, Component, name="Calculator",
            defaults={"namespace": "calculator",
                      "description": "Simple calculator application",
                      "language": lang},
        )
        if created:
            print(f"Created component: {comp.name}")

        for desc in CALCULATOR_HLRS:
            hlr = HighLevelRequirement(description=desc, component=comp)
            session.add(hlr)
            print(f"Added HLR: {desc[:80]}...")

        count = session.query(HighLevelRequirement).filter(
            HighLevelRequirement.component == comp
        ).count()
        print(f"\nBenchmark seeded: {count} HLRs for component '{comp.name}'")


if __name__ == "__main__":
    main()
```

---

## Phase B: Task Generation Agent

### Task 6: Create Task Generation Agent and Prompt

**Objective:** Create the agent that generates scoped, independent tasks from the OO design + verification methods.

**Files:**
- Create: `backend/ticketing_agent/generate_tasks.py`
- Create: `backend/ticketing_agent/generate_tasks_prompt.py`

**Step 1: Create the prompt** in `backend/ticketing_agent/generate_tasks_prompt.py`:

```python
"""Prompt engineering for task generation agent."""

SYSTEM_PROMPT = """\
You are a task generation agent. Your job is to break down an object-oriented
class design into discrete, independently-implementable tasks.

## Input
- OO class design (classes, methods, attributes, inheritance, associations)
- Verification methods tied to low-level requirements
- Existing codebase context (classes already implemented)

## Rules
1. Each task must implement ONE coherent unit of work (usually: one class or
   one method cluster with its associated verification methods).
2. Each task MUST list: which design nodes it covers, which verification tests
   it must satisfy, which files it creates/modifies.
3. Tasks should be ordered by dependency — base classes and interfaces before
   derived classes. Utility classes before consumers.
4. The task's source_files and test_files must be explicit paths.
5. For Python projects, use:
   - Source: `src/<package>/<module>.py`
   - Tests: `tests/<package>/test_<module>.py`
"""

TOOL_DEFINITION = {
    "name": "generate_tasks",
    "description": "Generate implementation tasks from the OO design and verification methods.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "design_node_qualified_names": {
                            "type": "array", "items": {"type": "string"},
                        },
                        "verification_test_names": {
                            "type": "array", "items": {"type": "string"},
                        },
                        "source_files": {"type": "array", "items": {"type": "string"}},
                        "test_files": {"type": "array", "items": {"type": "string"}},
                        "dependencies": {"type": "array", "items": {"type": "string"}},
                        "estimated_complexity": {
                            "type": "string", "enum": ["low", "medium", "high"],
                        },
                    },
                    "required": ["title", "description"],
                },
            },
            "component_name": {"type": "string"},
            "dependency_graph": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2, "maxItems": 2,
                },
            },
        },
        "required": ["tasks"],
    },
}


def build_task_context(classes, verifications, existing_classes):
    """Build context text for the task generation prompt."""
    lines = ["## OO Class Design\n"]
    for cls in classes:
        lines.append(f"### {cls['name']}")
        lines.append(f"Module: {cls.get('module', '')}")
        if cls.get('description'):
            lines.append(f"Description: {cls['description']}")
        if cls.get('attributes'):
            lines.append("Attributes:")
            for a in cls['attributes']:
                lines.append(f"  - {a['name']}: {a.get('type_name', 'any')} ({a.get('visibility', 'public')})")
        if cls.get('methods'):
            lines.append("Methods:")
            for m in cls['methods']:
                params = ", ".join(m.get('parameters', []))
                lines.append(f"  - {m['name']}({params}) -> {m.get('return_type', 'void')}")
        if cls.get('inherits_from'):
            lines.append(f"Inherits: {', '.join(cls['inherits_from'])}")
        if cls.get('requirement_ids'):
            lines.append(f"Requirements: {', '.join(cls['requirement_ids'])}")
        lines.append("")

    lines.append("## Verification Methods\n")
    for v in verifications:
        lines.append(f"- [{v['method']}] {v.get('test_name', 'unnamed')}: {v.get('description', '')}")
        lines.append("")

    if existing_classes:
        lines.append("## Existing Classes (do NOT recreate)\n")
        for c in existing_classes:
            lines.append(f"- {c.get('qualified_name', c.get('name', '?'))}")

    return "\n".join(lines)
```

**Step 2: Create the agent** in `backend/ticketing_agent/generate_tasks.py`:

```python
"""Agent: generate scoped implementation tasks from OO design + verification."""

import logging

from llm_caller import call_tool
from backend.pipeline.schemas import TaskBatchSchema
from backend.ticketing_agent.generate_tasks_prompt import (
    SYSTEM_PROMPT, TOOL_DEFINITION, build_task_context,
)

log = logging.getLogger("agents.generate_tasks")


def generate_tasks(
    hlr: dict,
    llrs: list[dict],
    oo_design: dict,
    verifications: list[dict],
    existing_classes: list[dict] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> TaskBatchSchema:
    """Generate implementation tasks from design and verification context."""
    context = build_task_context(
        classes=oo_design.get("classes", []),
        verifications=verifications,
        existing_classes=existing_classes or [],
    )

    component_name = hlr.get("component_name", "")
    user_msg = (
        f"Generate implementation tasks for component '{component_name}' "
        f"(HLR {hlr['id']}).\n\n{context}"
    )

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[TOOL_DEFINITION],
        tool_name="generate_tasks",
        model=model,
        prompt_log_file=prompt_log_file,
    )
    return TaskBatchSchema.model_validate(result)
```

---

### Task 7: Create Task Persistence Service

**Objective:** Persist generated tasks to SQLite with links to design nodes and verification methods.

**Files:**
- Create: `backend/pipeline/services.py`

```python
"""Service layer for task persistence and retrieval."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.db.models.tasks import Task, TaskDesignNode, TaskVerification
from backend.db.models.ontology import OntologyNode
from backend.db.models.verification import VerificationMethod
from backend.pipeline.schemas import TaskBatchSchema, TaskSchema

log = logging.getLogger("pipeline.services")


@dataclass
class TaskPersistResult:
    tasks_created: int = 0
    links_to_design: int = 0
    links_to_verification: int = 0


def persist_tasks(
    session: Session,
    batch: TaskBatchSchema,
    qname_to_node: dict[str, OntologyNode],
) -> TaskPersistResult:
    """Persist a batch of tasks to SQLite."""
    result = TaskPersistResult()
    ordered = _topological_sort(batch.tasks, batch.dependency_graph)
    title_to_task: dict[str, Task] = {}

    for ts in ordered:
        task = Task(title=ts.title, description=ts.description,
                     estimated_complexity=ts.estimated_complexity)
        if ts.dependencies:
            parent = title_to_task.get(ts.dependencies[0])
            if parent:
                task.parent = parent

        session.add(task)
        session.flush()
        title_to_task[ts.title] = task
        result.tasks_created += 1

        for qname in ts.design_node_qualified_names:
            if qname in qname_to_node:
                session.add(TaskDesignNode(
                    task=task, ontology_node=qname_to_node[qname]))
                result.links_to_design += 1

        for test_name in ts.verification_test_names:
            vm = session.query(VerificationMethod).filter_by(
                test_name=test_name).first()
            if vm:
                session.add(TaskVerification(task=task, verification_method=vm))
                result.links_to_verification += 1

    return result


def _topological_sort(tasks, graph):
    """Simple topological sort. Returns tasks with fewest deps first."""
    by_title = {t.title: t for t in tasks}
    in_degree = {t.title: 0 for t in tasks}
    for src, dst in graph:
        if dst in in_degree and src in by_title:
            in_degree[dst] += 1
    queue = sorted([t for t in in_degree if in_degree[t] == 0])
    result = [by_title[n] for n in queue]
    remaining = [t for t in tasks if t not in result]
    result.extend(remaining)
    return result
```

---

### Task 8: Create Task Generation CLI Script

**Objective:** Script to run task generation independently for debugging/iteration.

**Files:**
- Create: `scripts/05_generate_tasks.py`

---

### Task 9: Test Task Generation Prompt Context

**Objective:** Verify build_task_context produces correct markdown.

**Files:**
- Create: `tests/test_generate_tasks_prompt.py`

---

### Task 10: Test Task Persistence Service

**Objective:** Verify tasks persist with design/verification links using `seeded_session` fixture.

**Files:**
- Create: `tests/test_task_persistence.py`

---

### Task 11: Test Pipeline Schemas

**Objective:** Ensure TaskSchema and TaskBatchSchema validate/serialize correctly.

**Files:**
- Create: `tests/test_pipeline_schemas.py`

---

### Task 12: Wire Task Generation into Orchestrator

**Objective:** Add the task generation phase to `run_pipeline()` in `backend/pipeline/orchestrator.py`.

---

## Phase C: Skeleton Generator

### Task 13: Create Skeleton Generator Module

**Objective:** Generate empty Python class/method/attribute stubs from OO design.

**Files:**
- Create: `backend/ticketing_agent/generate_skeleton.py`

---

### Task 14: Create Python Skeleton Templates

**Objective:** Templates for generating Python class stubs, dataclasses, and __init__.py files.

**Files:**
- Create: `backend/ticketing_agent/skeleton_templates/__init__.py`
- Create: `backend/ticketing_agent/skeleton_templates/python.py`

---

### Task 15: Implement Class Skeleton Generator

**Objective:** Convert OODesignSchema.classes into `class Foo: ...` stubs with method signatures and `pass` bodies.

---

### Task 16: Implement Package Structure Generator

**Objective:** Create directory structure and __init__.py with proper imports from design modules.

---

### Task 17: Implement Skeleton-to-File Writer

**Objective:** Write generated skeletons to the workspace directory (under `src/`).

---

### Task 18: Test Skeleton Generator

**Objective:** Verify skeleton output is syntactically valid Python and importable.

**Files:**
- Create: `tests/test_generate_skeleton.py`

---

## Phase D: Test Writer Agent

### Task 19: Create Test Writer Agent Module and Prompt

**Objective:** Agent that generates pytest unit tests from verification methods.

**Files:**
- Create: `backend/ticketing_agent/write_tests.py`
- Create: `backend/ticketing_agent/write_tests_prompt.py`

**Step 1: Prompt design** — the prompt should include:
- The verification method (preconditions, actions, postconditions)
- The skeleton code being tested
- The test_name from the verification
- The LLR ID for traceability (test docstring references LLR: N)
- pytest conventions

---

### Task 20: Implement Test Writer Agent

**Objective:** Use call_tool to generate actual test files from verification context.

---

### Task 21: Implement Test File Writer

**Objective:** Write generated tests to workspace (under `tests/`).

---

### Task 22: Test Skeleton + Test Import Compatibility

**Objective:** Verify generated tests can import the skeleton modules they test.

---

### Task 23: Write Test Writer Tests

**Objective:** Test that verification methods → tests produces valid pytest files.

**Files:**
- Create: `tests/test_write_tests.py`

---

### Task 24: Implement Test Coverage Verifier

**Objective:** Verify every VerificationMethod in the database has a corresponding test function.

**Files:**
- Create: `backend/pipeline/test_coverage.py`

---

### Task 25: Wire Test Writer into Orchestrator

**Objective:** Add the test writing phase to `run_pipeline()`.

---

## Phase E: Implementation Agent

### Task 26: Create Implementation Agent Module and Prompt

**Objective:** Agent that fills in the skeleton with real implementation logic.

**Files:**
- Create: `backend/ticketing_agent/implement.py`
- Create: `backend/ticketing_agent/implement_prompt.py`

---

### Task 27: Create Implementation Prompt

**Objective:** Prompt includes: task description, skeleton code, design node context, related tests.

---

### Task 28: Implement Per-Task Code Generation

**Objective:** Generate implementation for one task at a time, writing to source files.

---

### Task 29: Implement Post-Task Test Verification

**Objective:** After each task implementation, run `pytest` on affected tests. Re-run LLM on failure.

---

### Task 30: Wire Implementation Agent into Orchestrator

**Objective:** Add implementation phase to `run_pipeline()`.

---

## Phase F: Design-Code Sync Hooks

### Task 31: Create Design Verification Hook

**Objective:** Compare implemented source against design schema.

**Files:**
- Create: `backend/pipeline/sync_hooks.py`

Must check:
- All designed classes exist in source
- All designed methods exist with matching signatures
- No unexpected extra public methods (unless documented)
- Attribute types match

---

### Task 32: Create Test Coverage Hook

**Objective:** Verify tests cover all verification methods.

Must check:
- Each verification_method.test_name has a corresponding test
- Test assertions match postconditions
- Test setup matches preconditions
- Test actions match verification actions

---

### Task 33: Create Neo4j Implementation Marker

**Objective:** After sync hooks pass, update Neo4j Design nodes with implementation_status="implemented", source_file, test_file.

**Files:**
- Modify: `backend/db/neo4j_sync.py` (add implementation status update to sync workflow)

---

### Task 34: Create Neo4j Test-Verification Link

**Objective:** Link test file paths to Verification nodes in Neo4j.

---

### Task 35: Test Sync Hooks

**Files:**
- Create: `tests/test_sync_hooks.py`

---

### Task 36: Wire Sync Hooks into Orchestrator

**Objective:** Call sync hooks after implementation, before final Neo4j update.

---

### Task 37: Final Neo4j Sync in Orchestrator

**Objective:** After all phases pass, do a full Neo4j sync (design nodes, tasks, verifications, implementation status).

---

## Phase G: Calculator Benchmark

### Task 38: Refine Calculator HLRs for Python Benchmark

**Objective:** Ensure the calculator HLRs are clean, testable, and scoped for Python.

**Files:**
- Modify: `scripts/04_benchmark_calculator.py`

---

### Task 39: Run Full Pipeline on Calculator Benchmark

**Objective:** Execute `run_pipeline()` end-to-end with the calculator HLRs. This is the integration test of the entire system.

---

### Task 40: Collect Pipeline Artifacts

**Objective:** Save all benchmark artifacts to `benchmark/calculator/`:
- `requirements.md` — all HLRs + LLRs
- `design/` — OO design JSON + diagrams
- `tasks.md` — generated tasks with dependencies
- `verification/` — verification methods + coverage report
- `implementation/` — source code
- `tests/` — test files
- `sync_report.md` — hook results
- `neo4j_export.json` — graph export

---

### Task 41: Create Benchmark Artifact Viewer

**Objective:** NiceGUI page or static HTML that displays all benchmark artifacts in a navigable interface.

**Files:**
- Create: `benchmark/viewer.py`

---

### Task 42: Implement Multi-Model LLM Analysis

**Objective:** Send benchmark artifacts to multiple LLM models (via llm-caller's multi-backend) and collect assessments on:
- Design quality (does the OO design appropriately solve the requirements?)
- Test adequacy (do tests cover the verification methods?)
- Implementation correctness (does code match design and pass tests?)

**Files:**
- Create: `benchmark/analysis.py`

---

### Task 43: Create Analysis Report

**Objective:** Aggregate multi-model assessments into a comparative report.

---

## Phase H: Dashboard & Documentation

### Task 44: Add Tasks View to Dashboard

**Objective:** NiceGUI page showing tasks, their status, linked design nodes, and verifications.

**Files:**
- Create: `frontend/pages/tasks.py` (or add to existing pages)

---

### Task 45: Add Pipeline Status View

**Objective:** Dashboard page showing pipeline run status (HLRs → LLRs → Design → Tasks → Implementation).

---

### Task 46: Write Integration Test for Full Pipeline

**Files:**
- Create: `tests/test_pipeline_integration.py`

---

### Task 47: Update TODO.md

**Objective:** Mark completed items, add new ones.

---

### Task 48: Write Spec-Driven Development Documentation

**Objective:** Document the entire workflow, architecture, and how to run the benchmark.

**Files:**
- Create: `docs/spec-driven-development.md`

---

## File Change Summary

**New files (~25):**
```
backend/pipeline/__init__.py
backend/pipeline/orchestrator.py
backend/pipeline/schemas.py
backend/pipeline/services.py
backend/pipeline/sync_hooks.py
backend/pipeline/test_coverage.py
backend/db/models/tasks.py
backend/services/neo4j_service.py
backend/ticketing_agent/generate_tasks.py
backend/ticketing_agent/generate_tasks_prompt.py
backend/ticketing_agent/generate_skeleton.py
backend/ticketing_agent/skeleton_templates/__init__.py
backend/ticketing_agent/skeleton_templates/python.py
backend/ticketing_agent/write_tests.py
backend/ticketing_agent/write_tests_prompt.py
backend/ticketing_agent/implement.py
backend/ticketing_agent/implement_prompt.py
benchmark/analysis.py
benchmark/viewer.py
docs/spec-driven-development.md
scripts/04_benchmark_calculator.py
scripts/05_generate_tasks.py
tests/test_pipeline_schemas.py
tests/test_task_persistence.py
tests/test_generate_tasks_prompt.py
tests/test_generate_skeleton.py
tests/test_write_tests.py
tests/test_sync_hooks.py
tests/test_pipeline_integration.py
```

**Modified files (~8):**
```
backend/db/models/ontology.py          # + implementation_status, source_file, test_file, task_links
backend/db/models/verification.py      # + task_links relationship
backend/db/models/__init__.py          # + Task imports
backend/db/neo4j_sync.py               # + task/implementation sync functions
backend/pipeline/orchestrator.py       # + full run_pipeline implementation (was skeleton)
TODO.md                                # update
```

---

## Execution Ordering and Parallelism

```
Phase A (Tasks 1-5): Sequential (Task 2 before Task 3, etc.)
  ├─ Task 1: Start Neo4j
  ├─ Task 2: ORM models + migration
  ├─ Task 3: Neo4j service + sync extensions
  ├─ Task 4: Pipeline package + schemas + orchestrator skeleton
  └─ Task 5: Calculator benchmark seed script

Phase B (Tasks 6-12): Task 6, 7 independent; 8-12 depend on 6+7
  ├─ Task 6: Task generation agent + prompt
  ├─ Task 7: Task persistence service
  ├─ Task 8: CLI script
  ├─ Task 9-11: Tests (parallel with each other)
  └─ Task 12: Wire into orchestrator

Phase C (Tasks 13-18): Task 13-14 independent; 15-17 sequential; 18 last
  ├─ Task 13: Skeleton module
  ├─ Task 14: Python templates
  ├─ Task 15: Class skeleton generator
  ├─ Task 16: Package structure
  ├─ Task 17: File writer
  └─ Task 18: Tests

Phase D (Tasks 19-25): Task 19-20 first, then 21-25
  ├─ Task 19: Test writer module + prompt
  ├─ Task 20: Agent implementation
  ├─ Task 21: Test file writer
  ├─ Task 22: Import compatibility
  ├─ Task 23: Tests
  ├─ Task 24: Coverage verifier
  └─ Task 25: Wire into orchestrator

Phase E (Tasks 26-30): Sequential
  ├─ Task 26: Implementation module + prompt
  ├─ Task 27: Prompt design
  ├─ Task 28: Per-task code gen
  ├─ Task 29: Post-task test verification
  └─ Task 30: Wire into orchestrator

Phase F (Tasks 31-37): Sequential within phase
Phase G (Tasks 38-43): Sequential (full pipeline run)
Phase H (Tasks 44-48): 44-45 parallel; 46-48 sequential
```

---

## Risks and Open Questions

1. **Neo4j availability:** Docker may or may not be available on this machine. If not, Neo4j sync should gracefully degrade (already partially handled by `try_sync_*` functions in neo4j_sync.py).

2. **llm-caller dependency:** All agents use `from llm_caller import call_tool`. This is a separate repo at `~/llm-caller`. The pattern is established and working.

3. **Python vs C++ focus migration:** The existing system was built for C++ (Conan, CMake, Doxygen). This plan targets Python for the calculator benchmark. The skeleton/test writer/implement agents need language-specific templates that are separate from the existing C++-focused ones.

4. **Workspace directory:** The pipeline needs a workspace directory where source/tests are generated. This should be configurable per-component and default to `workspace/<component_name>/`.

5. **Task granularity for subagent execution:** Some early-phase tasks (schemas, models) are straightforward enough to batch. Later-phase tasks (agents with tool calls) need full subagent treatment.

6. **Multi-model analysis:** Task 42 requires llm-caller's multi-backend support. This is available but needs proper provider configuration.
