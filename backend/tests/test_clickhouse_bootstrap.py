from __future__ import annotations

from filmgraph.repositories.clickhouse import (
    ClickHouseFilmGraphRepository,
    _override_database_directives,
)
from filmgraph.settings import ClickHouseSettings, load_settings


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def named_results(self):
        return [dict(row) for row in self._rows]


class _BootstrapClient:
    def __init__(self, counts: dict[str, int]):
        self.database = "__default__"
        self.commands: list[str] = []
        self.counts = counts

    def command(self, sql, **_kwargs):
        self.commands.append(sql)

    def query(self, sql, **_kwargs):
        if "FROM pipeline_stages" in sql:
            return _Result([{"count": self.counts.get("pipeline", 0)}])
        if "kind IN" in sql:
            return _Result([{"count": self.counts.get("stale", 0)}])
        if "kind = 'beat'" in sql:
            return _Result([{"count": self.counts.get("beats", 0)}])
        if "FROM graph_nodes" in sql:
            return _Result([{"count": self.counts.get("graph", 0)}])
        return _Result([])


def _settings(database: str = "clio", **overrides) -> ClickHouseSettings:
    values = {
        "host": "localhost",
        "port": 8443,
        "username": "default",
        "password": "secret",
        "database": database,
        "secure": True,
        "database_mode": "cloud",
        "bootstrap_schema": True,
        "create_database": True,
        "seed_demo": True,
        "allow_demo_reset": False,
    }
    values.update(overrides)
    return ClickHouseSettings(**values)


def test_database_directives_are_rewritten_without_touching_seed_values():
    source = "CREATE DATABASE IF NOT EXISTS filmgraph;\nUSE filmgraph;\nINSERT INTO t VALUES ('local://filmgraph/script');"
    rewritten = _override_database_directives(source, "clio")
    assert "CREATE DATABASE IF NOT EXISTS `clio`" in rewritten
    assert "USE `clio`" in rewritten
    assert "local://filmgraph/script" in rewritten
    assert _override_database_directives(source, "clio", create_database=False).lstrip().startswith("USE `clio`")


def test_cloud_bootstrap_seeds_empty_clio_database_with_cloud_safe_sql():
    repository = ClickHouseFilmGraphRepository(_settings())
    client = _BootstrapClient({"pipeline": 0, "graph": 0, "stale": 0, "beats": 0})
    repository._client = client

    repository.bootstrap()

    assert any(command == "CREATE DATABASE IF NOT EXISTS `clio`" for command in client.commands)
    assert any("USE `clio`" in command for command in client.commands)
    assert any(command.startswith("INSERT INTO pipeline_stages") for command in client.commands)
    assert not any(command.startswith("TRUNCATE TABLE") for command in client.commands)


def test_cloud_bootstrap_never_resets_an_existing_stale_graph():
    repository = ClickHouseFilmGraphRepository(
        _settings(allow_demo_reset=True)
    )
    client = _BootstrapClient({"pipeline": 1, "graph": 25, "stale": 1, "beats": 16})
    repository._client = client

    repository.bootstrap()

    assert repository._can_reset_demo is False
    assert not any(command.startswith("TRUNCATE TABLE") for command in client.commands)
    assert not any(command.startswith("INSERT INTO pipeline_stages") for command in client.commands)


def test_settings_infer_secure_cloud_defaults(monkeypatch):
    for key in (
        "CLIO_CLICKHOUSE_PORT",
        "CLIO_CLICKHOUSE_DATABASE",
        "CLIO_CLICKHOUSE_SECURE",
        "CLIO_DATABASE_MODE",
        "CLIO_CREATE_DATABASE",
        "CLIO_SEED_DEMO",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLIO_CLICKHOUSE_HOST", "example.us-central1.gcp.clickhouse.cloud")
    monkeypatch.setenv("CLIO_CLICKHOUSE_PASSWORD", "secret")

    settings = load_settings()

    assert settings.clickhouse is not None
    assert settings.clickhouse.database_mode == "cloud"
    assert settings.clickhouse.port == 8123
    assert settings.clickhouse.secure is True
    assert settings.clickhouse.create_database is False
    assert settings.clickhouse.seed_demo is False
