from __future__ import annotations

from pathlib import Path

from agent_runtime.agents.coding.tests.discovery import discover_targeted_tests
from agent_runtime.agents.coding.tests.profiles import default_validation_profile
from agent_runtime.agents.coding.tests.results import (
    ValidationCommand,
    ValidationResult,
    ValidationSuiteResult,
)
from agent_runtime.agents.coding.tests.runtime import (
    ResolvedValidationCommand,
    resolve_validation_commands,
)
from agent_runtime.agents.coding.tools.shell import run_command


def _runtime_execution_unavailable(
    result: dict[str, object],
    resolved: ResolvedValidationCommand,
) -> bool:
    try:
        returncode = int(result.get("returncode", 0))
    except (TypeError, ValueError):
        returncode = 1

    if returncode == 0:
        return False

    output = "\n".join(
        (
            str(result.get("stdout", "")),
            str(result.get("stderr", "")),
        )
    ).lower()

    generic_markers = (
        "executable not found",
        "is not recognized as an internal or external command",
        "failed trusted-runtime validation",
    )

    if any(marker in output for marker in generic_markers):
        return True

    if resolved.tool == "pytest":
        return (
            "no module named pytest" in output
            or "no module named 'pytest'" in output
        )

    if resolved.tool == "ruff":
        return (
            "no module named ruff" in output
            or "no module named 'ruff'" in output
        )

    return False



def run_validation_suite(
    repo_root: Path,
    *,
    runtime_root: Path | None = None,
    changed_files: list[str] | None = None,
    requested_commands: list[str] | None = None,
    allow_shell: bool = True,
    timeout_seconds: int = 60,
    profile_name: str = "default",
) -> ValidationSuiteResult:
    

    commands = build_validation_commands(
        repo_root,
        changed_files=changed_files or [],
        requested_commands=requested_commands or [],
    )

    suite = ValidationSuiteResult(profile=profile_name)

    if not allow_shell:
        suite.results = [
            ValidationResult(
                command=command.command,
                returncode=126,
                stderr="Shell disabled.",
                reason=command.reason,
            )

            for command in commands
        ]

        return suite

        runtime_root = (runtime_root or repo_root).resolve()

    for command in commands:
        resolved_candidates = resolve_validation_commands(
            runtime_root=runtime_root,
            execution_root=repo_root,
            command=command.command,
        )

        # Non-Python validation such as npm/npx continues through the
        # existing restricted shell-command path.
        if not resolved_candidates:
            raw_result = run_command(
                repo_root,
                command.command,
                timeout_seconds=timeout_seconds,
            )

            suite.results.append(
                ValidationResult(
                    command=str(
                        raw_result.get(
                            "command",
                            command.command,
                        )
                    ),
                    returncode=int(
                        raw_result.get(
                            "returncode",
                            1,
                        )
                    ),
                    stdout=str(raw_result.get("stdout", "")),
                    stderr=str(raw_result.get("stderr", "")),
                    reason=command.reason,
                )
            )
            continue

        raw_result: dict[str, object] | None = None

        for resolved in resolved_candidates:
            raw_result = run_command(
                repo_root,
                resolved.display_command,
                timeout_seconds=timeout_seconds,
                resolved_tokens=list(resolved.tokens),
                trusted_prefix=resolved.trusted_prefix,
            )

            # A real test/lint failure belongs to the code being validated.
            # Stop immediately rather than retrying under another interpreter.
            if not _runtime_execution_unavailable(
                raw_result,
                resolved,
            ):
                break

        if raw_result is None:
            raw_result = {
                "command": command.command,
                "returncode": 127,
                "stdout": "",
                "stderr": (
                    "Validation runtime unavailable: no suitable project "
                    "virtual environment, uv runtime, or system Python "
                    "could execute this validation command."
                ),
            }

        suite.results.append(
            ValidationResult(
                command=str(
                    raw_result.get(
                        "command",
                        command.command,
                    )
                ),
                returncode=int(
                    raw_result.get(
                        "returncode",
                        1,
                    )
                ),
                stdout=str(raw_result.get("stdout", "")),
                stderr=str(raw_result.get("stderr", "")),
                reason=command.reason,
            )
        )

    return suite




def build_validation_commands(
    repo_root: Path,
    *,
    changed_files: list[str],
    requested_commands: list[str],
) -> list[ValidationCommand]:
    
    commands: list[ValidationCommand] = []

    commands.extend(discover_targeted_tests(repo_root, changed_files))

    for command in requested_commands:
        commands.append(
            ValidationCommand(
                command=command,
                reason="Requested by planner or patcher.",
            )
        )

    if not commands:
        commands.extend(default_validation_profile(repo_root))

    return _dedupe_commands(commands)




def _dedupe_commands(commands: list[ValidationCommand]) -> list[ValidationCommand]:
    seen: set[str] = set()
    result: list[ValidationCommand] = []

    for command in commands:
        normalized = command.command.strip()

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        result.append(command)

    return result