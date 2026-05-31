#!/usr/bin/env python
"""
Generate skeleton source files from design data.

Reads OO design data from Neo4j (nodes + triples) and reconstructs
OODesignSchema-compatible dicts, then generates header/source stubs
that compile but are incomplete (TODO bodies, default return values).

This is pipeline step 05, run after 04_scaffold_project.py which creates
the project directory structure. The skeleton generator fills in the
class/method declarations based on the design ontology.

Steps:
  1. Read project metadata (name, working_directory) from SQLite
  2. Read architectural components from SQLite
  3. Load design nodes and triples from Neo4j
  4. Reconstruct OODesignSchema from Neo4j data
  5. Generate C++ header/source skeleton files per component
  6. (Optional) Verify the skeleton compiles

Assumes 03_design_requirements.py and 04_scaffold_project.py have been run.

Usage:
    source .venv/bin/activate
    python scripts/05_generate_skeleton.py
    python scripts/05_generate_skeleton.py --name calculator-engine --working-directory ~/dev/calculator-example
    python scripts/05_generate_skeleton.py --skip-build
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

from backend.db import init_db, get_session, get_or_create
from backend.db.models import Component, Language, ProjectMeta
from codegraph.neo4j import Neo4jConnection
from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.ticketing_agent.generate_skeleton import generate_skeleton
from services.dependencies import get_neo4j, init_neo4j, close_neo4j

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def _configure_logging():
    """Set up file logging for the skeleton generation run."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, "skeleton_pipeline.log")

    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)

    # Suppress noisy neo4j logs
    for name in ["neo4j", "neo4j.driver", "neo4j.io", "neo4j.pool"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    return log_file


def _get_or_create_project_meta(session) -> ProjectMeta:
    """Get the singleton ProjectMeta row, creating it if needed."""
    meta = session.query(ProjectMeta).filter_by(id=1).first()
    if not meta:
        meta = ProjectMeta(id=1, name="", description="", working_directory="")
        session.add(meta)
        session.flush()
    return meta


def _get_project_meta() -> dict:
    """Read project metadata from SQLite."""
    with get_session() as session:
        meta = _get_or_create_project_meta(session)
        return {
            "name": meta.name or "",
            "description": meta.description or "",
            "working_directory": meta.working_directory or "",
        }


def _set_project_meta(name: str = "", working_directory: str = "") -> None:
    """Persist project name and/or working directory to SQLite."""
    with get_session() as session:
        meta = _get_or_create_project_meta(session)
        if name:
            meta.name = name
        if working_directory:
            meta.working_directory = working_directory


def _reconstruct_oo_design_from_neo4j(
    neo4j_session,
    component_id: int | None = None,
) -> dict:
    """Reconstruct OODesignSchema-compatible dict from Neo4j design nodes.

    Reads :Design nodes and their relationships from Neo4j and rebuilds
    the data structures expected by the skeleton generators.

    Args:
        neo4j_session: Active Neo4j session.
        component_id: Optional component ID to filter nodes.

    Returns:
        Dict matching OODesignSchema.model_dump() format.
    """
    repo = DesignRepository(neo4j_session)

    # Fetch design nodes, optionally filtered by component
    if component_id is not None:
        nodes = repo.find_nodes(component_id=component_id)
    else:
        nodes = repo.find_nodes()

    classes = []
    interfaces = []
    enums = []
    all_modules = set()

    # Track node qualified names for relationship resolution
    qname_to_node = {n.qualified_name: n for n in nodes}

    for node in nodes:
        # Skip dependency-reference stubs
        if node.source_type == "dependency":
            continue

        kind = node.kind.lower() if node.kind else ""

        if kind == "class" or kind == "struct":
            cls_dict = _node_to_class_dict(node, neo4j_session, qname_to_node)
            classes.append(cls_dict)
            if cls_dict.get("module"):
                all_modules.add(cls_dict["module"])

        elif kind == "interface":
            iface_dict = _node_to_interface_dict(node, neo4j_session, qname_to_node)
            interfaces.append(iface_dict)
            if iface_dict.get("module"):
                all_modules.add(iface_dict["module"])

        elif kind == "enum" or kind.startswith("enum"):
            enum_dict = _node_to_enum_dict(node)
            enums.append(enum_dict)
            if enum_dict.get("module"):
                all_modules.add(enum_dict["module"])

    # Read associations (triples) to connect inheritance and interface realization
    associations = _reconstruct_associations(neo4j_session, qname_to_node)

    return {
        "modules": sorted(all_modules),
        "classes": classes,
        "interfaces": interfaces,
        "enums": enums,
        "associations": associations,
    }


def _node_to_class_dict(node, neo4j_session, qname_to_node: dict) -> dict:
    """Convert a Design node of kind 'class' to a class dict."""
    # Extract module and simple name from qualified_name
    qname = node.qualified_name
    if "::" in qname:
        parts = qname.rsplit("::", 1)
        module = parts[0]
        name = parts[1]
    else:
        module = ""
        name = qname

    # Fetch composed members (attributes and methods)
    attributes = []
    methods = []
    inherits_from = []
    realizes_interfaces = []

    # Query COMPOSES relationships to get members
    result = neo4j_session.run(
        """
        MATCH (parent:Design {qualified_name: $qn})-[:COMPOSES]->(member:Design)
        RETURN member
        """,
        {"qn": qname},
    )
    for record in result:
        member = dict(record["member"])
        member_kind = member.get("kind", "").lower() if member.get("kind") else ""

        if member_kind in ("attribute", "field", "data_member", "variable"):
            attr_module = member.get("qualified_name", "")
            attr_name = member.get("name", "")
            if "::" in attr_module:
                attr_name = attr_module.rsplit("::", 1)[-1]
            attributes.append({
                "name": attr_name,
                "type_name": member.get("type_signature", "") or member.get("definition", ""),
                "visibility": member.get("visibility", "private"),
                "description": member.get("description", ""),
            })

        elif member_kind in ("method", "function", "member_function"):
            method_module = member.get("qualified_name", "")
            method_name = member.get("name", "")
            if "::" in method_module:
                method_name = method_module.rsplit("::", 1)[-1]

            # Parse parameters from argsstring
            params = _parse_params(member.get("argsstring", ""))
            ret_type = member.get("type_signature", "") or member.get("definition", "")
            # Clean up return type — extract just the type part
            if ret_type and "(" in ret_type:
                # e.g. "void (int, double)" -> just use the whole thing as return type
                pass

            methods.append({
                "name": method_name,
                "visibility": member.get("visibility", "public"),
                "description": member.get("description", ""),
                "parameters": params,
                "return_type": ret_type,
                "is_const": member.get("is_const", False),
                "is_static": member.get("is_static", False),
                "is_virtual": member.get("is_virtual", False),
                "is_abstract": member.get("is_abstract", False),
            })

    # Query INHERITS relationships
    inh_result = neo4j_session.run(
        """
        MATCH (child:Design {qualified_name: $qn})-[:INHERITS]->(parent:Design)
        RETURN parent.qualified_name AS qn
        """,
        {"qn": qname},
    )
    for record in inh_result:
        parent_qname = record["qn"]
        # Use bare name if in same module, qualified otherwise
        inherits_from.append(parent_qname)

    # Query REALIZES relationships
    real_result = neo4j_session.run(
        """
        MATCH (cls:Design {qualified_name: $qn})-[:REALIZES]->(iface:Design)
        RETURN iface.qualified_name AS qn
        """,
        {"qn": qname},
    )
    for record in real_result:
        realizes_interfaces.append(record["qn"])

    return {
        "name": name,
        "module": module,
        "specialization": node.specialization or "",
        "description": node.description or "",
        "is_intercomponent": node.is_intercomponent,
        "attributes": attributes,
        "methods": methods,
        "inherits_from": inherits_from,
        "realizes_interfaces": realizes_interfaces,
        "requirement_ids": [],
    }


def _node_to_interface_dict(node, neo4j_session, qname_to_node: dict) -> dict:
    """Convert a Design node of kind 'interface' to an interface dict."""
    qname = node.qualified_name
    if "::" in qname:
        parts = qname.rsplit("::", 1)
        module = parts[0]
        name = parts[1]
    else:
        module = ""
        name = qname

    # Fetch interface methods via COMPOSES
    methods = []
    result = neo4j_session.run(
        """
        MATCH (parent:Design {qualified_name: $qn})-[:COMPOSES]->(member:Design)
        WHERE member.kind IN ['method', 'function', 'member_function']
        RETURN member
        """,
        {"qn": qname},
    )
    for record in result:
        member = dict(record["member"])
        method_module = member.get("qualified_name", "")
        method_name = member.get("name", "")
        if "::" in method_module:
            method_name = method_module.rsplit("::", 1)[-1]

        methods.append({
            "name": method_name,
            "visibility": member.get("visibility", "public"),
            "description": member.get("description", ""),
            "parameters": _parse_params(member.get("argsstring", "")),
            "return_type": member.get("type_signature", "") or member.get("definition", ""),
        })

    return {
        "name": name,
        "module": module,
        "specialization": node.specialization or "",
        "description": node.description or "",
        "is_intercomponent": node.is_intercomponent,
        "methods": methods,
    }


def _node_to_enum_dict(node) -> dict:
    """Convert a Design node of kind 'enum' to an enum dict."""
    qname = node.qualified_name
    if "::" in qname:
        parts = qname.rsplit("::", 1)
        module = parts[0]
        name = parts[1]
    else:
        module = ""
        name = qname

    # Enum values may be stored as COMPOSES members
    # For now, we can't easily get enum values from Neo4j design nodes
    # since they're typically just stored as a comma-separated description
    # The skeleton generator will add a TODO if values are empty
    values = []
    if node.description:
        # Try to parse "A, B, C" from description
        desc = node.description.strip()
        if desc and not desc.startswith((".", "The", "An", "Enum", "Represents")):
            # Might be a value list
            parts = [v.strip() for v in desc.split(",")]
            if all(p.isidentifier() for p in parts if p):
                values = parts

    return {
        "name": name,
        "module": module,
        "description": node.description or "",
        "values": values,
    }


def _parse_params(argsstring: str) -> list[dict]:
    """Parse C++ parameter types from an argsstring.

    Handles formats like "(int x, const std::string& y)" or just "int x, double y".
    Returns a list of dicts with 'name' and 'type_name' keys.
    """
    if not argsstring:
        return []

    # Remove outer parentheses if present
    s = argsstring.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()

    if not s:
        return []

    params = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue

        # Handle "const type& name" or "type name"
        tokens = part.split()
        if len(tokens) >= 2:
            # Last token is the name, everything before is the type
            name = tokens[-1].lstrip("&*")
            type_str = " ".join(tokens[:-1]).rstrip("&*").strip()
            # Remove default values
            if "=" in name:
                name = name.split("=")[0].strip()
            if "=" in type_str:
                type_str = type_str.split("=")[0].strip()
            params.append({"name": name, "type_name": type_str})
        elif len(tokens) == 1:
            # Just a type name, no parameter name
            params.append({"name": "", "type_name": tokens[0]})

    return params


def _reconstruct_associations(neo4j_session, qname_to_node: dict) -> list[dict]:
    """Reconstruct association dicts from Neo4j triples.

    Maps relationship types back to OODesignSchema association kinds.
    """
    associations = []

    # The predicate names defined in the ontology
    kind_mapping = {
        "ASSOCIATES": "associates",
        "AGGREGATES": "aggregates",
        "COMPOSES": "composes",
        "DEPENDS_ON": "depends_on",
        "REFERENCES": "references",
        "RETURNS": "returns",
        "INVOKES": "invokes",
        "INHERITS": "inherits_from",
        "REALIZES": "realizes",
        "TYPE_ARGUMENT": "type_argument",
        "TEMPLATE_PARAM": "template_param",
    }

    result = neo4j_session.run(
        """
        MATCH (s:Design)-[r]->(o:Design)
        WHERE type(r) <> 'COMPOSES' AND type(r) <> 'IMPLEMENTED_BY' AND type(r) <> 'TRACES_TO'
        RETURN s.qualified_name AS from_qn, type(r) AS rel_type,
               o.qualified_name AS to_qn, r.mechanism AS mechanism
        """
    )

    for record in result:
        rel_type = record["rel_type"]
        kind = kind_mapping.get(rel_type)
        if not kind:
            # Skip relationship types that don't map to associations
            continue

        # Skip inheritance and realization — they're captured in the class dict
        if kind in ("inherits_from", "realizes"):
            continue

        associations.append({
            "from_class": record["from_qn"],
            "to_class": record["to_qn"],
            "kind": kind,
            "description": "",
            "mechanism": record.get("mechanism", "") or "",
            "requirement_ids": [],
        })

    return associations


def step_generate_skeleton(args: argparse.Namespace):
    """Run the skeleton generation pipeline step."""
    print("=" * 60)
    print("STEP 5: Generate skeleton source files")
    print("=" * 60)

    # 0. Persist CLI-provided name/working-directory to DB
    if args.name or args.working_directory:
        _set_project_meta(name=args.name or "", working_directory=args.working_directory or "")

    # 1. Read project metadata
    meta = _get_project_meta()
    project_name = meta["name"]
    working_directory = meta["working_directory"]

    if not project_name:
        print("  ERROR: Project name not set.")
        print("  Use --name <project-name> or set it in the dashboard.\n")
        return None
    if not working_directory:
        print("  ERROR: Working directory not set.")
        print("  Use --working-directory <path> or set it in the dashboard.\n")
        return None

    # Determine the language
    language = args.language

    # Check if there's a language set on the component
    with get_session() as session:
        components = session.query(Component).order_by(Component.id).all()
        if components:
            comp = components[0]
            if comp.language_id:
                lang = session.query(Language).filter_by(id=comp.language_id).first()
                if lang:
                    language = lang.name.lower()
                    # Normalize
                    if "c++" in language or "cpp" in language:
                        language = "cpp"
                    elif "python" in language:
                        language = "python"

    print(f"  Project:  {project_name}")
    print(f"  Output:   {working_directory}")
    print(f"  Language:  {language}")

    # 2. Determine the project directory
    project_dir = os.path.join(working_directory, project_name)
    if not os.path.isdir(project_dir):
        print(f"  ERROR: Project directory not found: {project_dir}")
        print(f"  Run 04_scaffold_project.py first to create the project structure.\n")
        return None

    # 3. Read components
    libraries = []
    with get_session() as session:
        components = session.query(Component).order_by(Component.id).all()
        for comp in components:
            if comp.name == "Environment" or comp.name.startswith("Environment:"):
                continue
            lib = {"name": comp.name, "namespace": comp.namespace or ""}
            libraries.append(lib)

    if not libraries:
        print("  WARNING: No components found in the database.")
        print("  Generating skeleton for a single 'core' library.\n")
        libraries = [{"name": "core", "namespace": ""}]

    lib_names = ", ".join(lib["name"] for lib in libraries)
    print(f"  Libraries: {lib_names}")

    # 4. Reconstruct OO design from Neo4j
    print("\n  Reconstructing OO design from Neo4j...")

    with get_neo4j().session() as ns:
        # Generate skeleton per component
        all_results = []
        total_classes = 0
        total_interfaces = 0
        total_enums = 0

        for comp in components:
            if comp.name == "Environment" or comp.name.startswith("Environment:"):
                continue

            comp_id = comp.id
            comp_namespace = comp.namespace or comp.name.lower().replace(" ", "_")
            comp_source_dir = os.path.join(
                project_dir,
                project_name,  # library parent dir
                comp_namespace,
                "src",
            )

            print(f"\n  Component: {comp.name} (namespace: {comp_namespace})")
            print(f"  Source dir: {comp_source_dir}")

            oo_design = _reconstruct_oo_design_from_neo4j(ns, component_id=comp_id)

            n_classes = len(oo_design["classes"])
            n_interfaces = len(oo_design["interfaces"])
            n_enums = len(oo_design["enums"])
            total_classes += n_classes
            total_interfaces += n_interfaces
            total_enums += n_enums

            print(f"    {n_classes} classes, {n_interfaces} interfaces, {n_enums} enums")

            if n_classes == 0 and n_interfaces == 0 and n_enums == 0:
                print(f"    Skipping {comp.name} — no design nodes found")
                continue

            # 5. Generate skeleton files
            results = generate_skeleton(
                oo_design=oo_design,
                workspace_dir=comp_source_dir,
                source_root=".",
                language=language,
                project_name=comp_namespace,
            )

            for result in results:
                print(f"    Wrote: {result.file_path} ({len(result.classes_generated)} items)")

            all_results.extend(results)

        # Also try without component filter for cross-component items
        if not components or total_classes == 0:
            print("\n  No component-filtered design found. Trying all design nodes...")
            oo_design = _reconstruct_oo_design_from_neo4j(ns)

            if oo_design["classes"] or oo_design["interfaces"] or oo_design["enums"]:
                # Use first library's source directory
                fallback_dir = os.path.join(
                    project_dir,
                    project_name,
                    libraries[0]["namespace"] or libraries[0]["name"].lower().replace(" ", "_"),
                    "src",
                )

                results = generate_skeleton(
                    oo_design=oo_design,
                    workspace_dir=fallback_dir,
                    source_root=".",
                    language=language,
                    project_name=libraries[0]["namespace"] or libraries[0]["name"].lower().replace(" ", "_"),
                )

                for result in results:
                    print(f"    Wrote: {result.file_path} ({len(result.classes_generated)} items)")

                all_results.extend(results)

    # 6. Print summary
    print("\n" + "=" * 60)
    print("SKELETON GENERATION COMPLETE")
    print("=" * 60)
    print(f"\n  Total files generated: {len(all_results)}")
    print(f"  Total classes: {total_classes}")
    print(f"  Total interfaces: {total_interfaces}")
    print(f"  Total enums: {total_enums}")

    # 7. Optionally verify build
    if not args.skip_build:
        print("\n  Verifying build...")
        build_ok = _verify_build(project_dir, args)
        if build_ok:
            print("  Build verification: PASSED ✓")
        else:
            print("  Build verification: FAILED ✗")
            print("  Run with --skip-build to skip this step.")
    else:
        print("\n  Build verification: SKIPPED (--skip-build)")

    print()
    return project_dir


def _verify_build(project_dir: str, args: argparse.Namespace) -> bool:
    """Attempt to build the project to verify skeleton compiles.

    Returns True if the build succeeds, False otherwise.
    """
    import subprocess

    # Check if CMakeLists.txt exists
    cmake_file = os.path.join(project_dir, "CMakeLists.txt")
    if not os.path.isfile(cmake_file):
        print(f"    No CMakeLists.txt found at {cmake_file}")
        print("    Skipping build verification (project may not be scaffolded yet)")
        return True

    # Try to build using conan + cmake
    build_dir = os.path.join(project_dir, "build")

    try:
        # Step 1: conan install
        print("    Running conan install...")
        result = subprocess.run(
            ["conan", "install", ".", "--build=missing", "-s", "build_type=Debug"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"    Conan install failed: {result.stderr[:500]}")
            return False

        # Step 2: cmake configure
        print("    Running cmake configure...")
        os.makedirs(build_dir, exist_ok=True)
        result = subprocess.run(
            ["cmake", "..", "-DCMAKE_BUILD_TYPE=Debug"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"    CMake configure failed: {result.stderr[:500]}")
            return False

        # Step 3: cmake build
        print("    Running cmake build...")
        result = subprocess.run(
            ["cmake", "--build", ".", "--config", "Debug"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"    CMake build failed: {result.stderr[:500]}")
            return False

        return True

    except FileNotFoundError as e:
        print(f"    Build tool not found: {e}")
        print("    Skipping build verification")
        return True
    except subprocess.TimeoutExpired:
        print("    Build timed out")
        return False
    except Exception as e:
        print(f"    Build verification error: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate skeleton source files from design data.",
    )
    parser.add_argument(
        "--name", default="",
        help="Project name (kebab-case). Persisted to DB.",
    )
    parser.add_argument(
        "--working-directory", default="",
        help="Directory containing the project folder. Persisted to DB.",
    )
    parser.add_argument(
        "--language", default="cpp",
        choices=["cpp", "python"],
        help="Target language for skeleton generation (default: cpp)",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip build verification step",
    )
    parser.add_argument(
        "--model", default="",
        help="LLM model override (not used in skeleton generation, kept for consistency)",
    )

    args = parser.parse_args()

    log_file = _configure_logging()
    print(f"Pipeline log: {log_file}")

    init_neo4j()
    try:
        init_db()
        step_generate_skeleton(args)
    except Exception as e:
        logging.getLogger(__name__).exception("Skeleton generation failed: %s", e)
        print(f"\nSkeleton generation failed: {e}")
        print(f"Check {log_file} for details.")
        raise
    finally:
        close_neo4j()