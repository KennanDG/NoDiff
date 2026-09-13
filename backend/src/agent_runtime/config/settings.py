import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import List, Literal

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# from .secrets import get_secret_json


APP_DATA_DIRECTORY_NAME = "NoDiff"
RUNTIME_DATA_DIRECTORY_NAME = "agent-runtime"
logger = logging.getLogger(__name__)


def _runtime_env_file() -> Path | None:
    """Use one explicit dotenv file for Pydantic and os.getenv consumers."""

    configured = os.getenv("ENV_FILE", "").strip()
    if configured:
        # An explicit ENV_FILE remains relative to the launching shell, as before.
        return Path(os.path.expandvars(configured)).expanduser().absolute()
    if getattr(sys, "frozen", False):
        # Packaged builds receive environment variables from the desktop launcher.
        return None
    # This module lives at backend/src/agent_runtime/config/settings.py.
    return Path(__file__).resolve().parents[3] / ".env"


RUNTIME_ENV_FILE = _runtime_env_file()
if RUNTIME_ENV_FILE is not None:
    # Process variables supplied by Electron or the shell always take precedence.
    load_dotenv(dotenv_path=RUNTIME_ENV_FILE, override=False)


def _application_data_directory() -> Path:
    """Match Electron's appData directory without depending on the launch CWD."""

    if sys.platform == "win32":
        base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
        return Path(base) if base else Path.home() / "AppData" / "Roaming"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"

    return Path(os.getenv("XDG_CONFIG_HOME", "~/.config")).expanduser()


def default_agent_runtime_data_dir() -> Path:
    """Return the per-user writable root used by both FastAPI and Electron."""

    return (
        _application_data_directory()
        / APP_DATA_DIRECTORY_NAME
        / RUNTIME_DATA_DIRECTORY_NAME
    ).absolute()


def _resolve_runtime_path(
    value: str | Path,
    runtime_root: Path,
    *,
    legacy_relative: bool = True,
) -> Path:
    expanded = Path(os.path.expandvars(str(value).strip())).expanduser()
    if not expanded.is_absolute():
        # Old .env files prefixed each child with .agent-runtime. The new root
        # already represents that directory; do not create a second copy inside it.
        if legacy_relative and expanded.parts and expanded.parts[0] == ".agent-runtime":
            logger.warning("Rebasing legacy runtime path %s under %s", value, runtime_root)
            while expanded.parts and expanded.parts[0] == ".agent-runtime":
                expanded = Path(*expanded.parts[1:])
        expanded = runtime_root / expanded
    # On Store Python, resolve() can return a different physical path after the
    # directory exists. Directory creation/canonicalization happens at startup.
    return Path(os.path.abspath(expanded))


def _prepare_runtime_directory(value: Path) -> Path:
    value.mkdir(parents=True, exist_ok=True)
    # Resolve *after* mkdir so Windows AppData virtualization has a real target.
    return value.resolve()


class Settings(BaseSettings):

    def resolved_groq_api_key(self) -> str | None:
        if self.groq_api_key:
            return self.groq_api_key
        
        # if self.groq_secret_arn:
        #     self.groq_api_key = get_secret_json(self.groq_secret_arn).get("GROQ_API_KEY")
        #     return self.groq_api_key
        
        return None


    def resolved_deepseek_api_key(self) -> str | None:
        if self.deepseek_api_key:
            return self.deepseek_api_key

        # if self.deepseek_secret_arn:
        #     self.deepseek_api_key = get_secret_json(self.deepseek_secret_arn).get("DEEPSEEK_API_KEY")
        #     return self.deepseek_api_key

        return None


    def resolved_openrouter_api_key(self) -> str | None:
        if self.openrouter_api_key:
            return self.openrouter_api_key

        # if self.openrouter_secret_arn:
        #     self.openrouter_api_key = get_secret_json(self.openrouter_secret_arn).get("OPENROUTER_API_KEY")
        #     return self.openrouter_api_key

        return None


    def resolved_openai_api_key(self) -> str | None:
        if self.openai_api_key:
            return self.openai_api_key

        # if self.openai_secret_arn:
        #     self.openai_api_key = get_secret_json(self.openai_secret_arn).get("OPENAI_API_KEY")
        #     return self.openai_api_key

        return None


    def resolved_anthropic_api_key(self) -> str | None:
        if self.anthropic_api_key:
            return self.anthropic_api_key

        # if self.anthropic_secret_arn:
        #     self.anthropic_api_key = get_secret_json(self.anthropic_secret_arn).get("ANTHROPIC_API_KEY")
        #     return self.anthropic_api_key

        return None


    def resolved_langchain_api_key(self) -> str | None:
        if self.langchain_api_key:
            return self.langchain_api_key
        
        # if self.langchain_secret_arn:
        #     self.langchain_api_key = get_secret_json(self.langchain_secret_arn).get("LANGCHAIN_API_KEY")
        #     return self.langchain_api_key
        
        return None
    


    def resolved_agent_runtime_api_key(self) -> str | None:
        if self.agent_runtime_api_key:
            return self.agent_runtime_api_key
        
        # if self.agent_runtime_secret_arn:
        #     self.agent_runtime_api_key = get_secret_json(self.agent_runtime_secret_arn).get("AGENT_RUNTIME_API_KEY")
        #     return self.agent_runtime_api_key
        
        return None
    

    
    def resolved_github_token(self) -> str | None:
        if self.github_token:
            return self.github_token

        # if self.github_secret_arn:
        #     self.github_token = get_secret_json(self.github_secret_arn).get("GITHUB_TOKEN")
        #     return self.github_token

        return None


    def resolved_google_api_key(self) -> str | None:
        if self.google_api_key:
            return self.google_api_key

        # if self.google_secret_arn:
        #     self.google_api_key = get_secret_json(self.google_secret_arn).get("GOOGLE_API_KEY")
        #     return self.google_api_key

        return None


    def resolved_serpapi_api_key(self) -> str | None:
        """Return the SerpApi key used by the built-in web_search tool."""
        return self.serpapi_api_key

    model_config = SettingsConfigDict(
        env_file=RUNTIME_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore"
        )


    # All mutable backend state is rooted here. The default intentionally mirrors
    # frontend/electron/main.ts so a separately launched FastAPI process and a
    # packaged desktop-managed process select the same directory.
    agent_runtime_data_dir: Path = Field(
        default_factory=default_agent_runtime_data_dir,
        alias="AGENT_RUNTIME_DATA_DIR",
    )


    # App API key
    agent_runtime_api_key: str | None = Field(default=None, alias="AGENT_RUNTIME_API_KEY")
    agent_runtime_secret_arn: str | None = Field(default=None, alias="AGENT_RUNTIME_SECRET_ARN")
    agent_runtime_initialize_memory_on_startup: bool = Field(
        default=True,
        alias="AGENT_RUNTIME_INITIALIZE_MEMORY_ON_STARTUP",
    )
    agent_runtime_memory_init_strict: bool = Field(
        default=True,
        alias="AGENT_RUNTIME_MEMORY_INIT_STRICT",
    )

    # GitHub repository integration
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    github_secret_arn: str | None = Field(default=None, alias="GITHUB_SECRET_ARN")

    # Built-in web search integration. Packaged builds can populate this at
    # runtime through Agent Settings instead of requiring a .env file.
    serpapi_api_key: str | None = Field(default=None, alias="SERPAPI_API_KEY")
    github_token_kind: Literal["user", "installation"] = Field(
        default="user",
        alias="GITHUB_TOKEN_KIND",
    )
    github_api_url: str = Field(default="https://api.github.com", alias="GITHUB_API_URL")
    github_api_version: str = Field(default="2026-03-10", alias="GITHUB_API_VERSION")
    github_workspace_root: Path = Field(
        default=Path("github-workspaces"),
        alias="GITHUB_WORKSPACE_ROOT",
    )
    github_timeout_seconds: int = Field(default=120, alias="GITHUB_TIMEOUT_SECONDS")
    github_commit_author_name: str = Field(
        default="Agent Runtime",
        alias="GITHUB_COMMIT_AUTHOR_NAME",
    )
    github_commit_author_email: str = Field(
        default="agent-runtime@users.noreply.github.com",
        alias="GITHUB_COMMIT_AUTHOR_EMAIL",
    )
    github_allow_default_branch_push: bool = Field(
        default=False,
        alias="GITHUB_ALLOW_DEFAULT_BRANCH_PUSH",
    )
    github_max_commit_files: int = Field(
        default=100,
        ge=1,
        le=500,
        alias="GITHUB_MAX_COMMIT_FILES",
    )
    github_max_file_size_bytes: int = Field(
        default=5_000_000,
        ge=1,
        alias="GITHUB_MAX_FILE_SIZE_BYTES",
    )
    github_blocked_path_patterns: List[str] = Field(
        default_factory=lambda: [
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "id_rsa",
            "id_ed25519",
            "*credentials*",
            "*secrets*",
        ],
        alias="GITHUB_BLOCKED_PATH_PATTERNS",
    )

    # LangChain
    langchain_api_key: str | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    langsmith_api_url: str | None = Field(default="https://api.smith.langchain.com", alias="LANGCHAIN_ENDPOINT")
    langchain_secret_arn: str | None = Field(default=None, alias="LANGCHAIN_SECRET_ARN")
    langchain_project : str = Field(default="agent-runtime-dev", alias="LANGCHAIN_PROJECT")


    # Chat model routing. Model IDs can be overridden by the runtime admin API.
    coding_provider: Literal["groq", "deepseek", "openrouter", "openai", "anthropic", "google"] = Field(
        default="groq",
        alias="CODING_PROVIDER",
    )
    reasoning_provider: Literal["groq", "deepseek", "openrouter", "openai", "anthropic", "google"] = Field(
        default="deepseek",
        alias="REASONING_PROVIDER",
    )
    caption_provider: Literal["groq", "openrouter", "openai", "anthropic", "google"] = Field(
        default="groq",
        alias="CAPTION_PROVIDER",
    )
    voice_chat_provider: Literal["groq", "deepseek", "openrouter", "openai", "anthropic", "google"] = Field(
        default="groq",
        alias="VOICE_CHAT_PROVIDER",
    )
    voice_stt_provider: Literal["groq", "openai"] = Field(
        default="groq",
        alias="VOICE_STT_PROVIDER",
    )
    voice_tts_provider: Literal["groq", "openai"] = Field(
        default="groq",
        alias="VOICE_TTS_PROVIDER",
    )

    # Groq
    chat_model: str = Field(default="llama-3.1-8b-instant", alias="CHAT_MODEL")                   
    query_model: str = Field(default="llama-3.1-8b-instant", alias="QUERY_MODEL")         
    caption_model: str = Field(default="meta-llama/llama-4-scout-17b-16e-instruct", alias="CAPTION_MODEL")  # VLM
    verify_model: str = Field(default="llama-3.1-8b-instant", alias="VERIFY_MODEL")
    verify_docs_model: str = Field(default="llama-3.1-8b-instant", alias="VERIFY_DOCS_MODEL")
    coding_model: str = Field(default="openai/gpt-oss-120b", alias="CODING_MODEL") 
    reasoning_model: str = Field(default="deepseek-v4-pro", alias="REASONING_MODEL") 
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_api_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_URL")
    groq_secret_arn: str | None = Field(default=None, alias="GROQ_SECRET_ARN")

    # OpenAI-compatible chat providers used by the coding and reasoning slots.
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_api_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_URL")
    deepseek_secret_arn: str | None = Field(default=None, alias="DEEPSEEK_SECRET_ARN")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_api_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_URL")
    openrouter_secret_arn: str | None = Field(default=None, alias="OPENROUTER_SECRET_ARN")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_api_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_URL")
    openai_secret_arn: str | None = Field(default=None, alias="OPENAI_SECRET_ARN")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_api_url: str = Field(default="https://api.anthropic.com", alias="ANTHROPIC_URL")
    anthropic_secret_arn: str | None = Field(default=None, alias="ANTHROPIC_SECRET_ARN")    
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    google_api_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta", alias="GOOGLE_URL")
    google_secret_arn: str | None = Field(default=None, alias="GOOGLE_SECRET_ARN")

    # Non-secret runtime model selections are persisted here. Provider secrets remain
    # in environment/Secrets Manager or in the current backend process only.
    runtime_agent_config_path: Path = Field(
        default=Path("runtime-agent-config.json"),
        alias="AGENT_RUNTIME_CONFIG_PATH",
    )
    local_repository_session_path: Path = Field(
        default=Path("local-repository-session.json"),
        alias="AGENT_RUNTIME_LOCAL_REPOSITORY_SESSION_PATH",
    )
    # Loaded from the validated local repository session at application startup.
    # This is deliberately non-secret and is never read from an unvalidated path.
    last_opened_local_repository: str | None = None

    # Coding-agent execution profile. These defaults mirror CodingAgentSettings
    # and can be changed through the admin UI for subsequent runs. The legacy
    # coding_subagent_count / patch / progress fields remain for compatibility, but
    # the current divide-and-conquer runtime uses the fields prefixed below.
    coding_max_subtask_workers: int = Field(
        default=3, ge=1, le=6, alias="CODING_AGENT_MAX_SUBTASK_WORKERS"
    )
    coding_max_implementation_units: int = Field(
        default=12, ge=1, le=12, alias="CODING_AGENT_MAX_IMPLEMENTATION_UNITS"
    )
    coding_max_patch_retries_per_unit: int = Field(
        default=1, ge=0, le=4, alias="CODING_AGENT_MAX_PATCH_RETRIES_PER_UNIT"
    )
    coding_max_implementation_iterations: int = Field(
        default=2, ge=1, le=8, alias="CODING_AGENT_MAX_IMPLEMENTATION_ITERATIONS"
    )

    coding_route_max_tokens: int = Field(
        default=900, ge=256, le=2_000, alias="CODING_AGENT_ROUTE_MAX_TOKENS"
    )
    coding_planner_max_tokens: int = Field(
        default=3_000, ge=512, le=6_000, alias="CODING_AGENT_PLANNER_MAX_TOKENS"
    )
    coding_repo_navigation_max_tokens: int = Field(
        default=1_600, ge=512, le=4_000,
        alias="CODING_AGENT_REPO_NAVIGATION_MAX_TOKENS",
    )
    coding_simple_patch_max_tokens: int = Field(
        default=8_000, ge=2_000, le=16_000,
        alias="CODING_AGENT_SIMPLE_PATCH_MAX_TOKENS",
    )
    coding_reconciliation_max_tokens: int = Field(
        default=10_000, ge=2_000, le=32_000,
        alias="CODING_AGENT_RECONCILIATION_MAX_TOKENS",
    )
    coding_reconciliation_context_max_tokens: int = Field(
        default=24_000, ge=4_000, le=64_000,
        alias="CODING_AGENT_RECONCILIATION_CONTEXT_MAX_TOKENS",
    )
    coding_max_reasoning_reconciliations: int = Field(
        default=1, ge=0, le=3, alias="CODING_AGENT_MAX_REASONING_RECONCILIATIONS"
    )

    coding_context_prompt_base_tokens: int = Field(
        default=16_000, ge=4_000, le=64_000,
        alias="CODING_AGENT_CONTEXT_PROMPT_BASE_TOKENS",
    )
    coding_max_context_prompt_tokens: int = Field(
        default=32_000, ge=8_000, le=128_000,
        alias="CODING_AGENT_MAX_CONTEXT_PROMPT_TOKENS",
    )
    coding_context_prompt_reserve_tokens: int = Field(
        default=10_000, ge=2_000, le=64_000,
        alias="CODING_AGENT_CONTEXT_PROMPT_RESERVE_TOKENS",
    )
    coding_context_window_safety_tokens: int = Field(
        default=6_000, ge=1_000, le=32_000,
        alias="CODING_AGENT_CONTEXT_WINDOW_SAFETY_TOKENS",
    )
    coding_model_context_window_tokens: int = Field(
        default=131_072, ge=16_000, le=2_000_000,
        alias="CODING_AGENT_CODING_CONTEXT_WINDOW_TOKENS",
    )
    reasoning_model_context_window_tokens: int = Field(
        default=131_072, ge=16_000, le=2_000_000,
        alias="CODING_AGENT_REASONING_CONTEXT_WINDOW_TOKENS",
    )
    coding_model_max_output_tokens: int = Field(
        default=32_000, ge=2_000, le=128_000,
        alias="CODING_AGENT_CODING_MAX_OUTPUT_TOKENS",
    )
    reasoning_model_max_output_tokens: int = Field(
        default=32_000, ge=2_000, le=128_000,
        alias="CODING_AGENT_REASONING_MAX_OUTPUT_TOKENS",
    )

    # Legacy configuration aliases retained for rolling upgrades / old callers.
    coding_subagent_count: int = Field(
        default=3, ge=1, le=6, alias="CODING_AGENT_MAX_CONTEXT_WORKERS"
    )
    coding_patch_max_tokens: int = Field(
        default=20_000, ge=4_000, le=32_000, alias="CODING_AGENT_PATCH_MAX_TOKENS"
    )
    coding_progress_max_tokens: int = Field(
        default=1_200, ge=512, le=4_000, alias="CODING_AGENT_PROGRESS_MAX_TOKENS"
    )

    # FastEmbed
    
    rerank_device: str = Field(default="cpu", alias="RERANK_DEVICE") 


    # Voice Agent
    voice_stt_model: str = Field(default="whisper-large-v3-turbo", alias="VOICE_STT_MODEL")
    voice_chat_model: str = Field(default="llama-3.1-8b-instant", alias="VOICE_CHAT_MODEL")
    voice_chat_max_tokens: int = Field(default=2_048, alias="VOICE_CHAT_MAX_TOKENS")
    voice_tts_model: str = Field(default="canopylabs/orpheus-v1-english", alias="VOICE_TTS_MODEL")
    voice_tts_voice: str = Field(default="hannah", alias="VOICE_TTS_VOICE")
    voice_tts_enabled: bool = Field(default=True, alias="VOICE_TTS_ENABLED")
    voice_tts_max_chars: int = Field(default=200, alias="VOICE_TTS_MAX_CHARS")
    voice_max_clarifications: int = Field(default=2, alias="VOICE_MAX_CLARIFICATIONS")
    voice_max_audio_mb: int = Field(default=15, alias="VOICE_MAX_AUDIO_MB")

    @model_validator(mode="after")
    def resolve_runtime_paths(self) -> "Settings":
        runtime_root = _resolve_runtime_path(
            self.agent_runtime_data_dir, Path.cwd(), legacy_relative=False
        )
        self.agent_runtime_data_dir = runtime_root
        self.github_workspace_root = _resolve_runtime_path(
            self.github_workspace_root,
            runtime_root,
        )
        self.runtime_agent_config_path = _resolve_runtime_path(
            self.runtime_agent_config_path,
            runtime_root,
        )
        self.local_repository_session_path = _resolve_runtime_path(
            self.local_repository_session_path,
            runtime_root,
        )
        return self


def _legacy_runtime_roots(runtime_root: Path) -> list[Path]:
    """Return known pre-consolidation roots, without scanning arbitrary folders."""

    cwd = Path.cwd().resolve()
    candidates = [
        runtime_root / ".agent-runtime",
        cwd / ".agent-runtime",
        Path.home() / ".agent-runtime",
    ]
    if cwd.name.lower() == "backend":
        candidates.insert(1, cwd.parent / ".agent-runtime")

    app_data = _application_data_directory()
    candidates.extend(
        [
            app_data / "Coding Agent",
            app_data / "coding-agent-desktop",
            app_data / APP_DATA_DIRECTORY_NAME,
        ]
    )

    result: list[Path] = []
    canonical = runtime_root.resolve()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved != canonical and resolved not in result:
            result.append(resolved)
    return result


def _newest_legacy_file(roots: list[Path], relative_path: Path) -> Path | None:
    candidates = [root / relative_path for root in roots]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime_ns)


def _copy_legacy_file_if_missing(
    roots: list[Path],
    relative_path: Path,
    destination: Path,
) -> None:
    if destination.exists():
        return
    source = _newest_legacy_file(roots, relative_path)
    if source is None:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_legacy_sqlite_if_missing(
    roots: list[Path],
    filename: str,
    destination: Path,
) -> None:
    """Use SQLite's backup API so WAL-backed legacy databases copy consistently."""

    if destination.exists():
        return
    source = _newest_legacy_file(roots, Path("memory") / filename)
    if source is None:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.migrating")
    try:
        temporary.unlink(missing_ok=True)
        source_uri = f"{source.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source_connection:
            with sqlite3.connect(temporary) as destination_connection:
                source_connection.backup(destination_connection)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_runtime_data_layout(config: Settings) -> None:
    """Create the canonical layout and preserve usable state from older builds."""

    requested_root = config.agent_runtime_data_dir
    runtime_root = _prepare_runtime_directory(requested_root)
    # Rebase only paths that belong to this root; keep absolute expert overrides.
    for name in (
        "github_workspace_root",
        "runtime_agent_config_path",
        "local_repository_session_path",
    ):
        value = getattr(config, name)
        try:
            relative = value.relative_to(requested_root)
        except ValueError:
            continue
        setattr(config, name, runtime_root / relative)
    config.agent_runtime_data_dir = runtime_root
    _prepare_runtime_directory(config.github_workspace_root)
    config.runtime_agent_config_path.parent.mkdir(parents=True, exist_ok=True)
    config.local_repository_session_path.parent.mkdir(parents=True, exist_ok=True)
    (runtime_root / "memory").mkdir(parents=True, exist_ok=True)

    logger.info("Agent runtime data directory: %s", runtime_root)

    legacy_roots = _legacy_runtime_roots(runtime_root)
    coding_config_path = config.runtime_agent_config_path.with_name(
        f"{config.runtime_agent_config_path.stem}-coding-runtime"
        f"{config.runtime_agent_config_path.suffix}"
    )
    _copy_legacy_file_if_missing(
        legacy_roots,
        Path("runtime-agent-config.json"),
        config.runtime_agent_config_path,
    )
    _copy_legacy_file_if_missing(
        legacy_roots,
        Path("runtime-agent-config-coding-runtime.json"),
        coding_config_path,
    )
    
    memory_directory = runtime_root / "memory"
    _copy_legacy_file_if_missing(
        legacy_roots,
        Path("memory") / "maintenance.json",
        memory_directory / "maintenance.json",
    )
    _copy_legacy_sqlite_if_missing(
        legacy_roots,
        "checkpoints.sqlite3",
        memory_directory / "checkpoints.sqlite3",
    )
    _copy_legacy_sqlite_if_missing(
        legacy_roots,
        "store.sqlite3",
        memory_directory / "store.sqlite3",
    )


settings = Settings()
initialize_runtime_data_layout(settings)
