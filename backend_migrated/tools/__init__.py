"""Ticketing-specific design agent tools.

Extends :class:`codegraph.tools.dispatcher.CodeGraphDispatcher` with
mutable lookups and design-validation tools.

Module structure::

    tools/
    ├── __init__.py           # Re-exports DesignToolDispatcher
    ├── dispatcher.py         # DesignToolDispatcher(CodeGraphDispatcher)
    └── design_tools.py       # validate_design, check_class_name, find_mechanism

Generic discovery/lookup/format tools live in ``codegraph.tools``.

Usage::

    from backend_migrated.tools import DesignToolDispatcher

    dispatcher = DesignToolDispatcher(
        prior_class_lookup={"CalcEngine": "calc::CalcEngine"},
        dependency_lookup={"std::vector": "std::vector"},
    )
    # 21 codegraph tools + 4 design tools = 25 total
    schemas = dispatcher.all_tool_schemas
"""

from backend_migrated.tools.dispatcher import DesignToolDispatcher

__all__ = [
    "DesignToolDispatcher",
]
