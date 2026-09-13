from __future__ import annotations

import sys
import ast
import importlib.util
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable


CODING_TOOLS_DIR = Path(__file__).resolve().parent / "tools"
CUSTOM_PENDING_DIR = CODING_TOOLS_DIR / "custom_pending"
CUSTOM_APPROVED_DIR = CODING_TOOLS_DIR / "custom_approved"


STDLIB_IMPORT_ROOTS = frozenset(
    getattr(sys, "stdlib_module_names", ())
) | {"__future__"}

NODIFF_TOOL_IMPORT_PREFIXES = (
    "agent_runtime.agents.coding.tools",
    "agent_runtime.agents.voice.tools",
)

REVIEW_DIRECT_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
}

REVIEW_ATTRIBUTE_CALLS = {
    # Process execution
    "Popen",
    "popen",
    "system",

    # Destructive filesystem operations
    "chmod",
    "chown",
    "rename",
    "replace",
    "rmdir",
    "unlink",
    "write_bytes",
    "write_text",
}

MAX_CUSTOM_TOOL_RESULT_CHARS = 24_000
MAX_CUSTOM_TOOL_CALLS = 4


@dataclass(frozen=True)
class ApprovedTool:
    name: str
    path: Path
    purpose: str
    signature: str
    callable: Callable[..., Any]


class CustomToolValidationError(ValueError):
    pass


def _function_purpose(node: ast.FunctionDef | ast.AsyncFunctionDef, fallback: str) -> str:
    docstring = ast.get_docstring(node, clean=True)
    return docstring.splitlines()[0].strip() if docstring else fallback


def _is_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )

def review_custom_tool_source(name: str, source: str) -> list[str]:
    """Return non-blocking warnings for behavior the user should review."""

    normalized = source.replace("\r\n", "\n").strip() + "\n"

    try:
        tree = ast.parse(normalized, filename=f"{name}.py")
    except SyntaxError:
        # Syntax errors are handled by the hard validator.
        return []

    warnings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [item.name for item in node.names]

            for module in modules:
                root = module.split(".", 1)[0]

                is_stdlib = root in STDLIB_IMPORT_ROOTS
                is_nodiff_tool = any(
                    module == prefix or module.startswith(prefix + ".")
                    for prefix in NODIFF_TOOL_IMPORT_PREFIXES
                )

                if not is_stdlib and not is_nodiff_tool:
                    warnings.append(
                        f"Imports external/project module '{module}'. "
                        "It must be available in the packaged NoDiff runtime."
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            if module:
                root = module.split(".", 1)[0]

                is_stdlib = root in STDLIB_IMPORT_ROOTS
                is_nodiff_tool = any(
                    module == prefix or module.startswith(prefix + ".")
                    for prefix in NODIFF_TOOL_IMPORT_PREFIXES
                )

                if not is_stdlib and not is_nodiff_tool:
                    warnings.append(
                        f"Imports external/project module '{module}'. "
                        "It must be available in the packaged NoDiff runtime."
                    )

        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in REVIEW_DIRECT_CALLS
            ):
                warnings.append(
                    f"Uses powerful Python call '{node.func.id}(...)'."
                )

            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in REVIEW_ATTRIBUTE_CALLS
            ):
                warnings.append(
                    f"Uses potentially destructive/system call "
                    f"'.{node.func.attr}(...)'."
                )

    # Import-time execution deserves a warning, but should no longer be blocked.
    for index, node in enumerate(tree.body):
        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            continue

        if (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is not None and any(
                isinstance(item, ast.Call)
                for item in ast.walk(value)
            ):
                warnings.append(
                    "Contains a top-level assignment that executes code during import."
                )
            continue

        warnings.append(
            f"Contains top-level '{type(node).__name__}' logic that runs during import."
        )

    # Preserve ordering while removing duplicates.
    return list(dict.fromkeys(warnings))



def validate_approved_custom_tool_source(name: str, source: str) -> str:
    """Validate runtime compatibility.

    This intentionally does not attempt to restrict user-approved Python.
    Approved tools execute with the same process privileges as NoDiff.
    """

    normalized = source.replace("\r\n", "\n").strip() + "\n"

    try:
        tree = ast.parse(normalized, filename=f"{name}.py")
    except SyntaxError as exc:
        raise CustomToolValidationError(
            f"Tool source is not valid Python: "
            f"line {exc.lineno}: {exc.msg}"
        ) from exc

    target: ast.FunctionDef | None = None
    async_target: ast.AsyncFunctionDef | None = None

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            target = node

        elif isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            async_target = node

    if target is None:
        if async_target is not None:
            raise CustomToolValidationError(
                f"Tool entry function '{name}' is async. "
                "The current custom-tool runtime supports synchronous "
                "entry functions only."
            )

        raise CustomToolValidationError(
            f"Approved tool must define a public function named '{name}'."
        )

    # Additional public helper functions/classes are intentionally allowed.
    # Imports, decorators, filesystem access, subprocess usage, network access,
    # and dynamic Python are user-reviewed rather than source-policy blocked.

    return normalized



def validate_tool_signature(function: Callable[..., Any]) -> inspect.Signature:

    signature = inspect.signature(function)

    for parameter in signature.parameters.values():
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.POSITIONAL_ONLY,
        }:
            raise CustomToolValidationError(
                "Custom tools may not use *args or positional-only parameters. "
                "Named parameters and **kwargs are supported."
            )
        
    return signature


def _load_module(path: Path, source: str) -> ModuleType:
    module_name = f"agent_runtime_custom_tool_{path.stem}_{path.stat().st_mtime_ns}"
    spec = importlib.util.spec_from_file_location(module_name, path)

    if spec is None or spec.loader is None:
        raise CustomToolValidationError(f"Could not create an import spec for {path.name}.")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def _json_result(value: Any) -> tuple[str, bool]:
    try:
        text = json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)

    if len(text) <= MAX_CUSTOM_TOOL_RESULT_CHARS:
        return text, False
    
    return text[:MAX_CUSTOM_TOOL_RESULT_CHARS] + "\n...[tool result truncated]", True


class ApprovedCustomToolRegistry:
    """Load and invoke only user-approved custom coding tools."""

    def __init__(self, approved_dir: Path = CUSTOM_APPROVED_DIR) -> None:
        self.approved_dir = approved_dir.resolve()
        self._tools: dict[str, ApprovedTool] = {}

    def load(self) -> "ApprovedCustomToolRegistry":
        self._tools.clear()
        self.approved_dir.mkdir(parents=True, exist_ok=True)

        for path in sorted(self.approved_dir.glob("*.py")):
            try:
                source = path.read_text(encoding="utf-8")
                validate_approved_custom_tool_source(path.stem, source)
                module = _load_module(path, source)
                function = getattr(module, path.stem, None)

                if not callable(function):
                    continue

                signature = validate_tool_signature(function)
                tree = ast.parse(source, filename=str(path))
                node = next(
                    (
                        item
                        for item in tree.body
                        if isinstance(item, ast.FunctionDef) and item.name == path.stem
                    ),
                    None,
                )
                module_docstring = ast.get_docstring(tree, clean=True) or ""
                module_purpose = (
                    module_docstring.splitlines()[0].strip() if module_docstring else ""
                )
                purpose = (
                    _function_purpose(
                        node,
                        module_purpose or f"Approved custom tool {path.stem}.",
                    )
                    if node is not None
                    else module_purpose or f"Approved custom tool {path.stem}."
                )
                self._tools[path.stem] = ApprovedTool(
                    name=path.stem,
                    path=path,
                    purpose=purpose,
                    signature=str(signature),
                    callable=function,
                )
            except (OSError, CustomToolValidationError, ImportError, AttributeError):
                # Invalid approved files are treated as unavailable rather than making
                # the whole coding-agent startup fail.
                continue

        return self

    def list(self) -> list[ApprovedTool]:
        if not self._tools:
            self.load()
        return [self._tools[name] for name in sorted(self._tools)]

    def has(self, name: str) -> bool:
        if not self._tools:
            self.load()
        return name in self._tools

    def prompt_catalog(self, allowed_names: Iterable[str] | None = None) -> str:
        if not self._tools:
            self.load()

        allowed = set(allowed_names or self._tools)
        lines = []

        for tool in self.list():
            if tool.name not in allowed:
                continue
            lines.append(f"- {tool.name}{tool.signature}: {tool.purpose}")

        return "\n".join(lines)

    def invoke(
        self,
        name: str,
        *,
        repo_root: Path,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._tools:
            self.load()

        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Approved custom tool is not available: {name}")

        supplied = dict(arguments or {})
        # Runtime-owned path values may never be overridden by model output.
        supplied.pop("repo_root", None)
        signature = inspect.signature(tool.callable)

        if "repo_root" in signature.parameters:
            supplied["repo_root"] = str(repo_root.resolve())

        try:
            signature.bind(**supplied)
        except TypeError as exc:
            raise ValueError(f"Invalid arguments for {name}{tool.signature}: {exc}") from exc

        result = tool.callable(**supplied)
        rendered, truncated = _json_result(result)
        
        return {
            "tool_name": name,
            "arguments": {key: value for key, value in supplied.items() if key != "repo_root"},
            "output": rendered,
            "truncated": truncated,
            "success": True,
        }
