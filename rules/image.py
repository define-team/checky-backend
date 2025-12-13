from dom import ImageObject,Document
from errors import RuleError, ErrorType
from typing import List
CM_TO_PT = 28.35
class RuleImageCenterByMargins:
    def __init__(self, left_mm=30, right_mm=20, tol_pt=15):
        self.left_mm = left_mm
        self.right_mm = right_mm
        self.tol_pt = tol_pt

    def check(self, document: Document) -> List[RuleError]:
        errors = []

        for page in document.pages:
            page_left, _, page_right, _ = page.bbox

            print_left = page_left + self.left_mm * CM_TO_PT / 10
            print_right = page_right - self.right_mm * CM_TO_PT / 10
            print_center = (print_left + print_right) / 2

            for node in page.children:
                if not isinstance(node, ImageObject):
                    continue
                if not node.bbox or node.bbox == (0, 0, 0, 0):
                    continue

                img_center = (node.bbox[0] + node.bbox[2]) / 2

                if abs(img_center - print_center) > self.tol_pt:
                    errors.append(RuleError(
                        message="Изображение не центрировано относительно полей страницы",
                        node=node,
                        node_id=node.node_id,
                        error_type=ErrorType.IMAGE
                    ))

        return errors
