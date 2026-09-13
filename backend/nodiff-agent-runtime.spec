# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
    get_package_paths,
)


PROJECT_ROOT = Path(SPECPATH)
SOURCE_ROOT = PROJECT_ROOT / "src"

# NoDiff loads model providers, LangChain integrations, FastEmbed, and SQLite
# checkpointers dynamically. Collect their package metadata/data explicitly so
# the sidecar behaves the same way after PyInstaller freezes it.
COLLECT_PACKAGES = [
    "anthropic",
    "boto3",
    "fastembed",
    "google.genai",
    "googleapiclient",
    "groq",
    "langchain",
    "langchain_anthropic",
    "langchain_community",
    "langchain_core",
    "langchain_google_genai",
    "langchain_groq",
    "langchain_openai",
    "langgraph",
    "langgraph.checkpoint.sqlite",
    "sqlite_vec",
    "onnxruntime",
    "openai",
    "openrouter",
    "pydantic",
    "pydantic_settings",
]


datas = []
binaries = []
hiddenimports = collect_submodules("agent_runtime")


# ---------------------------------------------------------------------------
# NoDiff built-in coding resources
# ---------------------------------------------------------------------------
#
# The coding agent discovers built-in skills/tools from the filesystem.
#
# PyInstaller normally:
#   - does NOT include .md files automatically
#   - may bundle Python modules inside the PYZ archive instead of leaving their
#     source .py files on disk
#
# Because NoDiff scans these directories at runtime, preserve them as physical
# files underneath:
#
#   _internal/agent_runtime/agents/coding/skills
#   _internal/agent_runtime/agents/coding/tools
#

CODING_AGENT_ROOT = SOURCE_ROOT / "agent_runtime" / "agents" / "coding"

BUILTIN_RESOURCE_DIRECTORIES = {
    CODING_AGENT_ROOT / "skills": Path(
        "agent_runtime/agents/coding/skills"
    ),
    CODING_AGENT_ROOT / "tools": Path(
        "agent_runtime/agents/coding/tools"
    ),
}


def add_resource_tree(source_dir: Path, destination_dir: Path) -> None:
    if not source_dir.is_dir():
        raise RuntimeError(
            f"Required NoDiff resource directory does not exist: {source_dir}"
        )

    added = 0

    for source_file in source_dir.rglob("*"):
        if not source_file.is_file():
            continue

        # Never ship local bytecode/cache artifacts.
        if "__pycache__" in source_file.parts:
            continue

        if source_file.suffix.lower() in {".pyc", ".pyo"}:
            continue

        relative_file = source_file.relative_to(source_dir)

        # PyInstaller's destination is the containing directory, not the
        # destination filename.
        destination = destination_dir / relative_file.parent

        datas.append(
            (
                str(source_file),
                destination.as_posix(),
            )
        )
        added += 1

    if added == 0:
        raise RuntimeError(
            f"No files were found in required NoDiff resource directory: "
            f"{source_dir}"
        )

    print(
        f"[PyInstaller] bundled {added} resource file(s): "
        f"{source_dir} -> {destination_dir}"
    )


for source_dir, destination_dir in BUILTIN_RESOURCE_DIRECTORIES.items():
    add_resource_tree(source_dir, destination_dir)


# ---------------------------------------------------------------------------
# Third-party dynamic packages
# ---------------------------------------------------------------------------
for package in COLLECT_PACKAGES:
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package)
        datas.extend(package_datas)
        binaries.extend(package_binaries)
        hiddenimports.extend(package_hiddenimports)
    except Exception as exc:
        # Some namespace packages do not expose every optional provider in every
        # environment. The runtime will still fail clearly if a selected provider
        # is genuinely missing; do not make the entire freeze fail for an unused
        # optional namespace.
        print(f"[PyInstaller] optional collection skipped for {package}: {exc}")


# sqlite-vec is not a Python extension module. It ships a SQLite loadable
# extension (vec0.dll) which LangGraph loads dynamically at runtime.
#
# PyInstaller cannot reliably discover that dynamic DLL load, so guarantee that
# the DLL is copied beside the frozen sqlite_vec package.
_, sqlite_vec_package_dir = get_package_paths("sqlite_vec")

sqlite_vec_dll = Path(sqlite_vec_package_dir) / "vec0.dll"

if not sqlite_vec_dll.is_file():
    raise RuntimeError(
        "sqlite-vec is installed, but vec0.dll could not be found at "
        f"{sqlite_vec_dll}. Reinstall sqlite-vec before building."
    )

binaries.append(
    (
        str(sqlite_vec_dll),
        "sqlite_vec",
    )
)

print(f"[PyInstaller] sqlite-vec DLL: {sqlite_vec_dll}")


for distribution in [
    "fastapi",
    "uvicorn",
    "fastembed",
    "onnxruntime",
    "langchain",
    "langgraph-checkpoint-sqlite",
    "sqlite-vec",
]:
    try:
        datas.extend(copy_metadata(distribution))
    except Exception as exc:
        print(f"[PyInstaller] metadata collection skipped for {distribution}: {exc}")

REQUIRED_SKILLS = {
    "debug.md",
    "frontend_component.md",
    "frontend_styling.md",
    "implement_change.md",
    "repo.md",
    "tests.md",
    "web_search.md",
}

REQUIRED_TOOLS = {
    "__init__.py",
    "filesystem.py",
    "frontend_component_tools.py",
    "frontend_styling_tools.py",
    "patch.py",
    "search.py",
    "shell.py",
    "web_search.py",
}

skills_dir = CODING_AGENT_ROOT / "skills"
tools_dir = CODING_AGENT_ROOT / "tools"

missing_skills = [
    name for name in REQUIRED_SKILLS
    if not (skills_dir / name).is_file()
]

missing_tools = [
    name for name in REQUIRED_TOOLS
    if not (tools_dir / name).is_file()
]

if missing_skills or missing_tools:
    raise RuntimeError(
        "Required built-in NoDiff resources are missing before freeze. "
        f"Skills: {missing_skills or 'OK'}; "
        f"Tools: {missing_tools or 'OK'}"
    )

    
a = Analysis(
    [str(SOURCE_ROOT / "agent_runtime" / "api" / "main.py")],
    pathex=[str(SOURCE_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nodiff-agent-runtime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="nodiff-agent-runtime",
)
