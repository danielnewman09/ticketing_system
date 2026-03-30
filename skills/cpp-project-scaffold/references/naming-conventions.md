# Naming Conventions

This document defines how project/library names are transformed across different contexts.

## Project Name Transformations

Given a project name like `my-engine`:

| Context | Transform | Example |
|---------|-----------|---------|
| Directory name | as-is (kebab-case) | `my-engine/` |
| CMake project name | snake_case | `my_engine` |
| Conan package name | snake_case | `my_engine` |
| Conan class name | PascalCase | `MyEngine` |
| C++ namespace | snake_case | `my_engine` |

## Library Name Transformations

Given a library name like `core` in project `my-engine`:

| Context | Transform | Example |
|---------|-----------|---------|
| Directory name | `{project}/{lib}` (kebab-case) | `my-engine/core/` |
| CMake target name | `{project}_{lib}` (snake_case) | `my_engine_core` |
| CMake variable prefix | `{PROJECT}_{LIB}` (UPPER_SNAKE) | `MY_ENGINE_CORE` |
| Test directory name | `{project}/{lib}/test` | `my_engine/core/test` |
| Test target name | `{project}_{lib}_test` | `my_engine_core_test` |
| C++ namespace | short, terse name (single level) | `engine`, `core`, `phys` |
| Include path | `{lib}/src/File.hpp` (NOT `{project}/{lib}/...`) | `core/src/File.hpp` |
| Install header dest | `include/{lib-dir}/src/` | `include/core/src/` |

## C++ Namespace Style

Use a **single flat namespace** per library — no nested `project::lib` namespaces. Pick a short, terse name that's easy to type:

| Library | Good namespace | Bad namespace |
|---------|---------------|---------------|
| `calculation_engine` | `calc` | `calculator::calculation_engine` |
| `user_interface` | `ui` | `calculator::user_interface` |
| `physics` | `phys` | `my_engine::physics` |
| `core` | `core` | `my_engine::core` |
| `rendering` | `render` | `my_engine::rendering` |

## Library Parent Directory

**All libraries live inside a parent directory with the same name as the project.**
This creates a two-level structure: `{project-root}/{project-name}/{lib}/`.

- Directory: `{project-name}/` inside the project root (e.g., `my-engine/my-engine/`)
- Contains: `CMakeLists.txt` that calls `add_subdirectory()` for each library

Example for project `calculator` with libraries `core` and `ui`:
- `calculator/calculator/core/` — CORRECT
- `calculator/core/` — WRONG (library directly in project root)

## Build Preset Names

| Preset | Pattern | Example |
|--------|---------|---------|
| Debug component | `debug-{lib}-only` | `debug-core-only` |
| Release component | `release-{lib}-only` | `release-core-only` |
| Debug all tests | `debug-tests-only` | `debug-tests-only` |
| Release all tests | `release-tests-only` | `release-tests-only` |
| Coverage | `coverage-all` | `coverage-all` |
| Documentation | `doxygen` | `doxygen` |
| Codebase DB | `codebase-db` | `codebase-db` |
| Everything | `debug-all` | `debug-all` |
