# Component Pattern Reference

Use components when a library exposes **multiple CMake targets** that consumers link against independently.

## When to Use Components

- The library installs multiple `.a`/`.so`/`.lib` files intended as separate link targets
- Consumers may need only a subset of the library (e.g., just the C interface, not the C++ wrapper)
- The library's upstream CMake config defines multiple `::` targets (e.g., `qhull::qhullcpp`, `qhull::qhullstatic_r`)

## When NOT to Use Components

- The library produces a single library file — use simple `cpp_info.libs` instead
- Multiple `.a` files are just implementation details that get linked together

## Pattern

```python
def package_info(self):
    # Set the top-level CMake find_package name
    self.cpp_info.set_property("cmake_file_name", "qhull")

    # Debug suffix handling (if applicable)
    debug_suffix = "d" if self.settings.build_type == "Debug" else ""

    # Component 1: C++ interface
    self.cpp_info.components["qhullcpp"].set_property(
        "cmake_target_name", "qhull::qhullcpp")
    self.cpp_info.components["qhullcpp"].libs = ["qhullcpp"]
    self.cpp_info.components["qhullcpp"].requires = ["qhullstatic_r"]

    # Component 2: C library
    self.cpp_info.components["qhullstatic_r"].set_property(
        "cmake_target_name", "qhull::qhullstatic_r")
    self.cpp_info.components["qhullstatic_r"].libs = [f"qhullstatic_r{debug_suffix}"]

    # Platform-specific system libraries
    if self.settings.os == "Linux":
        self.cpp_info.components["qhullstatic_r"].system_libs = ["m"]
```

## Consumer Side

The consumer's CMakeLists.txt links against the specific component target:

```cmake
find_package(qhull CONFIG REQUIRED)

target_link_libraries(${LIB_NAME}
    PUBLIC
      qhull::qhullstatic_r   # Just the C library
)
```

## Inter-Component Dependencies

Use `requires` to express that one component depends on another:

```python
self.cpp_info.components["qhullcpp"].requires = ["qhullstatic_r"]
```

## External Dependencies in Components

If a component depends on another Conan package:

```python
self.cpp_info.components["mycomp"].requires = ["boost::headers", "sqlite3::sqlite3"]
```

## Debug Suffix Patterns

Libraries commonly use different debug naming. Check the library's CMakeLists.txt:

| Pattern | Example Debug | Example Release |
|---------|--------------|-----------------|
| `d` suffix | `qhullcpp_d` | `qhullcpp` |
| `_d` suffix | `libfoo_d` | `libfoo` |
| `-d` suffix | `bar-d` | `bar` |
| No suffix | `baz` | `baz` |

Handle in `package_info()`:
```python
debug_suffix = "d" if self.settings.build_type == "Debug" else ""
self.cpp_info.components["foo"].libs = [f"foo{debug_suffix}"]
```
