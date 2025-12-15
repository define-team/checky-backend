from dom import ImageObject, Document
from errors import RuleError, ErrorType
from typing import List

CM_TO_PT = 28.35

class RuleImageCenterByMargins:
    def __init__(self, left_mm=30, right_mm=20, tol_pt=7):
        self.left_mm = left_mm
        self.right_mm = right_mm
        self.tol_pt = tol_pt

    def check(self, document: Document) -> List[RuleError]:
        errors = []

        for page in document.pages:
            page_left, _, page_right, _ = page.bbox

            work_left = page_left + self.left_mm * CM_TO_PT / 10
            work_right = page_right - self.right_mm * CM_TO_PT / 10
            work_center = (work_left + work_right) / 2

            for node in page.children:
                if not isinstance(node, ImageObject):
                    continue
                if not node.bbox:
                    continue

                x0, _, x1, _ = node.bbox
                img_center = (x0 + x1) / 2

                if abs(img_center - work_center) > self.tol_pt:
                    errors.append(RuleError(
                        message="Изображение не центрировано относительно рабочей области страницы",
                        node=node,
                        node_id=node.node_id,
                        error_type=ErrorType.IMAGE
                    ))

        return errors
