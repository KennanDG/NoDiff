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

    # Required by LangGraph SqliteStore semantic/vector indexing.
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
