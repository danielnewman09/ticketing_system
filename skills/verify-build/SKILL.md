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

Run these commands in order **from the project root directory** — the directory containing `CMakeLists.txt` and `conanfile.py`. Confirm your working directory before running commands by checking for these files.

### 0. Confirm Working Directory

Before running any commands, verify you are in the project root:
```bash
ls CMakeLists.txt conanfile.py
```
If these files are not found, navigate to the correct directory or report the issue. Do NOT guess paths relative to a subdirectory.

### 1. Python Environment (if applicable)

If `python/setup.sh` exists, run it first:
```bash
bash python/setup.sh
```

If this step fails, check the error output:
- **Optional dependency failure** (e.g., `doxygen-index` package not found): note the failure and proceed. Documentation targets will be unavailable but the build is not blocked.
- **Core dependency failure** (e.g., pip itself is broken): report `build_success: false` with an explanation.

### 2. Install Dependencies

**Both Debug and Release profiles must be installed** because `CMakeUserPresets.json` includes
paths for both. If only one is installed, CMake will fail to parse the presets file entirely.

```bash
conan install . --build=missing -s build_type=Debug
conan install . --build=missing -s build_type=Release
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

### 6. Stop

**After all 5 pipeline steps pass**, call `task_complete` immediately with `build_success: true`.
Do NOT re-read files to "verify the final state" — the successful command outputs are sufficient.
Do NOT loop reading the same file multiple times.

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
- **CMake presets parse error** (e.g., `Invalid "configurePreset"`): If the error references `conan-release` or a Release preset, the Release Conan profile has not been installed. Run `conan install . --build=missing -s build_type=Release` and retry. Do NOT remove Release presets from `CMakeUserPresets.json` — they are needed for Release builds.
- **CMake presets include error** (missing `build/Release/generators/CMakePresets.json`): Same root cause — run `conan install . --build=missing -s build_type=Release` to generate the file. Do NOT remove the Release include path.

## Important Rules

- Do NOT start over from scratch — make targeted fixes
- Do NOT modify files that aren't related to the error
- Do NOT remove functionality to fix errors (e.g., don't delete Release presets to fix a missing Conan profile — install the profile instead)
- If the build passes but tests fail, still report `build_success: false`
- If you cannot fix an issue after 3 attempts, report failure with a clear explanation
- Call `task_complete` when done with `build_success: true/false`
- Once all pipeline steps pass, call `task_complete` immediately — do NOT re-read files to "verify the final state"
- Do NOT read the same file multiple times with the same arguments — if you've already read it, use the information you have
