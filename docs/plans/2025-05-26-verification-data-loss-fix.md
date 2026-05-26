# Verification Data Loss Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the data loss where `persist_decomposition()` discards verification conditions and actions, and simplify verification data retrieval with a repository convenience method.

**Architecture:** Add condition/action persistence to `persist_decomposition()` (matching the existing `persist_verification()` pattern). Add `get_verifications_for_llr()` to `VerificationRepository` to encapsulate the hydrated-fetch pattern. Replace the 40-line manual assembly in `combined_loop.py` with a call to the new method.

**Tech Stack:** Python, Neo4j (via `neo4j` driver), Pydantic, pytest

---

### Task 1: Add `get_verifications_for_llr()` to VerificationRepository

**Files:**
- Modify: `backend/db/neo4j/repositories/verification.py` (add method after `list_actions`)
- Modify: `tests/test_verification_repository.py` (add test class)

- [ ] **Step 1: Write the failing test**

Add a new test class `TestGetVerificationsForLlr` in `tests/test_verification_repository.py` after the existing `TestValidateReferences` class:

```python
class TestGetVerificationsForLlr:
    def test_returns_hydrated_dicts(self, neo4j_session):
        """get_verifications_for_llr returns VMs with conditions and actions."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "calc::CalculatorEngine::compute")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(
            llr_id=llr.id, method="automated",
            test_name="test_compute_returns_sum",
            description="Verify that compute(5, 3, 'add') returns 8.",
        )
        repo.add_condition(
            vm.id, phase="pre", order=0, operator="==",
            expected_value="initialized", subject_qualified_name="calc::CalculatorEngine::state",
        )
        repo.add_action(
            vm.id, order=0, description="Invoke CalculatorEngine.compute(5, 3, 'add')",
            callee_qualified_name="calc::CalculatorEngine::compute",
            caller_qualified_name="TestSuite",
        )
        repo.add_condition(
            vm.id, phase="post", order=0, operator="==",
            expected_value="8", subject_qualified_name="result",
        )

        result = repo.get_verifications_for_llr(llr.id)
        assert len(result) == 1
        v = result[0]
        assert v["method"] == "automated"
        assert v["test_name"] == "test_compute_returns_sum"
        assert v["description"] == "Verify that compute(5, 3, 'add') returns 8."
        assert len(v["preconditions"]) == 1
        assert v["preconditions"][0]["subject_qualified_name"] == "calc::CalculatorEngine::state"
        assert v["preconditions"][0]["operator"] == "=="
        assert v["preconditions"][0]["expected_value"] == "initialized"
        assert len(v["actions"]) == 1
        assert v["actions"][0]["description"] == "Invoke CalculatorEngine.compute(5, 3, 'add')"
        assert v["actions"][0]["callee_qualified_name"] == "calc::CalculatorEngine::compute"
        assert len(v["postconditions"]) == 1
        assert v["postconditions"][0]["subject_qualified_name"] == "result"
        assert v["postconditions"][0]["expected_value"] == "8"

    def test_returns_empty_list_when_no_verifications(self, neo4j_session):
        """get_verifications_for_llr returns [] for an LLR with no verifications."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        result = repo.get_verifications_for_llr(llr.id)
        assert result == []

    def test_multiple_verifications_for_one_llr(self, neo4j_session):
        """get_verifications_for_llr returns all VMs for an LLR."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        repo.create_verification(llr_id=llr.id, method="automated", test_name="test_a")
        repo.create_verification(llr_id=llr.id, method="review", test_name="test_b")
        result = repo.get_verifications_for_llr(llr.id)
        assert len(result) == 2
        methods = {v["method"] for v in result}
        assert methods == {"automated", "review"}

    def test_vm_with_no_conditions_or_actions(self, neo4j_session):
        """get_verifications_for_llr returns stub VMs with empty lists."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        repo.create_verification(llr_id=llr.id, method="automated", test_name="test_stub")
        result = repo.get_verifications_for_llr(llr.id)
        assert len(result) == 1
        v = result[0]
        assert v["preconditions"] == []
        assert v["actions"] == []
        assert v["postconditions"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_verification_repository.py::TestGetVerificationsForLlr -v`
Expected: FAIL — `AttributeError: 'VerificationRepository' object has no attribute 'get_verifications_for_llr'`

- [ ] **Step 3: Write the implementation**

Add the following method to `VerificationRepository` in `backend/db/neo4j/repositories/verification.py`, after the `list_actions` method (before the `validate_references` method):

```python
    # -----------------------------------------------------------------------
    # Hydrated verification retrieval
    # -----------------------------------------------------------------------

    def get_verifications_for_llr(self, llr_id: int) -> list[dict]:
        """Return fully-hydrated verification dicts for a given LLR.

        Each dict has: method, test_name, description, preconditions,
        actions, postconditions — matching the shape expected by
        format_llrs_with_verifications_for_prompt().
        """
        vms = self.list_verifications(llr_id)
        result = []
        for vm in vms:
            conditions = self.list_conditions(vm.id)
            actions = self.list_actions(vm.id)
            result.append({
                "method": vm.method,
                "test_name": vm.test_name,
                "description": vm.description,
                "preconditions": [
                    {
                        "subject_qualified_name": c.subject_qualified_name,
                        "operator": c.operator,
                        "expected_value": c.expected_value,
                        "object_qualified_name": c.object_qualified_name,
                    }
                    for c in conditions
                    if c.phase == "pre"
                ],
                "actions": [
                    {
                        "description": a.description,
                        "callee_qualified_name": a.callee_qualified_name,
                        "caller_qualified_name": a.caller_qualified_name,
                    }
                    for a in actions
                ],
                "postconditions": [
                    {
                        "subject_qualified_name": c.subject_qualified_name,
                        "operator": c.operator,
                        "expected_value": c.expected_value,
                        "object_qualified_name": c.object_qualified_name,
                    }
                    for c in conditions
                    if c.phase == "post"
                ],
            })
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_verification_repository.py::TestGetVerificationsForLlr -v`
Expected: PASS — all 4 tests green

- [ ] **Step 5: Commit**

```bash
git add backend/db/neo4j/repositories/verification.py tests/test_verification_repository.py
git commit -m "feat: add VerificationRepository.get_verifications_for_llr() convenience method"
```

---

### Task 2: Update `persist_decomposition()` to persist conditions and actions

**Files:**
- Modify: `backend/requirements/services/persistence.py` (update `persist_decomposition` and `DecompositionResult`)
- Modify: `tests/test_persistence.py` (add test class)

- [ ] **Step 1: Write the failing test**

Add a new test class `TestPersistDecompositionNeo4j` in `tests/test_persistence.py` after the existing `TestPersistDesignNeo4j` class:

```python
class TestPersistDecompositionNeo4j:
    """Integration tests for persist_decomposition with conditions and actions."""

    def test_persist_decomposition_stores_conditions_and_actions(self, neo4j_session):
        """persist_decomposition stores verification method stubs with full
        conditions and actions, not just method/test_name/description."""
        from backend.requirements.schemas import (
            VerificationConditionSchema,
            VerificationActionSchema,
            VerificationSchema,
            LowLevelRequirementSchema,
        )
        from backend.requirements.services.persistence import persist_decomposition
        from backend.db.neo4j.repositories.verification import VerificationRepository
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        llr_data = LowLevelRequirementSchema(
            description="The engine computes addition.",
            verifications=[
                VerificationSchema(
                    method="automated",
                    test_name="test_compute_returns_sum",
                    description="Verify that 2 + 3 returns 5.",
                    preconditions=[
                        VerificationConditionSchema(
                            subject_qualified_name="calc::Engine::state",
                            operator="==",
                            expected_value="initialized",
                            object_qualified_name="",
                        ),
                    ],
                    actions=[
                        VerificationActionSchema(
                            description="Call compute(2, 3, '+')",
                            callee_qualified_name="calc::Engine::compute",
                            caller_qualified_name="TestSuite",
                        ),
                    ],
                    postconditions=[
                        VerificationConditionSchema(
                            subject_qualified_name="calc::Engine::result",
                            operator="==",
                            expected_value="5",
                            object_qualified_name="",
                        ),
                    ],
                ),
            ],
        )

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall compute.")

        result = persist_decomposition(neo4j_session, hlr.id, [llr_data])

        assert result.llrs_created == 1
        assert result.verifications_created == 1
        assert result.conditions_created == 2  # 1 pre + 1 post
        assert result.actions_created == 1

        # Verify data in Neo4j via VerificationRepository
        ver_repo = VerificationRepository(neo4j_session)
        llrs = req_repo.list_llrs(hlr_id=hlr.id)
        assert len(llrs) == 1

        hydrated = ver_repo.get_verifications_for_llr(llrs[0].id)
        assert len(hydrated) == 1
        v = hydrated[0]
        assert v["method"] == "automated"
        assert v["test_name"] == "test_compute_returns_sum"
        assert len(v["preconditions"]) == 1
        assert v["preconditions"][0]["subject_qualified_name"] == "calc::Engine::state"
        assert v["preconditions"][0]["operator"] == "=="
        assert v["preconditions"][0]["expected_value"] == "initialized"
        assert len(v["actions"]) == 1
        assert v["actions"][0]["description"] == "Call compute(2, 3, '+')"
        assert v["actions"][0]["callee_qualified_name"] == "calc::Engine::compute"
        assert len(v["postconditions"]) == 1
        assert v["postconditions"][0]["subject_qualified_name"] == "calc::Engine::result"
        assert v["postconditions"][0]["expected_value"] == "5"

    def test_persist_decomposition_with_no_conditions_or_actions(self, neo4j_session):
        """persist_decomposition handles verification stubs with empty
        conditions and actions gracefully."""
        from backend.requirements.schemas import (
            VerificationSchema,
            LowLevelRequirementSchema,
        )
        from backend.requirements.services.persistence import persist_decomposition
        from backend.db.neo4j.repositories.verification import VerificationRepository
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        llr_data = LowLevelRequirementSchema(
            description="The engine returns immediately.",
            verifications=[
                VerificationSchema(
                    method="inspection",
                    test_name="test_immediate_response",
                    description="Verify synchronous response.",
                ),
            ],
        )

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall respond fast.")

        result = persist_decomposition(neo4j_session, hlr.id, [llr_data])

        assert result.llrs_created == 1
        assert result.verifications_created == 1
        assert result.conditions_created == 0
        assert result.actions_created == 0

        ver_repo = VerificationRepository(neo4j_session)
        llrs = req_repo.list_llrs(hlr_id=hlr.id)
        hydrated = ver_repo.get_verifications_for_llr(llrs[0].id)
        assert len(hydrated) == 1
        assert hydrated[0]["preconditions"] == []
        assert hydrated[0]["actions"] == []
        assert hydrated[0]["postconditions"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_persistence.py::TestPersistDecompositionNeo4j -v`
Expected: FAIL — `AssertionError: assert 0 == 2` on `result.conditions_created` (and possibly `AttributeError` if `DecompositionResult` doesn't have the new counters yet)

- [ ] **Step 3: Update `DecompositionResult` dataclass**

In `backend/requirements/services/persistence.py`, update the `DecompositionResult` dataclass to add the new counters:

```python
@dataclass
class DecompositionResult:
    llrs_created: int = 0
    verifications_created: int = 0
    conditions_created: int = 0
    actions_created: int = 0
```

- [ ] **Step 4: Update `persist_decomposition()` to persist conditions and actions**

In `backend/requirements/services/persistence.py`, replace the verification persistence loop inside `persist_decomposition()`:

Old code:
```python
        # Persist verification stubs in Neo4j
        for v in llr_data.verifications:
            ver_repo.create_verification(
                llr_id=llr.id,
                method=v.method,
                test_name=v.test_name,
                description=v.description,
            )
            result.verifications_created += 1
```

New code:
```python
        # Persist verification methods with conditions and actions
        for v in llr_data.verifications:
            vm = ver_repo.create_verification(
                llr_id=llr.id,
                method=v.method,
                test_name=v.test_name,
                description=v.description,
            )
            result.verifications_created += 1

            for i, cond in enumerate(v.preconditions):
                ver_repo.add_condition(
                    vm_id=vm.id,
                    phase="pre",
                    order=i,
                    operator=cond.operator,
                    expected_value=cond.expected_value,
                    subject_qualified_name=cond.subject_qualified_name,
                    object_qualified_name=cond.object_qualified_name,
                )
                result.conditions_created += 1

            for i, action in enumerate(v.actions):
                ver_repo.add_action(
                    vm_id=vm.id,
                    order=i,
                    description=action.description,
                    callee_qualified_name=action.callee_qualified_name,
                    caller_qualified_name=action.caller_qualified_name,
                )
                result.actions_created += 1

            for i, cond in enumerate(v.postconditions):
                ver_repo.add_condition(
                    vm_id=vm.id,
                    phase="post",
                    order=i,
                    operator=cond.operator,
                    expected_value=cond.expected_value,
                    subject_qualified_name=cond.subject_qualified_name,
                    object_qualified_name=cond.object_qualified_name,
                )
                result.conditions_created += 1
```

- [ ] **Step 5: Run test to verify it passes**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_persistence.py::TestPersistDecompositionNeo4j -v`
Expected: PASS — both tests green

- [ ] **Step 6: Commit**

```bash
git add backend/requirements/services/persistence.py tests/test_persistence.py
git commit -m "fix: persist verification conditions and actions in persist_decomposition()"
```

---

### Task 3: Simplify retrieval in `combined_loop.py`

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_loop.py` (replace lines 96-137)

- [ ] **Step 1: Replace the 40-line manual assembly block**

In `backend/ticketing_agent/design_verify/combined_loop.py`, replace the block from `llr_verifications: dict[int, list[dict]] = {}` through `llr_verifications[llr_id] = verifs_for_llr` (approximately lines 96-137) with:

```python
    # Format requirements with full verification stubs from decompose
    llr_verifications: dict[int, list[dict]] = {}
    if neo4j_session is not None and llrs:
        ver_repo = VerificationRepository(neo4j_session)
        for llr in llrs:
            verifs = ver_repo.get_verifications_for_llr(llr["id"])
            if verifs:
                llr_verifications[llr["id"]] = verifs
```

- [ ] **Step 2: Verify no other code references were affected**

Check that `format_llrs_with_verifications_for_prompt` is still called with the same arguments. The line below the replaced block should still read:

```python
    requirements_text = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
```

Also verify the `VerificationRepository` import at the top of the file is still used (it is — via `ver_repo`).

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_formatting_verifications.py -v`
Expected: PASS — formatting tests are unchanged

Run: `pytest tests/ -k "combined_loop" -v`
Expected: Any existing combined_loop tests pass (may be none if it's only integration-tested)

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_loop.py
git commit -m "refactor: replace manual verification assembly with get_verifications_for_llr()"
```

---

### Task 4: Update callers of `persist_decomposition` for new return type

**Files:**
- Check: `backend/pipeline/orchestrator.py`, `scripts/03_design_requirements.py`, `backend/ticketing_agent/mcp_server.py`, `frontend/data/hlr.py`

- [ ] **Step 1: Audit all callers of `persist_decomposition`**

Search for any code that reads `DecompositionResult` fields. Since we only *added* new fields (`conditions_created`, `actions_created`) with default values of 0, all existing callers are automatically compatible. No callers access the new fields. The existing `result.llrs_created` and `result.verifications_created` fields are untouched.

Verify by running: `grep -rn "persist_decomposition\|DecompositionResult" backend/ scripts/ frontend/ --include="*.py" | grep -v ".venv" | grep -v ".worktrees" | grep -v "__pycache__"`

- [ ] **Step 2: Commit (only if changes were needed)**

Only commit if any callers needed updating. Since `DecompositionResult` is a dataclass with default values, no caller changes are expected.

---

### Task 5: End-to-end verification

**Files:** None (manual verification)

- [ ] **Step 1: Run full Neo4j integration test suite**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_verification_repository.py tests/test_persistence.py -v`
Expected: All tests pass, including the new test classes

- [ ] **Step 2: Run full unit test suite**

Run: `pytest tests/test_formatting_verifications.py -v`
Expected: All formatting tests pass unchanged

- [ ] **Step 3: Run the project's existing test suite**

Run: `pytest tests/ -v --ignore=tests/integration -k "not neo4j" 2>&1 | tail -20`
Expected: All existing tests still pass