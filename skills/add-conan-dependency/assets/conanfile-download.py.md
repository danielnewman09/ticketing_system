# conanfile.py Template — Download Source

**Output path:** `conan/{dependency_name}/conanfile.py` (e.g., `conan/sqlite3/conanfile.py`)

For libraries distributed as tarballs/zips rather than Git repositories.

Variables to substitute:
- `{{CLASS_NAME}}` — PascalCase recipe class name
- `{{PACKAGE_NAME}}` — Conan package name
- `{{VERSION}}` — Package version
- `{{DOWNLOAD_URL}}` — Direct download URL
- `{{ARCHIVE_FORMAT}}` — Archive filename (e.g., `source.zip`)
- `{{EXTRACT_DIR}}` — Directory name inside the archive to flatten (optional)
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

    def source(self):
        download(self, "{{DOWNLOAD_URL}}", "{{ARCHIVE_FORMAT}}")
        unzip(self, "{{ARCHIVE_FORMAT}}")
        # Flatten extracted directory if needed
        copy(self, "*", src="{{EXTRACT_DIR}}", dst=".")

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()
        tc = CMakeToolchain(self)
        tc.generate()

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

## Notes

- If the downloaded source doesn't include a CMakeLists.txt, use the `conanfile-generated-cmake.py.md` template instead
- The `copy(self, "*", src=..., dst=".")` pattern flattens a nested archive directory to the source root
