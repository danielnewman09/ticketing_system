# Placeholder Source Files Template

Variables to substitute:
- `{{NAMESPACE}}` — A short, terse C++ namespace (single level, no nesting). Pick a concise abbreviation, e.g., `calc` not `calculator::calculation_engine`, `ui` not `user_interface`, `phys` not `physics_engine`
- `{{LIB_DIR_NAME}}` — Library directory name only (e.g., `user_interface`), NOT the full path from project root
- `{{LIB_TARGET_NAME}}` — Library target name

**CRITICAL**: `#include` paths start from the library directory name, NOT the project root directory.
For a project `calculator` with library `user_interface`, the include is:
```cpp
#include "user_interface/src/placeholder.hpp"   // CORRECT
// NOT: #include "calculator/user_interface/src/placeholder.hpp"
```
This works because the CMake include directory is set to the library parent directory.

## {{LIB_DIR_NAME}}/src/placeholder.hpp

```cpp
#ifndef PLACEHOLDER_HPP
#define PLACEHOLDER_HPP

namespace {{NAMESPACE}} {

/// Placeholder function — replace with real code
int placeholder();

}  // namespace {{NAMESPACE}}

#endif //PLACEHOLDER_HPP
```

## {{LIB_DIR_NAME}}/src/placeholder.cpp

```cpp
#include "{{LIB_DIR_NAME}}/src/placeholder.hpp"

namespace {{NAMESPACE}} {

int placeholder() {
    return 42;
}

}  // namespace {{NAMESPACE}}
```

## {{LIB_DIR_NAME}}/test/placeholder_test.cpp

```cpp
#include <gtest/gtest.h>

#include "{{LIB_DIR_NAME}}/src/placeholder.hpp"

TEST({{LIB_TARGET_NAME}}, Placeholder) {
    EXPECT_EQ({{NAMESPACE}}::placeholder(), 42);
}
```
