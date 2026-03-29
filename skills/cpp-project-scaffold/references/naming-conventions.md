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
| C++ namespace | `{project}::{lib}` (snake_case) | `my_engine::core` |
| Include path | `{project}/{lib}/src/File.hpp` | `my-engine/core/src/File.hpp` |
| Install header dest | `include/{target_name}` | `include/my_engine/core` |

## Library Parent Directory

The parent directory containing all libraries uses the project name:
- Directory: `{project}/` (kebab-case, e.g., `my-engine/`)
- Contains: `CMakeLists.txt` that adds all library subdirectories

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
