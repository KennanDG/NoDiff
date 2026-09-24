# Skill: Write Tests

Purpose: Add focused tests for behavior that changed or broke.

Use when:
- The user asks for tests.
- A fix needs regression coverage.

Allowed tools:
- list_files
- search_repo
- read_file
- write_file
- run_validation_suite

Steps:
1. Find the current repository's existing tests and choose the closest matching location. If no tests exist, use the repository's documented test layout or ask before adding a new convention.
2. Match existing test style and fixtures in this repository.
3. Add the smallest meaningful test.
4. Prefer unit tests before integration tests.
5. Run the targeted test file.

Rules:
- Keep test files inside the current repository, using paths relative to its root. Never reuse a path from another project.
- Do not add brittle tests tied to implementation details unless necessary.
- Do not require external services unless existing tests already do.
- Always validate through the coding agent validation module.
