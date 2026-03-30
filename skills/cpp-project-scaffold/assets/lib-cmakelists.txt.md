# Library CMakeLists.txt Template (Compiled Library)

Variables to substitute:
- `{{LIB_VAR_PREFIX}}` — Uppercase variable prefix (e.g., `MY_ENGINE_CORE`)
- `{{LIB_TARGET_NAME}}` — CMake target name (e.g., `my_engine_core`)
- `{{LIB_TEST_TARGET_NAME}}` — Test target name (e.g., `my_engine_core_test`)
- `{{LIB_DIR_NAME}}` — Library directory name (e.g., `core`)
- `{{CXX_STANDARD}}` — C++ standard (20, 23, 26)
- `{{FIND_PACKAGES}}` — `find_package()` calls for external dependencies
- `{{PUBLIC_LINK_LIBRARIES}}` — Public link targets (project libs + external)
- `{{PRIVATE_LINK_LIBRARIES}}` — Private link targets

```cmake
# Define library name
set({{LIB_VAR_PREFIX}}_NAME {{LIB_TARGET_NAME}})
set({{LIB_VAR_PREFIX}}_TEST_NAME {{LIB_TEST_TARGET_NAME}})

# Create the library
add_library(${{{LIB_VAR_PREFIX}}_NAME})
set_target_properties(${{{LIB_VAR_PREFIX}}_NAME} PROPERTIES
    LINKER_LANGUAGE CXX
    CXX_STANDARD {{CXX_STANDARD}}
    CXX_STANDARD_REQUIRED ON
)

# Find required packages
{{FIND_PACKAGES}}

# Add subdirectories to collect sources
add_subdirectory(src)
if(BUILD_TESTING)
  add_subdirectory(test)
endif()
if(ENABLE_BENCHMARKS)
  add_subdirectory(bench)
endif()

# Link libraries
target_link_libraries(${{{LIB_VAR_PREFIX}}_NAME}
    PUBLIC
      {{PUBLIC_LINK_LIBRARIES}}
    PRIVATE
      {{PRIVATE_LINK_LIBRARIES}}
)

# Add include directories to support "{lib-dir}/src/..." includes
target_include_directories(${{{LIB_VAR_PREFIX}}_NAME}
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>
        $<INSTALL_INTERFACE:include>
)

# Installation rules
install(TARGETS ${{{LIB_VAR_PREFIX}}_NAME}
    RUNTIME DESTINATION bin
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
)

# Install headers — preserves the {lib-dir}/src/ structure for consumers
install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/src/
    DESTINATION include/{{LIB_DIR_NAME}}/src
    FILES_MATCHING PATTERN "*.hpp"
)
```

## Notes

- The include directory pattern `$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>` sets the include root to the library parent directory, so includes use the library name only: `#include "{lib-dir}/src/MyClass.hpp"` — do NOT prefix with the project root directory
- Headers are installed to `include/{lib-dir}/src/` to match the build-time include path
- Remove the `PRIVATE` section from `target_link_libraries` if there are no private dependencies
- Remove `if(ENABLE_BENCHMARKS)` block if benchmarks are not needed for this library
