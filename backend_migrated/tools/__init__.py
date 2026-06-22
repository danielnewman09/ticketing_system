"""Ticketing-specific design and requirements agent tools.

Extends :class:`codegraph.tools.dispatcher.CodeGraphDispatcher` with
three purpose-built dispatchers:

- :class:`DesignToolDispatcher` — mutable design lookups + design tools +
  codegraph tools (for the design phase of the agent loop)
- :class:`VerificationDispatcher` — verification-resolution tools (for
  resolving notional verification stubs to qualified design names)
- :class:`RequirementsDispatcher` — HLR/LLR hierarchy retrieval tools

Module structure::

    tools/
    ├── __init__.py              # Re-exports all three dispatchers
    ├── dispatcher.py            # DesignToolDispatcher, VerificationDispatcher,
    │                            # RequirementsDispatcher
    ├── design_tools.py         # validate_design, check_class_name, produce_oo_design
    ├── verification_tools.py  # draft_verifications, commit_design_and_verifications
    └── requirements_tools.py   # get_requirement_hierarchy, get_llr_details,
                                 # search_requirements, list_requirements,
                                 # get_requirement_traces

Usage::

    from backend_migrated.tools import (
        DesignToolDispatcher,
        VerificationDispatcher,
        RequirementsDispatcher,
    )

    # Design + verification agent (single tool loop)
    design_disp = DesignToolDispatcher(
        prior_class_lookup={"Thermostat": "climate::Thermostat"},
        dependency_lookup={"std::vector": "std::vector"},
    )
    verif_disp = VerificationDispatcher(design_dispatcher=design_disp)

    # Requirements agent (standalone)
    req_disp = RequirementsDispatcher()
"""

from backend_migrated.tools.dispatcher import (
    DesignToolDispatcher,
    VerificationDispatcher,
    RequirementsDispatcher,
)

__all__ = [
    "DesignToolDispatcher",
    "VerificationDispatcher",
    "RequirementsDispatcher",
]