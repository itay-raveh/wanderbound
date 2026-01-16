"""Text utility functions."""


def choose_text_dir(text: str) -> str:
    return "rtl" if any("\u0590" <= char <= "\u05ff" for char in text) else "ltr"
