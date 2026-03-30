---
name: add-conan-dependency
description: Add a new from-source Conan dependency to the project. Creates a local conanfile.py in conan/{dependency_name}/, registers it in the root conanfile.py, updates the VSCode "Create Conan Dependencies" task, and wires the library into the consuming CMakeLists.txt.

<example>
Context: User wants to add a new library dependency.
user: "Add nlopt as a dependency for msd-sim"
assistant: "I'll create a local Conan recipe, register it in the root conanfile, update the VSCode task, and wire it into the consuming library's CMakeLists.txt."
<Follows skill steps>
</example>

<example>
Context: User wants to add a header-only or C library.
user: "Add sqlite3 as a C dependency"
assistant: "I'll create a local Conan recipe with C-only settings (removing cppstd/libcxx) and register it."
<Follows skill steps>
</example>

model: sonnet
---

# /add-conan-dependency Skill

## What This Does

Adds a new third-party library as a **locally-built from-source** Conan dependency. This follows the project convention where all dependencies are compiled locally via recipes stored in `conan/{dependency_name}/conanfile.py`, rather than relying on Conan Center packages.

## Inputs

The user must provide:
1. **Dependency name** — the package name to use in Conan
2. **Source URL** — Git repository URL or download URL
3. **Version / tag** — Git tag or release version
4. **Consuming library** — which project library uses this dependency

The user may optionally provide:
- **License** and **author**
- **Language** — C++ (default) or C-only
- **Custom CMake variables** to set (e.g., disable language bindings, disable tests)
- **Source patches** needed (e.g., update cmake_minimum_required)
- **Components** — if the library exposes multiple CMake targets
- **Custom options** (e.g., `use_long`, `threadsafe`)
- **Dependencies** — other Conan packages this library requires
- **C++ standard override** — if the library needs a different standard than the project

## Steps

### 1. Research the Library

Before generating anything, understand how the library builds:

**First, discover the correct git tag/branch for checkout.** Tag naming
conventions vary widely across projects — do not guess. Run:
```bash
git ls-remote --tags --refs {source_url} | head -30
```
Find the tag that matches the requested version. Use the exact tag name in the
conanfile's `git.checkout()` — do not guess the format.

Then examine the library's build system:
- Check its CMakeLists.txt for the `project()` name, `cmake_minimum_required`, library targets, and install rules
- Identify what CMake variables control build options (tests, apps, language bindings)
- Determine the header install structure
- Check if it has its own dependencies
- Note any known compatibility issues (e.g., C++20 incompatible syntax)

### 2. Create conan/{dependency_name}/conanfile.py

Write the recipe file to `conan/{dependency_name}/conanfile.py`.
Do NOT add extra subdirectories — the conanfile goes directly inside `conan/{dependency_name}/`.

Use the appropriate template:

- **Git source** (most libraries) — `assets/conanfile-git.py.md`
- **Download source** (e.g., tarball/zip) — `assets/conanfile-download.py.md`

Key decisions:
- **Source patching**: If `cmake_minimum_required` is below 3.15, patch it in `source()`. If `add_library` is hardcoded to SHARED/STATIC, patch to use `BUILD_SHARED_LIBS`.
- **Header copying**: Always include fallback `copy()` calls in `package()` for headers, in case `cmake.install()` doesn't install them properly.
- **Component architecture**: Use components in `package_info()` if the library exposes multiple CMake targets (see `references/component-pattern.md`).
- **C-only libraries**: Remove `compiler.libcxx` and `compiler.cppstd` in `configure()`.
- **C++ standard override**: Set `self.settings.compiler.cppstd` in `configure()` if the library isn't compatible with the project's standard.

### 3. Register in Root conanfile.py

Add a `self.requires("{dependency_name}/{version}")` line in the root `conanfile.py`'s `requirements()` method. Follow existing ordering conventions.

If the new library has **transitive Conan dependencies** that aren't already in the root conanfile, also add those (or ensure the local recipe's `requirements()` handles them).

### 4. Update VSCode Task

Add `conan create` commands to the "Create Conan Dependencies" task in `.vscode/tasks.json`. The commands follow this pattern:

```
"conan create conan/{dependency_name} --build=missing -s build_type=Debug;",
"conan create conan/{dependency_name} --build=missing -s build_type=Release;"
```

**Order matters**: Dependencies must be built before their dependents. Place the new commands after any dependencies it requires and before any packages that depend on it.

### 5. Wire into Consuming Library

In the consuming library's `CMakeLists.txt`:

1. Add `find_package({CMakePackageName} CONFIG REQUIRED)` (use CONFIG mode for Conan packages)
2. Add the target to `target_link_libraries()` as PUBLIC or PRIVATE:
   - **PUBLIC** if the dependency appears in the library's public headers
   - **PRIVATE** if only used internally

### 6. Done

After completing steps 1–5, call `write_complete` with the list of files you
created or modified. Do NOT run any build or conan commands — a separate
build verification phase handles that.

## Decision Guide

### When to use `find_package(... CONFIG)` vs `find_package(...)`

- **CONFIG mode** (`find_package(Foo CONFIG REQUIRED)`): Use for all Conan-managed packages. This finds the `FooConfig.cmake` generated by Conan.
- **Module mode** (`find_package(Foo REQUIRED)`): Only for packages that provide their own Find module or are found via CMake's built-in modules.

In this project, all local Conan recipes should use CONFIG mode.

### When to use components vs single target

- **Single target**: When the library has one CMake target (most libraries). Use `cpp_info.libs = ["{name}"]` and set `cmake_target_name`.
- **Components**: When the library has multiple link targets. Use `cpp_info.components["{name}"]` for each.

### Public vs Private linking

- **PUBLIC**: The dependency's headers are exposed in your library's public API (consumers transitively get the dependency)
- **PRIVATE**: The dependency is an implementation detail (consumers don't need it)

### Shared vs Static default

- Default to `shared: False` (static linking) — matches project convention
- Use `shared: True` only when the library specifically requires it

## Reference Files

- `references/component-pattern.md` — How to set up multi-component packages
- `references/source-patching.md` — Common source patches and when to apply them
- `references/c-library-handling.md` — Special handling for pure C libraries
