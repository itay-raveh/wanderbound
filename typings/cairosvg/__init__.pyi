def svg2png(
    bytestring: bytes,
    *,
    dpi: int = 96,
    scale: float = 1.0,
    unsafe: bool = False,
    invert_images: bool = False,
    output_width: int | None = None,
    output_height: int | None = None,
) -> bytes | None: ...
