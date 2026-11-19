from functools import lru_cache

from app.config import get_settings
from app.keitaro.base import KeitaroClient
from app.keitaro.errors import KeitaroError
from app.keitaro.http_client import KeitaroHttpClient
from app.keitaro.mock_client import MockKeitaroClient

__all__ = ["KeitaroClient", "KeitaroError", "get_keitaro_client"]


@lru_cache
def _client() -> KeitaroClient:
    settings = get_settings()
    if settings.keitaro_mock:
        return MockKeitaroClient(
            campaign_prefix=settings.campaign_prefix,
            redirect_url=settings.geo_redirect_url,
        )
    return KeitaroHttpClient(
        settings.keitaro_url, settings.keitaro_api_key, settings.keitaro_timeout
    )


def get_keitaro_client() -> KeitaroClient:
    """FastAPI-зависимость. В тестах подменяется через dependency_overrides."""
    return _client()
