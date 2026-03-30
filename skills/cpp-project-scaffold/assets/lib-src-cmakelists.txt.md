# Library src/CMakeLists.txt Template

Variables to substitute:
- `{{LIB_VAR_PREFIX}}` — Uppercase variable prefix matching parent (e.g., `MY_ENGINE_CORE`)

```cmake
target_sources(${{{LIB_VAR_PREFIX}}_NAME} PRIVATE
    placeholder.cpp
)
```

## Notes

- Sources are added via `target_sources()` referencing the library target variable from the parent
- Headers live alongside sources in `src/` and are installed by the parent CMakeLists via `install(DIRECTORY src/ ...)`
- As the library grows, add subdirectories with their own `target_sources()` calls:

```cmake
add_subdirectory(ModuleName)

target_sources(${{{LIB_VAR_PREFIX}}_NAME} PRIVATE
    TopLevelFile.cpp
)
```
