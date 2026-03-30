# Library CMakeLists.txt Template (Header-Only / INTERFACE Library)

Variables to substitute:
- `{{LIB_VAR_PREFIX}}` — Uppercase variable prefix (e.g., `MY_ENGINE_TYPES`)
- `{{LIB_TARGET_NAME}}` — CMake target name (e.g., `my_engine_types`)
- `{{LIB_DIR_NAME}}` — Library directory name (e.g., `types`)
- `{{FIND_PACKAGES}}` — `find_package()` calls for external dependencies
- `{{INTERFACE_LINK_LIBRARIES}}` — Interface link targets

```cmake
set({{LIB_VAR_PREFIX}}_NAME {{LIB_TARGET_NAME}})

# Header-only library
add_library(${{{LIB_VAR_PREFIX}}_NAME} INTERFACE)

# Find dependencies
{{FIND_PACKAGES}}

# Link dependencies (INTERFACE — header-only)
target_link_libraries(${{{LIB_VAR_PREFIX}}_NAME}
  INTERFACE
    {{INTERFACE_LINK_LIBRARIES}}
)

# Add include directories
target_include_directories(${{{LIB_VAR_PREFIX}}_NAME}
  INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>
    $<INSTALL_INTERFACE:include>
)

# Installation rules
install(TARGETS ${{{LIB_VAR_PREFIX}}_NAME}
  EXPORT ${{{LIB_VAR_PREFIX}}_NAME}Targets
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

# Install headers — preserves the {lib-dir}/src/ structure for consumers
install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/src/
  DESTINATION include/{{LIB_DIR_NAME}}/src
  FILES_MATCHING PATTERN "*.hpp"
)
```

## Notes

- Header-only libraries use `INTERFACE` for all target properties
- No `src/CMakeLists.txt` needed since there are no compiled sources
- Headers are installed to `include/{lib-dir}/src/` to match the build-time include path `#include "{lib-dir}/src/File.hpp"`
