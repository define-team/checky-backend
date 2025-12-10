from dataclasses import dataclass
from typing import Optional
from dom import Node

class ErrorType:
    FONT = "font"
    FONT_SIZE = "font_size"
    SPACING = "spacing"
    HEADING_STRUCTURE = "heading_structure"
    TABLE = "table"
    IMAGE = "image"
    LINK = "link"
    GENERAL = "general"
    PAGE_MARGIN = "page_margin"
    PAGE_NUMBER = "page_number"
    MISSING_IMAGE_DESCRIPTION = "missing_image_description"
    PARAGRAPH_JUSTIFIED = "paragraph_justified"

@dataclass
class RuleError:
    message: str
    node: Node
    node_id: int = 0
    error_type: str = ErrorType.GENERAL
    expected: Optional[str] = None
    found: Optional[str] = None
