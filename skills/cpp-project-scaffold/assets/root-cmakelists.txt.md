# Root CMakeLists.txt Template

Variables to substitute:
- `{{PROJECT_NAME}}` — CMake project name (e.g., `my_engine`)
- `{{PROJECT_NAME_UPPER}}` — Uppercase project name for variables
- `{{CXX_STANDARD}}` — C++ standard (20, 23, 26)
- `{{LIB_PARENT_DIR}}` — Library parent directory name (typically same as project)

```cmake
cmake_minimum_required(VERSION 3.15)

set(PROJECT_NAME {{PROJECT_NAME}})

project({{PROJECT_NAME}} VERSION 1.0 LANGUAGES CXX)

# Enable testing at the top level
enable_testing()

# Set compiler options
set(CMAKE_CXX_STANDARD {{CXX_STANDARD}})
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Required for shared libraries and pybind11 modules on aarch64
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Build options
option(BUILD_TESTING "Build the testing tree" ON)
option(ENABLE_COVERAGE "Enable code coverage" OFF)
option(ENABLE_CLANG_TIDY "Enable clang-tidy static analysis" OFF)
option(ENABLE_BENCHMARKS "Build performance benchmarks" OFF)
option(ENABLE_PROFILING "Enable profiling support (macOS only)" OFF)

# Enable warnings as errors for Release builds by default
if(CMAKE_BUILD_TYPE STREQUAL "Release")
  set(WARNINGS_AS_ERRORS_DEFAULT ON)
else()
  set(WARNINGS_AS_ERRORS_DEFAULT OFF)
endif()
option(WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ${WARNINGS_AS_ERRORS_DEFAULT})

# Python environment for documentation scripts
set(PROJECT_PYTHON "${CMAKE_SOURCE_DIR}/python/.venv/bin/python3")
if(EXISTS ${PROJECT_PYTHON})
  message(STATUS "Python venv found at ${PROJECT_PYTHON}")
else()
  message(STATUS "Python venv not found at ${PROJECT_PYTHON} — documentation targets will be unavailable. Run 'python/setup.sh' to create it.")
endif()

# Add useful compiler warnings
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wshadow
    -Wnon-virtual-dtor
    -Wold-style-cast
    -Wnull-dereference
    -Wdouble-promotion
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    add_compile_options(-Wimplicit-float-conversion)
  elseif(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    add_compile_options(-Wfloat-conversion)
  endif()
elseif(MSVC)
  add_compile_options(/W4)
endif()

# Warnings as errors configuration
if(WARNINGS_AS_ERRORS)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-Werror)
    message(STATUS "Warnings as errors enabled (-Werror)")
  elseif(MSVC)
    add_compile_options(/WX)
    message(STATUS "Warnings as errors enabled (/WX)")
  endif()
endif()

# Coverage configuration
if(ENABLE_COVERAGE)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(--coverage -O0 -fno-inline -fno-elide-constructors)
    add_link_options(--coverage)
    message(STATUS "Code coverage enabled")

    find_program(LCOV_PATH lcov)
    find_program(GENHTML_PATH genhtml)

    if(LCOV_PATH AND GENHTML_PATH)
      add_custom_target(coverage
        COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_BINARY_DIR}/coverage
        COMMAND ${LCOV_PATH} --directory . --zerocounters
        COMMAND ${LCOV_PATH} --directory . --capture --initial --output-file coverage_baseline.info --ignore-errors inconsistent,unsupported,format,gcov,source,range --filter range
        COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure || (exit 0)
        COMMAND ${LCOV_PATH} --directory . --capture --output-file coverage_test.info --ignore-errors inconsistent,unsupported,format,gcov,source,range --filter range
        COMMAND ${LCOV_PATH} --add-tracefile coverage_baseline.info --add-tracefile coverage_test.info --output-file coverage.info --ignore-errors inconsistent,unsupported,format,source,range
        COMMAND ${LCOV_PATH} --extract coverage.info '${CMAKE_SOURCE_DIR}/*' --output-file coverage_project.info --ignore-errors inconsistent,unsupported,format
        COMMAND ${LCOV_PATH} --remove coverage_project.info '*/test/*' '*/build/*' '*/bench/*' --output-file coverage_filtered.info --ignore-errors inconsistent,unsupported,format,unused
        COMMAND ${GENHTML_PATH} coverage_filtered.info --output-directory ${CMAKE_BINARY_DIR}/coverage --ignore-errors inconsistent,unsupported,format,corrupt,category,source,range --filter missing,range
        COMMAND ${LCOV_PATH} --summary coverage_filtered.info --ignore-errors inconsistent,unsupported,format
        WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
        COMMENT "Generating project-wide code coverage report"
      )
      message(STATUS "Coverage target 'coverage' added. HTML report will be in ${CMAKE_BINARY_DIR}/coverage")
    else()
      message(WARNING "lcov and/or genhtml not found. Coverage target will not be available.")
    endif()
  else()
    message(WARNING "Code coverage is only supported with GCC or Clang")
  endif()
endif()

# Profiling configuration (macOS only)
if(ENABLE_PROFILING)
  if(APPLE)
    add_compile_options(-g -O2)
    message(STATUS "Profiling support enabled (debug symbols + optimizations)")
  else()
    message(WARNING "Profiling support is only available on macOS (Xcode Instruments)")
  endif()
endif()

# Clang-tidy configuration
if(ENABLE_CLANG_TIDY)
  find_program(CLANG_TIDY_EXE NAMES "clang-tidy")
  if(CLANG_TIDY_EXE)
    message(STATUS "clang-tidy found: ${CLANG_TIDY_EXE}")
    set(CMAKE_CXX_CLANG_TIDY "${CLANG_TIDY_EXE}")
  else()
    message(WARNING "clang-tidy requested but not found")
  endif()
endif()

# Doxygen documentation (auto-enabled when doxygen is found)
find_package(Doxygen QUIET)
if(DOXYGEN_FOUND)
  set(DOXYGEN_IN ${CMAKE_SOURCE_DIR}/Doxyfile.in)
  set(DOXYGEN_OUT ${CMAKE_BINARY_DIR}/Doxyfile)

  configure_file(${DOXYGEN_IN} ${DOXYGEN_OUT} @ONLY)

  add_custom_target(doxygen
    COMMAND ${DOXYGEN_EXECUTABLE} ${DOXYGEN_OUT}
    WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
    COMMENT "Generating API documentation with Doxygen"
    VERBATIM
  )

  set(DOXYGEN_DB ${CMAKE_BINARY_DIR}/docs/codebase.db)

  if(EXISTS ${PROJECT_PYTHON})
    # Doxygen XML → SQLite codebase database
    add_custom_target(doxygen-db
      COMMAND ${PROJECT_PYTHON} ${CMAKE_SOURCE_DIR}/scripts/doxygen_to_sqlite.py
              ${CMAKE_BINARY_DIR}/docs/xml ${DOXYGEN_DB}
              --project-root ${CMAKE_SOURCE_DIR}
      DEPENDS doxygen
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      COMMENT "Generating codebase SQLite database from Doxygen XML"
      VERBATIM
    )

    # Public target: complete codebase database
    add_custom_target(codebase-db DEPENDS doxygen-db)
    message(STATUS "  Run 'cmake --build <build-dir> --target codebase-db' to generate codebase SQLite database")

    # Doxygen XML → Neo4j graph database
    add_custom_target(doxygen-neo4j
      COMMAND ${PROJECT_PYTHON} ${CMAKE_SOURCE_DIR}/scripts/doxygen_to_neo4j.py
              ${CMAKE_BINARY_DIR}/docs/xml
              --project-root ${CMAKE_SOURCE_DIR}
      DEPENDS doxygen
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      COMMENT "Ingesting Doxygen XML into Neo4j graph database"
      VERBATIM
    )

    # Public target: complete Neo4j codebase graph
    add_custom_target(codebase-neo4j DEPENDS doxygen-neo4j)
    message(STATUS "  Run 'cmake --build <build-dir> --target codebase-neo4j' to ingest into Neo4j")

    # Full codebase targets (extend these if you add more indexers)
    add_custom_target(codebase-full-db DEPENDS codebase-db)
    add_custom_target(codebase-full-neo4j DEPENDS codebase-neo4j)
  else()
    message(STATUS "  Python venv not found — codebase database targets unavailable")
  endif()

  message(STATUS "Doxygen found: ${DOXYGEN_EXECUTABLE}")
  message(STATUS "  Run 'cmake --build <build-dir> --target doxygen' to generate documentation")
  message(STATUS "  Output will be in ${CMAKE_BINARY_DIR}/docs/")
else()
  message(STATUS "Doxygen not found - documentation target will not be available")
endif()

# Always include the test directory first to define testing functions
if(BUILD_TESTING)
  add_subdirectory(test)
endif()

add_subdirectory({{LIB_PARENT_DIR}})

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)
```

## Notes

- The Python venv is optional — project builds without it, but documentation indexing targets are unavailable
- Coverage, profiling, benchmarking are all opt-in via CMake options
- The `codebase-full-db` and `codebase-full-neo4j` targets are extension points — add more indexers as `DEPENDS` as the project grows
