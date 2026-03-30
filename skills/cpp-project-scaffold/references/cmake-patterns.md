# CMake Patterns Reference

Key patterns used throughout the generated project skeleton.

## Include Directory Pattern

Libraries use generator expressions for include directories:

```cmake
target_include_directories(${LIB_NAME}
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>
        $<INSTALL_INTERFACE:include>
)
```

This allows consumers to write:
```cpp
#include "core/src/MyClass.hpp"
```

**CRITICAL**: The `..` goes up from the library directory to the library parent directory.
This means `#include` paths start from the **library directory name**, NOT the project root.
For a project `calculator` with library `user_interface`:
```cpp
#include "user_interface/src/Widget.hpp"   // CORRECT
// NOT: #include "calculator/user_interface/src/Widget.hpp"
```

## Source Collection Pattern

Sources are collected via `target_sources()` in `src/CMakeLists.txt`:

```cmake
target_sources(${LIB_NAME} PRIVATE
    File1.cpp
    File2.cpp
)
```

Headers live alongside sources in `src/` and are installed by the parent CMakeLists via directory install.

## Header Installation Pattern

Both compiled and header-only libraries use the same directory-based install:

```cmake
install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/src/
    DESTINATION include/{lib-dir}/src
    FILES_MATCHING PATTERN "*.hpp"
)
```

This preserves the include path structure: `#include "{lib-dir}/src/File.hpp"` works identically at build time and after install.

## Modular Source Subdirectories

As a library grows, organize into subdirectories:

```
src/
├── CMakeLists.txt        # Adds subdirectories + top-level sources
├── TopLevel.cpp
├── ModuleA/
│   ├── CMakeLists.txt    # target_sources(${LIB_NAME} PRIVATE ...)
│   └── ClassA.cpp
└── ModuleB/
    ├── CMakeLists.txt
    └── ClassB.cpp
```

Each subdirectory's CMakeLists calls `target_sources()` on the same library target.

## C++ Standard Pattern

All targets (libraries and tests) use `set_target_properties` with `CXX_STANDARD`:

```cmake
set_target_properties(${TARGET_NAME} PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
)
```

The root CMakeLists also sets the global default:

```cmake
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

## Test Pattern

Each library defines its own test executable directly using `add_executable()`:

```cmake
enable_testing()
find_package(GTest REQUIRED)

add_executable(${TEST_NAME})
target_sources(${TEST_NAME} PRIVATE test_file.cpp)

set_target_properties(${TEST_NAME} PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
)

target_link_libraries(${TEST_NAME}
    PRIVATE ${LIB_NAME} GTest::gtest GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(${TEST_NAME})
```

Note: GTest components use **lowercase** names: `GTest::gtest` and `GTest::gtest_main`.

## Conan + CMake Preset Integration

Conan generates preset files at:
- `build/Debug/generators/CMakePresets.json`
- `build/Release/generators/CMakePresets.json`

`CMakeUserPresets.json` includes these and defines user presets that inherit from `conan-debug` or `conan-release`.

## Conditional Build Sections

```cmake
if(BUILD_TESTING)
  add_subdirectory(test)
endif()

if(ENABLE_BENCHMARKS)
  add_subdirectory(bench)
endif()
```

## Optional Python Integration

The root CMakeLists checks for the Python venv before defining documentation targets:

```cmake
set(PROJECT_PYTHON "${CMAKE_SOURCE_DIR}/python/.venv/bin/python3")
if(EXISTS ${PROJECT_PYTHON})
  # Define documentation targets that use Python scripts
endif()
```

This makes the Python environment optional — the project builds without it.

## Doxygen Target Chain

```
doxygen          → Generates HTML + XML docs
  └── doxygen-db → Parses XML into SQLite codebase.db
       └── codebase-db  → Public target (extend with more indexers)

doxygen          → Generates HTML + XML docs
  └── doxygen-neo4j → Parses XML into Neo4j graph
       └── codebase-neo4j → Public target (extend with more indexers)

codebase-full-db    → DEPENDS codebase-db (+ deps-db if added later)
codebase-full-neo4j → DEPENDS codebase-neo4j (+ deps-neo4j if added later)
```
