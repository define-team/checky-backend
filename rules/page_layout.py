import statistics
from dom import Document, PageNumber, Paragraph, Line
from errors import RuleError, ErrorType
from typing import List
from dataclasses import dataclass

@dataclass
class AlignmentResult:
    is_justify: bool
    detected: str


JUSTIFY_TO_WORDS={
    "justify": "выравнивание по ширине",
    "center": "выравнивание по центру",
    "left": "выравнивание по левому краю",
    "right": "выравнивание по правому краю",
}
CM_TO_PT = 28.35
PT_TO_MM = 10 / CM_TO_PT

class RulePageMargins:
    """
    Проверка полей страницы по контенту (расстояние от текста/таблиц/картинок до краёв страницы)
    и наличие/позицию номера страницы
    """
    def __init__(self,
                 top_mm=20, bottom_mm=20, left_mm=30, right_mm=20,
                 tol_mm=1, right_toll_mm=2.5,
                 page_number_bottom_mm=20,
                 page_number_margin_mm=5):
        self.right_toll = right_toll_mm
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

                if right_mm + self.right_toll < self.right:
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
                    errors.extend(self.check_paragraph_alignment(node, page))


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
                        "Номер страницы не центрирован: "
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



    def check_paragraph_alignment(self, paragraph: Paragraph, page) -> List[RuleError]:
        errors = []

        lines = [l for l in paragraph.children if isinstance(l, Line) and l.bbox]
        # print(len(lines))
        # print("--------")
        # if not lines:
        #     return errors

        page_left, _, page_right, _ = page.bbox
        work_left  = page_left + self.left / 10 * CM_TO_PT
        work_right = page_right - self.right / 10 * CM_TO_PT

        if len(lines) == 1:
            if is_visually_multiline(paragraph, lines[0], work_left, work_right):
                errors.append(RuleError(
                    message="Абзац не выровнен по ширине",
                    node=paragraph,
                    node_id=paragraph.node_id,
                    error_type=ErrorType.PARAGRAPH_JUSTIFIED
                ))
            return errors
        if len(lines) == 2:
            lines_to_check = [lines[0]]
        else:
            lines_to_check = lines[1:-1]

        is_not_justify = detect_alignment(lines_to_check, work_left, work_right)

        if is_not_justify:
            errors.append(RuleError(
                message="Абзац не выровнен по ширине",
                node=paragraph,
                node_id=paragraph.node_id,
                error_type=ErrorType.PARAGRAPH_JUSTIFIED
            ))

        return errors







def detect_alignment(
    lines,
    work_left,
    work_right,
    tol_left=4,
    tol_right=6
) -> bool:
    """
    True   НЕ justify (ошибка)
    False  justify (ГОСТ выполнен)
    """

    lefts, rights = [], []

    for line in lines:
        l, _, r, _ = line.bbox
        lefts.append(l)
        rights.append(r)

    if not lefts:
        return False

    left_var = max(lefts) - min(lefts)
    right_gap = max(abs(work_right - r) for r in rights)
    # print (f"LEFT VAR: {left_var}, RIGHT GAP: {right_gap}")

    justify = (
        left_var <= tol_left and
        right_gap <= tol_right
    )

    if justify:
        # print("JUSTIFY DETECTED")
        return False
    else:
        # print("JUSTIFY NOT")
        return True


def is_collapsed_multiline_paragraph(paragraph, line, k=2.0):
    """
    True  PDF склеил много строк в одну
    """
    if not paragraph.bbox or not line.bbox:
        return False

    para_h = paragraph.bbox[3] - paragraph.bbox[1]
    line_h = line.bbox[3] - line.bbox[1]

    return para_h > k * line_h

def is_visually_multiline(paragraph, line, work_left, work_right,
                          h_ratio=2.0, w_ratio=0.7):
    para_h = paragraph.bbox[3] - paragraph.bbox[1]
    line_h = line.bbox[3] - line.bbox[1]

    para_w = line.bbox[2] - line.bbox[0]
    work_w = work_right - work_left

    tall = para_h > h_ratio * line_h
    wide = para_w > w_ratio * work_w

    return tall and wide
