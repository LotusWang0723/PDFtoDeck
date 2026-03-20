"""PDF parser: extract text, images, and vector paths using pymupdf."""

import fitz  # pymupdf
from .models import (
    BBox, TextElement, ImageElement, PathNode,
    VectorElement, PageElements, ElementType,
)
from ..config import DEFAULT_ICON_THRESHOLD, ICON_NODE_LIMIT


def _color_to_rgb(color) -> tuple:
    """Convert pymupdf drawing color (0-1 float tuple) to RGB (0-255 int).
    
    Used for vector path fill/stroke colors which are float tuples.
    """
    if not color:
        return (0, 0, 0)
    if isinstance(color, (int, float)):
        v = int(color * 255)
        return (v, v, v)
    return tuple(int(c * 255) for c in color[:3])


def _text_color_to_rgb(color_int) -> tuple:
    """Convert pymupdf text span color (packed int) to RGB (0-255).
    
    Text colors are stored as integers: 0xRRGGBB.
    E.g. 5884904 = 0x59CBE8 → (89, 203, 232) = light blue.
    """
    if not isinstance(color_int, (int, float)):
        return (0, 0, 0)
    ci = int(color_int)
    r = (ci >> 16) & 0xFF
    g = (ci >> 8) & 0xFF
    b = ci & 0xFF
    return (r, g, b)


def parse_pdf(
    pdf_path: str,
    icon_threshold: float = DEFAULT_ICON_THRESHOLD,
) -> list[PageElements]:
    """Parse a PDF file and extract elements from each page.

    Args:
        pdf_path: Path to the PDF file.
        icon_threshold: Max area ratio (0-1) for icon detection.

    Returns:
        List of PageElements, one per page.
    """
    doc = fitz.open(pdf_path)
    pages = []

    for page_num, page in enumerate(doc):
        pw, ph = page.rect.width, page.rect.height
        page_area = pw * ph
        elements = PageElements(
            page_num=page_num, width=pw, height=ph,
        )

        # --- Text extraction ---
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in blocks.get("blocks", []):
            if block.get("type") != 0:  # type 0 = text
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    bbox = BBox(*span["bbox"])
                    flags = span.get("flags", 0)
                    elements.texts.append(TextElement(
                        text=text,
                        bbox=bbox,
                        font_size=span.get("size", 12),
                        font_name=span.get("font", ""),
                        bold=bool(flags & 2**4),
                        italic=bool(flags & 2**1),
                    color=_text_color_to_rgb(span.get("color", 0)),
                    ))

        # --- Image extraction ---
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                ext = base_image.get("ext", "png")
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    r = img_rects[0]
                    bbox = BBox(r.x0, r.y0, r.x1, r.y1)
                    elements.images.append(ImageElement(
                        image_bytes=img_bytes, bbox=bbox, ext=ext,
                    ))
            except Exception:
                continue

        # --- Vector path extraction ---
        drawings = page.get_drawings()
        for d in drawings:
            nodes = []
            for item in d.get("items", []):
                op = item[0]  # operation: "l", "c", "m", "re", etc.
                if op == "m":  # moveto
                    nodes.append(PathNode(item[1].x, item[1].y, "move"))
                elif op == "l":  # lineto
                    nodes.append(PathNode(item[1].x, item[1].y, "line"))
                elif op == "c":  # curveto (bezier)
                    nodes.append(PathNode(item[3].x, item[3].y, "curve"))
                elif op == "re":  # rectangle
                    r = item[1]  # fitz.Rect
                    nodes.append(PathNode(r.x0, r.y0, "move"))
                    nodes.append(PathNode(r.x1, r.y0, "line"))
                    nodes.append(PathNode(r.x1, r.y1, "line"))
                    nodes.append(PathNode(r.x0, r.y1, "line"))
                    nodes.append(PathNode(r.x0, r.y0, "close"))

            if not nodes:
                continue

            rect = d.get("rect", page.rect)
            bbox = BBox(rect.x0, rect.y0, rect.x1, rect.y1)
            area_ratio = bbox.area / page_area if page_area > 0 else 1

            fill = _color_to_rgb(d.get("fill"))
            stroke = _color_to_rgb(d.get("color"))
            width = d.get("width", 1.0)

            # Classify vector element
            if area_ratio > icon_threshold:
                etype = ElementType.VECTOR_LARGE
            elif len(nodes) > ICON_NODE_LIMIT:
                etype = ElementType.ICON_IMAGE  # Plan B: SVG fallback
            else:
                etype = ElementType.ICON_SHAPE  # Plan A: editable shape

            elements.vectors.append(VectorElement(
                nodes=nodes, bbox=bbox,
                fill_color=fill, stroke_color=stroke,
                stroke_width=width, element_type=etype,
            ))

        pages.append(elements)

    doc.close()
    return pages
