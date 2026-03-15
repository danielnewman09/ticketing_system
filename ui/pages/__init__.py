"""Page definitions. Import this module to register all routes."""

from ui.pages.requirements import requirements_page
from ui.pages.hlr_detail import hlr_detail_page
from ui.pages.llr_detail import llr_detail_page
from ui.pages.components import components_page
from ui.pages.ontology import ontology_page

__all__ = [
    "requirements_page",
    "hlr_detail_page",
    "llr_detail_page",
    "components_page",
    "ontology_page",
]
