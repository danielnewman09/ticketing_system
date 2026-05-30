"""
Agent: generate empty class/method/attribute stubs from OO design.

Takes a OODesignSchema and produces a skeleton project structure with
one source file per module namespace. Supports both Python and C++ targets.

For Python: generates .py files with class definitions, method stubs,
and `pass` bodies.

For C++: generates .hpp/.cpp header/source pairs with class declarations,
method stubs returning default values, and TODO comments.

Usage:
    from backend.ticketing_agent.generate_skeleton import generate_skeleton

    # Python skeleton
    results = generate_skeleton(oo_design, workspace_dir="/tmp/project",
                                language="python")

    # C++ skeleton (generates .hpp/.cpp pairs)
    results = generate_skeleton(oo_design, workspace_dir="/tmp/project",
                                language="cpp", project_name="calculator")
"""

import logging
import os
from pathlib import Path

log = logging.getLogger("agents.generate_skeleton")


def generate_skeleton(
    oo_design: dict | object,
    workspace_dir: str = "",
    source_root: str = "src",
    language: str = "python",
    project_name: str = "",
) -> list:
    """Generate empty skeleton from the OO design.

    Args:
        oo_design: OODesignSchema instance or dict (from model_dump()).
        workspace_dir: Root directory where files will be rooted.
        source_root: Name of the source directory (default 'src').
            For C++ projects this is typically the library source directory
            inside the scaffolded project (e.g. 'calculation_engine/src').
        language: Target language — "python" or "cpp" (default "python").
        project_name: For C++ projects, the project name used to qualify
            namespaces (e.g. "calculator_engine").

    Returns:
        List of SkeletonResult with file paths and content.
    """
    # Convert to dict if it's a Pydantic model
    if hasattr(oo_design, "model_dump"):
        oo_design = oo_design.model_dump()

    if language == "python":
        from backend.ticketing_agent.skeleton_templates.python import (
            SkeletonResult,
            generate_skeleton_from_design,
        )

        results = generate_skeleton_from_design(
            oo_design,
            workspace_dir=workspace_dir,
            source_root=source_root,
        )
    elif language == "cpp":
        from backend.ticketing_agent.skeleton_templates.cpp import (
            SkeletonResult,
            generate_skeleton_from_design,
        )

        results = generate_skeleton_from_design(
            oo_design,
            workspace_dir=workspace_dir,
            source_root=source_root,
            project_name=project_name,
        )
    else:
        raise ValueError(f"Unsupported language: {language!r}. Use 'python' or 'cpp'.")

    # Write to disk
    for result in results:
        full_path = (
            Path(workspace_dir) / result.file_path if workspace_dir else Path(result.file_path)
        )
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(result.content)
        log.info("Wrote skeleton: %s (%d items)", full_path, len(result.classes_generated))

    return results


def write_init_files(
    results: list,
    workspace_dir: str = "",
) -> list[str]:
    """Write __init__.py files for all packages in a Python skeleton.

    Args:
        results: List of SkeletonResult from generate_skeleton.
        workspace_dir: Root directory.

    Returns:
        List of written __init__.py file paths.
    """
    from backend.ticketing_agent.skeleton_templates.python import (
        generate_init_py,
    )

    written = []
    # Determine package structure from file paths
    packages: dict[str, list[str]] = {}

    for result in results:
        file_path = result.file_path
        pkg_path = os.path.dirname(file_path)

        if pkg_path:
            packages.setdefault(pkg_path, []).append(result)
        else:
            # Top-level file, no package needed
            modules = os.path.splitext(os.path.basename(file_path))[0]
            init_content = generate_init_py(result.classes_generated, modules)
            full_path = (
                Path(workspace_dir) / os.path.dirname(file_path) / "__init__.py"
                if workspace_dir
                else Path("__init__.py")
            )
            if workspace_dir:
                Path(workspace_dir).mkdir(parents=True, exist_ok=True)
                # For top-level, the __init__ would be in src/
                top_level = os.path.dirname(file_path).split("/")[0] if "/" in file_path else "."
                full_path = Path(workspace_dir) / top_level / "__init__.py"
            written.append(str(full_path))
            full_path.write_text(init_content)

    for pkg_path, pkg_results in packages.items():
        # Generate __init__.py for this package
        all_classes = []
        for r in pkg_results:
            all_classes.extend([{"name": c} for c in r.classes_generated])
        module_name = os.path.basename(pkg_path)
        init_content = generate_init_py(all_classes, module_name)

        full_path = (
            Path(workspace_dir) / pkg_path / "__init__.py"
            if workspace_dir
            else Path(pkg_path) / "__init__.py"
        )
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(init_content)
        written.append(str(full_path))

    return written