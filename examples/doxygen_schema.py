
def create_schema(conn: sqlite3.Connection) -> None:
    """Create the database schema for code indexing."""
    conn.executescript("""
        -- Files table: source files in the codebase
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            refid TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            path TEXT,
            language TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_files_name ON files(name);
        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

        -- Namespaces table
        CREATE TABLE IF NOT EXISTS namespaces (
            id INTEGER PRIMARY KEY,
            refid TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_namespaces_name ON namespaces(name);

        -- Compounds table: classes, structs, unions, enums
        CREATE TABLE IF NOT EXISTS compounds (
            id INTEGER PRIMARY KEY,
            refid TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,  -- class, struct, union, enum, namespace
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            file_id INTEGER REFERENCES files(id),
            line_number INTEGER,
            brief_description TEXT,
            detailed_description TEXT,
            base_classes TEXT,  -- JSON array of base class names
            is_final INTEGER DEFAULT 0,
            is_abstract INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_compounds_name ON compounds(name);
        CREATE INDEX IF NOT EXISTS idx_compounds_qualified_name ON compounds(qualified_name);
        CREATE INDEX IF NOT EXISTS idx_compounds_kind ON compounds(kind);
        CREATE INDEX IF NOT EXISTS idx_compounds_file_id ON compounds(file_id);

        -- Members table: functions, variables, typedefs, enums
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY,
            refid TEXT UNIQUE NOT NULL,
            compound_id INTEGER REFERENCES compounds(id),
            kind TEXT NOT NULL,  -- function, variable, typedef, enum, define
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            type TEXT,
            definition TEXT,
            argsstring TEXT,
            file_id INTEGER REFERENCES files(id),
            line_number INTEGER,
            brief_description TEXT,
            detailed_description TEXT,
            protection TEXT,  -- public, protected, private
            is_static INTEGER DEFAULT 0,
            is_const INTEGER DEFAULT 0,
            is_constexpr INTEGER DEFAULT 0,
            is_virtual INTEGER DEFAULT 0,
            is_inline INTEGER DEFAULT 0,
            is_explicit INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_members_name ON members(name);
        CREATE INDEX IF NOT EXISTS idx_members_qualified_name ON members(qualified_name);
        CREATE INDEX IF NOT EXISTS idx_members_kind ON members(kind);
        CREATE INDEX IF NOT EXISTS idx_members_compound_id ON members(compound_id);
        CREATE INDEX IF NOT EXISTS idx_members_file_id ON members(file_id);

        -- Parameters table: function parameters
        CREATE TABLE IF NOT EXISTS parameters (
            id INTEGER PRIMARY KEY,
            member_id INTEGER REFERENCES members(id),
            position INTEGER NOT NULL,
            name TEXT,
            type TEXT NOT NULL,
            default_value TEXT,
            description TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_parameters_member_id ON parameters(member_id);

        -- Symbol references table: call graph and reference relationships
        CREATE TABLE IF NOT EXISTS symbol_refs (
            id INTEGER PRIMARY KEY,
            from_member_id INTEGER,
            to_member_refid TEXT NOT NULL,
            to_member_name TEXT NOT NULL,
            relationship TEXT NOT NULL,  -- 'calls', 'called_by'
            FOREIGN KEY (from_member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_symbol_refs_from ON symbol_refs(from_member_id);
        CREATE INDEX IF NOT EXISTS idx_symbol_refs_to ON symbol_refs(to_member_refid);

        -- Include dependencies
        CREATE TABLE IF NOT EXISTS includes (
            id INTEGER PRIMARY KEY,
            file_id INTEGER REFERENCES files(id),
            included_file TEXT NOT NULL,
            included_refid TEXT,
            is_local INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_includes_file_id ON includes(file_id);

        -- Metadata table
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()