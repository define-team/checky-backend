from typing import List
from dom import Document, Paragraph, Line
from errors import RuleError, ErrorType
import statistics


class RuleLineSpacing:
    """
    Проверка межстрочного интервала.
    ГОСТ 7.32: основной текст — 1.5
    """

    def __init__(self, expected=1.5, tol=0.15):
        self.expected = expected
        self.min_ratio = expected - tol
        self.max_ratio = expected + tol

    def check(self, document: Document) -> List[RuleError]:
        errors: List[RuleError] = []

        for page in document.pages:
            for node in page.children:
                if isinstance(node, Paragraph):
                    errors.extend(self.check_paragraph(node))

        return errors

    def check_paragraph(self, paragraph: Paragraph) -> List[RuleError]:
        errors: List[RuleError] = []
        lines = paragraph.children

        if len(lines) < 2:
            return errors

        bad_lines = []

        for prev, cur in zip(lines, lines[1:]):
            h = prev.bbox[3] - prev.bbox[1]
            if h <= 0:
                continue

            gap = cur.bbox[1] - prev.bbox[3]
            ratio = (h + gap) / h

            if not (self.min_ratio <= ratio <= self.max_ratio):
                bad_lines.append(ratio)

        if bad_lines and len(bad_lines) / (len(lines) - 1) > 0.3:
            errors.append(RuleError(
                message=(
                    f"Неверный межстрочный интервал: "
                    f"ожидалось {self.expected}, найдено "
                    f"{statistics.median(bad_lines):.2f}"
                ),
                node=paragraph,
                node_id=paragraph.node_id,
                error_type=ErrorType.SPACING
            ))

        return errors
