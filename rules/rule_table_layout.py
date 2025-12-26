import re
from typing import List, Optional
from dom import Document, Table, Paragraph
from errors import RuleError, ErrorType

CM_TO_PT = 28.35


class RuleTableLayout:
    """
    Проверки таблиц по ГОСТ 7.32:
    - центрирование
    - наличие и формат названия
    - положение названия
    """

    def __init__(
        self,
        left_mm=30,
        right_mm=20,
        tol_pt=7,
    ):
        self.left_mm = left_mm
        self.right_mm = right_mm
        self.tol_pt = tol_pt

    def check(self, document: Document) -> List[RuleError]:
        errors: List[RuleError] = []

        for page in document.pages:
            for node in page.children:
                if not isinstance(node, Table):
                    continue

                errors.extend(self._check_table_center(page, node))
                errors.extend(self._check_table_caption(page, node))

        return errors


    def _check_table_center(self, page, table: Table) -> List[RuleError]:
        errors = []

        page_left, _, page_right, _ = page.bbox

        work_left = page_left + self.left_mm * CM_TO_PT / 10
        work_right = page_right - self.right_mm * CM_TO_PT / 10
        work_center = (work_left + work_right) / 2

        x0, _, x1, _ = table.bbox
        table_center = (x0 + x1) / 2

        if abs(table_center - work_center) > self.tol_pt:
            errors.append(RuleError(
                message="Таблица не центрирована относительно рабочей области страницы",
                node=table,
                node_id=table.node_id,
                error_type=ErrorType.TABLE_ALIGNMENT
            ))

        return errors


    def _find_caption_above(
        self,
        page,
        table: Table
    ) -> Optional[Paragraph]:

        table_top = table.bbox[1]

        candidates = []
        for node in page.children:
            if not isinstance(node, Paragraph):
                continue

            if node.bbox[3] <= table_top:
                distance = table_top - node.bbox[3]
                if distance < 40:
                    candidates.append((distance, node))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]


    def _check_table_caption(self, page, table: Table) -> List[RuleError]:
        errors = []

        caption = self._find_caption_above(page, table)

        if not caption:
            errors.append(RuleError(
                message="Отсутствует название таблицы",
                node=table,
                node_id=table.node_id,
                error_type=ErrorType.TABLE_CAPTION
            ))
            return errors

        text = caption.text.strip()

        if not re.match(r"^Таблица\s+\d+(\s*[—-].+)?$", text):
            errors.append(RuleError(
                message="Неверный формат названия таблицы (ожидается «Таблица N — …»)",
                node=caption,
                node_id=caption.node_id,
                error_type=ErrorType.TABLE_CAPTION
            ))

        cap_center = (caption.bbox[0] + caption.bbox[2]) / 2
        table_center = (table.bbox[0] + table.bbox[2]) / 2

        if abs(cap_center - table_center) > self.tol_pt:
            errors.append(RuleError(
                message="Название таблицы не выровнено по центру",
                node=caption,
                node_id=caption.node_id,
                error_type=ErrorType.TABLE_CAPTION
            ))

        return errors
