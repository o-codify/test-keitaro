class AppError(Exception):
    """Ошибка бизнес-логики, которую показываем пользователю как есть."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
