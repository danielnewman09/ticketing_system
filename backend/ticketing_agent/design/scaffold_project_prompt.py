"""User message builder for the C++ project scaffold skill."""


def build_user_message(
    project_name: str,
    libraries: list[dict],
    extra_dependencies: list[str] | None = None,
    cpp_standard: int = 20,
) -> str:
    """Build the user message describing the project to scaffold.

    Args:
        project_name: Kebab-case project name (e.g. "my-engine").
        libraries: List of dicts, each with:
            - name: Library name (e.g. "core")
            - header_only: bool (default False)
            - depends_on: list of other library names (default [])
            - external_deps: list of Conan package refs (default [])
        extra_dependencies: Additional Conan dependencies for the whole project.
        cpp_standard: C++ standard version (20, 23, or 26).
    """
    lines = [
        "Scaffold a C++ project with the following parameters:",
        "",
        f"**Project name:** `{project_name}`",
        f"**C++ standard:** C++{cpp_standard}",
    ]

    if extra_dependencies:
        deps_str = ", ".join(f"`{d}`" for d in extra_dependencies)
        lines.append(f"**Additional Conan dependencies:** {deps_str}")

    lines.append("")
    lines.append("**Libraries:**")
    lines.append("")

    for lib in libraries:
        name = lib["name"]
        kind = "header-only (INTERFACE)" if lib.get("header_only") else "compiled"
        lines.append(f"- **{name}** ({kind})")

        deps = lib.get("depends_on", [])
        if deps:
            lines.append(f"  - Depends on: {', '.join(deps)}")

        ext = lib.get("external_deps", [])
        if ext:
            lines.append(f"  - External dependencies: {', '.join(ext)}")

    lines.append("")
    lines.append(
        f"**Library parent directory:** `{project_name}/` — all libraries go inside "
        f"`{project_name}/{project_name}/`, NOT directly in the project root."
    )
    lines.append("")
    lines.append(
        "Create ALL project files.  "
        "Call write_complete when all files have been generated."
    )

    return "\n".join(lines)
