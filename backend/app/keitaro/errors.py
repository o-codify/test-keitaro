class KeitaroError(Exception):
    """Ошибка обращения к Keitaro Admin API (сеть, авторизация, валидация)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
