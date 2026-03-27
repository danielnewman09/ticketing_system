# conanfile.py Template

Variables to substitute:
- `{{PROJECT_NAME}}` — Conan package name
- `{{CXX_STANDARD}}` — C++ standard as string (e.g., "20")
- `{{ADDITIONAL_REQUIREMENTS}}` — Extra `self.requires()` calls
- `{{FMT_WORKAROUND}}` — Include `tc.cache_variables["CMAKE_CXX_FLAGS"] = "-DFMT_USE_CONSTEVAL=0 -DFMT_CONSTEVAL="` if spdlog/fmt is a dependency

```python
from conan import ConanFile
from conan.tools.cmake import CMakeToolchain, CMake, cmake_layout, CMakeDeps


class {{PROJECT_CLASS_NAME}}(ConanFile):
    name = "{{PROJECT_NAME}}"
    version = "1.0"
    package_type = "application"

    # Binary configuration
    settings = "os", "compiler", "build_type", "arch"

    # Options
    options = {
        "enable_coverage": [True, False],
        "warnings_as_errors": [True, False],
        "enable_clang_tidy": [True, False],
        "enable_benchmarks": [True, False],
        "enable_profiling": [True, False],
    }
    default_options = {
        "enable_coverage": False,
        "warnings_as_errors": False,
        "enable_clang_tidy": False,
        "enable_benchmarks": False,
        "enable_profiling": False,
    }

    def configure(self):
        self.settings.compiler.cppstd = "{{CXX_STANDARD}}"

    exports_sources = "../../CMakeLists.txt", "../../src/*", "../../test/*", "../../*.cmake"

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()
        tc = CMakeToolchain(self)

        # Pass options to CMake
        tc.variables["ENABLE_COVERAGE"] = self.options.enable_coverage
        tc.variables["ENABLE_CLANG_TIDY"] = self.options.enable_clang_tidy
        tc.variables["ENABLE_BENCHMARKS"] = self.options.enable_benchmarks
        tc.variables["ENABLE_PROFILING"] = self.options.enable_profiling

        # Enable warnings as errors for Release builds by default
        if self.options.warnings_as_errors:
            tc.variables["WARNINGS_AS_ERRORS"] = True
        elif str(self.settings.build_type) == "Release":
            tc.variables["WARNINGS_AS_ERRORS"] = True
        else:
            tc.variables["WARNINGS_AS_ERRORS"] = False

        build_type = str(self.settings.build_type).lower()
        tc.variables["CMAKE_RUNTIME_OUTPUT_DIRECTORY"] = \
            f"${{CMAKE_BINARY_DIR}}/{build_type}"
        tc.variables["CMAKE_LIBRARY_OUTPUT_DIRECTORY"] = \
            f"${{CMAKE_BINARY_DIR}}/{build_type}"
        tc.variables["CMAKE_ARCHIVE_OUTPUT_DIRECTORY"] = \
            f"${{CMAKE_BINARY_DIR}}/{build_type}"

        # Set install prefix to repository root's installs directory
        import os
        install_prefix = os.path.abspath(os.path.join(self.recipe_folder, "..", "..", "installs"))
        tc.variables["CMAKE_INSTALL_PREFIX"] = install_prefix

        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

    def requirements(self):
        self.requires("gtest/1.15.0")
        {{ADDITIONAL_REQUIREMENTS}}

        # Optional benchmark dependency
        if self.options.enable_benchmarks:
            self.requires("benchmark/1.9.1")

    def build_requirements(self):
        self.tool_requires("cmake/3.22.6")

    def layout(self):
        cmake_layout(self)
        self.folders.base_install = "installs"

    def package_info(self):
        self.cpp_info.libs = []  # Adjust based on actual library names
```

## Notes

- `{{PROJECT_CLASS_NAME}}` should be the PascalCase version of the project name for the class
- `{{ADDITIONAL_REQUIREMENTS}}` is a block of `self.requires("package/version")` lines
- GTest is always included as a requirement
- Google Benchmark is optional, gated behind `enable_benchmarks`
- The `exports_sources` paths may need adjustment based on actual project structure
