from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ClickHouseSettings:
    host: str
    port: int
    username: str
    password: str
    database: str
    secure: bool


@dataclass(frozen=True)
class AppSettings:
    environment: str
    clickhouse: Optional[ClickHouseSettings]
    mcp_endpoint: Optional[str]
    mcp_command: Optional[str]
    graph_query_mode: str
    seed_file: Path
    use_memory_store: bool
    agent_runtime_mode: str
    github_token: Optional[str]
    agent_provider_url: Optional[str]
    agent_provider_model: Optional[str]
    agent_provider_api_key: Optional[str]
    google_cloud_project: Optional[str]
    google_cloud_location: Optional[str]


def _env(primary: str, legacy: str, default: Optional[str] = None) -> Optional[str]:
    """Read the CLIO name first while keeping older local env files working."""
    return os.getenv(primary) or os.getenv(legacy) or default


def load_settings() -> AppSettings:
    base_dir = Path(__file__).resolve().parents[2]
    _load_dotenv(base_dir / ".env")
    clickhouse_host = _env("CLIO_CLICKHOUSE_HOST", "FILMGRAPH_CLICKHOUSE_HOST")
    clickhouse = None
    if clickhouse_host:
        clickhouse = ClickHouseSettings(
            host=clickhouse_host,
            port=int(_env("CLIO_CLICKHOUSE_PORT", "FILMGRAPH_CLICKHOUSE_PORT", "8123") or "8123"),
            username=_env("CLIO_CLICKHOUSE_USER", "FILMGRAPH_CLICKHOUSE_USER", "default") or "default",
            password=_env("CLIO_CLICKHOUSE_PASSWORD", "FILMGRAPH_CLICKHOUSE_PASSWORD", "") or "",
            database=_env("CLIO_CLICKHOUSE_DATABASE", "FILMGRAPH_CLICKHOUSE_DATABASE", "filmgraph") or "filmgraph",
            secure=(_env("CLIO_CLICKHOUSE_SECURE", "FILMGRAPH_CLICKHOUSE_SECURE", "false") or "false").lower() == "true",
        )

    provider_key = os.getenv("AGENT_PROVIDER_API_KEY")
    provider_url = os.getenv("AGENT_PROVIDER_URL")
    provider_model = os.getenv("AGENT_PROVIDER_MODEL")
    configured_mode = os.getenv("AGENT_MODE") or _env("CLIO_AGENT_RUNTIME", "FILMGRAPH_AGENT_RUNTIME")
    agent_mode = (configured_mode or ("live" if provider_key and provider_url else "simulated")).lower()
    if agent_mode == "simulated":
        agent_mode = "simulation"

    return AppSettings(
        environment=_env("CLIO_ENV", "FILMGRAPH_ENV", "local") or "local",
        clickhouse=clickhouse,
        mcp_endpoint=_env("CLIO_MCP_ENDPOINT", "FILMGRAPH_MCP_ENDPOINT"),
        mcp_command=_env("CLIO_MCP_COMMAND", "FILMGRAPH_MCP_COMMAND"),
        graph_query_mode=os.getenv("GRAPH_QUERY_MODE", "auto").lower(),
        seed_file=base_dir / "infra" / "clickhouse" / "init" / "002_seed.sql",
        use_memory_store=(_env("CLIO_USE_MEMORY_STORE", "FILMGRAPH_USE_MEMORY_STORE", "true") or "true").lower() == "true",
        agent_runtime_mode=agent_mode,
        github_token=_env("CLIO_GITHUB_TOKEN", "GITHUB_TOKEN"),
        agent_provider_url=provider_url,
        agent_provider_model=provider_model,
        agent_provider_api_key=provider_key,
        google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION"),
    )


def _load_dotenv(path: Path) -> None:
    """Load the local project env without adding a runtime dependency."""
    # Unit tests intentionally control settings through process env and must
    # remain deterministic even when a developer has a local .env file.
    if os.getenv("PYTEST_CURRENT_TEST") or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
