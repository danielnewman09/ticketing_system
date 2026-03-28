#!/usr/bin/env python3
"""Example: add a Conan dependency to a C++ project using the LLM tool loop.

Drives a local LLM to create the conan recipe, register it in the project,
wire it into the consuming library, and verify the build.

Usage
-----
Basic::

    python examples/add_conan_dependency.py nlopt https://github.com/stevengj/nlopt.git 2.10.0 core

With options::

    python examples/add_conan_dependency.py nlopt https://github.com/stevengj/nlopt.git 2.10.0 core \\
        --license LGPL-2.1 \\
        --author "Steven G. Johnson" \\
        --project-dir /path/to/my-engine \\
        --verbose

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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from agents.skill_runner import run_skill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add a Conan dependency to a C++ project using an LLM agent.",
    )
    parser.add_argument(
        "library_name",
        help="Library name (e.g. nlopt, sqlite3, spdlog)",
    )
    parser.add_argument(
        "source_url",
        help="Source URL — Git repo or download URL",
    )
    parser.add_argument(
        "version",
        help="Version or Git tag (e.g. 2.10.0, v3.45.0)",
    )
    parser.add_argument(
        "consuming_library",
        help="Project library that will use this dependency (e.g. core)",
    )

    # Optional metadata
    parser.add_argument("--license", default="", help="License identifier (e.g. MIT, LGPL-2.1)")
    parser.add_argument("--author", default="", help="Library author")
    parser.add_argument("--language", default="C++", choices=["C++", "C"], help="Source language (default: C++)")
    parser.add_argument("--description", default="", help="Short description of the library")
    parser.add_argument(
        "--cmake-var", action="append", default=[],
        help="CMake variable to set as KEY=VALUE (e.g. --cmake-var NLOPT_PYTHON=OFF). Repeatable.",
    )
    parser.add_argument(
        "--component", action="append", default=[],
        help="Library component/target name if multi-component. Repeatable.",
    )

    # Paths
    parser.add_argument(
        "--skill-dir", default=str(_PROJECT_ROOT / "skills" / "add-conan-dependency"),
        help="Path to the skill directory (default: skills/add-conan-dependency)",
    )
    parser.add_argument(
        "--project-dir", "-p", default=".",
        help="Path to the existing C++ project root (default: cwd)",
    )
    parser.add_argument(
        "--log-dir", default=str(_PROJECT_ROOT / "logs"),
        help="Directory for prompt conversation logs (default: logs/)",
    )

    # LLM options
    parser.add_argument("--model", default="", help="LLM model override")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens per turn (default: 4096)")
    parser.add_argument("--max-turns", type=int, default=50, help="Max tool loop iterations (default: 50)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    return parser.parse_args()


def build_user_message(args: argparse.Namespace) -> str:
    """Build the user message from CLI arguments."""
    lines = [
        f"Add `{args.library_name}` as a locally-built Conan dependency.",
        "",
        f"**Library name:** `{args.library_name}`",
        f"**Source URL:** `{args.source_url}`",
        f"**Version/tag:** `{args.version}`",
        f"**Consuming library:** `{args.consuming_library}`",
        f"**Language:** {args.language}",
    ]

    if args.license:
        lines.append(f"**License:** {args.license}")
    if args.author:
        lines.append(f"**Author:** {args.author}")
    if args.description:
        lines.append(f"**Description:** {args.description}")

    if args.cmake_var:
        lines.append("")
        lines.append("**CMake variables to set:**")
        for var in args.cmake_var:
            lines.append(f"- `{var}`")

    if args.component:
        lines.append("")
        lines.append("**Components/targets:**")
        for comp in args.component:
            lines.append(f"- `{comp}`")

    lines.append("")
    lines.append(
        "Follow the skill instructions: research the library, create the conan recipe, "
        "register it, update VS Code tasks, wire into the consuming library, and verify "
        "the build.  Call task_complete when done."
    )

    return "\n".join(lines)


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"Error: project directory does not exist: {project_dir}", file=sys.stderr)
        sys.exit(1)

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    prompt_log = str(log_dir / f"add_dep_{args.library_name}.md")

    user_message = build_user_message(args)

    print(f"Library:    {args.library_name} {args.version}")
    print(f"Source:     {args.source_url}")
    print(f"Consumer:   {args.consuming_library}")
    print(f"Project:    {project_dir}")
    print(f"Skill dir:  {args.skill_dir}")
    print()

    result = run_skill(
        skill_dir=args.skill_dir,
        user_message=user_message,
        working_directory=str(project_dir),
        model=args.model,
        max_tokens=args.max_tokens,
        max_turns=args.max_turns,
        prompt_log_file=prompt_log,
    )

    print()
    print("=" * 60)
    print("DEPENDENCY ADDED")
    print("=" * 60)
    print()
    print(result.get("summary", "(no summary)"))
    print()

    files = result.get("files_modified", [])
    if files:
        print(f"Files modified ({len(files)}):")
        for f in files:
            print(f"  {f}")

    build_ok = result.get("build_success")
    if build_ok is not None:
        status = "PASSED" if build_ok else "FAILED"
        print(f"\nBuild: {status}")


if __name__ == "__main__":
    main()
