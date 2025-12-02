"""Custom exception classes for the album generator."""


class AlbumGeneratorError(Exception):
    pass


class ConfigurationError(AlbumGeneratorError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DataLoadError(AlbumGeneratorError):
    def __init__(self, message: str, file_path: str | None = None) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.message = message
