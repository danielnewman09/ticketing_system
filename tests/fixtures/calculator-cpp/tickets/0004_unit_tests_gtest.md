# Ticket 0004: Unit Tests with GTest — 100% Code Coverage

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
**Priority**: High
**Assignee**: TBD
**Created**: 2026-03-02
**Estimated Complexity**: Large
**Target Component(s)**: Tests, Calculator Logic
**Languages**: C++
**Requires Math Design**: No
**Generate Tutorial**: No
**Parent Ticket**: None
**Blocks**: [0005_ci_coverage_reporting](0005_ci_coverage_reporting.md)

---

## Summary

Write comprehensive unit tests for the `Calculator` class using Google Test (GTest). Tests must achieve 100% line and branch coverage of the `Calculator` class logic. The test executable is built exclusively under the `test` CMake preset and run via `ctest --preset test`. Coverage reports are generated using `gcov`/`lcov` and validated as part of the quality gate.

---

## Requirements

| ID | Requirement | Verification | Test/Proof | Status |
|----|-------------|--------------|------------|--------|
| R1 | tests/CalculatorTest.cpp exists and compiles under the test preset | Automated | `tests/build/test_build.py::test_calculator_test_compiles` | Draft |
| R2 | All digits 0-9 are individually tested for entry and display | Automated | `tests/CalculatorTest.cpp::DigitEntry_*` | Draft |
| R3 | All four arithmetic operations are tested with at least 2 cases each | Automated | `tests/CalculatorTest.cpp::Arithmetic_*` | Draft |
| R4 | Division by zero produces "Error" and blocks further input until Clear | Automated | `tests/CalculatorTest.cpp::DivByZero_*` | Draft |
| R5 | Operator chaining is tested with at least 2 chain scenarios | Automated | `tests/CalculatorTest.cpp::Chaining_*` | Draft |
| R6 | Clear resets from every state (mid-entry, post-result, post-error) | Automated | `tests/CalculatorTest.cpp::Clear_*` | Draft |
| R7 | Decimal point behavior is tested (entry, leading decimal, duplicate rejection) | Automated | `tests/CalculatorTest.cpp::Decimal_*` | Draft |
| R8 | Coverage report can be generated via the test preset toolchain | Automated | `tests/build/test_coverage.py::test_coverage_report_generated` | Draft |
| R9 | Calculator.cpp achieves 100% line coverage | Automated | `tests/build/test_coverage.py::test_calculator_cpp_100pct` | Draft |
| R10 | Calculator.h achieves 100% line coverage (all inline methods exercised) | Automated | `tests/build/test_coverage.py::test_calculator_h_100pct` | Draft |
| R11 | All tests pass when run via ctest --preset test | Automated | `tests/build/test_build.py::test_ctest_preset_passes` | Draft |

---

## Design Notes

- Use GTest's `TEST_F()` macros with a `CalculatorTest` fixture
- Fixture creates a fresh `Calculator` instance in `SetUp()`
- No teardown needed (Calculator has no external resources)
- Test cases for digit entry:
  - Single digit: press `5` -> display `"5"`
  - Multi-digit: press `1`, `2`, `3` -> display `"123"`
  - Leading zero suppression: press `0`, `5` -> display `"5"`
  - Zero entry: press `0` -> display `"0"`
- Decimal point test cases:
  - Decimal entry: `3`, `.`, `1`, `4` -> `"3.14"`
  - Leading decimal: `.`, `5` -> `"0.5"`
  - Double decimal ignored: `1`, `.`, `.`, `2` -> `"1.2"`
  - Decimal after operator: `5`, `+`, `.`, `3` -> second operand `"0.3"`
- Equals edge cases:
  - Equals with no operator: `5`, `=` -> `"5"` (no-op)
  - Equals with operator but no second operand: document chosen behavior
  - Multiple equals: document behavior
- Display formatting: trailing zero stripping, integer results without decimal
- Coverage toolchain:
  - Build with `--preset test` (coverage flags from ticket 0001)
  - Run tests via `ctest --preset test`
  - Run `lcov`/`gcov` to collect coverage data
  - Generate HTML report via `genhtml` to `build/test/coverage/`
  - Exclude test files and third-party code (GTest) from coverage

---

## Acceptance Criteria

1. [ ] All requirements with Verification=Automated have passing tests
2. [ ] ctest --preset test runs all tests successfully
3. [ ] Coverage report shows 100% line coverage on Calculator.cpp and Calculator.h
4. [ ] Code review approved

---

## Files

### New Files
- `tests/CalculatorTest.cpp` — GTest test suite for Calculator class
- `cmake/Coverage.cmake` — CMake module for coverage report generation (optional, may inline in tests/CMakeLists.txt)

### Modified Files
- `tests/CMakeLists.txt` — Add CalculatorTest target, link GTest, register with CTest
- `CMakePresets.json` — Add coverage report generation step if needed

---

## References
- Ticket 0001 (dependency — build system and test preset)
- Ticket 0003 (dependency — Calculator class must be implemented)
- Blocks 0005
