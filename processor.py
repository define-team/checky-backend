from parser_dom import PDFDOMParser
from renderer import render_errors
from errors import RuleError
from dom import Document

from rules.font import RuleFontSize
from rules.structure import RuleHeadingFollowedByParagraph
from rules.page_layout import RulePageMargins
from rules.image import RuleImageCenterByMargins
from rules.rule_line_spacing import RuleLineSpacing
from rules.paragraph_indent import RuleParagraphIndent

def process_pdf(input_bytes: bytes, draw_lines=False) -> bytes:
    errors: list[RuleError] = validate_pdf(input_bytes)

    return render_errors(input_bytes, errors, draw_lines=draw_lines)

def validate_pdf(input_bytes: bytes) -> list[RuleError]:
    parser = PDFDOMParser()
    document: Document = parser.parse_bytes(input_bytes)

    rules = [
        RuleFontSize(),
        RuleHeadingFollowedByParagraph(),
        RulePageMargins(),
        RuleImageCenterByMargins(),
        RuleLineSpacing(),
        RuleParagraphIndent()
    ]

    errors: list[RuleError] = []
    for r in rules:
        errors.extend(r.check(document))

    return errors
