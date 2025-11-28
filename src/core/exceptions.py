"""Custom exception classes for the album generator."""


class AlbumGeneratorError(Exception):
    pass


class ConfigurationError(AlbumGeneratorError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(AlbumGeneratorError):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class APIError(AlbumGeneratorError):
    def __init__(self, message: str, api_name: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.api_name = api_name
        self.status_code = status_code
        self.message = message


class DataLoadError(AlbumGeneratorError):
    def __init__(self, message: str, file_path: str | None = None) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.message = message


class PhotoProcessingError(AlbumGeneratorError):
    def __init__(self, message: str, photo_path: str | None = None) -> None:
        super().__init__(message)
        self.photo_path = photo_path
        self.message = message


__all__ = [
    "APIError",
    "AlbumGeneratorError",
    "ConfigurationError",
    "DataLoadError",
    "PhotoProcessingError",
    "ValidationError",
]
