from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _validation_progress(event: str, **payload: object) -> None:
    """Publish live command progress when called inside a LangGraph node."""
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        writer({"type": event, **payload})
    except Exception:
        # Standalone calls have no graph context; observability must never stop
        # validation or turn a passing command into an execution failure.
        logger.debug("Validation progress stream unavailable", exc_info=True)


def _output_tail(stream) -> str:
    # Regular files avoid EOF waits on pipes inherited by grandchildren (uv,
    # pytest, npm, etc.). Read a bounded snapshot even if a child is still alive.
    size = os.fstat(stream.fileno()).st_size
    stream.seek(max(0, size - 40_000))
    return stream.read(min(size, 40_000)).decode("utf-8", errors="replace")[-10_000:]


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.warning("Could not terminate validation process tree %s", process.pid)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            logger.warning("Could not terminate validation process group %s", process.pid)

    # Do not enter Popen's context manager or call communicate() here: both can
    # reintroduce an unbounded wait after the timeout we just enforced.
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("Validation process %s did not exit after termination", process.pid)

ALLOWED_COMMAND_PREFIXES = (
    ("pytest",),
    ("uv", "run", "pytest"),
    ("ruff", "check"),
    ("uv", "run", "ruff", "check"),
    ("ruff", "format", "--check"),
    ("uv", "run", "ruff", "format", "--check"),
    ("python", "-m", "pytest"),
    ("uv", "run", "python", "-m", "pytest"),
    ("python", "-m", "compileall"),
    ("uv", "run", "python", "-m", "compileall"),
    ("python", "-m", "py_compile"),
    ("python", "-c"),
    ("uv", "run", "python", "-m", "py_compile"),
    ("npx", "tsc"),
    ("npm", "run", "typecheck"),
    ("npm", "run", "build"),
    ("npx", "tailwindcss"),
)

BLOCKED_COMMANDS = {
    "sudo",
    "rm",
    "rmdir",
    "del",
    "format",
    "shutdown",
    "reboot",
    "mkfs",
    "chmod",
    "chown",
}

SHELL_CONTROL_TOKENS = {
    "&&",
    "||",
    ";",
    "|",
    ">",
    ">>",
    "<",
}


def _command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _starts_with_tokens(tokens: list[str], prefix: tuple[str, ...]) -> bool:
    return len(tokens) >= len(prefix) and tuple(tokens[: len(prefix)]) == prefix


def _strip_safe_cd_prefix(tokens: list[str]) -> tuple[list[str], str | None]:
    """Support commands like: cd agents/frontend && npx tsc --noEmit.

    This keeps shell=False while still allowing a narrowly-scoped cwd change.
    """
    if not tokens or tokens[0] != "cd":
        return tokens, None

    if len(tokens) < 4 or tokens[2] != "&&":
        return [], None

    cd_target = tokens[1]
    remaining = tokens[3:]

    if not remaining:
        return [], None

    return remaining, cd_target


def _is_allowed_tokens(tokens: list[str]) -> bool:
    if not tokens:
        return False

    if tokens[0] in BLOCKED_COMMANDS:
        return False

    if any(token in SHELL_CONTROL_TOKENS for token in tokens):
        return False

    return any(_starts_with_tokens(tokens, prefix) for prefix in ALLOWED_COMMAND_PREFIXES)


def is_allowed_command(command: str) -> bool:
    tokens = _command_tokens(command)
    tokens, _cwd = _strip_safe_cd_prefix(tokens)
    return _is_allowed_tokens(tokens)


def _resolve_working_directory(repo_root: Path, cwd_fragment: str | None) -> Path:
    root = repo_root.resolve()

    if not cwd_fragment:
        return root

    cwd_path = Path(cwd_fragment)

    if cwd_path.is_absolute() or ".." in cwd_path.parts:
        raise ValueError(f"Unsafe command working directory: {cwd_fragment}")

    resolved = (root / cwd_path).resolve()

    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Command working directory escapes repository root: {cwd_fragment}")

    if not resolved.is_dir():
        raise FileNotFoundError(f"Command working directory does not exist: {cwd_fragment}")

    return resolved


def run_command(repo_root: Path, command: str, timeout_seconds: int = 60) -> dict[str, object]:
    original_command = command
    tokens = _command_tokens(command)
    tokens, cwd_fragment = _strip_safe_cd_prefix(tokens)

    if not tokens or not _is_allowed_tokens(tokens):
        return {
            "command": original_command,
            "returncode": 126,
            "stdout": "",
            "stderr": "Command blocked by coding-agent allowlist.",
        }

    process = None
    started = time.monotonic()
    _validation_progress(
        "validation.command.started", command=original_command,
        timeout_seconds=timeout_seconds,
    )
    try:
        cwd = _resolve_working_directory(repo_root, cwd_fragment)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                tokens,
                cwd=cwd,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            timed_out = False
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                returncode = 124

            result = {
                "command": original_command,
                "returncode": returncode,
                "stdout": _output_tail(stdout),
                "stderr": _output_tail(stderr),
            }
            if timed_out:
                result["stderr"] = (
                    f"{result['stderr']}\nValidation timed out after {timeout_seconds}s. "
                    "Process-tree termination was requested."
                ).strip()

    except FileNotFoundError as exc:
        result = {
            "command": original_command,
            "returncode": 127,
            "stdout": "",
            "stderr": f"Executable not found: {exc}",
        }

    except Exception as exc:
        if process is not None and process.poll() is None:
            _terminate_process_tree(process)
        result = {
            "command": original_command,
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
        }

    except BaseException:
        if process is not None and process.poll() is None:
            _terminate_process_tree(process)
        raise

    _validation_progress(
        "validation.command.completed", command=original_command,
        returncode=result["returncode"],
        elapsed_seconds=round(time.monotonic() - started, 1),
    )
    return result
