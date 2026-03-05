# Ticket 0002: GUI Window Creation

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
**Estimated Complexity**: Medium
**Target Component(s)**: GUI, Application
**Languages**: C++
**Requires Math Design**: No
**Generate Tutorial**: No
**Parent Ticket**: None
**Blocks**: [0003_calculator_ui_components](0003_calculator_ui_components.md)

---

## Summary

Create the main application window for the Calculator using a cross-platform GUI toolkit. The window should have a fixed size appropriate for a calculator layout, a title bar reading "Calculator", and a clean application lifecycle (initialize, run event loop, teardown). The architecture must cleanly separate the windowing/rendering layer from the calculator logic to support testability.

---

## Requirements

| ID | Requirement | Verification | Test/Proof | Status |
|----|-------------|--------------|------------|--------|
| R1 | Application launches and displays a window titled "Calculator" | Inspection | — | Draft |
| R2 | Window dimensions are 320x480 pixels | Automated | `tests/gui/test_window.cpp::WindowSize` | Draft |
| R3 | Window is not resizable | Automated | `tests/gui/test_window.cpp::WindowNotResizable` | Draft |
| R4 | Closing the window exits the application with code 0 | Automated | `tests/gui/test_window.cpp::CleanExit` | Draft |
| R5 | Application class is separate from Calculator class (no calculator logic in Application) | Review | — | Draft |
| R6 | Calculator class stub exists with default constructor and destructor | Automated | `tests/unit/test_calculator_stub.cpp::ConstructDestruct` | Draft |
| R7 | No memory leaks or resource leaks on shutdown | Automated | `tests/gui/test_window.cpp::ASAN` | Draft |
| R8 | Builds cleanly with all three CMake presets from ticket 0001 | Automated | `tests/build/test_build.py::test_zero_warnings_all_presets` | Draft |

---

## Design Notes

- Create an `Application` class in `include/calculator/Application.h` and `src/Application.cpp`
- Responsibilities:
  - Initialize the GUI framework (window, renderer/context)
  - Run the main event loop
  - Handle graceful shutdown (close button, OS quit signals)
- Public interface:
  - `Application()` — constructor, initializes framework
  - `~Application()` — destructor, tears down framework
  - `int run()` — enters the main loop, returns exit code
  - `bool isRunning() const` — returns whether the main loop is active
- Window should be centered on screen at launch
- Main loop structure:
  1. Poll/process OS events (keyboard, mouse, window close)
  2. Handle the quit event to break the loop
  3. Clear the rendering surface each frame
  4. (Placeholder) Render UI — this is where ticket 0003 hooks in
  5. Present/swap the frame buffer
- Target a reasonable frame rate (vsync or 60 FPS cap)
- Define a `Calculator` class stub in `include/calculator/Calculator.h` and `src/Calculator.cpp`
- `Application` owns a `Calculator` instance by composition
- `main()` creates an `Application` instance and calls `run()`

---

## Acceptance Criteria

1. [ ] All requirements with Verification=Automated have passing tests
2. [ ] Manual inspection confirms window renders with correct title
3. [ ] Code review confirms separation of concerns (R5)
4. [ ] Builds cleanly with all three CMake presets

---

## Files

### New Files
- `include/calculator/Application.h` — Application class declaration
- `src/Application.cpp` — Application class implementation
- `include/calculator/Calculator.h` — Calculator class stub declaration
- `src/Calculator.cpp` — Calculator class stub implementation

### Modified Files
- `src/main.cpp` — Updated to instantiate Application and call run()
- `src/CMakeLists.txt` — Add new source files to calculator target

---

## References
- Ticket 0001 (dependency — build system must be in place)
- Blocks 0003
