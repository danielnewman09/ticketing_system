# test/CMakeLists.txt Template

Variables to substitute:
- `{{CXX_STANDARD}}` — C++ standard (17, 20, 23, 26) — use the project standard or 17 as minimum

```cmake
# test/CMakeLists.txt

# Create a test helper function to be used by all test directories
function(add_project_test)

    # Find the GTest package for all tests
    find_package(GTest REQUIRED)
    include(GoogleTest)

    # Parse function arguments
    set(options "")
    set(oneValueArgs NAME)
    set(multiValueArgs SOURCES LIBS INCLUDES)
    cmake_parse_arguments(TEST "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    # Create test executable
    add_executable(${TEST_NAME} ${TEST_SOURCES})

    # Set standard properties for all tests
    target_link_libraries(${TEST_NAME}
        PRIVATE ${TEST_LIBS} GTest::gtest GTest::gtest_main
    )

    target_include_directories(${TEST_NAME} PRIVATE
        ${TEST_INCLUDES}
        ${CMAKE_SOURCE_DIR}/src
    )

    # Set compile features
    target_compile_features(${TEST_NAME} PRIVATE cxx_std_{{CXX_STANDARD}})

    # Add to CTest using gtest_discover_tests
    gtest_discover_tests(${TEST_NAME}
        PROPERTIES
          TIMEOUT 300
          PROCESSORS 1
    )
endfunction()

# Include integration test subdirectory if it exists
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/integration)
  add_subdirectory(integration)
endif()
```

## Notes

- This function is available to all library test directories because `test/` is added via `add_subdirectory()` before the library parent directory in the root CMakeLists.txt
- Libraries can use this function OR define their own test executable directly (the pattern in this project uses direct definition for more control)
