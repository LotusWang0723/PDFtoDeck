"""PPT builder: generate .pptx from extracted PDF elements."""

import fitz  # for rendering curved vectors as PNG
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
    """Add a text box to the slide.

    pymupdf uses top-left origin (same as PPT), so NO Y-axis flip needed.
    """
    left = _pt_to_emu(te.bbox.x0)
    top = _pt_to_emu(te.bbox.y0)
    width = _pt_to_emu(te.bbox.width)
    height = _pt_to_emu(te.bbox.height)

    # Ensure minimum dimensions
    width = max(width, _pt_to_emu(10))
    height = max(height, _pt_to_emu(te.font_size * 1.5))

    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = False
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.margin_left = 0
    tf.margin_right = 0
    p = tf.paragraphs[0]
    p.text = te.text
    p.font.size = Pt(te.font_size)
    p.font.bold = te.bold
    p.font.italic = te.italic
    p.font.color.rgb = _rgb(te.color)
    if te.font_name:
        p.font.name = te.font_name


def _add_image_element(slide, ie, page_height: float):
    """Add an image to the slide.

    pymupdf uses top-left origin, so NO Y-axis flip.
    """
    left = _pt_to_emu(ie.bbox.x0)
    top = _pt_to_emu(ie.bbox.y0)
    width = _pt_to_emu(ie.bbox.width)
    height = _pt_to_emu(ie.bbox.height)

    stream = BytesIO(ie.image_bytes)
    slide.shapes.add_picture(stream, left, top, width, height)


def _add_freeform_shape(slide, ve: VectorElement, page_height: float):
    """Add an editable freeform shape (Plan A) to the slide.

    Uses python-pptx 1.x API: build_freeform → move_to / add_line_segments.
    pymupdf uses top-left origin — NO Y-axis flip.
    """
    if not ve.nodes:
        return

    left = _pt_to_emu(ve.bbox.x0)
    top = _pt_to_emu(ve.bbox.y0)
    width = _pt_to_emu(ve.bbox.width) or _pt_to_emu(1)
    height = _pt_to_emu(ve.bbox.height) or _pt_to_emu(1)

    bw = ve.bbox.width or 1
    bh = ve.bbox.height or 1

    def _normalize(node):
        """Normalize node coords to 0-1 range within bbox."""
        nx = (node.x - ve.bbox.x0) / bw
        ny = (node.y - ve.bbox.y0) / bh
        return (nx, ny)

    first = ve.nodes[0]
    sx, sy = _normalize(first)

    builder = slide.shapes.build_freeform(sx, sy, scale=(width, height))

    segment: list[tuple[float, float]] = []

    for node in ve.nodes[1:]:
        nx, ny = _normalize(node)

        if node.kind == "move":
            if segment:
                builder.add_line_segments(segment, close=False)
                segment = []
            builder.move_to(nx, ny)
        else:
            segment.append((nx, ny))

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
    """Add vector as a rectangle shape (Plan B fallback)."""
    left = _pt_to_emu(ve.bbox.x0)
    top = _pt_to_emu(ve.bbox.y0)
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


def _render_curved_vector_as_png(ve: VectorElement, scale: float = 3.0) -> bytes | None:
    """Render a curved vector element as a transparent PNG using pymupdf.
    
    Creates a temp page, replays the path with bezier curves, rasterizes to PNG.
    Returns PNG bytes or None on failure.
    """
    try:
        w = ve.bbox.width
        h = ve.bbox.height
        if w < 1 or h < 1:
            return None
        
        tmp_doc = fitz.open()
        page = tmp_doc.new_page(width=w, height=h)
        shape = page.new_shape()
        
        ox, oy = ve.bbox.x0, ve.bbox.y0
        
        # Track current point for proper bezier chaining
        current = None
        
        for item in ve.raw_items:
            op = item[0]
            if op == "m":
                current = fitz.Point(item[1].x - ox, item[1].y - oy)
            elif op == "l":
                pt = fitz.Point(item[1].x - ox, item[1].y - oy)
                if current is not None:
                    shape.draw_line(current, pt)
                current = pt
            elif op == "c":
                c1 = fitz.Point(item[1].x - ox, item[1].y - oy)
                c2 = fitz.Point(item[2].x - ox, item[2].y - oy)
                end = fitz.Point(item[3].x - ox, item[3].y - oy)
                if current is not None:
                    shape.draw_bezier(current, c1, c2, end)
                current = end
            elif op == "re":
                r = item[1]
                rect = fitz.Rect(r.x0 - ox, r.y0 - oy, r.x1 - ox, r.y1 - oy)
                shape.draw_rect(rect)
                current = fitz.Point(r.x0 - ox, r.y0 - oy)
        
        fill_rgb = None
        stroke_rgb = None
        if ve.fill_color is not None:
            fill_rgb = tuple(c / 255.0 for c in ve.fill_color[:3])
        if ve.stroke_color is not None:
            stroke_rgb = tuple(c / 255.0 for c in ve.stroke_color[:3])
        
        shape.finish(
            fill=fill_rgb, color=stroke_rgb,
            width=ve.stroke_width or 0.5,
            closePath=True,
        )
        shape.commit()
        
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=True)
        png_bytes = pix.tobytes("png")
        
        tmp_doc.close()
        return png_bytes
    except Exception:
        return None


def _add_curved_vector_as_png(slide, ve: VectorElement, page_height: float):
    """Render a curved vector as transparent PNG and add as picture."""
    png = _render_curved_vector_as_png(ve)
    if png:
        left = _pt_to_emu(ve.bbox.x0)
        top = _pt_to_emu(ve.bbox.y0)
        width = _pt_to_emu(ve.bbox.width) or _pt_to_emu(10)
        height = _pt_to_emu(ve.bbox.height) or _pt_to_emu(10)
        slide.shapes.add_picture(BytesIO(png), left, top, width, height)
    else:
        # Fallback to freeform approximation
        _add_freeform_shape(slide, ve, page_height)


def _add_branding_footer(slide, page_width: float, page_height: float):
    """Add a subtle PDFtoDeck branding footer to the slide."""
    text = "Converted by PDFtoDeck"
    font_size = 6
    box_width = 120
    box_height = 12

    left = _pt_to_emu(page_width - box_width - 8)
    top = _pt_to_emu(page_height - box_height - 4)
    width = _pt_to_emu(box_width)
    height = _pt_to_emu(box_height)

    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = False
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.margin_left = 0
    tf.margin_right = 0
    p = tf.paragraphs[0]
    p.text = text
    p.alignment = PP_ALIGN.RIGHT
    p.font.size = Pt(font_size)
    p.font.color.rgb = RGBColor(160, 160, 180)
    p.font.italic = True


def build_pptx(
    pages: list[PageElements],
    output_path: str,
    source_filename: str = "",
) -> str:
    """Build a .pptx file from parsed PDF pages.

    Args:
        pages: List of PageElements from pdf_parser.
        output_path: Where to save the .pptx file.
        source_filename: Original PDF filename (for PPTX metadata).

    Returns:
        The output file path.
    """
    prs = Presentation()

    # Set document metadata
    prs.core_properties.title = source_filename.replace(".pdf", "") if source_filename else "PDFtoDeck"
    prs.core_properties.comments = "Converted by PDFtoDeck — https://pdftodeck.com"

    for page in pages:
        # Set slide dimensions to match PDF page
        prs.slide_width = _pt_to_emu(page.width)
        prs.slide_height = _pt_to_emu(page.height)

        slide_layout = prs.slide_layouts[6]  # Blank layout
        slide = prs.slides.add_slide(slide_layout)

        # === Z-ORDER MATTERS ===
        # 1. Large vectors first (backgrounds, decorative shapes)
        for ve in page.vectors:
            if ve.element_type == ElementType.VECTOR_LARGE:
                _add_vector_as_image(slide, ve, page.height)

        # 2. Icon-image fallbacks (medium complexity vectors)
        for ve in page.vectors:
            if ve.element_type == ElementType.ICON_IMAGE:
                _add_vector_as_image(slide, ve, page.height)

        # 3. Editable freeform icon shapes (or PNG for curved ones)
        for ve in page.vectors:
            if ve.element_type == ElementType.ICON_SHAPE:
                if ve.has_curves:
                    # Curves can't be represented by freeform line segments
                    # Render as transparent PNG instead
                    _add_curved_vector_as_png(slide, ve, page.height)
                else:
                    _add_freeform_shape(slide, ve, page.height)

        # 4. Images (on top of vector backgrounds)
        for ie in page.images:
            _add_image_element(slide, ie, page.height)

        # 5. Text elements (topmost, always readable)
        for te in page.texts:
            _add_text_element(slide, te, page.height)

        # 6. PDFtoDeck branding (very top)
        _add_branding_footer(slide, page.width, page.height)

    prs.save(output_path)
    return output_path
