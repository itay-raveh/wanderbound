from app.logic.uploads.capacity import has_upload_capacity

GiB = 1024**3


def test_second_maximum_upload_is_rejected_before_it_can_fill_the_volume() -> None:
    assert (
        has_upload_capacity(
            workspace_bytes=30 * GiB,
            free_bytes=46 * GiB,
            active_upload_sizes=[4 * GiB],
            new_upload_size=4 * GiB,
        )
        is False
    )


def test_upload_is_admitted_when_the_workspace_and_filesystem_have_room() -> None:
    assert (
        has_upload_capacity(
            workspace_bytes=60 * GiB,
            free_bytes=76 * GiB,
            active_upload_sizes=[4 * GiB],
            new_upload_size=4 * GiB,
        )
        is True
    )
