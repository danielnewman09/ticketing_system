# conanfile.py Template — Generated CMakeLists.txt

For libraries that don't have their own CMake build system. The recipe generates
a CMakeLists.txt at build time.

This pattern is used by the `sqlite3` recipe, where the source is a pure C
amalgamation with no build system.

Variables to substitute:
- `{{CLASS_NAME}}` — PascalCase recipe class name
- `{{PACKAGE_NAME}}` — Conan package name
- `{{VERSION}}` — Package version
- `{{GENERATED_CMAKELISTS}}` — Complete CMakeLists.txt content as Python f-string
- `{{PACKAGE_INFO}}` — `package_info()` body

```python
from conan import ConanFile
from conan.tools.cmake import CMakeToolchain, CMake, cmake_layout, CMakeDeps
from conan.tools.files import download, unzip, copy, save
import os


class {{CLASS_NAME}}(ConanFile):
    name = "{{PACKAGE_NAME}}"
    version = "{{VERSION}}"
    package_type = "library"

    license = "{{LICENSE}}"
    author = "{{AUTHOR}}"
    url = "{{PROJECT_URL}}"
    description = "{{DESCRIPTION}}"
    topics = ({{TOPICS}})

    settings = "os", "compiler", "build_type", "arch"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
    }

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")

    def source(self):
        # Download and extract source
        download(self, "{{DOWNLOAD_URL}}", "source.zip")
        unzip(self, "source.zip")
        copy(self, "*", src="{{EXTRACT_DIR}}", dst=".")

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()
        tc = CMakeToolchain(self)
        tc.generate()

        # Generate CMakeLists.txt since the source doesn't include one
        cmakelists = {{GENERATED_CMAKELISTS}}
        save(self, os.path.join(self.source_folder, "CMakeLists.txt"), cmakelists)

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

    def layout(self):
        cmake_layout(self)

    def package_info(self):
        {{PACKAGE_INFO}}
```

## Example: sqlite3-style generated CMakeLists.txt

```python
cmakelists = f"""
cmake_minimum_required(VERSION 3.15)
project({self.name} C)

add_library({self.name} {self.name}.c)

target_include_directories({self.name} PUBLIC
    $<BUILD_INTERFACE:${{CMAKE_CURRENT_SOURCE_DIR}}>
    $<INSTALL_INTERFACE:include>
)

target_compile_definitions({self.name} PRIVATE
    SOME_DEFINE=1
)

if(UNIX AND NOT APPLE AND NOT EMSCRIPTEN)
    target_link_libraries({self.name} PUBLIC pthread dl m)
endif()

install(TARGETS {self.name}
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

install(FILES {self.name}.h DESTINATION include)
"""
```

## Notes

- Use this when the library has no CMake build system at all
- The generated CMakeLists.txt is created in `generate()`, not `source()`, so option values are available
- For C-only libraries, also remove compiler settings in `configure()`:
  ```python
  def configure(self):
      self.settings.rm_safe("compiler.libcxx")
      self.settings.rm_safe("compiler.cppstd")
  ```
