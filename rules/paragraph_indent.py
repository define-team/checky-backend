from dom import Paragraph
from errors import RuleError, ErrorType
from typing import List

CM_TO_PT = 28.35

class RuleParagraphIndent:
    """
    Проверка абзацного отступа первой строки (1.25 см по ГОСТ)
    """

    def __init__(self, indent_cm=1.25, tol_pt=4):
        self.indent_pt = indent_cm * CM_TO_PT
        self.tol = tol_pt

    def check(self, document) -> List[RuleError]:
        errors = []

        for page in document.pages:
            for node in page.children:
                if isinstance(node, Paragraph):
                    errors.extend(self.check_paragraph(node))

        return errors

    def check_paragraph(self, paragraph: Paragraph) -> List[RuleError]:
        errors = []
        lines = paragraph.children

        if len(lines) < 2:
            return errors

        first_line = lines[0]
        other_lines = lines[1:]

        base_left = sorted(l.bbox[0] for l in other_lines)[len(other_lines)//2]

        first_left = first_line.bbox[0]
        indent = first_left - base_left

        if abs(indent - self.indent_pt) > self.tol:
            errors.append(RuleError(
                message=(
                    f"Неверный абзацный отступ первой строки: "
                    f"{indent / CM_TO_PT:.2f} см (норма {self.indent_pt / CM_TO_PT:.2f} см)"
                ),
                node=paragraph,
                node_id=paragraph.node_id,
                error_type=ErrorType.PARAGRAPH_INDENT,
                expected=self.indent_pt / CM_TO_PT,
                found=indent / CM_TO_PT
            ))

        return errors
