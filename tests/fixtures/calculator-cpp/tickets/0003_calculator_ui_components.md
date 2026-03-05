# Ticket 0003: Calculator UI Components and Logic

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
**Target Component(s)**: GUI, Calculator Logic
**Languages**: C++
**Requires Math Design**: No
**Generate Tutorial**: No
**Parent Ticket**: None
**Blocks**: [0004_unit_tests_gtest](0004_unit_tests_gtest.md)

---

## Summary

Build the full calculator user interface and computation logic. This includes a display screen showing input and results, a number pad (0-9 with decimal point), arithmetic operation buttons (+, -, x, /), an Enter/equals button to evaluate, and a Clear button to reset. The calculator logic must be fully decoupled from the GUI rendering so that the `Calculator` class can be tested independently without any GUI dependencies.

---

## Requirements

| ID | Requirement | Verification | Test/Proof | Status |
|----|-------------|--------------|------------|--------|
| R1 | Display shows "0" on initial state and after clear | Automated | `tests/unit/CalculatorTest.cpp::InitialDisplay` | Draft |
| R2 | Pressing digit buttons updates the display with the entered number | Automated | `tests/unit/CalculatorTest.cpp::DigitEntry` | Draft |
| R3 | Leading zeros are suppressed (except "0.") | Automated | `tests/unit/CalculatorTest.cpp::LeadingZeroSuppression` | Draft |
| R4 | Decimal point appends correctly and cannot be entered twice per number | Automated | `tests/unit/CalculatorTest.cpp::DecimalPointBehavior` | Draft |
| R5 | All four arithmetic operations (+, -, x, /) produce correct results | Automated | `tests/unit/CalculatorTest.cpp::ArithmeticOperations` | Draft |
| R6 | Operator chaining evaluates intermediate results before applying the new operator | Automated | `tests/unit/CalculatorTest.cpp::OperatorChaining` | Draft |
| R7 | Division by zero displays "Error" and blocks input until Clear | Automated | `tests/unit/CalculatorTest.cpp::DivisionByZero` | Draft |
| R8 | Clear resets display to "0" and restores full functionality from any state | Automated | `tests/unit/CalculatorTest.cpp::ClearBehavior` | Draft |
| R9 | Keyboard keys 0-9, ., +, -, *, /, Enter/=, Escape/C map to calculator actions | Automated | `tests/gui/test_keyboard.cpp::KeyboardMapping` | Draft |
| R10 | Calculator class has no dependency on any GUI headers or libraries | Review | — | Draft |
| R11 | Display shows up to 10 significant digits with trailing zeros stripped | Automated | `tests/unit/CalculatorTest.cpp::DisplayFormatting` | Draft |

---

## Design Notes

- Expand the `Calculator` class from ticket 0002 with the following public interface:
  - `void pressDigit(int digit)` — Append digit (0-9) to current input
  - `void pressDecimal()` — Append decimal point (no-op if already present)
  - `void pressOperator(Operator op)` — Set pending operation
  - `void pressEquals()` — Evaluate the pending operation
  - `void pressClear()` — Reset to initial state
  - `std::string getDisplay() const` — Return the current display string
- Define `enum class Operator { Add, Subtract, Multiply, Divide }`
- Internal state: `currentValue_`, `inputBuffer_`, `pendingOperator_`, `hasDecimal_`, `newInput_`
- Button layout:
  ```
  ┌─────────────────────────┐
  │           0.00          │  <- Display
  ├──────┬──────┬──────┬────┤
  │  7   │  8   │  9   │  / │
  ├──────┼──────┼──────┼────┤
  │  4   │  5   │  6   │  x │
  ├──────┼──────┼──────┼────┤
  │  1   │  2   │  3   │  - │
  ├──────┼──────┼──────┼────┤
  │  C   │  0   │  .   │  + │
  ├──────┴──────┴──────┼────┤
  │                    │  = │
  └────────────────────┴────┘
  ```
- Each button must have a visible label and respond to mouse clicks
- Buttons should have visual feedback on hover/press
- The `Application` class owns the `Calculator` instance
- Each button click or keyboard event calls the corresponding `Calculator` method
- After each action, the display re-reads `Calculator::getDisplay()` to update

---

## Acceptance Criteria

1. [ ] All requirements with Verification=Automated have passing tests
2. [ ] Code review confirms Calculator class has zero GUI dependencies (R10)
3. [ ] Manual inspection confirms UI layout matches Design Notes grid
4. [ ] Builds cleanly with all three CMake presets

---

## Files

### New Files
- `include/calculator/Operator.h` — Operator enum definition

### Modified Files
- `include/calculator/Calculator.h` — Full calculator interface
- `src/Calculator.cpp` — Calculator logic implementation
- `src/Application.cpp` — Wire UI rendering and input handling to Calculator
- `include/calculator/Application.h` — Add render/input helpers if needed
- `src/CMakeLists.txt` — Add any new source files

---

## References
- Ticket 0001 (dependency — build system)
- Ticket 0002 (dependency — window and class stubs)
- Blocks 0004
