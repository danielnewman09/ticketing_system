---
name: cpp-project-scaffold
description: Scaffold a new C++20+ project with Conan 2.x, GTest, CMake presets, Doxygen documentation pipeline (SQLite + Neo4j via doxygen-index library), component-based library structure, VSCode tasks, coverage, benchmarking, and profiling support. Produces a complete, buildable project skeleton.

<example>
Context: User wants to create a brand-new C++ project from scratch.
user: "Scaffold a new C++ project called my-engine with libraries core and physics"
assistant: "I'll create a complete project skeleton with Conan, CMake presets, GTest, Doxygen, and your two libraries."
<Generates all files from templates>
</example>

<example>
Context: User wants a minimal project with just one library.
user: "Create a C++ project called utils-lib with a single library called utils"
assistant: "I'll scaffold a minimal project with one library, tests, and the full build pipeline."
<Generates all files from templates>
</example>

model: sonnet
---

# /cpp-project-scaffold Skill

## What This Does

Generates a complete, buildable C++20+ project skeleton with:
- **Conan 2.x** dependency management (GTest included by default)
- **CMake presets** for Debug/Release builds, per-component builds, and tooling targets
- **GTest** integration with per-library test executables
- **Doxygen** documentation pipeline → SQLite / Neo4j via `doxygen-index` library
- **VSCode tasks** for build, test, coverage, and documentation
- **Code coverage** (lcov/genhtml)
- **Optional benchmarking** (Google Benchmark)
- **Optional profiling** (macOS Instruments)
- **Component-based library structure** with per-library CMakeLists patterns
- **Python environment** with `doxygen-index` for documentation indexing

## Inputs

The user must provide:
1. **Project name** (e.g., `my-engine`) — used for directory name, CMake project, namespaces
2. **Library list** — one or more libraries to create (e.g., `core`, `physics`, `rendering`)
3. **Additional Conan dependencies** (optional) — beyond GTest (e.g., `eigen/3.4.0`, `spdlog/1.14.1`)
4. **C++ standard** (optional, default: C++20) — any of C++20, C++23, C++26

For each library, optionally specify:
- Whether it's **header-only** (INTERFACE) or a **compiled** library (default: compiled)
- **Dependencies on other project libraries** (e.g., physics depends on core)
- **External Conan dependencies** specific to this library

## Output Structure

```
{project-name}/
├── CMakeLists.txt              # Root CMake configuration
├── CMakeUserPresets.json        # Build presets (component builds, tooling)
├── conanfile.py                 # Conan recipe with all dependencies
├── Doxyfile.in                  # Doxygen configuration template
│
├── python/
│   ├── setup.sh                # Python venv setup script
│   └── requirements.txt        # Python dependencies (doxygen-index)
│
├── .vscode/
│   ├── tasks.json              # Build, test, coverage tasks
│   └── c_cpp_properties.json   # IntelliSense configuration
│
├── test/
│   └── CMakeLists.txt          # Project-level test directory (integration tests)
│
├── {lib-parent}/               # **REQUIRED**: library parent dir, same name as project
│   ├── CMakeLists.txt          # Adds all library subdirectories
│   │
│   ├── {lib-name}/             # One per library
│   │   ├── CMakeLists.txt      # Library target, deps, tests, install
│   │   ├── src/
│   │   │   ├── CMakeLists.txt  # Source file collection (target_sources)
│   │   │   ├── placeholder.hpp # Initial header file
│   │   │   └── placeholder.cpp # Initial source file
│   │   └── test/
│   │       ├── CMakeLists.txt  # Test executable setup
│   │       └── placeholder_test.cpp  # Initial test file
│   └── ...
│
├── build/                      # (gitignored) CMake build output
└── .gitignore
```

**CRITICAL**: Libraries are NOT placed directly in the project root. They go inside a
**library parent directory** that has the same name as the project. For example, a
project called `calculator` with libraries `calculation_engine` and `user_interface`:

```
calculator/                     # project root
├── CMakeLists.txt
├── conanfile.py
├── calculator/                 # library parent directory (same name as project!)
│   ├── CMakeLists.txt          # add_subdirectory(calculation_engine)
│   │                           # add_subdirectory(user_interface)
│   ├── calculation_engine/
│   │   ├── CMakeLists.txt
│   │   ├── src/
│   │   └── test/
│   └── user_interface/
│       ├── CMakeLists.txt
│       ├── src/
│       └── test/
└── ...
```

The root CMakeLists.txt references this via `add_subdirectory(calculator)`.
Do NOT place libraries at `calculator/calculation_engine/` — they must be at
`calculator/calculator/calculation_engine/`.

## Steps

### 1. Gather Project Parameters

Confirm with the user:
- Project name
- Library names and their types (compiled vs header-only)
- Inter-library dependencies
- Additional Conan dependencies
- C++ standard version

### 2. Generate Root CMakeLists.txt

Use the template from `assets/root-cmakelists.txt.md`. Key features:
- Project name and version from user input
- C++ standard from user input (default 20)
- `CMAKE_POSITION_INDEPENDENT_CODE ON`
- Build options: `BUILD_TESTING`, `ENABLE_COVERAGE`, `ENABLE_CLANG_TIDY`, `ENABLE_BENCHMARKS`, `ENABLE_PROFILING`, `WARNINGS_AS_ERRORS`
- Compiler warnings (Wall, Wextra, Wpedantic, etc.) for GCC/Clang/MSVC
- Coverage target with lcov/genhtml
- Profiling configuration (macOS)
- Doxygen documentation targets (doxygen → doxygen-db → codebase-db)
- Neo4j ingestion targets (doxygen-neo4j → codebase-neo4j)
- Full codebase targets: `codebase-full-db`, `codebase-full-neo4j`
- Python venv integration for scripts
- CPack configuration

### 3. Generate conanfile.py

Use the template from `assets/conanfile.py.md`. Key features:
- Project name and version
- C++ standard setting in `configure()`
- Options: `enable_coverage`, `warnings_as_errors`, `enable_clang_tidy`, `enable_benchmarks`, `enable_profiling`
- GTest requirement (always included)
- User-specified additional dependencies
- Optional benchmark dependency
- Output directory configuration
- Install prefix to `installs/` directory

### 4. Generate CMakeUserPresets.json

Use the template from `assets/cmake-user-presets.json.md`. Generate:
- Include paths for Conan-generated presets
- `coverage-debug` and `profiling-release` configure presets
- Per-library build presets: `debug-{lib}-only`, `release-{lib}-only`
- `debug-tests-only` and `release-tests-only` aggregating all test targets
- `coverage-all` preset
- `doxygen`, `codebase-db` presets
- `debug-all` preset listing all targets

### 5. Generate Test Directory (test/CMakeLists.txt)

Use the template from `assets/test-cmakelists.txt.md`. This is a minimal project-level test directory for integration tests. Individual libraries define their own test executables directly.

### 6. Generate Library Structure

For each library, generate using templates from `assets/`:

**Compiled library** (`assets/lib-cmakelists.txt.md`):
- Library target with `CXX_STANDARD` set via `set_target_properties`
- Package finding for external deps
- `src/` and `test/` subdirectories (conditional on `BUILD_TESTING`)
- `bench/` subdirectory (conditional on `ENABLE_BENCHMARKS`)
- Public/private library linking
- Include directories with generator expressions
- Directory-based header install preserving `{lib-dir}/src/` structure

**Header-only library** (`assets/lib-interface-cmakelists.txt.md`):
- INTERFACE library target
- INTERFACE dependencies
- INTERFACE include directories
- Directory-based header install preserving `{lib-dir}/src/` structure

**Source CMakeLists** (`assets/lib-src-cmakelists.txt.md`):
- `target_sources()` for source files

**Test CMakeLists** (`assets/lib-test-cmakelists.txt.md`):
- Direct `add_executable()` with `set_target_properties` for C++ standard
- Links `GTest::gtest` and `GTest::gtest_main` (lowercase)
- Include directories
- `gtest_discover_tests()`

### 7. Generate Doxyfile.in

Use the template from `assets/doxyfile.in.md`. Features:
- CMake variable substitution for project name, version, paths
- Recursive scanning of library parent directory
- Excludes test/bench/build directories
- HTML + XML output (XML for database generation)
- Custom Doxygen aliases (@ticket, @threadsafe, etc.)

### 8. Generate Python Environment

**python/setup.sh** — Creates venv and installs requirements
**python/requirements.txt** — `doxygen-index` library (provides SQLite + Neo4j ingestion from Doxygen XML)

### 9. Generate VSCode Tasks

Use the template from `assets/vscode-tasks.json.md`. Tasks:
- **Conan Build** (default) — `conan build . --build=missing -s build_type={Debug|Release}`
- **CMake Build** — direct cmake build
- **Generate Coverage Report** — runs coverage-all preset
- **Open Coverage Report** — opens HTML report
- **Run clang-tidy** — static analysis

### 10. Generate VSCode C/C++ Properties

Use the template from `assets/c-cpp-properties.json.md`. Creates `.vscode/c_cpp_properties.json` with:
- Mac and Linux configurations
- Include paths for each library directory
- Conan cache include paths (glob patterns)
- C++ standard matching the project
- CMake Tools as the configuration provider

### 12. Generate .gitignore

Standard C++ project gitignore including `build/`, `installs/`, `python/.venv/`, etc.

### 13. Generate Placeholder Source Files

For each compiled library:
- `src/placeholder.cpp` with namespace and a stub function
- `src/placeholder.hpp` with header guard and declaration
- `test/placeholder_test.cpp` with a GTest that includes the header

### 12. Verify Build

After generation, run:
```bash
cd {project-name}
python/setup.sh
conan install . --build=missing -s build_type=Debug
cmake --preset conan-debug
cmake --build --preset conan-debug
ctest --preset conan-debug
```

Report success or any issues.

## Reference Files

- `references/naming-conventions.md` — Variable naming patterns used across templates
- `references/cmake-patterns.md` — CMake patterns and conventions used in the generated project

## Important Notes

- All generated files use the project name for namespaces, target names, and directory names
- Library targets use underscore naming: `{project}_{lib}` (e.g., `my_engine_core`)
- Test targets append `_test`: `{project}_{lib}_test`
- The generated project is immediately buildable after `conan install`
- GTest is always included; other dependencies are user-configurable
- The Python environment installs `doxygen-index` which handles all Doxygen XML → database ingestion
- `doxygen-index` also supports indexing Conan dependencies via `doxygen-index full`
