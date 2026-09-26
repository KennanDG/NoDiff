from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


RuntimeKind = Literal["venv", "uv", "system"]


@dataclass(frozen=True)
class ResolvedValidationCommand:
    runtime_kind: RuntimeKind
    display_command: str
    tokens: tuple[str, ...]
    trusted_prefix: tuple[str, ...]
    tool: str


def _creationflags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _module_available(
    prefix: tuple[str, ...],
    module: str,
    *,
    cwd: Path,
) -> bool:
    code = (
        "import importlib.util, sys; "
        f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
    )

    try:
        completed = subprocess.run(
            [*prefix, "-c", code],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
            creationflags=_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return completed.returncode == 0


def _project_python_candidates(project_root: Path) -> list[Path]:
    if os.name == "nt":
        relative_candidates = (
            Path(".venv/Scripts/python.exe"),
            Path("venv/Scripts/python.exe"),
        )
    else:
        relative_candidates = (
            Path(".venv/bin/python"),
            Path("venv/bin/python"),
        )

    return [
        (project_root / relative).resolve()
        for relative in relative_candidates
        if (project_root / relative).is_file()
    ]


def _system_python_candidates() -> list[tuple[str, ...]]:
    candidates: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    for executable_name in ("python", "python3"):
        executable = shutil.which(executable_name)
        if not executable:
            continue

        candidate = (str(Path(executable).resolve()),)
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    # Windows machines frequently have the py launcher even when python.exe
    # is not directly available on PATH.
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            candidate = (str(Path(launcher).resolve()), "-3")
            if candidate not in seen:
                candidates.append(candidate)

    return candidates


def _has_uv_project(repo_root: Path) -> bool:
    return any(
        (repo_root / name).exists()
        for name in (
            "pyproject.toml",
            "uv.lock",
        )
    )


def _parse_python_validation_command(
    command: str,
) -> tuple[str, list[str]] | None:
    """
    Normalize supported Python validation commands into:

        (tool/module, remaining args)

    Examples:
        pytest test_x.py
        python -m pytest test_x.py
        uv run pytest test_x.py
        uv run python -m pytest test_x.py
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None

    if not tokens:
        return None

    # pytest ...
    if tokens[0] == "pytest":
        return "pytest", tokens[1:]

    # ruff ...
    if tokens[0] == "ruff":
        return "ruff", tokens[1:]

    # python -m <module> ...
    if (
        len(tokens) >= 3
        and tokens[0] in {"python", "python3"}
        and tokens[1] == "-m"
        and tokens[2] in {"pytest", "ruff", "compileall", "py_compile"}
    ):
        return tokens[2], tokens[3:]

    # uv run pytest ...
    if len(tokens) >= 3 and tokens[:2] == ["uv", "run"]:
        if tokens[2] in {"pytest", "ruff"}:
            return tokens[2], tokens[3:]

        # uv run python -m <module> ...
        if (
            len(tokens) >= 5
            and tokens[2] == "python"
            and tokens[3] == "-m"
            and tokens[4] in {
                "pytest",
                "ruff",
                "compileall",
                "py_compile",
            }
        ):
            return tokens[4], tokens[5:]

    return None


def _python_runtime_command(
    *,
    runtime_kind: RuntimeKind,
    prefix: tuple[str, ...],
    tool: str,
    args: list[str],
    display_prefix: str,
) -> ResolvedValidationCommand:
    tokens = (*prefix, "-m", tool, *args)

    return ResolvedValidationCommand(
        runtime_kind=runtime_kind,
        display_command=" ".join(
            [
                display_prefix,
                "-m",
                tool,
                *args,
            ]
        ),
        tokens=tokens,
        trusted_prefix=prefix,
        tool=tool,
    )


def _uv_runtime_command(
    *,
    uv_executable: str,
    tool: str,
    args: list[str],
) -> ResolvedValidationCommand:
    prefix = (uv_executable,)

    if tool in {"pytest", "ruff"}:
        tokens = (
            uv_executable,
            "run",
            tool,
            *args,
        )
        display = " ".join(["uv", "run", tool, *args])
    else:
        tokens = (
            uv_executable,
            "run",
            "python",
            "-m",
            tool,
            *args,
        )
        display = " ".join(
            [
                "uv",
                "run",
                "python",
                "-m",
                tool,
                *args,
            ]
        )

    return ResolvedValidationCommand(
        runtime_kind="uv",
        display_command=display,
        tokens=tokens,
        trusted_prefix=prefix,
        tool=tool,
    )


def resolve_validation_commands(
    *,
    runtime_root: Path,
    execution_root: Path,
    command: str,
) -> list[ResolvedValidationCommand]:
    """
    Return viable runtimes in priority order:

        project venv -> uv -> system Python

    runtime_root:
        Original repository. Used to discover .venv/venv.

    execution_root:
        Sandbox repository. Validation commands execute from here.
    """
    parsed = _parse_python_validation_command(command)

    if parsed is None:
        return []

    tool, args = parsed
    required_module = tool if tool in {"pytest", "ruff"} else None

    candidates: list[ResolvedValidationCommand] = []

    # 1. Project-owned virtual environment.
    for python_path in _project_python_candidates(runtime_root):
        prefix = (str(python_path),)

        if required_module and not _module_available(
            prefix,
            required_module,
            cwd=execution_root,
        ):
            continue

        try:
            relative = python_path.relative_to(runtime_root)
            display_python = relative.as_posix()
        except ValueError:
            display_python = python_path.name

        candidates.append(
            _python_runtime_command(
                runtime_kind="venv",
                prefix=prefix,
                tool=tool,
                args=args,
                display_prefix=display_python,
            )
        )

        # Prefer the first valid project venv.
        break

    # 2. uv-managed project runtime.
    uv_executable = shutil.which("uv")

    if uv_executable and _has_uv_project(execution_root):
        candidates.append(
            _uv_runtime_command(
                uv_executable=str(Path(uv_executable).resolve()),
                tool=tool,
                args=args,
            )
        )

    # 3. System Python, but only when the required validation module exists.
    for prefix in _system_python_candidates():
        if required_module and not _module_available(
            prefix,
            required_module,
            cwd=execution_root,
        ):
            continue

        candidates.append(
            _python_runtime_command(
                runtime_kind="system",
                prefix=prefix,
                tool=tool,
                args=args,
                display_prefix="python",
            )
        )
        break

    return candidates