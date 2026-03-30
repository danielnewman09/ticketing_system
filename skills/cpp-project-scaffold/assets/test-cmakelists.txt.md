# test/CMakeLists.txt Template

This is the project-level test directory. It is added via `add_subdirectory(test)` in the root CMakeLists.txt before the library parent directory.

Individual libraries define their own test executables directly in their `test/CMakeLists.txt` files using `add_executable()`.

```cmake
# test/CMakeLists.txt

# Include integration test subdirectory if it exists
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/integration)
  add_subdirectory(integration)
endif()
```

## Notes

- Each library's `test/CMakeLists.txt` creates its own test executable with direct `add_executable()`, `target_link_libraries()`, and `gtest_discover_tests()`
- This project-level `test/` directory is reserved for integration tests that span multiple libraries
- The directory is added before the library parent so any shared test utilities are available
