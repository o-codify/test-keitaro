import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.keitaro import get_keitaro_client
from app.keitaro.mock_client import MockKeitaroClient
from app.main import app


# Тестовые значения задаются явно — .env в тестах не читается
TEST_PREFIX = "test_chalimov_"
TEST_REDIRECT = "https://google.com"


@pytest.fixture
def kt() -> MockKeitaroClient:
    return MockKeitaroClient(campaign_prefix=TEST_PREFIX, redirect_url=TEST_REDIRECT)


@pytest.fixture
def api(kt):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    settings = Settings(
        _env_file=None,
        keitaro_mock=True,
        campaign_prefix=TEST_PREFIX,
        geo_redirect_url=TEST_REDIRECT,
        default_domain_id=1,
        default_group_id=1,
        default_traffic_source_id=1,
    )
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_keitaro_client] = lambda: kt
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
