# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata


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

for distribution in [
    "fastapi",
    "uvicorn",
    "fastembed",
    "onnxruntime",
    "langchain",
    "langgraph-checkpoint-sqlite",
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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="nodiff-agent-runtime",
)
