"""PPT builder: generate .pptx from extracted PDF elements."""

from pptx import Presentation
from pptx.util import Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from io import BytesIO

from .models import PageElements, ElementType, VectorElement, PathNode


# PDF points to EMU (English Metric Units, used by python-pptx)
# 1 point = 12700 EMU
PT_TO_EMU = 12700


def _pt_to_emu(val: float) -> int:
    return int(val * PT_TO_EMU)


def _rgb(color_tuple: tuple) -> RGBColor:
    r, g, b = color_tuple[:3]
    return RGBColor(min(r, 255), min(g, 255), min(b, 255))


def _add_text_element(slide, te, page_height: float):
    """Add a text box to the slide."""
    left = _pt_to_emu(te.bbox.x0)
    # PDF origin is bottom-left, PPT is top-left
    top = _pt_to_emu(page_height - te.bbox.y1)
    width = _pt_to_emu(te.bbox.width)
    height = _pt_to_emu(te.bbox.height)

    # Ensure minimum dimensions
    width = max(width, _pt_to_emu(10))
    height = max(height, _pt_to_emu(te.font_size * 1.5))

    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.text = te.text
    p.font.size = Pt(te.font_size)
    p.font.bold = te.bold
    p.font.italic = te.italic
    p.font.color.rgb = _rgb(te.color)
    if te.font_name:
        p.font.name = te.font_name


def _add_image_element(slide, ie, page_height: float):
    """Add an image to the slide."""
    left = _pt_to_emu(ie.bbox.x0)
    top = _pt_to_emu(page_height - ie.bbox.y1)
    width = _pt_to_emu(ie.bbox.width)
    height = _pt_to_emu(ie.bbox.height)

    stream = BytesIO(ie.image_bytes)
    slide.shapes.add_picture(stream, left, top, width, height)


def _add_freeform_shape(slide, ve: VectorElement, page_height: float):
    """Add an editable freeform shape (Plan A) to the slide.

    Uses python-pptx 1.x API: build_freeform → move_to / add_line_segments.
    """
    if not ve.nodes:
        return

    left = _pt_to_emu(ve.bbox.x0)
    top = _pt_to_emu(page_height - ve.bbox.y1)
    width = _pt_to_emu(ve.bbox.width) or _pt_to_emu(1)
    height = _pt_to_emu(ve.bbox.height) or _pt_to_emu(1)

    bw = ve.bbox.width or 1
    bh = ve.bbox.height or 1

    def _normalize(node):
        """Normalize node coords to 0-1 range within bbox, flipping Y."""
        nx = (node.x - ve.bbox.x0) / bw
        ny = 1.0 - (node.y - ve.bbox.y0) / bh
        return (nx, ny)

    # Split nodes into sub-paths at each "move" node
    # Each sub-path: start with move_to, then add_line_segments for the rest
    first = ve.nodes[0]
    sx, sy = _normalize(first)

    builder = slide.shapes.build_freeform(sx, sy, scale=(width, height))

    segment: list[tuple[float, float]] = []

    for node in ve.nodes[1:]:
        nx, ny = _normalize(node)

        if node.kind == "move":
            # Flush current segment
            if segment:
                builder.add_line_segments(segment, close=False)
                segment = []
            builder.move_to(nx, ny)
        else:
            # line, close, curve (simplified as line)
            segment.append((nx, ny))

    # Flush remaining segment (close=True to close the shape)
    if segment:
        builder.add_line_segments(segment, close=True)

    shape = builder.convert_to_shape(left, top)

    # Apply colors
    if ve.fill_color and ve.fill_color != (0, 0, 0):
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(ve.fill_color)
    else:
        shape.fill.background()

    if ve.stroke_color:
        shape.line.color.rgb = _rgb(ve.stroke_color)
        shape.line.width = Pt(ve.stroke_width or 1.0)


def _add_vector_as_image(slide, ve: VectorElement, page_height: float):
    """Add vector as SVG-rendered image (Plan B fallback)."""
    # For MVP, render complex vectors as a placeholder rectangle
    # Full SVG rendering will be added in Phase 2
    left = _pt_to_emu(ve.bbox.x0)
    top = _pt_to_emu(page_height - ve.bbox.y1)
    width = _pt_to_emu(ve.bbox.width) or _pt_to_emu(10)
    height = _pt_to_emu(ve.bbox.height) or _pt_to_emu(10)

    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE.RECTANGLE
        left, top, width, height,
    )
    if ve.fill_color:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(ve.fill_color)
    if ve.stroke_color:
        shape.line.color.rgb = _rgb(ve.stroke_color)


def build_pptx(pages: list[PageElements], output_path: str) -> str:
    """Build a .pptx file from parsed PDF pages.

    Args:
        pages: List of PageElements from pdf_parser.
        output_path: Where to save the .pptx file.

    Returns:
        The output file path.
    """
    prs = Presentation()

    for page in pages:
        # Set slide dimensions to match PDF page
        prs.slide_width = _pt_to_emu(page.width)
        prs.slide_height = _pt_to_emu(page.height)

        slide_layout = prs.slide_layouts[6]  # Blank layout
        slide = prs.slides.add_slide(slide_layout)

        # Add text elements
        for te in page.texts:
            _add_text_element(slide, te, page.height)

        # Add images
        for ie in page.images:
            _add_image_element(slide, ie, page.height)

        # Add vector elements
        for ve in page.vectors:
            if ve.element_type == ElementType.ICON_SHAPE:
                _add_freeform_shape(slide, ve, page.height)
            elif ve.element_type == ElementType.ICON_IMAGE:
                _add_vector_as_image(slide, ve, page.height)
            elif ve.element_type == ElementType.VECTOR_LARGE:
                _add_vector_as_image(slide, ve, page.height)

    prs.save(output_path)
    return output_path
