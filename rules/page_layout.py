import statistics
from dom import Document, PageNumber, Paragraph, Line
from errors import RuleError, ErrorType
from typing import List

CM_TO_PT = 28.35
PT_TO_MM = 10 / CM_TO_PT

class RulePageMargins:
    """
    Проверка полей страницы по контенту (расстояние от текста/таблиц/картинок до краёв страницы)
    и наличие/позицию номера страницы
    """
    def __init__(self,
                 top_mm=20, bottom_mm=20, left_mm=30, right_mm=20,
                 tol_mm=1,
                 page_number_bottom_mm=20,
                 page_number_margin_mm=5):
        self.top = top_mm
        self.bottom = bottom_mm
        self.left = left_mm
        self.right = right_mm
        self.tol = tol_mm
        self.page_number_bottom = page_number_bottom_mm
        self.page_number_margin = page_number_margin_mm

    def check(self, document: Document) -> List[RuleError]:
        errors: List[RuleError] = []

        for page in document.pages:
            content_boxes = []
            for node in page.children:
                if isinstance(node, PageNumber):
                    continue
                if hasattr(node, "bbox") and node.bbox:
                    content_boxes.append(node.bbox)

            if content_boxes:
                x0s, y0s, x1s, y1s = zip(*content_boxes)
                content_x0 = min(x0s)
                content_y0 = min(y0s)
                content_x1 = max(x1s)
                content_y1 = max(y1s)

                top_margin = content_y0
                bottom_margin = page.bbox[3] - content_y1
                left_margin = content_x0
                right_margin = page.bbox[2] - content_x1

                top_mm = top_margin * PT_TO_MM
                bottom_mm = bottom_margin * PT_TO_MM
                left_mm = left_margin * PT_TO_MM
                right_mm = right_margin * PT_TO_MM

                if top_mm + self.tol < self.top:
                    errors.append(RuleError(
                        message=f"Верхнее поле меньше ГОСТ: {top_mm:.1f} мм < {self.top} мм",
                        node=page,
                        node_id=page.node_id,
                        error_type=ErrorType.PAGE_MARGIN
                    ))

                if bottom_mm + self.tol < self.bottom:
                    errors.append(RuleError(
                        message=f"Нижнее поле меньше ГОСТ: {bottom_mm:.1f} мм < {self.bottom} мм",
                        node=page,
                        node_id=page.node_id,
                        error_type=ErrorType.PAGE_MARGIN
                    ))

                if left_mm + self.tol < self.left:
                    errors.append(RuleError(
                        message=f"Левое поле меньше ГОСТ: {left_mm:.1f} мм < {self.left} мм",
                        node=page,
                        node_id=page.node_id,
                        error_type=ErrorType.PAGE_MARGIN
                    ))

                if right_mm + self.tol < self.right:
                    errors.append(RuleError(
                        message=f"Правое поле меньше ГОСТ: {right_mm:.1f} мм < {self.right} мм",
                        node=page,
                        node_id=page.node_id,
                        error_type=ErrorType.PAGE_MARGIN
                    ))

            for node in page.children:
                if isinstance(node, PageNumber):
                    errors.extend(self.check_page_number(page, node))
                    continue

                if isinstance(node, Paragraph):
                    errors.extend(self.check_paragraph_alignment(node))


        return errors

    def check_page_number(self, page, page_number_node: PageNumber = None):
        errors: List[RuleError] = []

        if page.number > 0:
            if not page_number_node:
                errors.append(RuleError(
                    message="На странице отсутствует номер страницы",
                    node=page,
                    node_id=page.node_id,
                    error_type=ErrorType.PAGE_NUMBER
                ))
                return errors

            if page_number_node.text != str(page.number + 1):
                errors.append(RuleError(
                    message=(
                        f"Номер страницы не соответствует реальному: "
                        f"{page_number_node.text} != {page.number + 1}"
                    ),
                    node=page_number_node,
                    node_id=page_number_node.node_id,
                    error_type=ErrorType.PAGE_NUMBER
                ))

            page_left = page.bbox[0]
            page_right = page.bbox[2]
            page_print_center_x = (page_right + page_left) / 2 + (self.left - self.right) / 2 / 10 * CM_TO_PT

            number_center_x = (page_number_node.bbox[0] + page_number_node.bbox[2]) / 2
            tol = CM_TO_PT * 0.2

            if abs(number_center_x - page_print_center_x) > tol:
                errors.append(RuleError(
                    message=(
                        "Номер страницы не центрирован по горизонтали с учётом полей: "
                        f"{number_center_x / CM_TO_PT:.1f} != {page_print_center_x / CM_TO_PT:.1f}"
                    ),
                    node=page_number_node,
                    node_id=page_number_node.node_id,
                    error_type=ErrorType.PAGE_NUMBER
                ))

            number_top_from_bottom_mm = (page.bbox[3] - page_number_node.bbox[3]) * PT_TO_MM
            number_bottom_from_bottom_mm = (page.bbox[3] - page_number_node.bbox[1]) * PT_TO_MM

            if number_top_from_bottom_mm > self.page_number_bottom:
                errors.append(RuleError(
                    message=(
                        f"Верхняя граница номера страницы слишком высокая: "
                        f"{number_top_from_bottom_mm:.1f} мм > {self.page_number_bottom} мм"
                    ),
                    node=page_number_node,
                    node_id=page_number_node.node_id,
                    error_type=ErrorType.PAGE_NUMBER
                ))

            if number_bottom_from_bottom_mm < self.page_number_margin:
                errors.append(RuleError(
                    message=(
                        f"Нижняя граница номера страницы слишком близко к краю: "
                        f"{number_bottom_from_bottom_mm:.1f} мм < {self.page_number_margin} мм"
                    ),
                    node=page_number_node,
                    node_id=page_number_node.node_id,
                    error_type=ErrorType.PAGE_NUMBER
                ))

        return errors

    def check_paragraph_alignment(self, paragraph: Paragraph) -> List[RuleError]:
        errors = []
        lines = paragraph.children

        if len(lines) < 2:
            return errors

        tol = 5
        lefts = [l.bbox[0] for l in lines]
        rights = [l.bbox[2] for l in lines]
        centers = [(l + r) / 2 for l, r in zip(lefts, rights)]

        full_lines = lines[:-1]

        left_var = max(l.bbox[0] for l in full_lines) - min(l.bbox[0] for l in full_lines)
        right_var = max(l.bbox[2] for l in full_lines) - min(l.bbox[2] for l in full_lines)

        is_justify = left_var <= tol and right_var <= tol

        if not is_justify:
            errors.append(RuleError(
                message="Абзац не выровнен по ширине (ГОСТ)",
                node=paragraph,
                node_id=paragraph.node_id,
                error_type=ErrorType.PARAGRAPH_JUSTIFIED
            ))

        return errors
