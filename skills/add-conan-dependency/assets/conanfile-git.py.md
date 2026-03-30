# conanfile.py Template — Git Source (Most Common)

**Output path:** `conan/{dependency_name}/conanfile.py`

This is the standard pattern for libraries fetched from a Git repository.

Variables to substitute:
- `{{CLASS_NAME}}` — PascalCase recipe class name (e.g., `NloptRecipe`)
- `{{PACKAGE_NAME}}` — Conan package name (e.g., `nlopt`)
- `{{VERSION}}` — Package version (e.g., `2.10.0`)
- `{{LICENSE}}` — SPDX license identifier
- `{{AUTHOR}}` — Library author
- `{{GIT_URL}}` — Git repository URL
- `{{GIT_TAG}}` — Git tag or branch to checkout (e.g., `v2.10.0`, `main`)
- `{{DESCRIPTION}}` — Short package description
- `{{TOPICS}}` — Tuple of topic strings
- `{{CUSTOM_OPTIONS}}` — Additional options dict entries (optional)
- `{{CUSTOM_DEFAULT_OPTIONS}}` — Default values for custom options (optional)
- `{{CMAKE_VARIABLES}}` — Additional `tc.variables[...] = ...` lines
- `{{SOURCE_PATCHES}}` — Python code for patching source in `source()` (optional)
- `{{HEADER_COPY_RULES}}` — `copy()` calls in `package()` for fallback header installation
- `{{PACKAGE_INFO}}` — `package_info()` body with cmake_file_name, cmake_target_name, libs
- `{{REQUIREMENTS}}` — `requirements()` method body (optional)
- `{{CXX_STANDARD_OVERRIDE}}` — `self.settings.compiler.cppstd = "17"` etc. in `configure()` (optional)

```python
from conan import ConanFile
from conan.tools.cmake import CMakeToolchain, CMake, cmake_layout, CMakeDeps
from conan.tools.scm import Git
from conan.tools.files import copy
import os


class {{CLASS_NAME}}(ConanFile):
    name = "{{PACKAGE_NAME}}"
    version = "{{VERSION}}"
    package_type = "library"

    # Metadata
    license = "{{LICENSE}}"
    author = "{{AUTHOR}}"
    url = "{{GIT_URL}}"
    description = "{{DESCRIPTION}}"
    topics = ({{TOPICS}})

    # Binary configuration
    settings = "os", "compiler", "build_type", "arch"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        {{CUSTOM_OPTIONS}}
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        {{CUSTOM_DEFAULT_OPTIONS}}
    }

    def configure(self):
        {{CXX_STANDARD_OVERRIDE}}

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def source(self):
        git = Git(self)
        git.clone(url="{{GIT_URL}}", target=".")
        git.checkout("{{GIT_TAG}}")
        {{SOURCE_PATCHES}}

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_EXPORT_COMPILE_COMMANDS"] = "ON"
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        {{CMAKE_VARIABLES}}
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        {{HEADER_COPY_RULES}}

    def package_info(self):
        {{PACKAGE_INFO}}

    {{REQUIREMENTS}}

    def layout(self):
        cmake_layout(self)
```

## Minimal Example (nlopt-style)

```python
from conan import ConanFile
from conan.tools.cmake import CMakeToolchain, CMake, cmake_layout, CMakeDeps
from conan.tools.scm import Git
from conan.tools.files import copy
import os


class NloptRecipe(ConanFile):
    name = "nlopt"
    version = "2.10.0"
    package_type = "library"

    license = "MIT"
    author = "Steven G. Johnson"
    url = "https://github.com/stevengj/nlopt"
    description = "NLopt - nonlinear optimization library"
    topics = ("nlopt", "optimization", "nonlinear")

    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def source(self):
        git = Git(self)
        git.clone(url="https://github.com/stevengj/nlopt.git", target=".")
        git.checkout("v2.10.0")

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()
        tc = CMakeToolchain(self)
        tc.variables["CMAKE_EXPORT_COMPILE_COMMANDS"] = "ON"
        tc.variables["BUILD_SHARED_LIBS"] = self.options.shared
        tc.variables["NLOPT_PYTHON"] = "OFF"
        tc.variables["NLOPT_OCTAVE"] = "OFF"
        tc.variables["NLOPT_MATLAB"] = "OFF"
        tc.variables["NLOPT_GUILE"] = "OFF"
        tc.variables["NLOPT_SWIG"] = "OFF"
        tc.variables["NLOPT_TESTS"] = "OFF"
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()
        copy(self, "*.h",
             src=os.path.join(self.source_folder, "src", "api"),
             dst=os.path.join(self.package_folder, "include"),
             keep_path=False)
        copy(self, "*.hpp",
             src=os.path.join(self.source_folder, "src", "api"),
             dst=os.path.join(self.package_folder, "include"),
             keep_path=False)

    def package_info(self):
        self.cpp_info.set_property("cmake_file_name", "NLopt")
        self.cpp_info.set_property("cmake_target_name", "NLopt::nlopt")
        self.cpp_info.libs = ["nlopt"]
        self.cpp_info.includedirs = ["include"]
        if self.settings.os != "Windows":
            self.cpp_info.system_libs = ["m"]

    def layout(self):
        cmake_layout(self)
```
