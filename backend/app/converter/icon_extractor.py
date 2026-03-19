"""Icon extractor: classify and filter vector elements."""

from .models import VectorElement, ElementType
from ..config import DEFAULT_ICON_THRESHOLD, ICON_NODE_LIMIT


def classify_vector(
    ve: VectorElement,
    page_area: float,
    icon_threshold: float = DEFAULT_ICON_THRESHOLD,
    node_limit: int = ICON_NODE_LIMIT,
) -> ElementType:
    """Classify a vector element based on area and complexity.

    Args:
        ve: The vector element to classify.
        page_area: Total page area in points².
        icon_threshold: Max area ratio for icon detection.
        node_limit: Max path nodes for Plan A (editable shape).

    Returns:
        ElementType classification.
    """
    if page_area <= 0:
        return ElementType.VECTOR_LARGE

    area_ratio = ve.bbox.area / page_area

    if area_ratio > icon_threshold:
        return ElementType.VECTOR_LARGE
    elif ve.node_count > node_limit:
        return ElementType.ICON_IMAGE   # Plan B
    else:
        return ElementType.ICON_SHAPE   # Plan A
