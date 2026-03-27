# .vscode/tasks.json Template

No variables to substitute — this is project-agnostic.

```json
{
    "version": "2.0.0",
    "inputs": [
        {
            "id": "buildType",
            "description": "Build Type",
            "type": "pickString",
            "options": [
                "Debug",
                "Release"
            ],
            "default": "Release"
        },
        {
            "id": "enableCoverage",
            "description": "Enable Code Coverage",
            "type": "pickString",
            "options": [
                "False",
                "True"
            ],
            "default": "False"
        }
    ],
    "tasks": [
        {
            "label": "Conan Build",
            "type": "shell",
            "command": "conan build . --build=missing -s build_type=${input:buildType} -o \"&:enable_coverage=${input:enableCoverage}\"",
            "group": {
                "kind": "build",
                "isDefault": true
            },
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared"
            },
            "problemMatcher": [
                "$gcc"
            ]
        },
        {
            "label": "CMake Build",
            "hide": true,
            "type": "shell",
            "command": "cmake --build ${command:cmake.buildDirectory}",
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared"
            },
            "problemMatcher": [
                "$gcc"
            ]
        },
        {
            "label": "Generate Coverage Report",
            "type": "shell",
            "command": "cmake",
            "args": [
                "--build",
                "--preset",
                "coverage-all"
            ],
            "group": "test",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": true,
                "panel": "shared"
            },
            "problemMatcher": []
        },
        {
            "label": "Open Coverage Report",
            "type": "shell",
            "command": "open",
            "args": [
                "${workspaceFolder}/build/Debug/coverage/index.html"
            ],
            "presentation": {
                "echo": true,
                "reveal": "silent",
                "focus": false,
                "panel": "shared"
            },
            "problemMatcher": []
        },
        {
            "label": "Setup Python",
            "type": "shell",
            "command": "bash python/setup.sh",
            "options": {
                "cwd": "${workspaceFolder}"
            },
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": true,
                "panel": "shared"
            },
            "problemMatcher": []
        }
    ]
}
```

## Notes

- The "Open Coverage Report" task uses macOS `open` command — change to `xdg-open` for Linux or `start` for Windows
- Add project-specific tasks as needed (e.g., "Create Conan Dependencies" for custom Conan packages)
