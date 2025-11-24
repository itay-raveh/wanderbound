"""Custom exception classes for the album generator."""


class AlbumGeneratorError(Exception):
    """Base exception for all album generator errors."""


class ValidationError(AlbumGeneratorError):
    """Raised when input validation fails.

    Args:
        message: Error message describing what validation failed
        field: Optional field name that failed validation
    """

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class APIError(AlbumGeneratorError):
    """Raised when an external API call fails.

    Args:
        message: Error message describing the API failure
        api_name: Name of the API that failed
        status_code: Optional HTTP status code if available
    """

    def __init__(
        self, message: str, api_name: str, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.api_name = api_name
        self.status_code = status_code
        self.message = message


class DataLoadError(AlbumGeneratorError):
    """Raised when trip data cannot be loaded or parsed.

    Args:
        message: Error message describing the data loading failure
        file_path: Optional path to the file that failed to load
    """

    def __init__(self, message: str, file_path: str | None = None) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.message = message


class PhotoProcessingError(AlbumGeneratorError):
    """Raised when photo processing fails.

    Args:
        message: Error message describing the photo processing failure
        photo_path: Optional path to the photo that failed
    """

    def __init__(self, message: str, photo_path: str | None = None) -> None:
        super().__init__(message)
        self.photo_path = photo_path
        self.message = message
