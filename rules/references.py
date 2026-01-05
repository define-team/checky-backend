import re
from dom import Document, Heading, Paragraph
from errors import RuleError, ErrorType
from typing import List

REFERENCE_TITLES = {
    "список литературы",
    "список использованных источников",
    "библиографический список",
}

REFERENCE_ITEM_RE = re.compile(r"^\s*(\[\d+]|\\d+[.)])\s+")

def normalize_title(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


class RuleReferencesSection:
    def check(self, document: Document) -> List[RuleError]:
        errors = []

        headings = [
            node for node in document.walk()
            if isinstance(node, (Heading, Paragraph))
        ]

        ref_heading = None
        for h in headings:
            if normalize_title(node.text) in REFERENCE_TITLES:
                ref_heading = h
                break

        if not ref_heading:
            errors.append(RuleError(
                message="Отсутствует раздел «Список литературы»",
                node=document,
                node_id=document.node_id,
                error_type=ErrorType.REFERENCES
            ))
            return errors

        following = []
        node = ref_heading.next_sibling
        while node and not isinstance(node, Heading):
            following.append(node)
            node = node.next_sibling

        paragraphs = [n for n in following if isinstance(n, Paragraph)]

        if not paragraphs:
            errors.append(RuleError(
                message="Раздел «Список литературы» пуст",
                node=ref_heading,
                node_id=ref_heading.node_id,
                error_type=ErrorType.REFERENCES
            ))
            return errors

        bad_items = []
        for p in paragraphs:
            text = "".join(
                span.text for line in p.children for span in line.spans
            ).strip()

            if not REFERENCE_ITEM_RE.match(text):
                bad_items.append(p)

        if bad_items:
            errors.append(RuleError(
                message="Некоторые источники в списке литературы не имеют нумерации",
                node=bad_items[0],
                node_id=bad_items[0].node_id,
                error_type=ErrorType.REFERENCES
            ))

        return errors
