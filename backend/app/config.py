from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Настройки берутся из .env (или переменных окружения).

    Поля без значения по умолчанию обязательны: если их нет в .env,
    приложение не стартует и сообщает, что именно нужно задать.
    Значения по умолчанию оставлены только у технических параметров.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Keitaro (URL и ключ нужны только при KEITARO_MOCK=false — проверяет клиент)
    keitaro_mock: bool
    keitaro_url: str = ""
    keitaro_api_key: str = ""
    keitaro_timeout: float = 20.0

    # База данных: если DATABASE_URL пустой — SQLite в backend/app.db
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"

    # Правила создания кампаний — только из .env
    campaign_prefix: str
    geo_redirect_url: str
    default_domain_id: int | None = None
    default_group_id: int | None = None
    default_traffic_source_id: int | None = None

    # Кэш офферов для автокомплита
    offer_cache_ttl_seconds: int = 300

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing = [
            str(err["loc"][0]).upper() for err in exc.errors() if err["type"] == "missing"
        ]
        if missing:
            raise RuntimeError(
                f"В {ENV_FILE} не заданы обязательные настройки: {', '.join(missing)}. "
                "Скопируйте .env.example в .env и заполните их."
            ) from exc
        raise
