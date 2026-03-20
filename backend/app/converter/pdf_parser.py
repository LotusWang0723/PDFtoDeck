"""PDF parser: extract text, images, and vector paths using pymupdf."""

import fitz  # pymupdf
from .models import (
    BBox, TextElement, ImageElement, PathNode,
    VectorElement, PageElements, ElementType,
    TextBlock,
)
from ..config import DEFAULT_ICON_THRESHOLD, ICON_NODE_LIMIT


def _color_to_rgb(color) -> tuple:
    """Convert pymupdf color (0-1 float) to RGB (0-255 int)."""
    if not color:
        return (0, 0, 0)
    if isinstance(color, (int, float)):
        v = int(color * 255)
        return (v, v, v)
    return tuple(int(c * 255) for c in color[:3])


def _color_int_to_rgb(color_int) -> tuple:
    """Convert pymupdf integer color to RGB (0-255).
    
    pymupdf text colors are stored as integers representing RGB.
    """
    if isinstance(color_int, (int, float)):
        ci = int(color_int)
        r = (ci >> 16) & 0xFF
        g = (ci >> 8) & 0xFF
        b = ci & 0xFF
        return (r, g, b)
    return (0, 0, 0)


def _merge_text_blocks(
    raw_spans: list[dict], page_width: float, page_height: float
) -> list[TextBlock]:
    """Merge individual text spans into logical text blocks.
    
    Groups spans that are vertically close and horizontally overlapping
    into single TextBlock objects (preserving per-span styling).
    """
    if not raw_spans:
        return []
    
    # Sort by y position, then x
    raw_spans.sort(key=lambda s: (s["bbox"][1], s["bbox"][0]))
    
    blocks: list[TextBlock] = []
    current_lines: list[list[dict]] = []
    current_bbox = None
    
    for span in raw_spans:
        sbbox = span["bbox"]  # (x0, y0, x1, y1)
        
        if current_bbox is None:
            current_lines = [[span]]
            current_bbox = list(sbbox)
            continue
        
        # Check if this span belongs to the same block:
        # - vertically close (within 2x font size gap)
        # - horizontally overlapping or adjacent
        font_size = span.get("size", 12)
        y_gap = sbbox[1] - current_bbox[3]  # gap between block bottom and span top
        x_overlap = min(sbbox[2], current_bbox[2]) - max(sbbox[0], current_bbox[0])
        
        # Same line: y positions are very close
        is_same_line = abs(sbbox[1] - current_lines[-1][0]["bbox"][1]) < font_size * 0.5
        
        # New line in same block: small y gap and reasonable x overlap
        is_next_line = (0 <= y_gap < font_size * 2.0 and 
                       x_overlap > -page_width * 0.3)
        
        if is_same_line:
            current_lines[-1].append(span)
            current_bbox[2] = max(current_bbox[2], sbbox[2])
            current_bbox[3] = max(current_bbox[3], sbbox[3])
        elif is_next_line:
            current_lines.append([span])
            current_bbox[0] = min(current_bbox[0], sbbox[0])
            current_bbox[1] = min(current_bbox[1], sbbox[1])
            current_bbox[2] = max(current_bbox[2], sbbox[2])
            current_bbox[3] = max(current_bbox[3], sbbox[3])
        else:
            # Flush current block
            blocks.append(_build_text_block(current_lines, current_bbox))
            current_lines = [[span]]
            current_bbox = list(sbbox)
    
    if current_lines:
        blocks.append(_build_text_block(current_lines, current_bbox))
    
    return blocks


def _build_text_block(lines: list[list[dict]], bbox: list) -> TextBlock:
    """Build a TextBlock from grouped lines of spans."""
    # Build full text with line breaks
    text_parts = []
    primary_font_size = 12.0
    primary_font_name = ""
    primary_color = (255, 255, 255)
    primary_bold = False
    primary_italic = False
    max_char_count = 0
    
    for line_spans in lines:
        line_text = ""
        for span in line_spans:
            line_text += span.get("text", "")
        text_parts.append(line_text)
        
        # Track the most common style (by character count)
        for span in line_spans:
            chars = len(span.get("text", ""))
            if chars > max_char_count:
                max_char_count = chars
                primary_font_size = span.get("size", 12)
                primary_font_name = span.get("font", "")
                primary_color = _color_int_to_rgb(span.get("color", 0))
                flags = span.get("flags", 0)
                primary_bold = bool(flags & 2**4)
                primary_italic = bool(flags & 2**1)
    
    full_text = "\n".join(text_parts)
    
    return TextBlock(
        text=full_text,
        bbox=BBox(*bbox),
        font_size=primary_font_size,
        font_name=primary_font_name,
        bold=primary_bold,
        italic=primary_italic,
        color=primary_color,
        line_spans=lines,
    )


def parse_pdf(
    pdf_path: str,
    icon_threshold: float = DEFAULT_ICON_THRESHOLD,
) -> list[PageElements]:
    """Parse a PDF file and extract elements from each page."""
    doc = fitz.open(pdf_path)
    pages = []

    for page_num, page in enumerate(doc):
        pw, ph = page.rect.width, page.rect.height
        page_area = pw * ph
        elements = PageElements(
            page_num=page_num, width=pw, height=ph,
        )

        # --- Text extraction → merge into blocks ---
        raw_spans = []
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in blocks.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    raw_spans.append(span)

        # Merge spans into logical text blocks
        text_blocks = _merge_text_blocks(raw_spans, pw, ph)
        elements.text_blocks = text_blocks
        
        # Also keep individual TextElements for backward compat
        for span in raw_spans:
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
                color=_color_int_to_rgb(span.get("color", 0)),
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
            has_curve = False
            for item in d.get("items", []):
                op = item[0]
                if op == "m":
                    nodes.append(PathNode(item[1].x, item[1].y, "move"))
                elif op == "l":
                    nodes.append(PathNode(item[1].x, item[1].y, "line"))
                elif op == "c":
                    has_curve = True
                    # Store all 3 bezier control points
                    nodes.append(PathNode(item[1].x, item[1].y, "curve_c1"))
                    nodes.append(PathNode(item[2].x, item[2].y, "curve_c2"))
                    nodes.append(PathNode(item[3].x, item[3].y, "curve"))
                elif op == "re":
                    r = item[1]
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
            has_fill = d.get("fill") is not None
            has_stroke = d.get("color") is not None
            width = d.get("width", 1.0)

            # Classify vector element
            if area_ratio > icon_threshold:
                etype = ElementType.VECTOR_LARGE
            elif len(nodes) > ICON_NODE_LIMIT:
                etype = ElementType.ICON_IMAGE  # Plan B: render as image
            else:
                etype = ElementType.ICON_SHAPE  # Plan A: editable shape

            elements.vectors.append(VectorElement(
                nodes=nodes, bbox=bbox,
                fill_color=fill if has_fill else None,
                stroke_color=stroke if has_stroke else None,
                stroke_width=width, element_type=etype,
                has_curves=has_curve,
            ))

        pages.append(elements)

    doc.close()
    return pages
