from functools import cache

from app.logic.layout.builder import _build_pages

# Helpers


def _names(prefix: str, n: int) -> list[str]:
    """Generate n dummy media names with a prefix."""
    return [f"{prefix}{i}" for i in range(n)]


# Supported album grids: portrait-only 1/2/3, landscape-only 1/3/4,
# and one portrait with two landscapes. This oracle packs actual grid shapes
# rather than reusing the production page-count or mixing helpers.
GRIDS = ((1, 0), (2, 0), (3, 0), (0, 1), (0, 3), (0, 4), (1, 2))


@cache
def _minimum_pages(portraits: int, landscapes: int) -> int:
    if portraits == landscapes == 0:
        return 0
    return 1 + min(
        _minimum_pages(portraits - p, landscapes - l)
        for p, l in GRIDS
        if p <= portraits and l <= landscapes
    )


class TestBuildPages:
    def test_1p_4l_no_mix(self) -> None:
        """Should NOT mix - 1P + 4L = 2 pages is better than 1P2L + 1L + 1L = 3."""
        portraits = _names("p", 1)
        landscapes = _names("l", 4)
        pages = list(_build_pages(portraits, landscapes))
        assert len(pages) == 2

    def test_4p_3l_prefers_mixed(self) -> None:
        """4P+3L: mixed [P,L,L]+[P,P,P]+[L]=3pp beats [P,P]+[P,P]+[L,L,L]."""
        portraits = _names("p", 4)
        landscapes = _names("l", 3)
        pages = list(_build_pages(portraits, landscapes))
        assert len(pages) == 3
        sizes = sorted(len(p) for p in pages)
        assert sizes == [1, 3, 3]

    def test_1p_6l_prefers_mixed(self) -> None:
        """1P+6L: mixed [P,L,L]+[L,L,L,L]=2pp beats [P]+[L,L,L]+[L,L,L]."""
        portraits = _names("p", 1)
        landscapes = _names("l", 6)
        pages = list(_build_pages(portraits, landscapes))
        assert len(pages) == 2
        sizes = sorted(len(p) for p in pages)
        assert sizes == [3, 4]

    def test_6p_5l_avoids_3l_page(self) -> None:
        """6P+5L should NOT mix - [P,P,P]*2 + [L,L,L,L] + [L] avoids a 0p-3l page."""
        portraits = _names("p", 6)
        landscapes = _names("l", 5)
        pages = list(_build_pages(portraits, landscapes))
        assert len(pages) == 4
        sizes = sorted(len(p) for p in pages)
        assert sizes == [1, 3, 3, 4]

    def test_packing_preserves_every_photo_in_valid_minimal_grids(self) -> None:
        for p in range(21):
            for l in range(21):
                portraits = _names("p", p)
                landscapes = _names("l", l)
                pages = list(_build_pages(portraits, landscapes))
                assert sorted(item for page in pages for item in page) == sorted(
                    portraits + landscapes
                ), (p, l)
                for page in pages:
                    shape = (
                        sum(name.startswith("p") for name in page),
                        sum(name.startswith("l") for name in page),
                    )
                    assert shape in GRIDS, (p, l, page)
                assert len(pages) == _minimum_pages(p, l), (p, l)
