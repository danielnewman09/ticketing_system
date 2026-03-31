"""Data-fetching functions for UI pages. Run in threads via asyncio.to_thread."""

from frontend.data.components import (
    add_dependency,
    create_dependency_manager,
    delete_dependency,
    delete_dependency_manager,
    ensure_component_language,
    fetch_component_detail,
    fetch_components_data,
    fetch_components_options,
    update_dependency_index_config,
)
from frontend.data.dependencies import (
    accept_recommendation,
    add_manual_recommendation,
    fetch_dependency_graph_data,
    fetch_dependency_node_detail_data,
    fetch_design_dependency_links_data,
    fetch_pending_recommendations_summary,
    fetch_recommendations,
    reject_use_stdlib,
    save_recommendations,
    update_recommendation_status,
)
from frontend.data.hlr import (
    create_hlr,
    decompose_hlr,
    delete_hlr,
    fetch_hlr_detail,
    fetch_requirements_data,
    update_hlr,
)
from frontend.data.llr import (
    create_llr,
    delete_llr,
    fetch_llr_detail,
    update_llr,
)
from frontend.data.ontology import (
    fetch_codebase_graph_data,
    fetch_graph_node_detail,
    fetch_hlr_graph_data,
    fetch_neighbourhood_graph_data,
    fetch_node_detail_full,
    fetch_ontology_data,
    fetch_ontology_graph_data,
    resolve_node_id_by_qualified_name,
    update_member_type,
)
from frontend.data.project import (
    fetch_environment_data,
    fetch_project_meta,
    update_project_meta,
)

__all__ = [
    # project
    "fetch_project_meta",
    "update_project_meta",
    "fetch_environment_data",
    # hlr
    "fetch_requirements_data",
    "fetch_hlr_detail",
    "create_hlr",
    "update_hlr",
    "delete_hlr",
    "decompose_hlr",
    # llr
    "fetch_llr_detail",
    "create_llr",
    "update_llr",
    "delete_llr",
    # components
    "fetch_components_data",
    "fetch_component_detail",
    "fetch_components_options",
    "ensure_component_language",
    "create_dependency_manager",
    "add_dependency",
    "update_dependency_index_config",
    "delete_dependency",
    "delete_dependency_manager",
    # ontology
    "fetch_ontology_data",
    "fetch_ontology_graph_data",
    "fetch_codebase_graph_data",
    "fetch_hlr_graph_data",
    "fetch_neighbourhood_graph_data",
    "fetch_graph_node_detail",
    "fetch_node_detail_full",
    "resolve_node_id_by_qualified_name",
    "update_member_type",
    # dependencies
    "fetch_dependency_graph_data",
    "fetch_dependency_node_detail_data",
    "fetch_design_dependency_links_data",
    "fetch_recommendations",
    "save_recommendations",
    "update_recommendation_status",
    "accept_recommendation",
    "add_manual_recommendation",
    "reject_use_stdlib",
    "fetch_pending_recommendations_summary",
]
