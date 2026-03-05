# Ticket 0005: CI Integration and Coverage Reporting

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
**Priority**: Medium
**Assignee**: TBD
**Created**: 2026-03-02
**Estimated Complexity**: Medium
**Target Component(s)**: CI/CD, Build System
**Languages**: C++, CMake, YAML
**Requires Math Design**: No
**Generate Tutorial**: No
**Parent Ticket**: None
**Blocks**: None

---

## Summary

Create a GitHub Actions CI pipeline that builds the calculator project with all three CMake presets, runs the test suite, generates a coverage report, and enforces the 100% coverage gate on the `Calculator` class. This provides the traceability loop: ticket -> code -> test -> coverage -> CI verification, ensuring the project can serve as a traceable reference implementation.

---

## Requirements

| ID | Requirement | Verification | Test/Proof | Status |
|----|-------------|--------------|------------|--------|
| R1 | .github/workflows/ci.yml exists and is valid YAML | Automated | `tests/ci/test_ci_config.py::test_ci_yaml_valid` | Draft |
| R2 | CI triggers on push to main and pull requests targeting main | Automated | `tests/ci/test_ci_config.py::test_ci_triggers` | Draft |
| R3 | All three presets build successfully in CI with zero warnings (-Werror) | Automated | CI pipeline green status | Draft |
| R4 | Test results are reported in the CI job summary (JUnit XML via --gtest_output) | Inspection | CI job summary | Draft |
| R5 | Coverage report is generated and uploaded as a build artifact | Inspection | CI artifacts list | Draft |
| R6 | Pipeline fails if Calculator.cpp line coverage drops below 100% | Automated | `tests/ci/test_ci_config.py::test_coverage_gate_script` | Draft |
| R7 | Traceability summary artifact is generated with commit SHA, test counts, and coverage data | Automated | `tests/ci/test_ci_config.py::test_traceability_summary_script` | Draft |

---

## Design Notes

- Create `.github/workflows/ci.yml`
- Trigger on: `push` to `main`, `pull_request` targeting `main`
- Use Ubuntu latest runner
- Install dependencies: `cmake`, `g++`, `lcov`, GUI framework dev packages
- Build all three presets in the pipeline:
  - `cmake --preset debug && cmake --build --preset debug`
  - `cmake --preset release && cmake --build --preset release`
  - `cmake --preset test && cmake --build --preset test`
- Run `ctest --preset test` after building the test preset
- Report test results using GitHub Actions test reporter (JUnit XML via `--gtest_output=xml:`)
- After test execution, run lcov/gcov to collect coverage
- Generate HTML coverage report as a build artifact
- Extract line coverage for `src/Calculator.cpp` and `include/calculator/Calculator.h`
- Fail the pipeline if either file is below 100% line coverage
- Upload coverage report as a GitHub Actions artifact
- Generate `build/test/traceability-summary.txt` containing:
  - Commit SHA
  - Ticket references found in commit messages
  - Test count (pass/fail/skip)
  - Coverage percentage per source file

---

## Acceptance Criteria

1. [ ] All requirements with Verification=Automated have passing tests
2. [ ] CI pipeline runs green on a clean push to main
3. [ ] Coverage report artifact is downloadable from CI
4. [ ] Code review approved

---

## Files

### New Files
- `.github/workflows/ci.yml` — GitHub Actions CI pipeline
- `scripts/check-coverage.sh` — Script to parse lcov output and enforce coverage thresholds
- `scripts/traceability-summary.sh` — Script to generate the traceability summary

### Modified Files
- `CMakePresets.json` — Add CI-specific preset if needed (e.g., `-Werror` flag)
- `tests/CMakeLists.txt` — Ensure JUnit XML output is configured for GTest

---

## References
- Ticket 0001 (dependency — CMake presets)
- Ticket 0004 (dependency — tests and coverage infrastructure)
