"""PPT builder: generate .pptx from extracted PDF elements."""

import io
import fitz  # for rendering vectors as images
from pptx import Presentation
from pptx.util import Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from io import BytesIO

from .models import (
    PageElements, ElementType, VectorElement, PathNode,
    TextBlock,
)


PT_TO_EMU = 12700  # 1 point = 12700 EMU


def _pt_to_emu(val: float) -> int:
    return int(val * PT_TO_EMU)


def _rgb(color_tuple: tuple) -> RGBColor:
    r, g, b = color_tuple[:3]
    return RGBColor(min(max(r, 0), 255), min(max(g, 0), 255), min(max(b, 0), 255))


def _color_int_to_rgb(color_int) -> tuple:
    """Convert pymupdf integer color to RGB (0-255)."""
    if isinstance(color_int, (int, float)):
        ci = int(color_int)
        r = (ci >> 16) & 0xFF
        g = (ci >> 8) & 0xFF
        b = ci & 0xFF
        return (r, g, b)
    return (0, 0, 0)


def _add_text_block(slide, tb: TextBlock, page_height: float):
    """Add a merged text block with per-line styling."""
    left = _pt_to_emu(tb.bbox.x0)
    top = _pt_to_emu(tb.bbox.y0)
    width = _pt_to_emu(tb.bbox.width)
    height = _pt_to_emu(tb.bbox.height)

    width = max(width, _pt_to_emu(20))
    height = max(height, _pt_to_emu(tb.font_size * 1.5))

    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = True
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.margin_left = 0
    tf.margin_right = 0

    first_para = True
    for line_spans in tb.line_spans:
        if first_para:
            p = tf.paragraphs[0]
            first_para = False
        else:
            p = tf.add_paragraph()

        for span in line_spans:
            text = span.get("text", "")
            if not text:
                continue
            run = p.add_run()
            run.text = text
            run.font.size = Pt(span.get("size", 12))
            flags = span.get("flags", 0)
            run.font.bold = bool(flags & 2**4)
            run.font.italic = bool(flags & 2**1)
            run.font.color.rgb = _rgb(_color_int_to_rgb(span.get("color", 0)))
            font_name = span.get("font", "")
            if font_name:
                run.font.name = font_name


def _add_image_element(slide, ie, page_height: float):
    """Add an image to the slide."""
    left = _pt_to_emu(ie.bbox.x0)
    top = _pt_to_emu(ie.bbox.y0)
    width = _pt_to_emu(ie.bbox.width)
    height = _pt_to_emu(ie.bbox.height)

    stream = BytesIO(ie.image_bytes)
    slide.shapes.add_picture(stream, left, top, width, height)


def _add_freeform_shape(slide, ve: VectorElement, page_height: float):
    """Add an editable freeform shape (Plan A).
    
    Uses python-pptx 1.x: build_freeform → move_to / add_line_segments.
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
        nx = (node.x - ve.bbox.x0) / bw
        ny = (node.y - ve.bbox.y0) / bh
        return (nx, ny)

    # Filter to main path nodes (skip bezier control points for freeform)
    main_nodes = [n for n in ve.nodes if n.kind not in ("curve_c1", "curve_c2")]
    if not main_nodes:
        return

    first = main_nodes[0]
    sx, sy = _normalize(first)
    builder = slide.shapes.build_freeform(sx, sy, scale=(width, height))

    segment: list[tuple[float, float]] = []
    for node in main_nodes[1:]:
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
    if ve.fill_color is not None:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(ve.fill_color)
    else:
        shape.fill.background()

    if ve.stroke_color is not None:
        shape.line.color.rgb = _rgb(ve.stroke_color)
        shape.line.width = Pt(ve.stroke_width or 0.5)
    else:
        shape.line.fill.background()


def _add_vector_as_image(slide, ve: VectorElement, page_height: float):
    """Add vector as a filled rectangle (Plan B for large/complex shapes)."""
    left = _pt_to_emu(ve.bbox.x0)
    top = _pt_to_emu(ve.bbox.y0)
    width = _pt_to_emu(ve.bbox.width) or _pt_to_emu(10)
    height = _pt_to_emu(ve.bbox.height) or _pt_to_emu(10)

    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE.RECTANGLE
        left, top, width, height,
    )
    if ve.fill_color is not None:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(ve.fill_color)
    else:
        shape.fill.background()

    if ve.stroke_color is not None:
        shape.line.color.rgb = _rgb(ve.stroke_color)
    else:
        shape.line.fill.background()


def _render_vector_as_png(
    ve: VectorElement, page_width: float, page_height: float, scale: float = 2.0
) -> bytes | None:
    """Render a vector element as a transparent PNG using pymupdf.
    
    Creates a temporary single-page PDF with the vector path,
    then rasterizes it to a PNG image with transparency.
    Returns PNG bytes or None on failure.
    """
    try:
        # Create a small page just for this vector
        tmp_doc = fitz.open()
        w = ve.bbox.width
        h = ve.bbox.height
        if w < 1 or h < 1:
            return None
        
        page = tmp_doc.new_page(width=w, height=h)
        shape = page.new_shape()
        
        # Replay the path nodes, offset to local coordinates
        ox, oy = ve.bbox.x0, ve.bbox.y0
        
        i = 0
        nodes = ve.nodes
        while i < len(nodes):
            n = nodes[i]
            px, py = n.x - ox, n.y - oy
            
            if n.kind == "move":
                shape.draw_line(fitz.Point(px, py), fitz.Point(px, py))
            elif n.kind == "line":
                if shape.last_point:
                    shape.draw_line(shape.last_point, fitz.Point(px, py))
            elif n.kind == "close":
                if shape.last_point:
                    shape.draw_line(shape.last_point, fitz.Point(px, py))
            elif n.kind == "curve_c1" and i + 2 < len(nodes):
                c1 = fitz.Point(px, py)
                c2 = fitz.Point(nodes[i+1].x - ox, nodes[i+1].y - oy)
                end = fitz.Point(nodes[i+2].x - ox, nodes[i+2].y - oy)
                if shape.last_point:
                    shape.draw_bezier(shape.last_point, c1, c2, end)
                i += 2  # skip c2 and endpoint
            elif n.kind == "curve":
                # Fallback: treat as line
                if shape.last_point:
                    shape.draw_line(shape.last_point, fitz.Point(px, py))
            i += 1
        
        # Apply fill/stroke
        fill_rgb = None
        stroke_rgb = None
        if ve.fill_color is not None:
            fill_rgb = tuple(c / 255.0 for c in ve.fill_color[:3])
        if ve.stroke_color is not None:
            stroke_rgb = tuple(c / 255.0 for c in ve.stroke_color[:3])
        
        shape.finish(
            fill=fill_rgb,
            color=stroke_rgb,
            width=ve.stroke_width or 0.5,
        )
        shape.commit()
        
        # Render to PNG with transparency
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=True)
        png_bytes = pix.tobytes("png")
        
        tmp_doc.close()
        return png_bytes
    except Exception:
        return None


def _add_branding_footer(slide, page_width: float, page_height: float):
    """Add a subtle PDFtoDeck branding footer."""
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
    """Build a .pptx file from parsed PDF pages."""
    prs = Presentation()

    # Set document metadata
    prs.core_properties.title = (
        source_filename.replace(".pdf", "").replace(".PDF", "")
        if source_filename else "PDFtoDeck"
    )
    prs.core_properties.comments = "Converted by PDFtoDeck — https://pdftodeck.com"

    for page in pages:
        prs.slide_width = _pt_to_emu(page.width)
        prs.slide_height = _pt_to_emu(page.height)

        slide_layout = prs.slide_layouts[6]  # Blank
        slide = prs.slides.add_slide(slide_layout)

        # === Z-ORDER: backgrounds → vectors → images → text ===

        # 1. Large vectors (backgrounds)
        for ve in page.vectors:
            if ve.element_type == ElementType.VECTOR_LARGE:
                _add_vector_as_image(slide, ve, page.height)

        # 2. Icon fallbacks — render complex/curved ones as transparent PNG
        for ve in page.vectors:
            if ve.element_type == ElementType.ICON_IMAGE:
                # Try rendering as transparent PNG first
                png = _render_vector_as_png(ve, page.width, page.height)
                if png:
                    left = _pt_to_emu(ve.bbox.x0)
                    top = _pt_to_emu(ve.bbox.y0)
                    w = _pt_to_emu(ve.bbox.width) or _pt_to_emu(10)
                    h = _pt_to_emu(ve.bbox.height) or _pt_to_emu(10)
                    slide.shapes.add_picture(BytesIO(png), left, top, w, h)
                else:
                    _add_vector_as_image(slide, ve, page.height)

        # 3. Editable freeform icon shapes
        for ve in page.vectors:
            if ve.element_type == ElementType.ICON_SHAPE:
                if ve.has_curves:
                    # Curves don't convert well to freeform line segments
                    # Render as transparent PNG instead
                    png = _render_vector_as_png(ve, page.width, page.height)
                    if png:
                        left = _pt_to_emu(ve.bbox.x0)
                        top = _pt_to_emu(ve.bbox.y0)
                        w = _pt_to_emu(ve.bbox.width) or _pt_to_emu(10)
                        h = _pt_to_emu(ve.bbox.height) or _pt_to_emu(10)
                        slide.shapes.add_picture(BytesIO(png), left, top, w, h)
                    else:
                        _add_freeform_shape(slide, ve, page.height)
                else:
                    _add_freeform_shape(slide, ve, page.height)

        # 4. Images
        for ie in page.images:
            _add_image_element(slide, ie, page.height)

        # 5. Text blocks (merged paragraphs)
        for tb in page.text_blocks:
            _add_text_block(slide, tb, page.height)

        # 6. Branding
        _add_branding_footer(slide, page.width, page.height)

    prs.save(output_path)
    return output_path
