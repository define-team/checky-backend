from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple

_node_id_counter = 0

def generate_node_id():
    global _node_id_counter
    _node_id_counter += 1
    return _node_id_counter

@dataclass
class Node:
    parent: Optional["Node"] = None
    children: List["Node"] = field(default_factory=list)
    orig: Any = None
    node_type: str = "node"
    errors: List[Any] = field(default_factory=list)
    node_id: int = field(default_factory=generate_node_id)

    def add_child(self, node: "Node"):
        node.parent = self
        self.children.append(node)

    def replace_child(self, old_node: "Node", new_node: "Node"):
        """
        Заменяет old_node на new_node в children.
        Безопасно, без рекурсивных сравнений.
        """
        for i, child in enumerate(self.children):
            if child is old_node:
                new_node.parent = self
                self.children[i] = new_node
                old_node.parent = None
                return True
        return False

    @property
    def next_sibling(self) -> Optional["Node"]:
        if not self.parent:
            return None
        siblings = self.parent.children
        idx = siblings.index(self)
        if idx + 1 < len(siblings):
            return siblings[idx + 1]
        return None

    @property
    def prev_sibling(self) -> Optional["Node"]:
        if not self.parent:
            return None
        siblings = self.parent.children
        idx = siblings.index(self)
        if idx - 1 >= 0:
            return siblings[idx - 1]
        return None

@dataclass
class Span(Node):
    text: str = ""
    font: str = ""
    size: float = 0.0
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    node_type: str = "span"

@dataclass
class Line(Node):
    spans: List[Span] = field(default_factory=list)
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    node_type: str = "line"
    orig: None

@dataclass
class Paragraph(Node):
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    style: str = "normal"
    node_type: str = "paragraph"

@dataclass
class PageNumber(Node):
    text: str = ""
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    node_type: str = "page_number"

@dataclass
class Heading(Node):
    level: int = 1
    text: str = ""
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    node_type: str = "heading"

@dataclass
class Table(Node):
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    raw_data: dict = field(default_factory=dict)
    node_type: str = "table"

@dataclass
class ImageObject(Node):
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    image_bytes: bytes = b""
    node_type: str = "image"

@dataclass
class Link(Node):
    uri: str = ""
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    node_type: str = "link"

@dataclass
class Page(Node):
    number: int = 0
    bbox: Tuple[float, float, float, float] = (0,0,0,0)
    node_type: str = "page"

@dataclass
class Document(Node):
    pages: List[Page] = field(default_factory=list)
    node_type: str = "document"
