from typing import Any

import httpx

from app.keitaro.base import JSON
from app.keitaro.errors import KeitaroError


class KeitaroHttpClient:
    """Клиент Keitaro Admin API v1 (https://admin-api.docs.keitaro.io/)."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 20.0):
        if not base_url or not api_key:
            raise KeitaroError(
                "Не заданы KEITARO_URL / KEITARO_API_KEY в .env "
                "(или включите KEITARO_MOCK=true для работы без трекера)",
                status_code=None,
            )
        base = base_url.rstrip("/")
        if not base.endswith("/admin_api/v1"):
            base += "/admin_api/v1"
        self._http = httpx.Client(
            base_url=base,
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroError(f"Keitaro недоступен: {exc}") from exc

        if response.status_code >= 400:
            raise KeitaroError(_error_message(response), status_code=response.status_code)
        if not response.content:
            return None
        return response.json()

    # --- справочники ---
    def list_domains(self) -> list[JSON]:
        return self._request("GET", "/domains")

    def list_campaign_groups(self) -> list[JSON]:
        return self._request("GET", "/groups", params={"type": "campaigns"})

    def list_traffic_sources(self) -> list[JSON]:
        return self._request("GET", "/traffic_sources")

    def list_offers(self) -> list[JSON]:
        return self._request("GET", "/offers")

    def get_offer(self, offer_id: int) -> JSON:
        return self._request("GET", f"/offers/{offer_id}")

    # --- кампании ---
    def list_campaigns(self) -> list[JSON]:
        return self._request("GET", "/campaigns")

    def get_campaign(self, campaign_id: int) -> JSON:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: JSON) -> JSON:
        return self._request("POST", "/campaigns", json=payload)

    def delete_campaign(self, campaign_id: int) -> None:
        # В Keitaro DELETE переносит кампанию в архив
        self._request("DELETE", f"/campaigns/{campaign_id}")

    # --- потоки ---
    def list_streams(self, campaign_id: int) -> list[JSON]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def get_stream(self, stream_id: int) -> JSON:
        return self._request("GET", f"/streams/{stream_id}")

    def create_stream(self, payload: JSON) -> JSON:
        return self._request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: JSON) -> JSON:
        return self._request("PUT", f"/streams/{stream_id}", json=payload)


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        # nginx перед Keitaro отвечает HTML-страницей (например, на несуществующий id)
        if response.status_code == 404:
            return "объект не найден (404)"
        return f"HTTP {response.status_code}"
    if isinstance(data, dict):
        for key in ("error", "message", "errors"):
            if data.get(key):
                return _flatten(data[key])
        # ошибки валидации: {"alias": ["Alias is required"]}
        return _flatten(data)
    return str(data)[:500]


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_flatten(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(_flatten(v) for v in value)
    return str(value)
