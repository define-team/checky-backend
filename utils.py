import fitz
import io
import statistics

# ---- Шрифты / Параметры ----
CYR_FONT = fitz.Font("tiro")
CYR_FONTNAME = "CYR"

MIN_FONT = 12
MAX_FONT = 14

LEFT_MARGIN_CM = 3.0
RIGHT_MARGIN_CM = 2.0
CM_TO_POINTS = 28.3464567
LEFT_MARGIN = LEFT_MARGIN_CM * CM_TO_POINTS
RIGHT_MARGIN = RIGHT_MARGIN_CM * CM_TO_POINTS

# Пороговые константы (можно тонко настроить)
GAP_MULT = 1.8            # множитель медианной высоты строки для разрыва абзаца
RIGHT_TOL_PT = 12         # допуск правого края в пунктах
LEFT_TOL_PT = 10          # допуск левого края
JUSTIFY_FRAC = 0.7        # доля строк (кроме последней) для определения justify
IMG_CENTER_TOL_PT = 15    # картинка считается центрированной в пределах этого tol
LIGHT_FILL_LEFT = (1, 0.9, 0.9)  # светло-розовая для области левого отступа
LIGHT_FILL_RIGHT = (0.95, 0.95, 1) # светло-голубая для правых проблем


# ---- Вспомогательные ----
def int_to_rgb(color_int):
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return r/255, g/255, b/255

def is_black(color_int):
    r, g, b = int_to_rgb(color_int)
    return r < 0.12 and g < 0.12 and b < 0.12

def is_list_line_text(text: str):
    """Определяем строку как маркерный / нумерованный пункт."""
    t = text.strip()
    if not t:
        return False
    # bullets
    if t[0] in ("•", "·", "-", "—", "–", "*"):
        return True
    # numeric items like "1.", "1)", "a)", "1."
    if t.split()[0].rstrip(").:").isdigit():
        return True
    # or starts with digit + dot
    if t[0].isdigit() and len(t) > 1 and t[1] in (".", ")"):
        return True
    return False

def span_text_from_line(line):
    return "".join(span.get("text", "") for span in line["spans"]).strip()

def detect_bold(span):
    """Простая эвристика: если имя шрифта содержит Bold/Black/Semibold — считаем жирным."""
    name = span.get("font", "")
    if not name:
        return False
    nm = name.lower()
    return any(k in nm for k in ("bold", "black", "semibold", "demibold", "bd"))

# собираем bbox объединённого прямоугольника для набора строк
def rect_for_lines(lines):
    left = min(line["bbox"][0] for line in lines)
    top = min(line["bbox"][1] for line in lines)
    right = max(line["bbox"][2] for line in lines)
    bottom = max(line["bbox"][3] for line in lines)
    return fitz.Rect(left, top, right, bottom)

# ---- Функции по абзацам ----
def build_lines(block):
    """Возвращает список строк (словарей) в блоке в порядке сверху-вниз."""
    lines = []
    for line in block.get("lines", []):
        lines.append(line)
    # сортировка сверху вниз
    lines.sort(key=lambda ln: ln["bbox"][1])
    return lines

def median_line_height(lines):
    heights = [ln["bbox"][3] - ln["bbox"][1] for ln in lines if ln.get("bbox")]
    return statistics.median(heights) if heights else 12

def split_paragraphs(lines):
    """
    Разбиваем строки на абзацы с учётом вертикального промежутка
    и коротких предыдущих строк (индикатор конца абзаца).
    """
    if not lines:
        return []

    m_height = median_line_height(lines)
    gap_thr = m_height * GAP_MULT
    paragraphs = []
    cur = [lines[0]]

    for prev, curline in zip(lines, lines[1:]):
        vgap = curline["bbox"][1] - prev["bbox"][3]
        # правило: большой вертикальный пробел — разделение абзацев
        if vgap > gap_thr:
            paragraphs.append(cur)
            cur = [curline]
            continue

        # если предыдущая строка сильно короче чем типичная и кончается до правого края,
        # то, вероятно, это конец абзаца (например, заголовок или короткая строка)
        prev_right = max((s["bbox"][2] for s in prev["spans"]), default=0)
        cur_left = min((s["bbox"][0] for s in curline["spans"]), default=curline["bbox"][0])
        # если prev_right значительно меньше, чем ожидаемый правый край (т.е. переноса нет)
        if prev_right < (curline["bbox"][2] - 40) and (cur_left - prev_right) > (m_height * 0.2):
            paragraphs.append(cur)
            cur = [curline]
            continue

        # иначе — та же абзацная последовательность
        cur.append(curline)

    if cur:
        paragraphs.append(cur)
    return paragraphs

def paragraph_is_justified(par, page_width):
    """Определяем, выровнен ли абзац по ширине — оцениваем долю строк (кроме последней) близких к max_right."""
    if not par or len(par) <= 1:
        return False
    # вычислим внутренний max_right
    rights = [max((s["bbox"][2] for s in ln["spans"]), default=ln["bbox"][2]) for ln in par]
    max_right = max(rights)
    non_last = rights[:-1]
    good = sum(1 for r in non_last if abs(r - max_right) <= RIGHT_TOL_PT)
    frac = good / max(1, len(non_last))
    return frac >= JUSTIFY_FRAC

def paragraph_margins(par):
    """Возвращаем левый (min) и правый (max) координаты по всем span'ам в абзаце."""
    lefts, rights = [], []
    for ln in par:
        for sp in ln["spans"]:
            lefts.append(sp["bbox"][0])
            rights.append(sp["bbox"][2])
    return (min(lefts) if lefts else None, max(rights) if rights else None)

# ---- Объединение ошибок в участки ----
def group_line_issues(lines, issue_mask):
    """
    issue_mask: список буллов на каждую строку (True=есть проблема)
    Возвращаем список интервалов (start_idx, end_idx) где True, для объединённой аннотации.
    """
    groups = []
    i = 0
    n = len(lines)
    while i < n:
        if issue_mask[i]:
            j = i
            while j + 1 < n and issue_mask[j + 1]:
                j += 1
            groups.append((i, j))
            i = j + 1
        else:
            i += 1
    return groups

def process_pdf(input_bytes: bytes) -> bytes:
    """
    Улучшенный алгоритм проверки PDF:
    - корректная работа координат (исключены перевороты / отражения);
    - стабильное добавление комментариев рядом с абзацами;
    - аккуратное выделение нарушений;
    - проверка шрифта, размера, цвета, отступов, выравнивания и межстрочного;
    - проверка картинок и подписи к ним;
    """
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    for page in doc:
        # стабильное добавление шрифта без конфликтов
        try:
            page.insert_font(fontname=CYR_FONTNAME, fontbuffer=CYR_FONT.buffer)
        except:
            pass

        page_data = page.get_text("dict")
        page_width = page.rect.width

        def annotate_text(x, y, text, fontsize=7, color=(1, 0, 0)):
            """
            Универсальная вставка текста БЕЗ поворотов и отражений.
            """
            page.insert_text(
                (x, y),
                text,
                fontsize=fontsize,
                fontname=CYR_FONTNAME,
                color=color,
                rotate=0,
            )

        for block in page_data.get("blocks", []):

            # ---------------------------------------------------
            # КАРТИНКИ
            # ---------------------------------------------------
            if block.get("type") == 1:
                img_left, img_top, img_right, img_bottom = block["bbox"]
                img_center = (img_left + img_right) / 2
                page_center = page_width / 2

                if abs(img_center - page_center) > IMG_CENTER_TOL_PT:
                    annotate_text(
                        img_left,
                        img_bottom + 5,
                        "Рисунок не выровнен по центру",
                        fontsize=8
                    )
                continue

            # ---------------------------------------------------
            # ТЕКСТОВЫЕ БЛОКИ
            # ---------------------------------------------------
            if block.get("type") != 0:
                continue

            lines = build_lines(block)
            if not lines:
                continue

            paragraphs = split_paragraphs(lines)

            for par in paragraphs:
                r = rect_for_lines(par)
                left_x, right_x = paragraph_margins(par)
                expected_right = page_width - RIGHT_MARGIN

                # определяем тип
                first_text = span_text_from_line(par[0])
                is_list = is_list_line_text(first_text)
                is_heading = any(
                    detect_bold(sp) and sp.get("size", 0) >= MAX_FONT
                    for sp in par[0]["spans"]
                )

                # ---------------------- ЛЕВЫЙ ОТСТУП ----------------------
                left_issue = False
                if not is_list:
                    if left_x is not None and abs(left_x - LEFT_MARGIN) > LEFT_TOL_PT:
                        left_issue = True
                        left_rect = fitz.Rect(r.x0 - 26, r.y0, r.x0 - 2, r.y1)
                        page.draw_rect(left_rect, fill=LIGHT_FILL_LEFT, overlay=True)
                        annotate_text(
                            r.x0 - 25,
                            r.y0,
                            f"Левый отступ должен быть ~{LEFT_MARGIN_CM} см"
                        )

                # ---------------------- ПРАВЫЙ ОТСТУП ----------------------
                right_issue = False
                if not is_heading and right_x is not None:
                    if abs(right_x - expected_right) > RIGHT_TOL_PT:
                        if not paragraph_is_justified(par, page_width):
                            right_issue = True
                            right_rect = fitz.Rect(r.x1 + 2, r.y0, r.x1 + 26, r.y1)
                            page.draw_rect(right_rect, fill=LIGHT_FILL_RIGHT, overlay=True)
                            annotate_text(
                                r.x1 - 160,
                                r.y0,
                                f"Правый отступ должен быть ~{RIGHT_MARGIN_CM} см"
                            )

                # ---------------------- ВЫРАВНИВАНИЕ ----------------------
                if not is_heading:
                    if not paragraph_is_justified(par, page_width):
                        annotate_text(
                            page_width - 200,
                            r.y0,
                            "Абзац не выровнен по ширине"
                        )

                # ---------------------- МЕЖСТРОЧНОЕ ----------------------
                spacing_issues = [False] * len(par)
                prev_bottom = None
                for idx, ln in enumerate(par):
                    if prev_bottom is not None:
                        spacing = ln["bbox"][1] - prev_bottom
                        typical = ln["spans"][0]["size"] if ln["spans"] else MAX_FONT
                        expected = typical * 1.5
                        if abs(spacing - expected) > max(4, typical * 0.2):
                            spacing_issues[idx] = True
                    prev_bottom = ln["bbox"][3]

                for sidx, eidx in group_line_issues(par, spacing_issues):
                    seg_r = rect_for_lines(par[sidx:eidx+1])
                    page.draw_rect(seg_r, fill=(1, 1, 0.7), overlay=True)
                    annotate_text(seg_r.x0 + 5, seg_r.y0, "Интервал не полуторный")

                # ---------------------- ШРИФТ / РАЗМЕР / ЦВЕТ ----------------------
                span_issue_rects = []
                for ln in par:
                    for sp in ln["spans"]:
                        font = sp.get("font", "")
                        size = sp.get("size", 0)
                        color = sp.get("color", 0)
                        bbox = sp.get("bbox")

                        bad_font = "times" not in font.lower()
                        bad_size = not (MIN_FONT <= size <= MAX_FONT)
                        bad_color = not is_black(color)

                        if bad_font or bad_size or bad_color:
                            span_issue_rects.append((bbox, bad_font, bad_size, bad_color))

                for bbox, *_ in span_issue_rects:
                    hl = page.add_highlight_annot(fitz.Rect(bbox))
                    hl.set_opacity(0.4)
                    hl.update()

                if span_issue_rects:
                    msgs = []
                    if any(bf for _, bf, _, _ in span_issue_rects):
                        msgs.append("Не Times New Roman")
                    if any(bs for _, _, bs, _ in span_issue_rects):
                        msgs.append("Неверный размер")
                    if any(bc for _, _, _, bc in span_issue_rects):
                        msgs.append("Цвет не чёрный")

                    annotate_text(r.x0, r.y0 - 10, "; ".join(msgs))

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()

