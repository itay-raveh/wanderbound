"""Asset management and photo page processing for HTML generation."""

from src.core.logger import get_logger
from src.data.models import PhotoPage, PhotoWithDims
from src.media.layout_engine import (
    is_one_portrait_two_landscapes,
    is_three_portraits,
)

logger = get_logger(__name__)


def make_photo_pages_data(
    photo_pages: list[list[PhotoWithDims]],
) -> list[PhotoPage]:
    photo_pages_paths: list[PhotoPage] = []

    for page in photo_pages:
        asset_photos = [p.path for p in page if p.path.exists()]

        if not asset_photos:
            continue

        layout_class = None
        grid_style = None

        if len(page) == 3:
            if is_three_portraits(page):
                layout_class = "three-portraits"
            elif is_one_portrait_two_landscapes(page):
                layout_class = "portrait-landscape-split"
                grid_style = _calc_pll_grid_style(page)

        photo_pages_paths.append(
            PhotoPage(
                photos=asset_photos,
                layout_class=layout_class,
                grid_style=grid_style,
            )
        )

    return photo_pages_paths


def _calc_pll_grid_style(page: list[PhotoWithDims]) -> str:
    page_content_width_mm = 272
    row_gap_mm = 7

    raw_ar_p = page[0].aspect_ratio or 3 / 4.0
    ar_p = max(raw_ar_p, 3 / 4.0)
    ar_l1 = page[1].aspect_ratio or 4 / 3.0
    ar_l2 = page[2].aspect_ratio or 4 / 3.0
    ar_l_avg = (ar_l1 + ar_l2) / 2

    numerator = (2 * page_content_width_mm / ar_l_avg) + row_gap_mm
    denominator = (1 / ar_p) + (2 / ar_l_avg)

    w_p = numerator / denominator
    w_l = page_content_width_mm - w_p

    return f"grid-template-columns: {w_p}fr {w_l}fr;"
