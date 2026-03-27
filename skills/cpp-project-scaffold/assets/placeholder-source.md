# Placeholder Source Files Template

Variables to substitute:
- `{{NAMESPACE}}` — C++ namespace (e.g., `my_engine_core`)
- `{{LIB_DIR_NAME}}` — Library directory for includes (e.g., `my-engine-core`)
- `{{LIB_TARGET_NAME}}` — Library target name (e.g., `my_engine_core`)

## src/placeholder.hpp

```cpp
#pragma once

namespace {{NAMESPACE}} {

/// Placeholder function — replace with real code
int placeholder();

}  // namespace {{NAMESPACE}}
```

## src/placeholder.cpp

```cpp
#include "{{LIB_DIR_NAME}}/src/placeholder.hpp"

namespace {{NAMESPACE}} {

int placeholder() {
    return 42;
}

}  // namespace {{NAMESPACE}}
```

## test/placeholder_test.cpp

```cpp
#include <gtest/gtest.h>

#include "{{LIB_DIR_NAME}}/src/placeholder.hpp"

TEST({{LIB_TARGET_NAME}}, Placeholder) {
    EXPECT_EQ({{NAMESPACE}}::placeholder(), 42);
}
```
