# .vscode/c_cpp_properties.json Template

Variables to substitute:
- `{{LIB_PARENT_DIR}}` — Library parent directory name (same as project name)
- `{{CXX_STANDARD}}` — C++ standard as `c++20`, `c++23`, `c++26`
- `{{LIB_INCLUDE_PATHS}}` — One `"${workspaceFolder}/{{LIB_PARENT_DIR}}/{lib}"` entry per library

```json
{
  "configurations": [
    {
      "name": "Mac",
      "includePath": [
        "${workspaceFolder}/**",
        {{LIB_INCLUDE_PATHS}}
        "${workspaceFolder}/test",
        "/Users/*/.conan2/p/**/p/include",
        "/opt/homebrew/include"
      ],
      "defines": [],
      "compilerPath": "/usr/bin/clang++",
      "cStandard": "c17",
      "cppStandard": "{{CXX_STANDARD}}",
      "intelliSenseMode": "macos-clang-arm64",
      "configurationProvider": "ms-vscode.cmake-tools"
    },
    {
      "name": "Linux",
      "includePath": [
        "${workspaceFolder}/{{LIB_PARENT_DIR}}",
        "${workspaceFolder}/test",
        "/home/*/.conan2/p/*/p/include"
      ],
      "defines": [],
      "compilerPath": "/usr/bin/g++",
      "cStandard": "c17",
      "cppStandard": "{{CXX_STANDARD}}",
      "intelliSenseMode": "linux-gcc-x64",
      "configurationProvider": "ms-vscode.cmake-tools"
    }
  ],
  "version": 4
}
```

## Notes

- The Mac configuration uses `**` glob for Conan includes to match the nested cache structure
- Linux uses a simpler `*` glob since paths may differ
- Each library gets its own include path entry so IntelliSense resolves `#include "{lib}/src/..."` correctly
- `configurationProvider` delegates to CMake Tools for build-system-aware IntelliSense
- The `{{LIB_INCLUDE_PATHS}}` variable should expand to one line per library, e.g.:
  ```json
  "${workspaceFolder}/calculator/calculation_engine",
  "${workspaceFolder}/calculator/user_interface",
  ```
