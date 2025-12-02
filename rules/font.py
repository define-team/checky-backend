from dom import Span, Document, Page
from errors import RuleError, ErrorType
from typing import List
import fitz


class RuleFontSize:
    def __init__(self, font_name="TimesNewRoman", font_size_from=12, font_size_to=14, size_tol=0.1):
        self.font_name = font_name
        self.font_size_from = font_size_from
        self.font_size_to = font_size_to
        self.size_tol = size_tol

    def check(self, document: Document) -> List[RuleError]:
        errors: List[RuleError] = []

        def get_real_font(span: Span) -> str:
            page_node = span
            while page_node and not isinstance(page_node, Page):
                page_node = page_node.parent

            if not page_node or not hasattr(page_node, "orig"):
                return getattr(span.orig, "get", lambda x, d=None: d)("font", span.font)

            pdf_page: fitz.Page = page_node.orig

            fonts = pdf_page.get_fonts(full=True)
            font_map = {str(x[0]): x[3] for x in fonts}  # xref -> font_name
            span_font_key = getattr(span.orig, "get", lambda x, d=None: d)("font", span.font)

            return font_map.get(span_font_key, span_font_key)

        def check_node(node):
            if isinstance(node, Span):
                local_errors = []

                real_font = get_real_font(node)

                if self.font_name not in real_font:
                    local_errors.append(RuleError(
                        message=f"Неверный шрифт: {real_font} → должен содержать '{self.font_name}'",
                        node=node,
                        node_id=node.node_id,
                        error_type=ErrorType.FONT
                    ))

                if not (self.font_size_from - self.size_tol <= node.size <= self.font_size_to + self.size_tol):
                    local_errors.append(RuleError(
                        message=f"Неверный размер: {node.size} → допустимо {self.font_size_from}-{self.font_size_to}",
                        node=node,
                        node_id=node.node_id,
                        error_type=ErrorType.FONT_SIZE
                    ))

                if local_errors:
                    target = node.parent
                    while target and target.node_type not in ("paragraph", "heading"):
                        target = target.parent
                    if target:
                        for err in local_errors:
                            err.node_id = target.node_id
                        target.errors.extend(local_errors)
                        errors.extend(local_errors)

            for child in getattr(node, "children", []):
                check_node(child)

        check_node(document)
        return errors
