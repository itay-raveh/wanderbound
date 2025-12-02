"""Step filtering and selection utility functions."""

from src.core.logger import get_logger
from src.data.models import Step

from .args import Args

logger = get_logger(__name__)


def _get_steps_distributed(all_steps: list[Step], count: int) -> list[Step]:
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


def filter_steps(all_steps: list[Step], args: Args) -> list[Step]:
    if args.sample:
        dist_steps = _get_steps_distributed(all_steps, args.sample)
        logger.info("Sampled %d steps evenly across the trip", len(dist_steps))
        return dist_steps

    if args.steps:
        range_steps: list[Step] = all_steps[args.steps]
        logger.info(
            "Filtered to steps %d-%d: %d steps", args.steps.start, args.steps.stop, len(range_steps)
        )
        return range_steps

    logger.info("Using all %d steps", len(all_steps))
    return all_steps
