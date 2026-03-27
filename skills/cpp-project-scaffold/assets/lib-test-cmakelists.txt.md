# Library test/CMakeLists.txt Template

Variables to substitute:
- `{{LIB_VAR_PREFIX}}` — Uppercase variable prefix matching parent (e.g., `MY_ENGINE_CORE`)
- `{{LIB_TARGET_NAME}}` — Library target to link against (e.g., `my_engine_core`)
- `{{CXX_STANDARD}}` — C++ standard (20, 23, 26)
- `{{ADDITIONAL_TEST_LINK_LIBRARIES}}` — Extra libraries needed for tests (optional)

```cmake
enable_testing()

find_package(GTest REQUIRED)
add_executable(${{{LIB_VAR_PREFIX}}_TEST_NAME})

target_sources(${{{LIB_VAR_PREFIX}}_TEST_NAME} PRIVATE
    placeholder_test.cpp
)

set_target_properties(${{{LIB_VAR_PREFIX}}_TEST_NAME} PROPERTIES LINKER_LANGUAGE CXX)

target_link_libraries(${{{LIB_VAR_PREFIX}}_TEST_NAME}
    PRIVATE
      {{LIB_TARGET_NAME}}
      GTest::GTest
      GTest::Main
      {{ADDITIONAL_TEST_LINK_LIBRARIES}}
)

target_compile_features(${{{LIB_VAR_PREFIX}}_TEST_NAME} PRIVATE cxx_std_{{CXX_STANDARD}})
target_compile_options(${{{LIB_VAR_PREFIX}}_TEST_NAME} PRIVATE -Wno-unused-result)

target_include_directories(${{{LIB_VAR_PREFIX}}_TEST_NAME} PUBLIC
    ${GTEST_INCLUDE_DIRS}
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../src>
)

# Discover and register tests with CTest
include(GoogleTest)
gtest_discover_tests(${{{LIB_VAR_PREFIX}}_TEST_NAME})
```

## Notes

- The test executable name comes from the `_TEST_NAME` variable set in the parent library CMakeLists
- As tests grow, add subdirectories with `target_sources()` calls or add more source files directly
- The include directories allow `#include "MyClass.hpp"` from the src directory
