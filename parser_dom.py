import fitz
from dom import *

CM_TO_PT = 28.35
RED_INDENT_CM = 0.1
PAGE_LEFT_CM = 3

fitz.TOOLS.set_subset_fontnames(False)

class PDFDOMParser:

    def parse_bytes(self, input_bytes: bytes, debug_page: int = None) -> Document:
        doc_pdf = fitz.open(stream=input_bytes, filetype="pdf")
        root = Document()

        for page_index, page in enumerate(doc_pdf):
            page_node = Page(number=page_index, bbox=(0, 0, page.rect.width, page.rect.height), orig=page)
            root.add_child(page_node)
            root.pages.append(page_node)

            self._parse_page_content(page, page_node)

            if debug_page is not None and page_index == debug_page:
                self.debug_page(page_node)

        return root


    def _parse_page_content(self, page, page_node: Page):
        links = page.get_links()
        link_rects = [(fitz.Rect(l["from"]), l["uri"]) for l in links]

        dict_data = page.get_text("dict")["blocks"]
        sorted_blocks = self.sort_blocks_by_y(dict_data)

        for block in sorted_blocks:
            btype = block.get("type", 0)
            if btype == 0:
                para = self._parse_text_block(block, link_rects)
                if para:
                    page_node.add_child(para)
            elif btype == 1:
                table_node = Table(bbox=tuple(block["bbox"]), raw_data=block, orig=block)
                page_node.add_child(table_node)
            elif btype == 2:
                img_node = self._parse_image_block(block, page)
                if img_node:
                    page_node.add_child(img_node)

        self._detect_page_number(page_node)

        self._merge_paragraphs(page_node)


    def sort_blocks_by_y(self, blocks):
        blocks_with_bbox = [b for b in blocks if b.get("bbox")]
        blocks_without_bbox = [b for b in blocks if not b.get("bbox")]

        blocks_with_bbox.sort(key=lambda b: b["bbox"][1])

        result = []
        wi, bi = 0, 0
        for b in blocks:
            if b.get("bbox"):
                result.append(blocks_with_bbox[wi])
                wi += 1
            else:
                result.append(blocks_without_bbox[bi])
                bi += 1
        return result


    def _merge_paragraphs(self, page_node: Page):
        merged_children = []
        prev_para = None
        page_left = CM_TO_PT * PAGE_LEFT_CM

        for node in list(page_node.children):
            if not isinstance(node, Paragraph):
                merged_children.append(node)
                continue

            if not any(span.text.strip() for line in node.children for span in line.spans):
                continue

            if prev_para:
                prev_y1 = prev_para.children[-1].bbox[3]
                cur_y0 = node.children[0].bbox[1]
                y_gap = cur_y0 - prev_y1

                avg_size_prev = sum(span.size for line in prev_para.children for span in line.spans) / max(1, sum(len(line.spans) for line in prev_para.children))
                max_line_gap = avg_size_prev * 1.5

                first_line_x0 = node.children[0].bbox[0]
                red_indent = first_line_x0 - page_left > CM_TO_PT * RED_INDENT_CM

                avg_size_cur = sum(span.size for line in node.children for span in line.spans) / max(1, sum(len(line.spans) for line in node.children))
                font_diff = abs(avg_size_prev - avg_size_cur) > 0.1

                if not red_indent and not font_diff and y_gap <= max_line_gap:
                    for child in node.children:
                        prev_para.add_child(child)
                    px0, py0, px1, py1 = prev_para.bbox
                    cx0, cy0, cx1, cy1 = node.bbox
                    prev_para.bbox = (min(px0, cx0), min(py0, cy0), max(px1, cx1), max(py1, cy1))
                    continue

            merged_children.append(node)
            prev_para = node

        page_node.children = merged_children


    def _parse_text_block(self, block, link_rects) -> Optional[Paragraph]:
        para = Paragraph(orig=block)

        all_spans = []
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if text:
                    all_spans.append(span)

        if not all_spans:
            return None

        all_spans.sort(key=lambda s: (s["bbox"][3], s["bbox"][0]))

        y_threshold = 2.0
        i = 0
        n = len(all_spans)

        while i < n:
            first_span = all_spans[i]
            y_center = (first_span["bbox"][1] + first_span["bbox"][3]) / 2
            line_node = Line(bbox=None, orig=None)
            para.add_child(line_node)

            while i < n:
                span = all_spans[i]
                span_y_center = (span["bbox"][1] + span["bbox"][3]) / 2
                if abs(span_y_center - y_center) > y_threshold:
                    break

                span_rect = fitz.Rect(span["bbox"])
                link_node = None
                for lrect, uri in link_rects:
                    if span_rect.intersects(lrect):
                        link_node = Link(uri=uri, bbox=tuple(lrect))
                        line_node.add_child(link_node)
                        break

                span_node = Span(
                    text=span.get("text", ""),
                    font=span.get("font", ""),
                    size=span.get("size", 0.0),
                    bbox=tuple(span["bbox"]),
                    orig=span
                )

                if link_node:
                    link_node.add_child(span_node)
                else:
                    line_node.spans.append(span_node)
                    line_node.add_child(span_node)

                i += 1

            if line_node.spans:
                x0 = min(s.bbox[0] for s in line_node.children)
                y0 = min(s.bbox[1] for s in line_node.children)
                x1 = max(s.bbox[2] for s in line_node.children)
                y1 = max(s.bbox[3] for s in line_node.children)
                line_node.bbox = (x0, y0, x1, y1)

        x0 = min(line.bbox[0] for line in para.children)
        y0 = min(line.bbox[1] for line in para.children)
        x1 = max(line.bbox[2] for line in para.children)
        y1 = max(line.bbox[3] for line in para.children)
        para.bbox = (x0, y0, x1, y1)

        return para

    def _parse_image_block(self, block, page) -> Optional[ImageObject]:
        images = page.get_images(full=True)
        if not images:
            return None
        xref = images[0][0]
        pix = page.parent.extract_image(xref)
        return ImageObject(
            bbox=tuple(block["bbox"]),
            image_bytes=pix["image"],
            orig=block
        )


    def _detect_page_number(self, page_node: Page):
        for node in reversed(page_node.children):
            if isinstance(node, Paragraph) and node.children:
                text = "".join(span.text for line in node.children for span in line.spans).strip()
                if text.isdigit():
                    page_number_node = PageNumber(
                        text=text,
                        bbox=node.bbox,
                        orig=node.orig
                    )
                    page_node.replace_child(node, page_number_node)
                    break


    def debug_page(self, page_node: Page):
        print(f"\n=== Debug Page {page_node.number} ===")
        for idx, node in enumerate(page_node.children):
            if isinstance(node, Paragraph):
                print(f"Paragraph {idx} bbox={node.bbox}")
                for l_idx, line in enumerate(node.children):
                    print(f"  Line {l_idx} bbox={line.bbox}")
                    for s_idx, span in enumerate(line.spans):
                        link_info = ""
                        if span.parent.node_type == "link":
                            link_info = f" (link: {span.parent.uri})"
                        print(f"    Span {s_idx}: '{span.text}' font={span.font} size={span.size}{link_info}")
            elif isinstance(node, ImageObject):
                print(f"Image {idx} bbox={node.bbox}")
            elif isinstance(node, Table):
                print(f"Table {idx} bbox={node.bbox}")
            elif isinstance(node, PageNumber):
                print(f"PageNumber {idx} bbox={node.bbox} text={node.text}")
        print("=== End Debug ===\n")
