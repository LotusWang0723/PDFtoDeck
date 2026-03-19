"""Data models for the converter pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ElementType(Enum):
    TEXT = "text"
    IMAGE = "image"
    ICON_SHAPE = "icon_shape"      # Freeform editable (Plan A)
    ICON_IMAGE = "icon_image"      # SVG fallback (Plan B)
    VECTOR_LARGE = "vector_large"  # Exceeds threshold, treat as image


@dataclass
class BBox:
    """Bounding box in PDF coordinates (points, origin bottom-left)."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return abs(self.x1 - self.x0)

    @property
    def height(self) -> float:
        return abs(self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class TextElement:
    text: str
    bbox: BBox
    font_size: float
    font_name: str = ""
    bold: bool = False
    italic: bool = False
    color: tuple = (0, 0, 0)  # RGB 0-255


@dataclass
class ImageElement:
    image_bytes: bytes
    bbox: BBox
    ext: str = "png"  # png, jpeg


@dataclass
class PathNode:
    """A single point in a vector path."""
    x: float
    y: float
    kind: str = "line"  # line, curve, move, close


@dataclass
class VectorElement:
    nodes: list[PathNode] = field(default_factory=list)
    bbox: BBox = None
    fill_color: Optional[tuple] = None   # RGB 0-255
    stroke_color: Optional[tuple] = None
    stroke_width: float = 1.0
    element_type: ElementType = ElementType.ICON_SHAPE

    @property
    def node_count(self) -> int:
        return len(self.nodes)


@dataclass
class PageElements:
    """All extracted elements from a single PDF page."""
    page_num: int
    width: float   # page width in points
    height: float  # page height in points
    texts: list[TextElement] = field(default_factory=list)
    images: list[ImageElement] = field(default_factory=list)
    vectors: list[VectorElement] = field(default_factory=list)
