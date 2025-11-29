"""SVG parsing and cleaning utilities."""

from lxml import etree


def remove_xml_declarations(svg_data: str) -> str:
    """Remove XML declaration and DOCTYPE from SVG to avoid DTD fetching."""
    lines = svg_data.split("\n")
    cleaned_lines = []
    skip_doctype = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<?xml"):
            continue
        if stripped.startswith("<!DOCTYPE"):
            skip_doctype = True
            continue
        if skip_doctype:
            if ">" in line:
                skip_doctype = False
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def parse_svg_with_lxml(svg_data: str) -> etree._Element:
    """Parse SVG string into lxml Element."""
    svg_clean = remove_xml_declarations(svg_data)

    # Use parser that doesn't fetch external DTDs
    parser = etree.XMLParser(
        recover=True,
        strip_cdata=False,
        no_network=True,  # Don't fetch external DTDs
        huge_tree=True,  # Allow large SVG files
    )

    root = etree.fromstring(svg_clean.encode("utf-8"), parser=parser)

    # Register SVG namespace if not already registered
    if (
        root is not None
        and hasattr(root, "nsmap")
        and root.nsmap
        and "http://www.w3.org/2000/svg" not in root.nsmap.values()
    ):
        etree.register_namespace("svg", "http://www.w3.org/2000/svg")

    if root is None:
        raise ValueError("Parsed SVG root is None")

    return root


def get_svg_viewbox(root: etree._Element) -> list[float]:
    """Get viewBox from SVG root element."""
    # Assume viewBox exists and is valid
    viewbox_str = root.attrib["viewBox"]
    return [float(x) for x in viewbox_str.split()]
