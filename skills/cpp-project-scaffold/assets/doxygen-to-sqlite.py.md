# scripts/doxygen_to_sqlite.py Template

This script parses Doxygen XML output and creates a SQLite database for codebase navigation.
It is self-contained using only Python stdlib. No variables to substitute — copy as-is.

```python
#!/usr/bin/env python3
"""
Doxygen XML to SQLite Database Converter

Parses Doxygen XML output and creates a SQLite database for codebase navigation.
Enables fast code search, symbol lookup, and documentation queries.

Usage:
    python doxygen_to_sqlite.py <xml_dir> <output_db> [--project-root <path>]

Example:
    python doxygen_to_sqlite.py build/Debug/docs/xml build/Debug/docs/codebase.db
"""

import argparse
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the database schema for code indexing."""
    conn.executescript("""
        -- Files table: source files in the codebase
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            relative_path TEXT,
            language TEXT,
            kind TEXT DEFAULT 'source'
        );

        -- Classes table: classes, structs, enums
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            qualified_name TEXT,
            kind TEXT DEFAULT 'class',
            file_id INTEGER REFERENCES files(id),
            line_number INTEGER,
            brief TEXT,
            detailed TEXT,
            template_params TEXT,
            is_abstract INTEGER DEFAULT 0
        );

        -- Functions table: functions, methods
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            qualified_name TEXT,
            kind TEXT DEFAULT 'function',
            return_type TEXT,
            class_id INTEGER REFERENCES classes(id),
            file_id INTEGER REFERENCES files(id),
            line_number INTEGER,
            brief TEXT,
            detailed TEXT,
            is_static INTEGER DEFAULT 0,
            is_const INTEGER DEFAULT 0,
            is_virtual INTEGER DEFAULT 0,
            is_pure_virtual INTEGER DEFAULT 0,
            access TEXT DEFAULT 'public',
            template_params TEXT
        );

        -- Parameters table
        CREATE TABLE IF NOT EXISTS parameters (
            id INTEGER PRIMARY KEY,
            function_id INTEGER REFERENCES functions(id),
            name TEXT,
            type TEXT,
            default_value TEXT,
            position INTEGER
        );

        -- Includes table: #include relationships
        CREATE TABLE IF NOT EXISTS includes (
            id INTEGER PRIMARY KEY,
            source_file_id INTEGER REFERENCES files(id),
            included_path TEXT,
            is_local INTEGER DEFAULT 1
        );

        -- Inheritance table
        CREATE TABLE IF NOT EXISTS inheritance (
            id INTEGER PRIMARY KEY,
            derived_id INTEGER REFERENCES classes(id),
            base_name TEXT,
            access TEXT DEFAULT 'public',
            is_virtual INTEGER DEFAULT 0
        );

        -- Call graph table
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY,
            caller_id INTEGER REFERENCES functions(id),
            callee_name TEXT,
            callee_id INTEGER REFERENCES functions(id)
        );

        -- Members table: member variables
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            qualified_name TEXT,
            type TEXT,
            class_id INTEGER REFERENCES classes(id),
            file_id INTEGER REFERENCES files(id),
            line_number INTEGER,
            brief TEXT,
            access TEXT DEFAULT 'public',
            is_static INTEGER DEFAULT 0
        );

        -- Documentation table: standalone docs
        CREATE TABLE IF NOT EXISTS documentation (
            id INTEGER PRIMARY KEY,
            symbol_name TEXT,
            symbol_kind TEXT,
            brief TEXT,
            detailed TEXT,
            file_id INTEGER REFERENCES files(id),
            line_number INTEGER
        );

        -- FTS5 full-text search index
        CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
            name,
            qualified_name,
            kind,
            brief,
            detailed,
            file_path,
            content='',
            tokenize='porter'
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name);
        CREATE INDEX IF NOT EXISTS idx_classes_qualified ON classes(qualified_name);
        CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name);
        CREATE INDEX IF NOT EXISTS idx_functions_qualified ON functions(qualified_name);
        CREATE INDEX IF NOT EXISTS idx_functions_class ON functions(class_id);
        CREATE INDEX IF NOT EXISTS idx_members_class ON members(class_id);
        CREATE INDEX IF NOT EXISTS idx_files_path ON files(relative_path);
    """)


def get_text(element, tag: str) -> str:
    """Extract text content from a child element."""
    child = element.find(tag)
    if child is None:
        return ""
    # Handle mixed content (text with nested elements)
    return "".join(child.itertext()).strip()


def get_brief(element) -> str:
    """Extract brief description."""
    return get_text(element, "briefdescription")


def get_detailed(element) -> str:
    """Extract detailed description."""
    return get_text(element, "detaileddescription")


def get_location(element) -> tuple:
    """Extract file path and line number from location element."""
    loc = element.find("location")
    if loc is not None:
        return loc.get("file", ""), int(loc.get("line", 0))
    return "", 0


def make_relative(path: str, project_root: str) -> str:
    """Make a path relative to the project root."""
    if not path or not project_root:
        return path
    try:
        return str(Path(path).relative_to(project_root))
    except ValueError:
        return path


def get_or_create_file(conn: sqlite3.Connection, path: str, project_root: str,
                       file_cache: dict) -> Optional[int]:
    """Get or create a file record, returning its ID."""
    if not path:
        return None
    if path in file_cache:
        return file_cache[path]

    relative = make_relative(path, project_root)
    language = "cpp" if path.endswith((".cpp", ".hpp", ".h", ".cxx", ".cc")) else "other"
    kind = "header" if path.endswith((".hpp", ".h")) else "source"

    cursor = conn.execute(
        "INSERT OR IGNORE INTO files (path, relative_path, language, kind) VALUES (?, ?, ?, ?)",
        (path, relative, language, kind)
    )
    if cursor.lastrowid:
        file_cache[path] = cursor.lastrowid
        return cursor.lastrowid

    cursor = conn.execute("SELECT id FROM files WHERE path = ?", (path,))
    row = cursor.fetchone()
    if row:
        file_cache[path] = row[0]
        return row[0]
    return None


def process_compound(conn: sqlite3.Connection, xml_file: Path, project_root: str,
                     file_cache: dict, class_cache: dict) -> None:
    """Process a Doxygen compound XML file."""
    try:
        tree = ET.parse(xml_file)
    except ET.ParseError:
        return

    root = tree.getroot()

    for compounddef in root.findall("compounddef"):
        kind = compounddef.get("kind", "")
        compound_name = get_text(compounddef, "compoundname")

        if kind == "file":
            # Process file-level definitions
            file_path = ""
            loc = compounddef.find("location")
            if loc is not None:
                file_path = loc.get("file", "")

            file_id = get_or_create_file(conn, file_path, project_root, file_cache)

            # Process includes
            for inc in compounddef.findall("includes"):
                included = inc.text or ""
                is_local = 1 if inc.get("local") == "yes" else 0
                if file_id:
                    conn.execute(
                        "INSERT INTO includes (source_file_id, included_path, is_local) VALUES (?, ?, ?)",
                        (file_id, included, is_local)
                    )

            # Process file-level functions
            for section in compounddef.findall("sectiondef"):
                for memberdef in section.findall("memberdef"):
                    process_memberdef(conn, memberdef, None, file_id, project_root,
                                     file_cache, compound_name)

        elif kind in ("class", "struct", "enum", "union", "namespace"):
            # Get location
            file_path, line_number = get_location(compounddef)
            file_id = get_or_create_file(conn, file_path, project_root, file_cache)

            # Check if abstract
            is_abstract = 0
            for section in compounddef.findall("sectiondef"):
                for memberdef in section.findall("memberdef"):
                    if memberdef.get("virt") == "pure-virtual":
                        is_abstract = 1
                        break

            # Template params
            template_params = ""
            tpl = compounddef.find("templateparamlist")
            if tpl is not None:
                params = []
                for param in tpl.findall("param"):
                    ptype = get_text(param, "type")
                    pname = get_text(param, "declname")
                    params.append(f"{ptype} {pname}".strip())
                template_params = ", ".join(params)

            cursor = conn.execute(
                """INSERT OR IGNORE INTO classes
                   (name, qualified_name, kind, file_id, line_number, brief, detailed,
                    template_params, is_abstract)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (compound_name.split("::")[-1], compound_name, kind, file_id,
                 line_number, get_brief(compounddef), get_detailed(compounddef),
                 template_params, is_abstract)
            )
            class_id = cursor.lastrowid
            if class_id:
                class_cache[compound_name] = class_id

            # Process inheritance
            for base in compounddef.findall("basecompoundref"):
                base_name = base.text or ""
                access = base.get("prot", "public")
                is_virtual = 1 if base.get("virt") == "virtual" else 0
                if class_id:
                    conn.execute(
                        "INSERT INTO inheritance (derived_id, base_name, access, is_virtual) VALUES (?, ?, ?, ?)",
                        (class_id, base_name, access, is_virtual)
                    )

            # Process members
            for section in compounddef.findall("sectiondef"):
                for memberdef in section.findall("memberdef"):
                    process_memberdef(conn, memberdef, class_id, file_id, project_root,
                                     file_cache, compound_name)


def process_memberdef(conn: sqlite3.Connection, memberdef, class_id: Optional[int],
                      file_id: Optional[int], project_root: str, file_cache: dict,
                      scope: str) -> None:
    """Process a memberdef element (function, variable, etc.)."""
    kind = memberdef.get("kind", "")
    name = get_text(memberdef, "name")
    if not name:
        return

    # Get member location (may differ from parent compound)
    member_file, member_line = get_location(memberdef)
    if member_file:
        member_file_id = get_or_create_file(conn, member_file, project_root, file_cache)
    else:
        member_file_id = file_id

    qualified_name = f"{scope}::{name}" if scope else name
    access = memberdef.get("prot", "public")

    if kind == "function":
        return_type = get_text(memberdef, "type")
        is_static = 1 if memberdef.get("static") == "yes" else 0
        is_const = 1 if memberdef.get("const") == "yes" else 0
        is_virtual = 1 if memberdef.get("virt") in ("virtual", "pure-virtual") else 0
        is_pure_virtual = 1 if memberdef.get("virt") == "pure-virtual" else 0

        template_params = ""
        tpl = memberdef.find("templateparamlist")
        if tpl is not None:
            params = []
            for param in tpl.findall("param"):
                ptype = get_text(param, "type")
                pname = get_text(param, "declname")
                params.append(f"{ptype} {pname}".strip())
            template_params = ", ".join(params)

        cursor = conn.execute(
            """INSERT INTO functions
               (name, qualified_name, kind, return_type, class_id, file_id, line_number,
                brief, detailed, is_static, is_const, is_virtual, is_pure_virtual,
                access, template_params)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, qualified_name, kind, return_type, class_id, member_file_id,
             member_line, get_brief(memberdef), get_detailed(memberdef),
             is_static, is_const, is_virtual, is_pure_virtual, access, template_params)
        )
        func_id = cursor.lastrowid

        # Process parameters
        for i, param in enumerate(memberdef.findall("param")):
            param_type = get_text(param, "type")
            param_name = get_text(param, "declname")
            default_val = get_text(param, "defval")
            if func_id:
                conn.execute(
                    "INSERT INTO parameters (function_id, name, type, default_value, position) VALUES (?, ?, ?, ?, ?)",
                    (func_id, param_name, param_type, default_val, i)
                )

        # Process call graph references
        for ref in memberdef.findall("references"):
            callee_name = ref.text or ""
            if func_id and callee_name:
                conn.execute(
                    "INSERT INTO calls (caller_id, callee_name) VALUES (?, ?)",
                    (func_id, callee_name)
                )

    elif kind == "variable":
        var_type = get_text(memberdef, "type")
        is_static = 1 if memberdef.get("static") == "yes" else 0

        conn.execute(
            """INSERT INTO members
               (name, qualified_name, type, class_id, file_id, line_number,
                brief, access, is_static)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, qualified_name, var_type, class_id, member_file_id,
             member_line, get_brief(memberdef), access, is_static)
        )


def build_search_index(conn: sqlite3.Connection) -> None:
    """Build the FTS5 search index from existing data."""
    # Index classes
    conn.execute("""
        INSERT INTO search_index (name, qualified_name, kind, brief, detailed, file_path)
        SELECT c.name, c.qualified_name, c.kind, c.brief, c.detailed,
               COALESCE(f.relative_path, '')
        FROM classes c LEFT JOIN files f ON c.file_id = f.id
    """)

    # Index functions
    conn.execute("""
        INSERT INTO search_index (name, qualified_name, kind, brief, detailed, file_path)
        SELECT fn.name, fn.qualified_name, fn.kind, fn.brief, fn.detailed,
               COALESCE(f.relative_path, '')
        FROM functions fn LEFT JOIN files f ON fn.file_id = f.id
    """)

    # Index members
    conn.execute("""
        INSERT INTO search_index (name, qualified_name, kind, brief, detailed, file_path)
        SELECT m.name, m.qualified_name, 'variable', m.brief, '',
               COALESCE(f.relative_path, '')
        FROM members m LEFT JOIN files f ON m.file_id = f.id
    """)


def main():
    parser = argparse.ArgumentParser(description="Convert Doxygen XML to SQLite database")
    parser.add_argument("xml_dir", help="Path to Doxygen XML output directory")
    parser.add_argument("output_db", help="Path to output SQLite database")
    parser.add_argument("--project-root", default=".", help="Project root for relative paths")
    args = parser.parse_args()

    xml_dir = Path(args.xml_dir)
    if not xml_dir.exists():
        print(f"Error: XML directory not found: {xml_dir}", file=sys.stderr)
        sys.exit(1)

    project_root = str(Path(args.project_root).resolve())

    # Create/open database
    db_path = Path(args.output_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    create_schema(conn)

    file_cache = {}
    class_cache = {}

    # Process all XML files
    xml_files = sorted(xml_dir.glob("*.xml"))
    print(f"Processing {len(xml_files)} XML files...")

    for xml_file in xml_files:
        if xml_file.name == "index.xml":
            continue
        process_compound(conn, xml_file, project_root, file_cache, class_cache)

    conn.commit()

    # Build search index
    print("Building search index...")
    build_search_index(conn)
    conn.commit()

    # Print statistics
    for table in ["files", "classes", "functions", "parameters", "includes",
                  "inheritance", "calls", "members"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")

    conn.close()
    print(f"Database created: {db_path}")


if __name__ == "__main__":
    main()
```
