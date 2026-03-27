# Library src/CMakeLists.txt Template

Variables to substitute:
- `{{LIB_VAR_PREFIX}}` — Uppercase variable prefix matching parent (e.g., `MY_ENGINE_CORE`)

```cmake
target_sources(${{{LIB_VAR_PREFIX}}_NAME} PRIVATE
    placeholder.cpp
)

set(
    HEADER_FILES
        ${CMAKE_CURRENT_SOURCE_DIR}/placeholder.hpp
    # Add more headers here as needed
    PARENT_SCOPE
)
```

## Notes

- Sources are added via `target_sources()` referencing the library target variable from the parent
- `HEADER_FILES` is set with `PARENT_SCOPE` so the parent CMakeLists can use it for installation
- As the library grows, add subdirectories with their own `target_sources()` calls and update `HEADER_FILES`
- Subdirectory pattern for modules:

```cmake
add_subdirectory(ModuleName)

target_sources(${{{LIB_VAR_PREFIX}}_NAME} PRIVATE
    TopLevelFile.cpp
)

set(
    HEADER_FILES
        ${CMAKE_CURRENT_SOURCE_DIR}/TopLevelFile.hpp
    PARENT_SCOPE
)
```
