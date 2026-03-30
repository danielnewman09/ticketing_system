---
name: verify-build
description: Verify that a C++ project using Conan 2.x and CMake presets builds and tests pass. Reads errors, makes targeted fixes, and retries. Reusable after scaffolding, dependency changes, or any code modifications.

<example>
Context: After scaffolding a new project.
user: "Verify the build for my-engine at /path/to/my-engine"
assistant: "I'll run the build pipeline and fix any issues."
<Runs conan install, cmake configure, build, and test>
</example>

<example>
Context: After adding a new Conan dependency.
user: "Verify the build after adding spdlog"
assistant: "I'll verify the build compiles and tests still pass with the new dependency."
<Runs build pipeline, fixes linking issues if needed>
</example>

model: sonnet
---

# /verify-build Skill

## What This Does

Runs the standard C++ build pipeline and verifies everything compiles and tests pass. If a step fails, reads the error output and makes targeted fixes before retrying.

This skill is designed to be called after other skills (scaffolding, adding dependencies, code changes) to verify the project is in a good state.

## Build Pipeline

Run these commands in order from the project root:

### 1. Python Environment (if applicable)

If `python/setup.sh` exists, run it first:
```bash
bash python/setup.sh
```

### 2. Install Dependencies

```bash
conan install . --build=missing -s build_type=Debug
```

### 3. Configure

```bash
cmake --preset conan-debug
```

### 4. Build

```bash
cmake --build --preset conan-debug
```

### 5. Test

```bash
ctest --preset conan-debug
```

## Error Handling

When a step fails:

1. **Read the error output carefully** — identify the root cause (missing include, linking error, syntax error, missing dependency, etc.)
2. **Use `read_file` and `list_directory`** to understand the current file state
3. **Use `edit_file` to make a targeted fix** — do not rewrite entire files
4. **Retry only the failing step** — do not re-run earlier successful steps
5. **If a fix introduces new errors**, address them incrementally

Common issues and fixes:
- **Missing include**: Add the `#include` directive or fix the include path
- **Linking error**: Check `target_link_libraries` in CMakeLists.txt
- **Conan package not found**: Verify the dependency is in `conanfile.py` and `find_package` is called
- **Test failure**: Read the test output, fix the test or the code under test
- **CMake configuration error**: Check variable names, target names, and preset definitions

## Important Rules

- Do NOT start over from scratch — make targeted fixes
- Do NOT modify files that aren't related to the error
- If the build passes but tests fail, still report `build_success: false`
- If you cannot fix an issue after 3 attempts, report failure with a clear explanation
- Call `task_complete` when done with `build_success: true/false`
