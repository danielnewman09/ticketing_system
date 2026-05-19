"""
Agent: generate empty class/method/attribute stubs from OO design.

Takes a OODesignSchema and produces a skeleton project structure with
one source file per module namespace. Each file contains class definitions
with method signatures and `pass` bodies.

Usage:
    from backend.ticketing_agent.generate_skeleton import generate_skeleton

    results = generate_skeleton(oo_design, workspace_dir="/tmp/project")
"""

import logging
import os
from pathlib import Path

from backend.ticketing_agent.skeleton_templates.python import (
    SkeletonResult,
    generate_skeleton_from_design,
)

log = logging.getLogger("agents.generate_skeleton")


def generate_skeleton(
    oo_design: dict | object,
    workspace_dir: str = "",
    source_root: str = "src",
) -> list[SkeletonResult]:
    """Generate empty skeleton from the OO design.

    Args:
        oo_design: OODesignSchema instance or dict (from model_dump()).
        workspace_dir: Root directory where files will be rooted.
        source_root: Name of the source directory (default 'src').

    Returns:
        List of SkeletonResult with file paths and content.
    """
    # Convert to dict if it's a Pydantic model
    if hasattr(oo_design, "model_dump"):
        oo_design = oo_design.model_dump()

    results = generate_skeleton_from_design(
        oo_design, workspace_dir=workspace_dir, source_root=source_root,
    )

    # Write to disk
    for result in results:
        full_path = Path(workspace_dir) / result.file_path if workspace_dir else Path(result.file_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(result.content)
        log.info("Wrote skeleton: %s (%d classes)", full_path, len(result.classes_generated))

    return results


def write_init_files(
    results: list[SkeletonResult],
    workspace_dir: str = "",
) -> list[str]:
    """Write __init__.py files for all packages in the skeleton.

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
            full_path = Path(workspace_dir) / os.path.dirname(file_path) / "__init__.py" if workspace_dir else Path("__init__.py")
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
            all_classes.extend([
                {"name": c} for c in r.classes_generated
            ])
        module_name = os.path.basename(pkg_path)
        init_content = generate_init_py(all_classes, module_name)

        full_path = Path(workspace_dir) / pkg_path / "__init__.py" if workspace_dir else Path(pkg_path) / "__init__.py"
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(init_content)
        written.append(str(full_path))

    return written
