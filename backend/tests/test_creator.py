def test_create_campaign_builds_two_streams(api, kt):
    resp = api.post("/api/campaigns", json={"name": "campaign1", "geo": "mx, au", "offer_id": 5})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "test_chalimov_campaign1"
    assert body["geo"] == ["MX", "AU"]
    assert body["url"].startswith("https://in.posdk.xyz/")

    campaign = kt.get_campaign(body["id"])
    assert campaign["domain_id"] == 1
    assert campaign["group_id"] == 1
    assert campaign["traffic_source_id"] == 1
    assert campaign["type"] == "position"

    geo_stream, offer_stream = kt.list_streams(body["id"])
    assert geo_stream["position"] == 1
    assert geo_stream["schema"] == "redirect"
    assert geo_stream["action_payload"] == "https://google.com"
    assert geo_stream["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}]

    assert offer_stream["position"] == 2
    assert offer_stream["filters"] == []
    assert [(o["offer_id"], o["share"]) for o in offer_stream["offers"]] == [(5, 100)]

    # кампания сразу доступна в редакторе
    view = api.get(f"/api/campaigns/{body['id']}/streams").json()
    offers_stream = view["streams"][0]
    assert offers_stream["has_offers"] is True
    assert [o["offer_id"] for o in offers_stream["offers"]] == [5]
    assert view["streams"][1]["has_offers"] is False


def test_create_validates_offer_and_geo(api):
    assert api.post("/api/campaigns", json={"name": "x", "geo": "MX", "offer_id": 999}).status_code == 422
    assert api.post("/api/campaigns", json={"name": "x", "geo": "MEX", "offer_id": 1}).status_code == 422


def test_rollback_when_stream_fails(api, kt, monkeypatch):
    before = {c["id"] for c in kt.list_campaigns()}
    calls = {"n": 0}
    original = kt.create_stream

    def flaky(payload):
        calls["n"] += 1
        if calls["n"] == 2:
            from app.keitaro import KeitaroError

            raise KeitaroError("boom", 500)
        return original(payload)

    monkeypatch.setattr(kt, "create_stream", flaky)
    resp = api.post("/api/campaigns", json={"name": "broken", "geo": "MX", "offer_id": 1})
    assert resp.status_code == 502
    assert {c["id"] for c in kt.list_campaigns()} == before


def test_campaign_list_filters_by_prefix(api, kt):
    kt.create_campaign({"name": "someone_else"})
    names = [c["name"] for c in api.get("/api/campaigns").json()]
    assert "test_chalimov_demo" in names
    assert "someone_else" not in names
    all_names = [c["name"] for c in api.get("/api/campaigns?only_mine=false").json()]
    assert "someone_else" in all_names


def test_offer_stream_is_default_type(api, kt):
    body = api.post("/api/campaigns", json={"name": "types", "geo": "MX", "offer_id": 1}).json()
    geo_stream, offer_stream = kt.list_streams(body["id"])
    assert geo_stream["type"] == "regular"
    assert offer_stream["type"] == "default"


def test_traffic_source_required_when_available(api, kt, monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = app.dependency_overrides[get_settings]()
    monkeypatch.setattr(settings, "default_traffic_source_id", None)
    resp = api.post("/api/campaigns", json={"name": "nosource", "geo": "MX", "offer_id": 1})
    assert resp.status_code == 422
    assert "источник" in resp.json()["detail"]

    # Ключ без прав на TrafficSources: Keitaro отдаёт пустой список
    kt.traffic_sources = []
    assert api.get("/api/dictionaries").json()["traffic_sources"] == []
    resp = api.post("/api/campaigns", json={"name": "nosource", "geo": "MX", "offer_id": 1})
    assert resp.status_code == 201, resp.text
    assert kt.get_campaign(resp.json()["id"])["traffic_source_id"] == 0
