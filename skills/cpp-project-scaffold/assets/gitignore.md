# .gitignore Template

```
# Build directories
build/
installs/
cmake-build-*/

# IDE
.idea/
.vs/
*.swp
*.swo
*~

# Conan
CMakeUserPresets.json is tracked — do NOT ignore it
# But the generated presets from Conan are in build/ which is already ignored

# Python
python/.venv/
__pycache__/
*.pyc
*.pyo

# Coverage
*.gcno
*.gcda
*.info

# OS
.DS_Store
Thumbs.db

# Compiled objects
*.o
*.obj
*.a
*.lib
*.so
*.dylib
*.dll

# Executables (without extension)
# Don't ignore — too broad. Rely on build/ being ignored.
```
