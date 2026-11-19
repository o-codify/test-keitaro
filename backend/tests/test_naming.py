import pytest

from app.services.naming import apply_prefix, distribute_evenly, parse_geo


def test_prefix_added_once():
    assert apply_prefix("campaign1", "test_chalimov_") == "test_chalimov_campaign1"
    assert apply_prefix("test_chalimov_campaign1", "test_chalimov_") == "test_chalimov_campaign1"
    assert apply_prefix("  TEST_CHALIMOV_x ", "test_chalimov_") == "test_chalimov_x"


def test_parse_geo():
    assert parse_geo("mx, AU;ro  mx") == ["MX", "AU", "RO"]
    assert parse_geo(["br"]) == ["BR"]
    with pytest.raises(ValueError):
        parse_geo("MEX")
    with pytest.raises(ValueError):
        parse_geo(" , ")


@pytest.mark.parametrize(
    "count,expected",
    [(1, [100]), (2, [50, 50]), (3, [34, 33, 33]), (4, [25, 25, 25, 25]), (6, [17, 17, 17, 17, 16, 16])],
)
def test_distribute_evenly(count, expected):
    assert distribute_evenly(count) == expected
    assert sum(distribute_evenly(count)) == 100


def test_distribute_rest():
    assert distribute_evenly(2, 75) == [38, 37]
    assert distribute_evenly(0) == []


def test_settings_require_env_values(monkeypatch, tmp_path):
    import pytest

    from app import config

    for var in ("CAMPAIGN_PREFIX", "GEO_REDIRECT_URL", "KEITARO_MOCK"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setitem(config.Settings.model_config, "env_file", tmp_path / "missing.env")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError) as exc:
            config.get_settings()
        message = str(exc.value)
        assert "CAMPAIGN_PREFIX" in message and "GEO_REDIRECT_URL" in message and "KEITARO_MOCK" in message
    finally:
        config.get_settings.cache_clear()
