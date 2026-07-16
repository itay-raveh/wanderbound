from app.core.config import Settings


def test_application_defaults_belong_to_settings() -> None:
    defaulted_fields = (
        "ENVIRONMENT",
        "VITE_FRONTEND_URL",
        "MAX_UPLOAD_SIZE_BYTES",
        "UPLOAD_PART_SIZE_BYTES",
    )

    assert all(
        not Settings.model_fields[field_name].is_required()
        for field_name in defaulted_fields
    )
