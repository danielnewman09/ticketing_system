# C Library Handling Reference

Special handling required when the dependency is a pure C library (no C++ code).

## The Problem

Conan sets `compiler.cppstd` and `compiler.libcxx` by default, which don't apply to
C-only libraries. This can cause:
- Package ID conflicts (same C library built with different C++ standards)
- Layout computation issues in `cmake_layout()`

## The Fix

Remove C++ compiler settings in `configure()`:

```python
def configure(self):
    if self.options.shared:
        self.options.rm_safe("fPIC")
    # This is a C library, not C++
    self.settings.rm_safe("compiler.libcxx")
    self.settings.rm_safe("compiler.cppstd")
```

## Generated CMakeLists.txt

When generating a CMakeLists.txt for a C library, use `project(... C)`:

```python
cmakelists = f"""
cmake_minimum_required(VERSION 3.15)
project({self.name} C)

add_library({self.name} {self.name}.c)
...
"""
```

## Package Info

After removing compiler settings, you may need to explicitly set `includedirs` and
`libdirs` because `cmake_layout()` computes them differently:

```python
def package_info(self):
    self.cpp_info.libs = ["sqlite3"]
    # Explicitly set — required because configure() removes compiler settings
    self.cpp_info.includedirs = ["include"]
    self.cpp_info.libdirs = ["lib"]
    self.cpp_info.set_property("cmake_file_name", "SQLite3")
    self.cpp_info.set_property("cmake_target_name", "SQLite3::SQLite3")
```

## Common System Libraries for C

Platform-specific system libraries commonly needed by C libraries:

| Library | Platform | Purpose |
|---------|----------|---------|
| `m` | Linux, macOS | Math library (sin, cos, sqrt, etc.) |
| `pthread` | Linux | POSIX threads |
| `dl` | Linux | Dynamic loading (dlopen, dlsym) |
| `rt` | Linux | Real-time extensions |

```python
if self.settings.os in ["Linux", "FreeBSD"]:
    self.cpp_info.system_libs = ["pthread", "dl", "m"]
```

## C++ Standard Override (Not C-only)

If the library is C++ but incompatible with the project's standard (e.g., uses
syntax removed in C++20), override the standard in `configure()`:

```python
def configure(self):
    # Library uses syntax removed in C++20; force C++17
    self.settings.compiler.cppstd = "17"
```

The resulting `.a`/`.so` links fine with C++20 consumers — the standard only
affects compilation of the library itself.
