"""Step filtering and selection utility functions."""

from src.data.models import Step

__all__ = ["get_steps_distributed", "get_steps_in_range"]


def get_steps_in_range(all_steps: list[Step], start: int, end: int) -> list[Step]:
    # Convert to 0-indexed
    start_idx = max(0, start - 1)
    end_idx = min(len(all_steps), end)
    return all_steps[start_idx:end_idx]


def get_steps_distributed(all_steps: list[Step], count: int) -> list[Step]:
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
