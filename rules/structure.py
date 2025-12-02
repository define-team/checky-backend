from dom import Node, Document, Heading, Paragraph
from errors import RuleError, ErrorType
from typing import List

class RuleHeadingFollowedByParagraph:
    """Проверяет структуру заголовков и абзацев"""
    def check(self, document: Document) -> List[RuleError]:
        errors: List[RuleError] = []

        def check_children(children: List[Node]):
            for i, node in enumerate(children):
                if isinstance(node, Heading):
                    next_node = node.next_sibling
                    while next_node and not isinstance(next_node, (Paragraph, Heading)):
                        next_node = next_node.next_sibling

                    if not next_node:
                        error = RuleError(
                            message=f"После заголовка '{node.text.strip()}' нет абзаца/подзаголовка",
                            node=node,
                            node_id=node.node_id,
                            error_type=ErrorType.HEADING_STRUCTURE
                        )
                        node.errors.append(error)
                        errors.append(error)
                    elif isinstance(next_node, Heading) and next_node.level > node.level + 1:
                        error = RuleError(
                            message=f"После заголовка '{node.text.strip()}' сразу заголовок слишком низкого уровня",
                            node=node,
                            node_id=node.node_id,
                            error_type=ErrorType.HEADING_STRUCTURE
                        )
                        node.errors.append(error)
                        errors.append(error)

                check_children(getattr(node, "children", []))

        check_children(document.children)
        return errors
