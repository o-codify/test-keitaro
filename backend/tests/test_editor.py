"""Сценарии из видео с существующей обёрткой."""

DEMO = 101  # демо-кампания mock-клиента: поток 1001 (гео -> Google), поток 1002 (офферы 1,2,3)
STREAM = 1002


def offers_stream(view):
    return next(s for s in view["streams"] if s["id"] == STREAM)


def shares(view):
    return [(o["offer_id"], o["status"], o["share"]) for o in offers_stream(view)["offers"]]


def kt_shares(kt):
    return [(o["offer_id"], o["share"]) for o in kt.get_stream(STREAM)["offers"]]


def test_fetch_shows_offer_streams_and_plain_streams(api):
    view = api.post(f"/api/campaigns/{DEMO}/fetch").json()
    assert [s["id"] for s in view["streams"]] == [STREAM, 1001]
    assert shares(view) == [(1, "active", 34), (2, "active", 33), (3, "active", 33)]
    plain = view["streams"][1]
    assert plain["has_offers"] is False and plain["offers"] == []
    assert offers_stream(view)["dirty"] is False


def test_add_recalculates_and_needs_push(api, kt):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    view = api.post(f"/api/streams/{STREAM}/offers", json={"offer_id": 4}).json()
    assert shares(view) == [(1, "active", 25), (2, "active", 25), (3, "active", 25), (4, "active", 25)]
    assert offers_stream(view)["dirty"] is True
    # в Keitaro ещё ничего не поменялось
    assert kt_shares(kt) == [(1, 34), (2, 33), (3, 33)]

    view = api.post(f"/api/streams/{STREAM}/push").json()
    assert offers_stream(view)["dirty"] is False
    assert kt_shares(kt) == [(1, 25), (2, 25), (3, 25), (4, 25)]


def test_cancel_drops_unpublished_offers(api, kt):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    api.post(f"/api/streams/{STREAM}/offers", json={"offer_id": 4})
    api.post(f"/api/streams/{STREAM}/offers/1/remove")
    view = api.post(f"/api/streams/{STREAM}/cancel").json()
    assert shares(view) == [(1, "active", 34), (2, "active", 33), (3, "active", 33)]
    assert offers_stream(view)["dirty"] is False
    assert kt_shares(kt) == [(1, 34), (2, 33), (3, 33)]


def test_add_existing_offer_conflicts(api):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    assert api.post(f"/api/streams/{STREAM}/offers", json={"offer_id": 1}).status_code == 409
    assert api.post(f"/api/streams/{STREAM}/offers", json={"offer_id": 9999}).status_code == 404


def test_remove_then_bring_back(api, kt):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    view = api.post(f"/api/streams/{STREAM}/offers/1/remove").json()
    assert shares(view) == [(2, "active", 50), (3, "active", 50), (1, "removed", 0)]
    assert offers_stream(view)["dirty"] is True

    api.post(f"/api/streams/{STREAM}/push")
    assert kt_shares(kt) == [(2, 50), (3, 50)]

    view = api.post(f"/api/streams/{STREAM}/offers/1/restore").json()
    assert shares(view) == [(1, "active", 34), (2, "active", 33), (3, "active", 33)]
    assert offers_stream(view)["dirty"] is True
    api.post(f"/api/streams/{STREAM}/push")
    assert sorted(kt_shares(kt)) == [(1, 34), (2, 33), (3, 33)]


def test_offer_removed_in_keitaro_becomes_removed_on_fetch(api, kt):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    # пользователь удалил оффер прямо в Keitaro
    api.post(f"/api/mock/streams/{STREAM}/offers/2/delete")
    view = api.post(f"/api/campaigns/{DEMO}/fetch").json()
    assert shares(view) == [(1, "active", 34), (3, "active", 33), (2, "removed", 0)]
    assert offers_stream(view)["dirty"] is False  # это состояние Keitaro, а не черновик

    view = api.post(f"/api/streams/{STREAM}/offers/2/restore").json()
    assert offers_stream(view)["dirty"] is True


def test_pinned_share_is_kept(api, kt):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    api.post(f"/api/streams/{STREAM}/offers", json={"offer_id": 4})  # 25 x 4
    view = api.post(f"/api/streams/{STREAM}/offers/3/pin", json={"pinned": True}).json()
    assert shares(view)[2] == (3, "active", 25)

    view = api.post(f"/api/streams/{STREAM}/offers/1/remove").json()
    # 25 закреплено, остаток 75 делится между 2 и 4
    assert shares(view) == [(2, "active", 38), (3, "active", 25), (4, "active", 37), (1, "removed", 0)]

    view = api.post(f"/api/streams/{STREAM}/offers/1/restore").json()
    assert shares(view) == [(1, "active", 25), (2, "active", 25), (3, "active", 25), (4, "active", 25)]

    view = api.post(f"/api/streams/{STREAM}/offers/3/pin", json={"pinned": True, "share": 40}).json()
    assert shares(view) == [(1, "active", 20), (2, "active", 20), (3, "active", 40), (4, "active", 20)]
    assert offers_stream(view)["share_total"] == 100

    api.post(f"/api/streams/{STREAM}/push")
    assert kt_shares(kt) == [(1, 20), (2, 20), (3, 40), (4, 20)]


def test_pin_over_100_rejected(api):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    api.post(f"/api/streams/{STREAM}/offers/1/pin", json={"pinned": True, "share": 70})
    resp = api.post(f"/api/streams/{STREAM}/offers/2/pin", json={"pinned": True, "share": 40})
    assert resp.status_code == 400


def test_push_rejects_wrong_total(api):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    api.post(f"/api/streams/{STREAM}/offers/1/pin", json={"pinned": True, "share": 50})
    api.post(f"/api/streams/{STREAM}/offers/2/pin", json={"pinned": True, "share": 30})
    view = api.post(f"/api/streams/{STREAM}/offers/3/pin", json={"pinned": True, "share": 10}).json()
    assert offers_stream(view)["share_total"] == 90
    assert api.post(f"/api/streams/{STREAM}/push").status_code == 400


def test_plain_stream_not_editable(api):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    assert api.post("/api/streams/1001/offers", json={"offer_id": 4}).status_code == 400


def test_audit_log(api):
    api.post(f"/api/campaigns/{DEMO}/fetch")
    api.post(f"/api/streams/{STREAM}/offers", json={"offer_id": 4})
    api.post(f"/api/streams/{STREAM}/push")
    actions = [e["action"] for e in api.get(f"/api/campaigns/{DEMO}/log").json()]
    assert actions[:3] == ["push", "add", "fetch"]


def test_keitaro_link_points_to_campaign_page():
    from app.config import Settings
    from app.services.editor import keitaro_link

    settings = Settings(
        _env_file=None,
        keitaro_mock=False,
        keitaro_url="https://tracker.example.com/",
        campaign_prefix="test_",
        geo_redirect_url="https://google.com",
    )
    assert keitaro_link(settings, 215437) == "https://tracker.example.com/admin/#!/campaign/215437"
