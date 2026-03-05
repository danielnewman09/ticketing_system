# Ticket 0001: CMake Project Configuration with Presets

## Status
- [x] Draft
- [ ] C++ Design
- [ ] C++ Design Review
- [ ] C++ Test Writing
- [ ] C++ Implementation
- [ ] C++ Quality Gate
- [ ] Integration Test
- [ ] Implementation Review
- [ ] Documentation
- [ ] Merged / Complete

**Current Phase**: Draft
**Type**: Feature
**Priority**: Critical
**Assignee**: TBD
**Created**: 2026-03-02
**Estimated Complexity**: Medium
**Target Component(s)**: Build System
**Languages**: C++, CMake
**Requires Math Design**: No
**Generate Tutorial**: No
**Parent Ticket**: None
**Blocks**: [0002_gui_window_creation](0002_gui_window_creation.md), [0003_calculator_ui_components](0003_calculator_ui_components.md), [0004_unit_tests_gtest](0004_unit_tests_gtest.md)

---

## Summary

Set up the CMake build system for the Calculator GUI application. This includes the top-level `CMakeLists.txt`, CMake presets for Debug, Release, and Test configurations, dependency management for the GUI toolkit (Qt6 or Dear ImGui via SDL2), and the foundational project structure. All subsequent tickets depend on this configuration being in place.

---

## Requirements

| ID | Requirement | Verification | Test/Proof | Status |
|----|-------------|--------------|------------|--------|
| R1 | C++17 standard is enforced (CMAKE_CXX_STANDARD 17, REQUIRED ON, EXTENSIONS OFF) | Automated | `tests/build/test_cmake_config.py::test_cpp17_enforced` | Draft |
| R2 | CMakePresets.json defines configure presets for debug, release, and test | Automated | `tests/build/test_presets.py::test_configure_presets_exist` | Draft |
| R3 | CMakePresets.json defines build presets inheriting from each configure preset | Automated | `tests/build/test_presets.py::test_build_presets_exist` | Draft |
| R4 | CMakePresets.json defines a test preset that runs CTest with --output-on-failure | Automated | `tests/build/test_presets.py::test_test_preset_ctest_flags` | Draft |
| R5 | Test configure preset enables coverage flags (--coverage or -fprofile-arcs -ftest-coverage) | Automated | `tests/build/test_presets.py::test_coverage_flags_enabled` | Draft |
| R6 | GTest v1.14+ is available via FetchContent under the test configuration | Automated | `tests/build/test_presets.py::test_gtest_fetchcontent` | Draft |
| R7 | All three presets configure and build with zero warnings under -Wall -Wextra -Wpedantic | Automated | `tests/build/test_build.py::test_zero_warnings_all_presets` | Draft |
| R8 | cmake --preset test && ctest --preset test executes successfully | Automated | `tests/build/test_build.py::test_ctest_preset_runs` | Draft |

---

## Design Notes

- Set minimum CMake version to 3.25 (required for presets workflow support)
- Define project name `Calculator` with `CXX` language
- Configure output directories: `CMAKE_RUNTIME_OUTPUT_DIRECTORY`, `CMAKE_LIBRARY_OUTPUT_DIRECTORY`
- Use `find_package()` for the chosen GUI framework
- Use `FetchContent` to pull GTest for the test configuration
- Guard test dependencies with `BUILD_TESTING` option (default ON)
- Directory layout:
  ```
  calculator/
  ├── CMakeLists.txt
  ├── CMakePresets.json
  ├── src/
  │   ├── CMakeLists.txt
  │   └── main.cpp          (minimal entry point, empty main)
  ├── include/
  │   └── calculator/
  └── tests/
      └── CMakeLists.txt
  ```
- `src/CMakeLists.txt` defines the `calculator` executable target
- `tests/CMakeLists.txt` is included conditionally via `BUILD_TESTING`
- Build presets:
  - `debug` — Debug build, build directory `build/debug`
  - `release` — Release build with optimizations, build directory `build/release`
  - `test` — Debug build with coverage flags, build directory `build/test`

---

## Acceptance Criteria

1. [ ] All requirements with Verification=Automated have passing tests
2. [ ] `cmake --preset test && ctest --preset test` succeeds end-to-end
3. [ ] Code review approved
4. [ ] Directory structure matches Design Notes specification

---

## Files

### New Files
- `CMakeLists.txt` — Top-level build configuration
- `CMakePresets.json` — CMake preset definitions
- `src/CMakeLists.txt` — Source target definitions
- `src/main.cpp` — Minimal application entry point
- `tests/CMakeLists.txt` — Test target definitions

---

## References
- Blocks 0002, 0003, 0004
