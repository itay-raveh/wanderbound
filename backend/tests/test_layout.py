import pytest

from app.logic.layout.builder import (
    _build_pages,
    _landscape_page_count,
    _landscape_pages,
    _optimal_mixed_count,
    _pages_of,
    _portrait_page_count,
    _three_page_count,
)

# Helpers


def _names(prefix: str, n: int) -> list[str]:
    """Generate n dummy media names with a prefix."""
    return [f"{prefix}{i}" for i in range(n)]


VALID_PORTRAIT_SIZES = {1, 2, 3}
VALID_LANDSCAPE_SIZES = {1, 3, 4}
VALID_MIXED_SIZE = 3  # 1P + 2L


# _portrait_page_count


class TestPortraitPageCount:
    @pytest.mark.parametrize(
        ("n", "expected"),
        [
            (0, 0),
            (1, 1),
            (2, 1),
            (3, 1),
            (4, 2),
            (5, 2),
            (6, 2),
            (7, 3),
            (9, 3),
            (10, 4),
        ],
    )
    def test_values(self, n: int, expected: int) -> None:
        assert _portrait_page_count(n) == expected

    def test_is_ceil_n_over_3(self) -> None:
        for n in range(50):
            assert _portrait_page_count(n) == -(-n // 3)


# _landscape_page_count


class TestLandscapePageCount:
    @pytest.mark.parametrize(
        ("n", "expected"),
        [
            (0, 0),
            (1, 1),
            (2, 2),
            (3, 1),
            (4, 1),
            (5, 2),
            (6, 2),
            (7, 2),
            (8, 2),
            (9, 3),
            (10, 3),
            (11, 3),
            (12, 3),
            (13, 4),
        ],
    )
    def test_values(self, n: int, expected: int) -> None:
        assert _landscape_page_count(n) == expected

    def test_n2_is_special_case(self) -> None:
        """n=2 is the only case where ceil(n/4) is wrong (gives 1, need 2)."""
        assert _landscape_page_count(2) == 2


# _three_page_count


class TestThreePageCount:
    @pytest.mark.parametrize(
        ("n", "expected"),
        [(3, 1), (4, 0), (6, 2), (7, 1), (8, 0), (9, 3), (10, 2), (11, 1), (12, 0)],
    )
    def test_values(self, n: int, expected: int) -> None:
        assert _three_page_count(n) == expected

    def test_is_neg_n_mod_4(self) -> None:
        for n in range(3, 50):
            assert _three_page_count(n) == -n % 4


# _optimal_mixed_count


class TestOptimalMixedCount:
    def test_no_photos(self) -> None:
        assert _optimal_mixed_count(0, 0) == 0

    def test_only_portraits(self) -> None:
        assert _optimal_mixed_count(5, 0) == 0

    def test_only_landscapes(self) -> None:
        assert _optimal_mixed_count(0, 8) == 0

    def test_1p_4l_no_mixing_is_better(self) -> None:
        """1P+4L: mix -> 1P2L+2 singles = 3pp, no mix -> 1P+4L = 2pp."""
        assert _optimal_mixed_count(1, 4) == 0

    def test_1p_2l_mixing_is_better(self) -> None:
        """1P + 2L: mixing gives 1 page, no mix gives 1P + 2 singles = 3 pages."""
        assert _optimal_mixed_count(1, 2) == 1

    def test_result_minimizes_pages(self) -> None:
        """Brute-force verify that the returned b gives the minimum total pages."""
        for p in range(15):
            for l in range(15):
                b = _optimal_mixed_count(p, l)
                total = (
                    b + _portrait_page_count(p - b) + _landscape_page_count(l - 2 * b)
                )

                # Check all other valid b values give >= total
                for b2 in range(min(p, l // 2) + 1):
                    t2 = (
                        b2
                        + _portrait_page_count(p - b2)
                        + _landscape_page_count(l - 2 * b2)
                    )
                    assert total <= t2, (
                        f"p={p}, l={l}: b={b} gives {total}, b={b2} gives {t2}"
                    )


# _pages_of


class TestPagesOf:
    def test_exact_multiple(self) -> None:
        items = _names("l", 6)
        pages = list(_pages_of(items, 3))
        assert len(pages) == 2
        assert all(len(p) == 3 for p in pages)

    def test_remainder(self) -> None:
        items = _names("l", 7)
        pages = list(_pages_of(items, 3))
        assert len(pages) == 3
        assert [len(p) for p in pages] == [3, 3, 1]

    def test_empty(self) -> None:
        assert list(_pages_of([], 4)) == []

    def test_all_items_present(self) -> None:
        items = _names("x", 10)
        pages = list(_pages_of(items, 4))
        assert sorted(p for page in pages for p in page) == sorted(items)


# _landscape_pages


class TestLandscapePages:
    def test_empty(self) -> None:
        assert list(_landscape_pages([])) == []

    def test_singles(self) -> None:
        items = _names("l", 2)
        pages = list(_landscape_pages(items))
        assert pages == [[items[0]], [items[1]]]

    def test_n5_edge_case(self) -> None:
        items = _names("l", 5)
        pages = list(_landscape_pages(items))
        assert len(pages) == 2
        assert len(pages[0]) == 4
        assert len(pages[1]) == 1

    @pytest.mark.parametrize("n", [3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 20])
    def test_valid_page_sizes(self, n: int) -> None:
        items = _names("l", n)
        pages = list(_landscape_pages(items))
        for page in pages:
            assert len(page) in VALID_LANDSCAPE_SIZES, (
                f"invalid page size {len(page)} for n={n}"
            )

    @pytest.mark.parametrize("n", [3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 20])
    def test_optimal_page_count(self, n: int) -> None:
        items = _names("l", n)
        pages = list(_landscape_pages(items))
        assert len(pages) == _landscape_page_count(n)

    @pytest.mark.parametrize("n", range(21))
    def test_all_items_consumed(self, n: int) -> None:
        items = _names("l", n)
        pages = list(_landscape_pages(items))
        flat = [p for page in pages for p in page]
        assert sorted(flat) == sorted(items)


# Integration tests for _build_pages


class TestBuildPages:
    def test_empty(self) -> None:
        assert list(_build_pages([], [])) == []

    def test_only_portraits(self) -> None:
        portraits = _names("p", 5)
        pages = list(_build_pages(portraits, []))
        assert len(pages) == 2  # ceil(5/3)
        flat = [p for page in pages for p in page]
        assert sorted(flat) == sorted(portraits)

    def test_only_landscapes(self) -> None:
        landscapes = _names("l", 7)
        pages = list(_build_pages([], landscapes))
        flat = [p for page in pages for p in page]
        assert sorted(flat) == sorted(landscapes)

    def test_1p_2l_mixed(self) -> None:
        portraits = _names("p", 1)
        landscapes = _names("l", 2)
        pages = list(_build_pages(portraits, landscapes))
        assert len(pages) == 1
        assert len(pages[0]) == 3

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
        """6P+5L should NOT mix — [P,P,P]*2 + [L,L,L,L] + [L] avoids a 0p-3l page."""
        portraits = _names("p", 6)
        landscapes = _names("l", 5)
        pages = list(_build_pages(portraits, landscapes))
        assert len(pages) == 4
        sizes = sorted(len(p) for p in pages)
        assert sizes == [1, 3, 3, 4]

    @pytest.mark.parametrize(
        ("p", "l"),
        [
            (0, 0),
            (1, 0),
            (0, 1),
            (3, 3),
            (1, 2),
            (1, 4),
            (4, 6),
            (5, 10),
            (3, 7),
            (10, 10),
        ],
    )
    def test_all_items_consumed(self, p: int, l: int) -> None:
        portraits = _names("p", p)
        landscapes = _names("l", l)
        pages = list(_build_pages(portraits, landscapes))
        flat = [item for page in pages for item in page]
        assert sorted(flat) == sorted(portraits + landscapes)

    @pytest.mark.parametrize(
        ("p", "l"),
        [
            (0, 0),
            (1, 0),
            (0, 1),
            (3, 3),
            (1, 2),
            (1, 4),
            (4, 6),
            (5, 10),
            (3, 7),
            (10, 10),
        ],
    )
    def test_page_count_is_optimal(self, p: int, l: int) -> None:
        """Total pages should equal what _optimal_mixed_count + formulas predict."""
        portraits = _names("p", p)
        landscapes = _names("l", l)
        pages = list(_build_pages(portraits, landscapes))

        mixed = _optimal_mixed_count(p, l)
        expected = (
            mixed
            + _portrait_page_count(p - mixed)
            + _landscape_page_count(l - 2 * mixed)
        )
        assert len(pages) == expected

    @pytest.mark.parametrize(
        ("p", "l"),
        [(3, 3), (1, 2), (4, 6), (5, 10), (3, 7), (10, 10), (6, 12)],
    )
    def test_no_single_photo_pages_when_avoidable(self, p: int, l: int) -> None:
        """With enough photos, every page should have at least 2 items."""
        portraits = _names("p", p)
        landscapes = _names("l", l)
        pages = list(_build_pages(portraits, landscapes))

        # Only allow singles if total count makes them unavoidable
        singles = sum(1 for page in pages if len(page) == 1)
        # A single is unavoidable only if we have exactly 1 item of some type left over
        assert singles <= (p % 3 == 1) + (l in {1, 2}) + (l == 5)
