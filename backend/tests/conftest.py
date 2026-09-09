from __future__ import annotations

from filmgraph.api import create_app
from filmgraph.dependencies import get_repository, get_service, get_settings


def reset_singletons():
    get_repository.cache_clear()
    get_service.cache_clear()
    get_settings.cache_clear()


def app():
    reset_singletons()
    return create_app()

