# Source Patching Reference

Common patches needed when building third-party libraries from source.

## When to Patch

Patch in `source()` (not `generate()`) because `source()` runs once at download time,
while `generate()` runs every build.

## Common Patches

### 1. cmake_minimum_required Too Low

Many libraries have `cmake_minimum_required(VERSION 2.8)` or `3.0` which triggers
deprecation warnings with modern CMake. Update to 3.15 minimum:

```python
def source(self):
    git = Git(self)
    git.clone(url="...", target=".")
    git.checkout("v1.0.0")

    # Patch cmake_minimum_required
    cmake_file = os.path.join(self.source_folder, "CMakeLists.txt")
    with open(cmake_file, 'r') as f:
        content = f.read()
    content = content.replace(
        'cmake_minimum_required(VERSION 3.0)',
        'cmake_minimum_required(VERSION 3.15)')
    with open(cmake_file, 'w') as f:
        f.write(content)
```

### 2. Hardcoded SHARED/STATIC Library Type

Some libraries hardcode `add_library(foo SHARED ...)` instead of respecting
`BUILD_SHARED_LIBS`. Patch to remove the explicit type:

```python
content = content.replace(
    'add_library(ecos SHARED ${ecos_headers} ${ecos_sources})',
    'add_library(ecos ${ecos_headers} ${ecos_sources})')
```

Then in `generate()`:
```python
tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
```

### 3. Multiple Patches in One Source

```python
def source(self):
    git = Git(self)
    git.clone(url="...", target=".")
    git.checkout("v2.0.10")

    cmake_file = os.path.join(self.source_folder, "CMakeLists.txt")
    with open(cmake_file, 'r') as f:
        content = f.read()

    # Patch 1: cmake_minimum_required
    content = content.replace(
        'cmake_minimum_required(VERSION 3.5)',
        'cmake_minimum_required(VERSION 3.15)')

    # Patch 2: Remove hardcoded SHARED
    content = content.replace(
        'add_library(ecos SHARED ${sources})',
        'add_library(ecos ${sources})')

    with open(cmake_file, 'w') as f:
        f.write(content)
```

## Disabling Unwanted Build Targets

Instead of patching, prefer setting CMake variables in `generate()`:

```python
def generate(self):
    tc = CMakeToolchain(self)
    # Disable tests
    tc.variables["BUILD_TESTING"] = "OFF"
    # Disable applications/tools
    tc.variables["BUILD_APPLICATIONS"] = "OFF"
    # Disable language bindings
    tc.variables["NLOPT_PYTHON"] = "OFF"
    tc.variables["NLOPT_OCTAVE"] = "OFF"
    tc.generate()
```

Check the library's CMakeLists.txt for available `option()` variables.

## When NOT to Patch

- If the library has CMake options to control behavior, use `tc.variables` instead
- If only header installation is wrong, use `copy()` in `package()` as fallback
- Don't patch to add features — keep patches minimal and defensive
