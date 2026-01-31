import math


def choose_text_dir(text: str) -> str:
    # Basic Hebrew and Arabic ranges
    rtl_ranges = [
        ("\u0590", "\u05ff"),  # Hebrew
        ("\u0600", "\u06ff"),  # Arabic
        ("\u0750", "\u077f"),  # Arabic Supplement
        ("\u08a0", "\u08ff"),  # Arabic Extended-A
        ("\ufb50", "\ufdff"),  # Arabic Presentation Forms-A
        ("\ufe70", "\ufeff"),  # Arabic Presentation Forms-B
    ]
    return (
        "rtl"
        if any(
            any(start <= char <= end for start, end in rtl_ranges)
            for char in text
        )
        else "ltr"
    )


_WIDTH = 80


def calculate_visual_length(text: str) -> int:
    """Calculate visual length by simulating line wrapping.

    Returns estimated character consumption (lines * _WIDTH).
    """
    if not text:
        return 0

    lines = 0
    # Use split('\n') to preserve empty lines from consecutive/trailing newlines
    for para in text.split("\n"):
        if not para:
            lines += 1
        else:
            lines += math.ceil(len(para) / _WIDTH)

    return lines * _WIDTH


def find_visual_split_index(text: str, threshold: int) -> int:
    """Find the character index to split text such that visual length matches threshold.

    Favor splitting at newlines.
    """
    current_visual_len = 0
    current_char_idx = 0

    start = 0
    while start < len(text):
        # Find next newline
        try:
            end = text.index("\n", start)
            segment = text[start:end]
            has_newline = True
        except ValueError:
            end = len(text)
            segment = text[start:]
            has_newline = False

        # visual cost of this segment (line)
        # Empty line = 1 line cost
        cost = _WIDTH if not segment else math.ceil(len(segment) / _WIDTH) * _WIDTH

        if current_visual_len + cost > threshold:
            if current_char_idx > 0:
                return current_char_idx

            # Must split inside this massive segment
            # Calculate how many characters fit in the remaining threshold
            chars_that_fit = max(1, (threshold // _WIDTH) * _WIDTH)
            return current_char_idx + chars_that_fit

        current_visual_len += cost
        # Advance index: segment len + 1 for the newline if present
        step_len = len(segment) + (1 if has_newline else 0)
        current_char_idx += step_len
        start = end + 1

    return len(text)
