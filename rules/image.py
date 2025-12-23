from dom import ImageObject, Document, Paragraph
from errors import RuleError, ErrorType
from typing import List
import re

CM_TO_PT = 28.35


class RuleImageCenterByMargins:
    def __init__(self, left_mm=30, right_mm=20, tol_pt=7, caption_gap_pt=20):
        self.left_mm = left_mm
        self.right_mm = right_mm
        self.tol_pt = tol_pt
        self.caption_gap_pt = caption_gap_pt

    def check(self, document: Document) -> List[RuleError]:
        errors = []

        for page in document.pages:
            page_left, _, page_right, _ = page.bbox

            work_left = page_left + self.left_mm * CM_TO_PT / 10
            work_right = page_right - self.right_mm * CM_TO_PT / 10
            work_center = (work_left + work_right) / 2

            children = page.children

            for i, node in enumerate(children):
                if not isinstance(node, ImageObject) or not node.bbox:
                    continue

                x0, y0, x1, y1 = node.bbox
                img_center = (x0 + x1) / 2

                if abs(img_center - work_center) > self.tol_pt:
                    errors.append(RuleError(
                        message="Изображение не центрировано относительно рабочей области страницы",
                        node=node,
                        node_id=node.node_id,
                        error_type=ErrorType.IMAGE
                    ))

                caption = self._find_caption(children, i, y1)

                if caption is None:
                    errors.append(RuleError(
                        message="У изображения отсутствует подпись (Рис. ...)",
                        node=node,
                        node_id=node.node_id,
                        error_type=ErrorType.IMAGE
                    ))
                    continue

                cx0, _, cx1, _ = caption.bbox
                caption_center = (cx0 + cx1) / 2

                if abs(caption_center - work_center) > self.tol_pt:
                    errors.append(RuleError(
                        message="Подпись к рисунку не центрирована",
                        node=caption,
                        node_id=caption.node_id,
                        error_type=ErrorType.IMAGE
                    ))

        return errors


    def _find_caption(self, children, img_index, img_bottom_y) -> Paragraph | None:
        if img_index + 1 >= len(children):
            return None

        candidate = children[img_index + 1]

        if not isinstance(candidate, Paragraph) or not candidate.bbox:
            return None

        gap = candidate.bbox[1] - img_bottom_y
        if gap < 0 or gap > self.caption_gap_pt:
            return None

        text = self._paragraph_text(candidate)
        if not self._is_caption_text(text):
            return None

        return candidate

    def _paragraph_text(self, paragraph: Paragraph) -> str:
        return "".join(
            span.text
            for line in paragraph.children
            for span in getattr(line, "spans", [])
        )

    def _is_caption_text(self, text: str) -> bool:
        return bool(re.match(r"(рис\.?|рисунок).*", text.strip().lower()))
