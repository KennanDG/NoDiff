import os

from agent_runtime.config.settings import settings


def ensure_langsmith_env() -> None:
    """Populate LangSmith environment variables before traced runtimes are built."""

    api_key = settings.resolved_langchain_api_key()
    if api_key:
        # Current LangSmith names.
        os.environ["LANGSMITH_API_KEY"] = api_key
        # Legacy LangChain alias retained for installed integrations that still read it.
        os.environ["LANGCHAIN_API_KEY"] = api_key

    endpoint = (
        getattr(settings, "langsmith_api_url", None)
        or os.environ.get("LANGSMITH_ENDPOINT")
        or os.environ.get("LANGCHAIN_ENDPOINT")
    )
    if endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = endpoint
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint

    project = getattr(settings, "langchain_project", None)
    if project:
        os.environ["LANGSMITH_PROJECT"] = project
        os.environ["LANGCHAIN_PROJECT"] = project

    # Current name plus the legacy alias used by older LangChain releases.
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
