# Design: Refactor combined_tools.py into Per-Tool Files with Class-Based Dispatcher

**Date:** 2026-07-22  
**Status:** Approved

## Problem

`backend/ticketing_agent/design_verify/combined_tools.py` is 1148 lines and growing. It contains:

- 13 tool schema definitions (JSON dicts at module level)
- 4 standalone helper functions
- 2 qname-resolution functions
- A 580-line `make_combined_dispatcher()` closure containing 9 inner dispatch functions that share 5 constructor parameters and 3 mutable state variables via closure capture

The closure structure makes it difficult to:
- Navigate to a specific tool's logic (all 9 handlers are indented inside one function)
- Test individual tools in isolation (need to construct the entire closure)
- Reuse tool logic across agents (check_class_name and find_mechanism are duplicated between design_oo_tools and combined_tools)
- Understand what state a handler depends on (everything is closed over implicitly)

## Solution

Refactor `combined_tools.py` into a `tools/` package with:
1. **One file per tool** — each tool defines its own `SCHEMA` dict and `handle()` function
2. **A `CombinedDispatcher` class** replacing the closure — state becomes explicit instance attributes
3. **Shared helpers extracted** into `tools/helpers/` — pure functions reusable across all dispatchers
4. **A `ToolDispatcher` base class** — lightweight registry pattern, reusable for future dispatcher migrations
5. **Discovery tools** extracted to `tools/utilities/` — thin schema files delegating to `discover_tool_dispatch`

### Approach

Handler-per-file with `ToolDispatcher` base class and `DispatcherContext`-pattern (the dispatcher instance itself is the context). Each tool file exports a `SCHEMA` dict and a `handle(ctx, tool_input) -> str` function. `ctx` is the `CombinedDispatcher` instance with all shared state as public attributes.

## Package Structure

```
backend/ticketing_agent/
    tools/
        __init__.py                  # ToolDispatcher base class
        helpers/
            __init__.py              # re-exports
            qname.py                 # qname_resolves, suggest_qname
            draft_state.py           # build_draft_lookup, draft_summary
            commit_schema.py         # commit_tool_schema
            design_validation.py     # validate_oo_design, extract_type_refs
            discovery.py             # discover_tool_dispatch, slim_compound
        design_verify/
            __init__.py              # exports CombinedDispatcher
            dispatcher.py            # CombinedDispatcher(ToolDispatcher)
            draft_design.py          # SCHEMA + handle()
            validate_design.py       # SCHEMA + handle()
            check_class_name.py      # SCHEMA + handle()
            find_mechanism.py         # SCHEMA + handle()
            validate_qualified_names.py  # SCHEMA + handle()
            lookup_design_element.py # SCHEMA + handle()
            draft_verifications.py   # SCHEMA + handle()
            commit.py                # SCHEMA + handle()
        utilities/
            __init__.py
            list_sources.py          # SCHEMA (delegates to discover_tool_dispatch)
            search_symbols.py        # SCHEMA
            get_compound.py          # SCHEMA
            browse_namespace.py       # SCHEMA
            find_inheritance.py      # SCHEMA
```

## Component Design

### ToolDispatcher Base Class

Lives in `tools/__init__.py`. ~25 lines. Registers handler functions by tool name alongside their schemas. Provides `dispatch()` for tool-loop routing and `all_tool_schemas` for the LLM call.

```python
class ToolDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], str]] = {}
        self._schemas: dict[str, dict] = {}

    def register(self, name: str, schema: dict, handler: Callable[[dict], str]) -> None:
        if name in self._handlers:
            raise ValueError(f"Duplicate tool handler: {name}")
        self._handlers[name] = handler
        self._schemas[name] = schema

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        handler = self._handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        return handler(tool_input)

    @property
    def all_tool_schemas(self) -> list[dict]:
        return list(self._schemas.values())
```

Schemas are co-registered with handlers, so they can never get out of sync. `all_tool_schemas` replaces the module-level `ALL_TOOLS` list.

### CombinedDispatcher

Lives in `tools/design_verify/dispatcher.py`. The class replaces `make_combined_dispatcher()`. Constructor signature is identical to the old function, so caller migration is minimal.

```python
class CombinedDispatcher(ToolDispatcher):
    def __init__(self, prior_class_lookup, dependency_lookup=None,
                 intercomponent_classes=None, neo4j_session=None, toolset=None):
        super().__init__()
        # Immutable context
        self.prior_class_lookup = prior_class_lookup
        self.dep_lookup = dict(dependency_lookup or {})
        self.intercomponent_classes = intercomponent_classes or []
        self.neo4j_session = neo4j_session
        self.toolset = toolset
        # Mutable draft state
        self.draft_design = None
        self.draft_lookup = {}
        self.draft_verifications = {}
        # Register handlers grouped by purpose
        self._register_design_tools()
        self._register_verification_tools()
        self._register_discovery_tools()
```

Registration groups (`_register_design_tools`, `_register_verification_tools`, `_register_discovery_tools`) make it easy to see which tools belong where and enable future `DesignDispatcher` subclasses to reuse the same handler registration.

Handlers are registered via lambdas that bind `self`:

```python
self.register("draft_design", DRAFT_DESIGN_SCHEMA, lambda inp: handle_draft_design(self, inp))
```

### Handler Pattern

Each tool file follows the same pattern:

1. **`SCHEMA`** — the Anthropic-format tool definition (JSON dict)
2. **`handle(ctx, tool_input) -> str`** — `ctx` is the `CombinedDispatcher` instance

Read-only handlers (like `check_class_name`) read `ctx.draft_lookup`, `ctx.prior_class_lookup`, etc. State-mutating handlers (like `draft_design`) write `ctx.draft_design`, `ctx.draft_lookup`. No `nonlocal` — state is always accessed via `ctx`.

Example:

```python
# tools/design_verify/check_class_name.py
SCHEMA = { ... }

def handle(ctx, tool_input: dict) -> str:
    name = tool_input.get("name", "")
    # ... search ctx.draft_lookup, ctx.prior_class_lookup, ctx.dep_lookup, ctx.intercomponent_classes
```

### Shared Helpers

Extracted from `combined_tools.py` and `design_oo_tools.py`. All dropped the `_` prefix since they're now public module functions.

| Old location | New location | Name change |
|---|---|---|
| `combined_tools._qname_resolves` | `helpers/qname.py` | `qname_resolves` |
| `combined_tools._suggest_qname` | `helpers/qname.py` | `suggest_qname` |
| `combined_tools._build_draft_lookup` | `helpers/draft_state.py` | `build_draft_lookup` |
| `combined_tools._draft_summary` | `helpers/draft_state.py` | `draft_summary` |
| `combined_tools` inline enum collision check | `helpers/draft_state.py` | `check_enum_collisions` |
| `combined_tools._commit_tool_schema` | `helpers/commit_schema.py` | `commit_tool_schema` |
| `combined_tools._slim_compound` | `helpers/discovery.py` | `slim_compound` |
| `combined_tools._dispatch_discovery` | `helpers/discovery.py` | `discover_tool_dispatch` |
| `design_oo_tools._validate_oo_design` | `helpers/design_validation.py` | `validate_oo_design` |
| `design_oo_tools._extract_type_refs` | `helpers/design_validation.py` | `extract_type_refs` |

### Discovery Tools

The five discovery tools (`list_sources`, `search_symbols`, `get_compound`, `browse_namespace`, `find_inheritance`) are schema-only files that delegate to `discover_tool_dispatch()` in `helpers/discovery.py`. Each handler is a one-liner:

```python
# tools/utilities/search_symbols.py
def handle(ctx, tool_input: dict) -> str:
    return discover_tool_dispatch("search_symbols", tool_input, ctx.toolset)
```

`discover_tool_dispatch` routes by name to the `DependencyGraphTools` method, handles missing toolset gracefully, and applies result-slimming for `get_compound`.

### Handler Grouping and Future Dispatcher Composition

The three current dispatchers have overlapping tools:

| Tool | design_oo | verify_llr | combined |
|---|---|---|---|
| validate_design | yes | | yes |
| check_class_name | yes | | yes |
| find_mechanism | yes | | yes |
| produce_oo_design | yes | | |
| validate_qualified_names | | yes | yes |
| lookup_design_element | | yes | yes |
| produce_verifications | | yes | |
| draft_design | | | yes |
| draft_verifications | | | yes |
| commit_design_and_verifications | | | yes |
| 5 discovery tools | | | yes |

The shared handlers (check_class_name, find_mechanism, validate_qualified_names, lookup_design_element) are the same logic — they just read from different context. When `design_oo_tools.py` migrates to `tools/design/dispatcher.py`, `DesignDispatcher` will import and register the same handler files. The "terminal" tools differ per agent (`produce_oo_design` vs `commit_design_and_verifications`), so those remain agent-specific.

## Migration Changes

### Files deleted

- `combined_tools.py` — replaced entirely by the `tools/` package

### Files modified

| File | Change |
|---|---|
| `combined_loop.py` | Change 3 lines: import `CombinedDispatcher` from new location, use `dispatcher.all_tool_schemas` and `dispatcher.dispatch` |
| `design_oo_tools.py` | Change import: `_validate_oo_design` → `from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design` |

### `combined_loop.py` changes (3 lines)

```python
# Before:
from backend.ticketing_agent.design_verify.combined_tools import ALL_TOOLS, make_combined_dispatcher
dispatcher = make_combined_dispatcher(...)
result = call_tool_loop(..., tools=ALL_TOOLS, tool_dispatcher=dispatcher, ...)

# After:
from backend.ticketing_agent.tools.design_verify import CombinedDispatcher
dispatcher = CombinedDispatcher(...)
result = call_tool_loop(..., tools=dispatcher.all_tool_schemas, tool_dispatcher=dispatcher.dispatch, ...)
```

### `design_oo_tools.py` changes (1 import + 2 references)

```python
# Before:
def _extract_type_refs(...): ...
def _validate_oo_design(...): ...

# After:
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design, extract_type_refs
# (references to _validate_oo_design → validate_oo_design, _extract_type_refs → extract_type_refs)
```

### `verify_llr_tools.py`

No changes. It has its own simpler versions of `validate_qualified_names` and `lookup_design_element` that query Neo4j directly without draft state. When it migrates to `tools/verify/`, those can be refactored to share helpers, but that's a separate task.

### Tests

No existing tests target `combined_tools.py` directly. Integration tests test via `combined_loop.py` and will continue to pass once the import changes. New unit tests can target individual handler functions by creating a lightweight mock context object with just the needed attributes.

## Future Migration Path

When `design_oo_tools.py` migrates:

```python
# tools/design/dispatcher.py
class DesignDispatcher(ToolDispatcher):
    def __init__(self, prior_class_lookup, dependency_lookup=None, ...):
        super().__init__()
        self.prior_class_lookup = prior_class_lookup
        self.dep_lookup = dict(dependency_lookup or {})
        ...
        self._register_handlers()

    def _register_handlers(self):
        self.register("validate_design", VALIDATE_DESIGN_SCHEMA,
                       lambda inp: handle_validate_design(self, inp))
        # Reuses check_class_name and find_mechanism handlers from design_verify/
        self.register("check_class_name", CHECK_CLASS_NAME_SCHEMA,
                       lambda inp: handle_check_class_name(self, inp))
        self.register("find_mechanism", FIND_MECHANISM_SCHEMA,
                       lambda inp: handle_find_mechanism(self, inp))
        self.register("produce_oo_design", PRODUCE_OO_DESIGN_SCHEMA,
                       lambda inp: handle_produce_oo_design(self, inp))
```

Similarly, `verify_llr_tools.py` becomes `tools/verify/dispatcher.py` with a `VerifyDispatcher`.

## Approximate Line Counts

| File | Lines | Notes |
|---|---|---|
| `tools/__init__.py` | ~25 | ToolDispatcher base class |
| `tools/helpers/qname.py` | ~80 | qname_resolves + suggest_qname |
| `tools/helpers/draft_state.py` | ~90 | build_draft_lookup, draft_summary, check_enum_collisions |
| `tools/helpers/commit_schema.py` | ~25 | commit_tool_schema |
| `tools/helpers/design_validation.py` | ~180 | validate_oo_design + extract_type_refs |
| `tools/helpers/discovery.py` | ~50 | discover_tool_dispatch + slim_compound |
| `tools/design_verify/dispatcher.py` | ~60 | CombinedDispatcher class |
| `tools/design_verify/draft_design.py` | ~55 | Schema + handler |
| `tools/design_verify/validate_design.py` | ~40 | Schema + handler |
| `tools/design_verify/check_class_name.py` | ~65 | Schema + handler |
| `tools/design_verify/find_mechanism.py` | ~70 | Schema + handler (Neo4j fallback) |
| `tools/design_verify/validate_qualified_names.py` | ~55 | Schema + handler |
| `tools/design_verify/lookup_design_element.py` | ~60 | Schema + handler (Neo4j fallback) |
| `tools/design_verify/draft_verifications.py` | ~140 | Most complex verification logic |
| `tools/design_verify/commit.py` | ~95 | Schema + handler + qname collection |
| `tools/utilities/list_sources.py` | ~15 | Schema only |
| `tools/utilities/search_symbols.py` | ~25 | Schema only |
| `tools/utilities/get_compound.py` | ~20 | Schema only |
| `tools/utilities/browse_namespace.py` | ~25 | Schema only |
| `tools/utilities/find_inheritance.py` | ~25 | Schema only |
| **Total** | **~1140** | vs. 1148 in one monolith |

Same total line count, but now each file is independently readable (max ~180 lines for the validation helper, ~140 for the draft_verifications handler) instead of a single 1148-line closure.