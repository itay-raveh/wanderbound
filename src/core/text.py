import math


def choose_text_dir(text: str) -> str:
    return "rtl" if any("\u0590" <= char <= "\u05ff" for char in text) else "ltr"


_WIDTH = 40


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
    if not text:
        return 0

    current_visual_len = 0
    current_char_idx = 0

    # We scan paragraph by paragraph
    # We must treat the split carefully to track original indices
    # text.split('\n') loses the strictly original positions if we aren't careful?
    # Actually, iterating by finding \n is safer.

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
            return min(len(segment), max(1, (threshold // _WIDTH) * _WIDTH))

        current_visual_len += cost
        # Advance index: segment len + 1 for the newline if present
        step_len = len(segment) + (1 if has_newline else 0)
        current_char_idx += step_len
        start = end + 1

    return len(text)
