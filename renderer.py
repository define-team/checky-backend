import fitz
from errors import RuleError

CM_TO_PT = 28.35

def render_errors(input_bytes: bytes, errors: list[RuleError], draw_lines=False) -> bytes:
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    grouped = {}
    for err in errors:
        grouped.setdefault(err.node_id, []).append(err)

    for errs in grouped.values():
        node = errs[0].node
        page_node = node
        while page_node and not hasattr(page_node, "number"):
            page_node = page_node.parent
        if page_node is None:
            continue
        page = doc[page_node.number]

        if hasattr(node, "bbox") and node.bbox != (0,0,0,0):
            rect = fitz.Rect(*node.bbox)
            comment_text = "\n".join([e.message for e in errs])
            page.add_text_annot((CM_TO_PT, max(rect.y0, CM_TO_PT)), comment_text)

            if draw_lines:
                page.draw_rect(rect, color=(1,0,0), width=1)

    return doc.write()
