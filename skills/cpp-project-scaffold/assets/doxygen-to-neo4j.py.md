# scripts/doxygen_to_neo4j.py Template

This script parses Doxygen XML output and creates a Neo4j property graph.
Requires the `neo4j` Python package. No variables to substitute — copy as-is.

```python
#!/usr/bin/env python3
"""
Doxygen XML to Neo4j Graph Database Ingester

Parses Doxygen XML output and creates a property graph in Neo4j for
codebase navigation and call graph traversal.

Usage:
    python doxygen_to_neo4j.py <xml_dir> [options]

Example:
    python doxygen_to_neo4j.py build/Debug/docs/xml
    python doxygen_to_neo4j.py build/Debug/docs/xml --uri bolt://localhost:7687
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase


# ---------------------------------------------------------------------------
# Neo4j schema: constraints and indexes
# ---------------------------------------------------------------------------

SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
    "CREATE CONSTRAINT class_qualified IF NOT EXISTS FOR (c:Class) REQUIRE c.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT function_qualified IF NOT EXISTS FOR (fn:Function) REQUIRE fn.qualified_name IS UNIQUE",
    "CREATE INDEX file_relative IF NOT EXISTS FOR (f:File) ON (f.relative_path)",
    "CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
    "CREATE INDEX function_name IF NOT EXISTS FOR (fn:Function) ON (fn.name)",
]


def setup_schema(driver):
    """Create constraints and indexes."""
    with driver.session() as session:
        for stmt in SCHEMA_STATEMENTS:
            try:
                session.run(stmt)
            except Exception:
                pass  # Constraint may already exist


def get_text(element, tag: str) -> str:
    """Extract text content from a child element."""
    child = element.find(tag)
    if child is None:
        return ""
    return "".join(child.itertext()).strip()


def get_brief(element) -> str:
    return get_text(element, "briefdescription")


def get_detailed(element) -> str:
    return get_text(element, "detaileddescription")


def get_location(element) -> tuple:
    loc = element.find("location")
    if loc is not None:
        return loc.get("file", ""), int(loc.get("line", 0))
    return "", 0


def make_relative(path: str, project_root: str) -> str:
    if not path or not project_root:
        return path
    try:
        return str(Path(path).relative_to(project_root))
    except ValueError:
        return path


def merge_file(tx, path: str, relative_path: str, language: str, kind: str):
    tx.run(
        """MERGE (f:File {path: $path})
           SET f.relative_path = $relative_path, f.language = $language, f.kind = $kind""",
        path=path, relative_path=relative_path, language=language, kind=kind
    )


def merge_class(tx, name: str, qualified_name: str, kind: str, file_path: str,
                line: int, brief: str, detailed: str, is_abstract: bool):
    tx.run(
        """MERGE (c:Class {qualified_name: $qualified_name})
           SET c.name = $name, c.kind = $kind, c.line_number = $line,
               c.brief = $brief, c.detailed = $detailed, c.is_abstract = $is_abstract
           WITH c
           OPTIONAL MATCH (f:File {path: $file_path})
           FOREACH (_ IN CASE WHEN f IS NOT NULL THEN [1] ELSE [] END |
             MERGE (f)-[:CONTAINS]->(c))""",
        qualified_name=qualified_name, name=name, kind=kind, line=line,
        brief=brief, detailed=detailed, is_abstract=is_abstract, file_path=file_path
    )


def merge_function(tx, name: str, qualified_name: str, return_type: str,
                   class_qn: Optional[str], file_path: str, line: int,
                   brief: str, detailed: str, access: str,
                   is_static: bool, is_const: bool, is_virtual: bool):
    tx.run(
        """MERGE (fn:Function {qualified_name: $qualified_name})
           SET fn.name = $name, fn.return_type = $return_type,
               fn.line_number = $line, fn.brief = $brief, fn.detailed = $detailed,
               fn.access = $access, fn.is_static = $is_static,
               fn.is_const = $is_const, fn.is_virtual = $is_virtual
           WITH fn
           OPTIONAL MATCH (f:File {path: $file_path})
           FOREACH (_ IN CASE WHEN f IS NOT NULL THEN [1] ELSE [] END |
             MERGE (f)-[:CONTAINS]->(fn))
           WITH fn
           OPTIONAL MATCH (c:Class {qualified_name: $class_qn})
           FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
             MERGE (c)-[:HAS_METHOD]->(fn))""",
        qualified_name=qualified_name, name=name, return_type=return_type,
        line=line, brief=brief, detailed=detailed, access=access,
        is_static=is_static, is_const=is_const, is_virtual=is_virtual,
        file_path=file_path, class_qn=class_qn or ""
    )


def add_inheritance(tx, derived_qn: str, base_name: str, access: str):
    tx.run(
        """MATCH (d:Class {qualified_name: $derived_qn})
           MERGE (b:Class {qualified_name: $base_name})
           MERGE (d)-[:INHERITS {access: $access}]->(b)""",
        derived_qn=derived_qn, base_name=base_name, access=access
    )


def add_include(tx, source_path: str, included_path: str, is_local: bool):
    tx.run(
        """MATCH (s:File {path: $source_path})
           MERGE (t:File {path: $included_path})
           MERGE (s)-[:INCLUDES {is_local: $is_local}]->(t)""",
        source_path=source_path, included_path=included_path, is_local=is_local
    )


def add_call(tx, caller_qn: str, callee_name: str):
    tx.run(
        """MATCH (caller:Function {qualified_name: $caller_qn})
           MERGE (callee:Function {qualified_name: $callee_name})
           MERGE (caller)-[:CALLS]->(callee)""",
        caller_qn=caller_qn, callee_name=callee_name
    )


def process_compound(driver, xml_file: Path, project_root: str) -> None:
    """Process a Doxygen compound XML file into Neo4j."""
    try:
        tree = ET.parse(xml_file)
    except ET.ParseError:
        return

    root = tree.getroot()

    with driver.session() as session:
        for compounddef in root.findall("compounddef"):
            kind = compounddef.get("kind", "")
            compound_name = get_text(compounddef, "compoundname")

            if kind == "file":
                file_path = ""
                loc = compounddef.find("location")
                if loc is not None:
                    file_path = loc.get("file", "")

                if file_path:
                    relative = make_relative(file_path, project_root)
                    language = "cpp" if file_path.endswith((".cpp", ".hpp", ".h")) else "other"
                    fkind = "header" if file_path.endswith((".hpp", ".h")) else "source"
                    session.execute_write(merge_file, file_path, relative, language, fkind)

                    for inc in compounddef.findall("includes"):
                        included = inc.text or ""
                        is_local = inc.get("local") == "yes"
                        if included:
                            session.execute_write(add_include, file_path, included, is_local)

                # File-level functions
                for section in compounddef.findall("sectiondef"):
                    for memberdef in section.findall("memberdef"):
                        if memberdef.get("kind") == "function":
                            process_function(session, memberdef, None, file_path,
                                            compound_name, project_root)

            elif kind in ("class", "struct", "enum", "union"):
                file_path, line = get_location(compounddef)

                if file_path:
                    relative = make_relative(file_path, project_root)
                    language = "cpp" if file_path.endswith((".cpp", ".hpp", ".h")) else "other"
                    fkind = "header" if file_path.endswith((".hpp", ".h")) else "source"
                    session.execute_write(merge_file, file_path, relative, language, fkind)

                is_abstract = any(
                    m.get("virt") == "pure-virtual"
                    for s in compounddef.findall("sectiondef")
                    for m in s.findall("memberdef")
                )

                session.execute_write(
                    merge_class, compound_name.split("::")[-1], compound_name,
                    kind, file_path, line, get_brief(compounddef),
                    get_detailed(compounddef), is_abstract
                )

                for base in compounddef.findall("basecompoundref"):
                    base_name = base.text or ""
                    access = base.get("prot", "public")
                    if base_name:
                        session.execute_write(add_inheritance, compound_name, base_name, access)

                for section in compounddef.findall("sectiondef"):
                    for memberdef in section.findall("memberdef"):
                        if memberdef.get("kind") == "function":
                            process_function(session, memberdef, compound_name,
                                            file_path, compound_name, project_root)


def process_function(session, memberdef, class_qn: Optional[str],
                     file_path: str, scope: str, project_root: str):
    """Process a function memberdef into Neo4j."""
    name = get_text(memberdef, "name")
    if not name:
        return

    member_file, member_line = get_location(memberdef)
    if not member_file:
        member_file = file_path

    if member_file:
        relative = make_relative(member_file, project_root)
        language = "cpp" if member_file.endswith((".cpp", ".hpp", ".h")) else "other"
        fkind = "header" if member_file.endswith((".hpp", ".h")) else "source"
        session.execute_write(merge_file, member_file, relative, language, fkind)

    qualified_name = f"{scope}::{name}" if scope else name
    return_type = get_text(memberdef, "type")
    access = memberdef.get("prot", "public")
    is_static = memberdef.get("static") == "yes"
    is_const = memberdef.get("const") == "yes"
    is_virtual = memberdef.get("virt") in ("virtual", "pure-virtual")

    session.execute_write(
        merge_function, name, qualified_name, return_type, class_qn,
        member_file, member_line, get_brief(memberdef), get_detailed(memberdef),
        access, is_static, is_const, is_virtual
    )

    for ref in memberdef.findall("references"):
        callee = ref.text or ""
        if callee:
            session.execute_write(add_call, qualified_name, callee)


def main():
    parser = argparse.ArgumentParser(description="Ingest Doxygen XML into Neo4j")
    parser.add_argument("xml_dir", help="Path to Doxygen XML output directory")
    parser.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j username")
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", "password"),
                        help="Neo4j password (or set NEO4J_PASSWORD env var)")
    parser.add_argument("--database", default="neo4j", help="Neo4j database name")
    parser.add_argument("--project-root", default=".", help="Project root for relative paths")
    parser.add_argument("--clear", action="store_true", help="Clear existing data first")
    args = parser.parse_args()

    xml_dir = Path(args.xml_dir)
    if not xml_dir.exists():
        print(f"Error: XML directory not found: {xml_dir}", file=sys.stderr)
        sys.exit(1)

    project_root = str(Path(args.project_root).resolve())

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))

    if args.clear:
        with driver.session(database=args.database) as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("Cleared existing data")

    setup_schema(driver)

    xml_files = sorted(xml_dir.glob("*.xml"))
    print(f"Processing {len(xml_files)} XML files...")

    for i, xml_file in enumerate(xml_files):
        if xml_file.name == "index.xml":
            continue
        process_compound(driver, xml_file, project_root)
        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(xml_files)} files...")

    # Print statistics
    with driver.session(database=args.database) as session:
        for label in ["File", "Class", "Function"]:
            count = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
            print(f"  {label}: {count}")

        for rel_type in ["CONTAINS", "CALLS", "INCLUDES", "INHERITS", "HAS_METHOD"]:
            count = session.run(
                f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS c"
            ).single()["c"]
            print(f"  {rel_type}: {count}")

    driver.close()
    print("Neo4j ingestion complete")


if __name__ == "__main__":
    main()
```
