# CMakeUserPresets.json Template

Variables to substitute:
- `{{LIBRARY_BUILD_PRESETS}}` — Array of per-library build preset objects
- `{{ALL_LIB_TARGETS}}` — Comma-separated list of all library targets
- `{{ALL_TEST_TARGETS}}` — Comma-separated list of all test targets
- `{{JOBS}}` — Parallel job count (default: number of CPU cores)

```json
{
    "version": 4,
    "vendor": {
        "conan": {}
    },
    "include": [
        "build/Debug/generators/CMakePresets.json",
        "build/Release/generators/CMakePresets.json"
    ],
    "configurePresets": [
        {
            "name": "coverage-debug",
            "inherits": "conan-debug",
            "displayName": "Debug with Coverage",
            "description": "Debug build with code coverage enabled (use: conan install . -o \"&:enable_coverage=True\")"
        },
        {
            "name": "profiling-release",
            "inherits": "conan-debug",
            "displayName": "Release with Profiling",
            "description": "Release build with debug symbols for profiling",
            "cacheVariables": {
                "ENABLE_PROFILING": "ON"
            }
        }
    ],
    "buildPresets": [
        {{LIBRARY_BUILD_PRESETS}},
        {
            "name": "debug-tests-only",
            "displayName": "Build all tests (Debug)",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": [{{ALL_TEST_TARGETS}}]
        },
        {
            "name": "release-tests-only",
            "displayName": "Build all tests (Release)",
            "configurePreset": "conan-release",
            "jobs": {{JOBS}},
            "targets": [{{ALL_TEST_TARGETS}}]
        },
        {
            "name": "coverage-all",
            "displayName": "Generate Coverage Report",
            "description": "Run all tests and generate combined HTML coverage report",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": ["coverage"]
        },
        {
            "name": "doxygen",
            "displayName": "Generate Doxygen Documentation",
            "description": "Generate API documentation with Doxygen",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": ["doxygen"]
        },
        {
            "name": "codebase-db",
            "displayName": "Generate Codebase SQLite Database",
            "description": "Generate codebase.db with Doxygen symbols",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": ["codebase-db"]
        },
        {
            "name": "codebase-neo4j",
            "displayName": "Ingest Codebase into Neo4j",
            "description": "Ingest Doxygen symbols into Neo4j graph database",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": ["codebase-neo4j"]
        },
        {
            "name": "codebase-full-db",
            "displayName": "Full Codebase SQLite Database",
            "description": "Complete codebase.db with all indexers",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": ["codebase-full-db"]
        },
        {
            "name": "codebase-full-neo4j",
            "displayName": "Full Codebase Neo4j Graph",
            "description": "Complete Neo4j graph with all indexers",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": ["codebase-full-neo4j"]
        },
        {
            "name": "debug-all",
            "displayName": "Build Everything (Debug)",
            "description": "Build all libraries, tests, and documentation databases",
            "configurePreset": "conan-debug",
            "jobs": {{JOBS}},
            "targets": [{{ALL_LIB_TARGETS}}, {{ALL_TEST_TARGETS}}, "codebase-db", "codebase-neo4j"]
        }
    ]
}
```

## Per-Library Build Preset Pattern

For each library `{lib}` with target `{project}_{lib}` and test target `{project}_{lib}_test`:

```json
{
    "name": "debug-{lib}-only",
    "displayName": "Build {project}-{lib} (Debug)",
    "configurePreset": "conan-debug",
    "jobs": {{JOBS}},
    "targets": ["{project}_{lib}", "{project}_{lib}_test"]
},
{
    "name": "release-{lib}-only",
    "displayName": "Build {project}-{lib} (Release)",
    "configurePreset": "conan-release",
    "jobs": {{JOBS}},
    "targets": ["{project}_{lib}", "{project}_{lib}_test"]
}
```

For header-only libraries (no test target):

```json
{
    "name": "debug-{lib}-only",
    "displayName": "Build {project}-{lib} (Debug)",
    "configurePreset": "conan-debug",
    "jobs": {{JOBS}},
    "targets": ["{project}_{lib}"]
}
```
