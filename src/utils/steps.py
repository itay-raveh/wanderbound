"""Step filtering and selection utility functions."""

from ..models import Step

__all__ = ["get_steps_in_range", "get_steps_distributed"]


def get_steps_in_range(all_steps: list[Step], start: int, end: int) -> list[Step]:
    """Get steps within a specified range.

    Args:
        all_steps: Complete list of all steps in the trip.
        start: Start step number (1-indexed, inclusive).
        end: End step number (1-indexed, inclusive).

    Returns:
        List of Step objects within the specified range.
    """
    # Convert to 0-indexed
    start_idx = max(0, start - 1)
    end_idx = min(len(all_steps), end)
    return all_steps[start_idx:end_idx]


def get_steps_distributed(all_steps: list[Step], count: int) -> list[Step]:
    """Get evenly distributed steps across the entire trip.

    Samples steps at evenly spaced intervals to provide a representative
    view of the trip. Useful for testing or generating preview albums.

    Args:
        all_steps: Complete list of all steps in the trip.
        count: Number of steps to sample.

    Returns:
        List of Step objects evenly distributed across the trip.
        Returns all steps if count >= len(all_steps), or empty list if count <= 0.
    """
    if not all_steps or count <= 0:
        return []
    if count >= len(all_steps):
        return all_steps

    step_indices = []
    for i in range(count):
        idx = int((i / (count - 1)) * (len(all_steps) - 1)) if count > 1 else 0
        step_indices.append(idx)

    unique_indices = list(dict.fromkeys(step_indices))
    return [all_steps[idx] for idx in unique_indices]
