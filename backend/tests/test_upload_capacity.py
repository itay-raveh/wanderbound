from app.logic.uploads.capacity import StorageCapacity, has_upload_capacity

GiB = 1024**3
MiB = 1024**2


def test_second_maximum_upload_is_rejected_before_it_can_fill_the_volume() -> None:
    assert (
        has_upload_capacity(
            capacity=StorageCapacity(
                total_bytes=50 * GiB,
                free_bytes=46 * GiB,
                persistent_budget_bytes=20 * GiB,
                minimum_free_bytes=256 * MiB,
            ),
            active_upload_sizes=[4 * GiB],
            new_upload_size=4 * GiB,
        )
        is False
    )


def test_upload_is_admitted_when_the_workspace_and_filesystem_have_room() -> None:
    assert (
        has_upload_capacity(
            capacity=StorageCapacity(
                total_bytes=80 * GiB,
                free_bytes=76 * GiB,
                persistent_budget_bytes=20 * GiB,
                minimum_free_bytes=256 * MiB,
            ),
            active_upload_sizes=[4 * GiB],
            new_upload_size=4 * GiB,
        )
        is True
    )
