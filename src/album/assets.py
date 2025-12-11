"""Asset management and photo page processing for HTML generation."""

from src.core.logger import get_logger
from src.data.models import AssetPhoto, Photo, PhotoPageData
from src.media.layout_engine import (
    is_one_portrait_two_landscapes,
    is_three_portraits,
)

logger = get_logger(__name__)


def calculate_photo_pages_data(
    photo_pages: list[list[Photo]],
) -> list[PhotoPageData]:
    photo_pages_paths: list[PhotoPageData] = []

    for page in photo_pages:
        # Create tasks for all photos in the page
        asset_photos = [
            AssetPhoto(id=p.id, path=p.path.absolute()) for p in page if p.path.exists()
        ]

        if not asset_photos:
            continue

        # Calculate layout flags on-the-fly based on photo aspect ratios
        layout_class = None
        grid_style = None

        if len(page) == 3:
            if is_three_portraits(page):
                layout_class = "three-portraits"
            elif is_one_portrait_two_landscapes(page):
                layout_class = "portrait-landscape-split"
                grid_style = _calc_pll_grid_style(page)

        photo_pages_paths.append(
            PhotoPageData(
                photos=asset_photos,
                layout_class=layout_class,
                grid_style=grid_style,
            )
        )

    return photo_pages_paths


def _calc_pll_grid_style(page: list[Photo]) -> str:
    # Calculate dynamic grid split accounting for row gap
    # Constants from CSS
    page_content_width_mm = 272  # 297mm (A4) - 20mm (padding) - 5mm (col gap)
    row_gap_mm = 7

    # Get aspect ratios
    # Clamp portrait AR to minimum 0.75 (3:4) to prevent extremely narrow columns
    # that cause misalignment for phone screenshots or cropped images.
    raw_ar_p = page[0].aspect_ratio or 0.75
    ar_p = max(raw_ar_p, 0.75)
    ar_l1 = page[1].aspect_ratio or 1.33  # Default to 4:3
    ar_l2 = page[2].aspect_ratio or 1.33
    ar_l_avg = (ar_l1 + ar_l2) / 2

    # Formula derived to ensure:
    # Height(Left) = Height(Right_Top) + Gap + Height(Right_Bottom)
    # W_p / AR_p = (W_l / AR_l) + Gap + (W_l / AR_l)
    # W_p / AR_p = (2 * W_l / AR_l) + Gap
    # We also know: W_p + W_l = PAGE_CONTENT_WIDTH_MM
    # ... solving for W_p (P_p) ...

    numerator = (2 * page_content_width_mm / ar_l_avg) + row_gap_mm
    denominator = (1 / ar_p) + (2 / ar_l_avg)

    w_p = numerator / denominator
    w_l = page_content_width_mm - w_p

    return f"grid-template-columns: {w_p:.2f}fr {w_l:.2f}fr;"
