#!/usr/bin/env python3
"""Example: scaffold a C++ project using the LLM tool loop.

Drives a local LLM (via the configured LLM_BACKEND) to create a complete
C++ project skeleton by writing files through sandboxed terminal tools.

Usage
-----
Basic::

    python examples/scaffold_cpp_project.py my-engine core physics

With options::

    python examples/scaffold_cpp_project.py my-engine core physics \\
        --std 23 \\
        --dep eigen/3.4.0 --dep spdlog/1.14.1 \\
        --header-only physics \\
        --lib-dep physics:core \\
        --lib-ext-dep physics:eigen/3.4.0 \\
        --output /tmp/projects \\
        --log-dir logs/scaffold

Environment
-----------
Configure the LLM backend before running::

    export LLM_BACKEND=openai                              # or anthropic, gemini
    export LLM_BASE_URL=http://10.0.0.17:8001/v1
    export LLM_MODEL=unsloth/Qwen3.5-9B-GGUF:Q4_K_M
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.ticketing_agent.design.scaffold_project import scaffold_project


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a C++ project using an LLM agent with terminal tools.",
    )
    parser.add_argument(
        "project_name",
        help="Project name in kebab-case (e.g. my-engine)",
    )
    parser.add_argument(
        "libraries",
        nargs="+",
        help="Library names to create (e.g. core physics rendering)",
    )

    # Project-level options
    parser.add_argument(
        "--std", type=int, default=20, choices=[20, 23, 26],
        help="C++ standard version (default: 20)",
    )
    parser.add_argument(
        "--dep", action="append", default=[],
        help="Additional Conan dependency (e.g. eigen/3.4.0). Repeatable.",
    )

    # Per-library options
    parser.add_argument(
        "--header-only", action="append", default=[],
        help="Mark a library as header-only/INTERFACE (e.g. --header-only utils). Repeatable.",
    )
    parser.add_argument(
        "--lib-dep", action="append", default=[],
        help="Inter-library dependency as lib:depends_on (e.g. --lib-dep physics:core). Repeatable.",
    )
    parser.add_argument(
        "--lib-ext-dep", action="append", default=[],
        help="Per-library external dep as lib:pkg (e.g. --lib-ext-dep physics:eigen/3.4.0). Repeatable.",
    )

    # Paths
    parser.add_argument(
        "--skill-dir", default=str(_PROJECT_ROOT / "skills" / "cpp-project-scaffold"),
        help="Path to the skill directory (default: skills/cpp-project-scaffold)",
    )
    parser.add_argument(
        "--output", "-o", default=".",
        help="Directory where the project folder will be created (default: cwd)",
    )
    parser.add_argument(
        "--log-dir", default=str(_PROJECT_ROOT / "logs"),
        help="Directory for prompt conversation logs (default: logs/)",
    )

    # LLM options
    parser.add_argument(
        "--model",
        default="",
        help="LLM model override (default: LLM_MODEL env var)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=4096,
        help="Max tokens per LLM turn (default: 4096)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=50,
        help="Max tool loop iterations (default: 50)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def build_libraries(args: argparse.Namespace) -> list[dict]:
    """Build the libraries list from CLI arguments."""
    # Parse per-library dependencies
    lib_deps: dict[str, list[str]] = {}
    for entry in args.lib_dep:
        lib, dep = entry.split(":", 1)
        lib_deps.setdefault(lib, []).append(dep)

    # Parse per-library external dependencies
    lib_ext_deps: dict[str, list[str]] = {}
    for entry in args.lib_ext_dep:
        lib, dep = entry.split(":", 1)
        lib_ext_deps.setdefault(lib, []).append(dep)

    header_only = set(args.header_only)

    libraries = []
    for name in args.libraries:
        lib = {"name": name}
        if name in header_only:
            lib["header_only"] = True
        if name in lib_deps:
            lib["depends_on"] = lib_deps[name]
        if name in lib_ext_deps:
            lib["external_deps"] = lib_ext_deps[name]
        libraries.append(lib)

    return libraries


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    libraries = build_libraries(args)

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    prompt_log = str(log_dir / "scaffold.md")

    print(f"Project:    {args.project_name}")
    print(f"Libraries:  {', '.join(lib['name'] for lib in libraries)}")
    print(f"C++ std:    C++{args.std}")
    print(f"Output:     {output_dir}")
    print(f"Skill dir:  {args.skill_dir}")
    if args.dep:
        print(f"Extra deps: {', '.join(args.dep)}")
    print()

    result = scaffold_project(
        skill_dir=args.skill_dir,
        project_name=args.project_name,
        libraries=libraries,
        working_directory=str(output_dir),
        extra_dependencies=args.dep or None,
        cpp_standard=args.std,
        model=args.model,
        max_tokens=args.max_tokens,
        max_turns=args.max_turns,
        prompt_log_file=prompt_log,
    )

    print()
    print("=" * 60)
    print("SCAFFOLD COMPLETE")
    print("=" * 60)
    print()
    print(result.get("summary", "(no summary)"))
    print()

    files = result.get("files_modified", [])
    if files:
        print(f"Files ({len(files)}):")
        for f in files:
            print(f"  {f}")

    build_ok = result.get("build_success")
    if build_ok is not None:
        status = "PASSED" if build_ok else "FAILED"
        print(f"\nBuild: {status}")


if __name__ == "__main__":
    main()
