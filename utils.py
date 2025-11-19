import fitz
import io
import statistics
import re

_marker_re = re.compile(r"""^(
    [\u2022\u2023\-\–\—\*·]+ |    # bullets/dashes
    \d+[\.\)] |                   # 1.  or 1)
    [a-zA-Z]\)                    # a)
    )$""", re.X)

CYR_FONT = fitz.Font("tiro")
CYR_FONTNAME = "CYR"
MIN_FONT = 12
MAX_FONT = 14
LEFT_MARGIN_CM = 3.0
RIGHT_MARGIN_CM = 2.0
CM_TO_POINTS = 28.3464567
LEFT_MARGIN = LEFT_MARGIN_CM * CM_TO_POINTS
RIGHT_MARGIN = RIGHT_MARGIN_CM * CM_TO_POINTS
GAP_MULT = 1.8
RIGHT_TOL_PT = 12
LEFT_TOL_PT = 10
JUSTIFY_FRAC = 0.7
IMG_CENTER_TOL_PT = 15
LIGHT_FILL_LEFT = (1, 0.9, 0.9)
LIGHT_FILL_RIGHT = (0.95, 0.95, 1)
FIRST_LINE_INDENT_CM = 1.25
FIRST_LINE_INDENT_PT = FIRST_LINE_INDENT_CM * CM_TO_POINTS
MIN_LEN_FOR_LEFT_CHECK_PT = 2.0 * CM_TO_POINTS

# УПРОЩЁННАЯ ПРОВЕРКА ЛЕВОГО ОТСТУПА ---

def check_left_indent(line):
    """
    Упрощённая проверка: строка должна начинаться правее чем 3 см.
    Не учитываем списки, красную строку и т.д.
    """

    spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
    if not spans:
        return False  # пустая строка, нарушение не считаем

    line_left = min(sp["bbox"][0] for sp in spans)

    if line_left < LEFT_MARGIN:
        return True  # нарушение

    return False

def is_text_line(ln):
    """Строка считается текстовой, если содержит хотя бы один span с текстом."""
    spans = ln.get("spans", [])
    return any(s.get("text", "").strip() for s in spans)


def line_height(ln):
    """Высота строки по bbox."""
    return ln["bbox"][3] - ln["bbox"][1]


def detect_table_like(ln):
    """
    Признак таблицы:
    — слишком много spans (таблица разбивает текст на ячейки)
    — слишком маленькая высота строки (часто у таблиц)
    """
    spans = ln.get("spans", [])
    if len(spans) >= 8:
        return True

    if line_height(ln) < 6:
        return True

    return False


def check_global_line_spacing(page, page_dict, fontname):
    """
    Проверяет межстрочный интервал по всей странице между любыми строками.
    Рисует фиолетовые линии между проблемными строками.
    """
    all_lines = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            all_lines.append(ln)

    if len(all_lines) < 2:
        return
    all_lines.sort(key=lambda ln: ln["bbox"][1])

    for i in range(len(all_lines) - 1):
        ln1 = all_lines[i]
        ln2 = all_lines[i + 1]

        if not is_text_line(ln1) or not is_text_line(ln2):
            continue
        if detect_table_like(ln1) or detect_table_like(ln2):
            continue

        gap = ln2["bbox"][1] - ln1["bbox"][3]

        h1 = line_height(ln1)
        h2 = line_height(ln2)
        avg_h = (h1 + h2) / 2
        expected_min = avg_h * 0.15
        expected_max = avg_h * 0.50

        if gap < expected_min or gap > expected_max:
            y = (ln1["bbox"][3] + ln2["bbox"][1]) / 2

            x0 = min(ln1["bbox"][0], ln2["bbox"][0]) - 10
            x1 = max(ln1["bbox"][2], ln2["bbox"][2]) + 10

            page.draw_line(
                (x0, y),
                (x1, y),
                color=(0.6, 0.0, 0.8),
                width=2
            )

            page.insert_text(
                (x0, y - 6),
                "Неверный межстрочный интервал",
                fontsize=7,
                fontname=fontname,
                color=(0.6, 0.0, 0.8)
            )


def is_marker_token(tok: str) -> bool:
    t = tok.strip()
    if not t:
        return False
    if len(t) <= 3 and all(not ch.isalnum() for ch in t):
        return True
    if _marker_re.match(t):
        return True
    return False

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

def rect_for_lines(lines):
    left = min(line["bbox"][0] for line in lines)
    top = min(line["bbox"][1] for line in lines)
    right = max(line["bbox"][2] for line in lines)
    bottom = max(line["bbox"][3] for line in lines)
    return fitz.Rect(left, top, right, bottom)

def build_lines(block):
    """Возвращает список строк (словарей) в блоке в порядке сверху-вниз."""
    lines = []
    for line in block.get("lines", []):
        lines.append(line)
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
        if vgap > gap_thr:
            paragraphs.append(cur)
            cur = [curline]
            continue

        prev_right = max((s["bbox"][2] for s in prev["spans"]), default=0)
        cur_left = min((s["bbox"][0] for s in curline["spans"]), default=curline["bbox"][0])
        if prev_right < (curline["bbox"][2] - 40) and (cur_left - prev_right) > (m_height * 0.2):
            paragraphs.append(cur)
            cur = [curline]
            continue

        cur.append(curline)

    if cur:
        paragraphs.append(cur)
    return paragraphs

def paragraph_is_justified(par, page_width):
    """Определяем, выровнен ли абзац по ширине — оцениваем долю строк (кроме последней) близких к max_right."""
    if not par or len(par) <= 1:
        return False
    rights = [max((s["bbox"][2] for s in ln["spans"]), default=ln["bbox"][2]) for ln in par]
    max_right = max(rights)
    non_last = rights[:-1]
    good = sum(1 for r in non_last if abs(r - max_right) <= RIGHT_TOL_PT)
    frac = good / max(1, len(non_last))
    return frac >= JUSTIFY_FRAC

def paragraph_margins(par):
    """
    Возвращает левый и правый края абзаца.
    Игнорирует короткие последующие строки, красную строку, списочные маркеры
    и случайные выбросы (как в таблицах).
    """
    left_candidates = []
    right_candidates = []

    for ln in par:
        spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
        if not spans:
            continue

        line_left = min(sp["bbox"][0] for sp in spans)
        line_right = max(sp["bbox"][2] for sp in spans)

        if (line_right - line_left) < 40:
            continue

        left_candidates.append(line_left)
        right_candidates.append(line_right)

    if not left_candidates:
        return None, None

    import statistics
    return statistics.median(left_candidates), statistics.median(right_candidates)

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
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    for page in doc:
        page_dict = page.get_text("dict")
        page_width = page.rect.width
        page.insert_font(fontname=CYR_FONTNAME, fontbuffer=CYR_FONT.buffer)
        data = page.get_text("dict")
        page_width = page.rect.width

        for block in data.get("blocks", []):

            if block.get("type") == 1:  # image
                img_left = block["bbox"][0]
                img_right = block["bbox"][2]
                img_center = (img_left + img_right) / 2
                page_center = page_width / 2
                if abs(img_center - page_center) > IMG_CENTER_TOL_PT:
                    # прямоугольник под картинкой и подпись
                    page.insert_text(
                        (img_left, block["bbox"][3] + 4),
                        "Рисунок не выровнен по центру",
                        fontsize=8,
                        color=(1, 0, 0),
                        fontname=CYR_FONTNAME
                    )
                continue

            if block.get("type") != 0:
                continue

            lines = build_lines(block)
            if not lines:
                continue

            paragraphs = split_paragraphs(lines)

            for par in paragraphs:
                heights = [ln["bbox"][3] - ln["bbox"][1] for ln in par]
                med_h = statistics.median(heights) if heights else 12

                left_x, right_x = paragraph_margins(par)
                expected_right = page_width - RIGHT_MARGIN

                first_text = span_text_from_line(par[0]) if par[0].get("spans") else ""
                is_list = is_list_line_text(first_text)
                is_bold_heading = any(detect_bold(sp) for sp in par[0]["spans"]) and (
                            par[0]["spans"][0]["size"] >= MAX_FONT)
                treat_right = not is_bold_heading

                line_lengths = []
                for ln in par:
                    spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
                    if not spans:
                        continue
                    left_l = min(s["bbox"][0] for s in spans)
                    right_l = max(s["bbox"][2] for s in spans)
                    line_lengths.append(right_l - left_l)
                avg_line_len = statistics.median(line_lengths) if line_lengths else 0

                left_issue = False
                for ln in par:
                    if check_left_indent(ln):
                        left_issue = True
                        break

                # # --- НОВЫЙ алгоритм проверки левого отступа ---
                # # --- ЛЕВЫЙ ОТСТУП — НОВАЯ ЛОГИКА ---
                # left_issue = False
                #
                # # текст первой строки
                first_line_text = span_text_from_line(par[0])
                first_char = first_line_text.strip()[0] if first_line_text.strip() else ""
                #
                # # вычисляем левый край первой строки абзаца
                # first_spans = [s for s in par[0].get("spans", []) if s.get("text", "").strip()]
                # first_left = min(s["bbox"][0] for s in first_spans) if first_spans else None
                #
                # # если margin не вычислился — считаем, что 3 см
                # if left_x is None:
                #     left_x = LEFT_MARGIN
                #
                # # виды строк
                # is_heading = is_bold_heading
                #
                #
                # # допустимые варианты красной строки:
                # acceptable_first_line_offsets = [
                #     LEFT_MARGIN,  # 3 см
                #     LEFT_MARGIN + FIRST_LINE_INDENT_PT  # 3 + 1.25 = 4.25 см
                # ]
                #
                # # ---- 1. Заголовки не проверяем ----
                # if is_heading:
                #     left_issue = False
                #

                # # ---- 3. Первая строка абзаца: допускаем 3 см и 4.25 см ----
                # elif first_left is not None and any(
                #         abs(first_left - a) <= LEFT_TOL_PT for a in acceptable_first_line_offsets):
                #     left_issue = False
                #
                # # ---- 4. Все остальные строки должны быть ровно 3 см ----
                # else:
                #     if abs(left_x - LEFT_MARGIN) > (LEFT_TOL_PT + 2):
                #         # допускаем до 2 pt погрешности PDF
                #         left_issue = True
                # # ---- 2. Подписи к рисункам не проверяем ----
                # elif is_image_caption:
                #     left_issue = False
                #
                is_image_caption = first_char == "Р"  # «Рисунок ...»


                # ПРАВЫЙ ОТСТУП — НОВАЯ ПРОСТАЯ ЛОГИКА
                right_issue = False

                if is_bold_heading:
                    right_issue = False

                elif is_image_caption:
                    right_issue = False

                else:
                    if right_x is not None and right_x > expected_right + RIGHT_TOL_PT:
                        right_issue = True

                # выравнивание по ширине

                align_issue = False

                if len(par) > 1:
                    rights = []
                    for ln in par[:-1]:  # все кроме последней
                        r = max(s["bbox"][2] for s in ln["spans"])
                        rights.append(r)

                    median_right = statistics.median(rights)

                    bad = 0
                    for r in rights:
                        if abs(r - median_right) > 20:
                            bad += 1
                    lefts = [min(s["bbox"][0] for s in ln["spans"]) for ln in par[:-1]]
                    median_left = statistics.median(lefts)
                    left_bad = sum(1 for l in lefts if abs(l - median_left) > 25)

                    if left_bad / len(lefts) > 0.3:
                        align_issue = True

                    if bad / len(rights) > 0.3:
                        align_issue = True

                # межстрочный интервал по абзацу
                spacing_issues = [False] * len(par)

                for idx in range(1, len(par)):
                    prev_ln = par[idx - 1]
                    ln = par[idx]

                    spacing = ln["bbox"][1] - prev_ln["bbox"][3]

                    prev_h = prev_ln["bbox"][3] - prev_ln["bbox"][1]

                    if prev_h <= 0:
                        continue

                    ratio = spacing / prev_h

                    if not (0.20 <= ratio <= 0.50):
                        spacing_issues[idx] = True

                # шрифт/размер/цвет на уровне span
                span_issue_rects = []
                for ln in par:
                    line_text = span_text_from_line(ln)
                    first_token = line_text.split()[0] if line_text.split() else ""
                    line_is_list_marker = is_list and is_marker_token(first_token)

                    for sp in ln["spans"]:
                        sp_text = sp.get("text", "").strip()
                        if line_is_list_marker and sp_text and is_marker_token(sp_text):
                            continue

                        font = sp.get("font", "")
                        size = sp.get("size", 0)
                        color = sp.get("color", 0)
                        bbox = sp.get("bbox")
                        bad_font = not ("Times" in font or "Times" in font.lower())
                        bad_size = not (MIN_FONT <= size <= MAX_FONT)
                        bad_color = not is_black(color)


                        if bad_font or bad_size or bad_color:
                            span_issue_rects.append((bbox, bad_font, bad_size, bad_color, size))

                # --- теперь рисуем и группируем пометки абзацно (а не построчно) ---
                # левый отступ — светлая заливка слева блока
                # --- вместо старой заливки слева:
                if left_issue:
                    r = rect_for_lines(par)
                    # координата линии чуть левее фактического левого края абзаца
                    line_x = r.x0 - 6
                    y0 = r.y0
                    y1 = r.y1
                    # рисуем сплошную вертикальную линию (красная)
                    page.draw_line((line_x, y0), (line_x, y1), color=(0.85, 0.15, 0.15), width=2)
                    # подпись сверху рядом с линией (горизонтально, читаемо)
                    page.insert_text(
                        (line_x - 4, y0 - 5),
                        f"Неверный левый отступ ",
                        # ≠ {LEFT_MARGIN_CM} см
                        fontsize=8,
                        fontname=CYR_FONTNAME,
                        color=(0.6, 0, 0)
                    )

                # --- вместо старой заливки справа:
                if right_issue:
                    r = rect_for_lines(par)
                    # координата линии чуть правее фактического правого края абзаца
                    line_x = r.x1 + 6
                    y0 = r.y0
                    y1 = r.y1
                    # рисуем сплошную вертикальную линию (синяя)
                    page.draw_line((line_x, y0), (line_x, y1), color=(0, 0.2, 0.8), width=2)
                    # подпись сверху справа от линии (горизонтально)
                    page.insert_text(
                        (line_x - 80, y0 - 5),
                        f"Правый отступ ≠ {RIGHT_MARGIN_CM} см",
                        fontsize=8,
                        fontname=CYR_FONTNAME,
                        color=(0, 0, 0.6)
                    )

                # выравнивание по ширине
                if align_issue:
                    r = rect_for_lines(par)
                    page.insert_text((page_width - 220, r.y0), "Абзац не выровнен по ширине", fontsize=8,
                                     fontname=CYR_FONTNAME, color=(1, 0, 0))

                # --- неправильный межстрочный интервал (НОВАЯ ОТРИСОВКА) ---
                groups = group_line_issues(par, spacing_issues)
                for (sidx, eidx) in groups:
                    for i in range(sidx, eidx + 1):
                        if i == 0:
                            continue

                        prev_ln = par[i - 1]
                        ln = par[i]

                        # горизонтальные границы — пересечение строк
                        x0 = max(prev_ln["bbox"][0], ln["bbox"][0])
                        x1 = min(prev_ln["bbox"][2], ln["bbox"][2])

                        if x1 <= x0:
                            continue

                        # ровно посередине интервала
                        y = (prev_ln["bbox"][3] + ln["bbox"][1]) / 2

                        page.draw_line(
                            (x0, y),
                            (x1, y),
                            color=(0.6, 0.0, 0.8),
                            width=2
                        )

                    # подпись
                    top_ln = par[sidx]
                    page.insert_text(
                        (top_ln["bbox"][0], top_ln["bbox"][1] - 6),
                        "Неверный межстрочный интервал",
                        fontsize=7,
                        fontname=CYR_FONTNAME,
                        color=(0.6, 0.0, 0.8)
                    )
                # check_global_line_spacing(page, page_dict, CYR_FONTNAME)
                # подсветка span-level проблем (шрифт/размер/цвет) — делаем highlight + подпись у первого
                for bbox, bad_font, bad_size, bad_color, size in span_issue_rects:
                    rect = fitz.Rect(bbox)
                    page.draw_rect(rect, fill=(1, 0, 0), fill_opacity=0.35, color=None, width=0, overlay=True)

                # подписи для span-issues — чтобы не писать на каждую, сгруппируем по близости
                # (простая стратегия: если есть хоть одна span_issue в абзаце — пишем одно сообщение сверху)
                if span_issue_rects:
                    r = rect_for_lines(par)
                    msgs = []
                    if any(x[1] for x in span_issue_rects): msgs.append("Шрифт не Times New Roman")
                    if any(x[2] for x in span_issue_rects): msgs.append(f"Размер не {MIN_FONT}-{MAX_FONT} ")
                    if any(x[3] for x in span_issue_rects): msgs.append("Не чёрный цвет")
                    page.insert_text((r.x0, r.y0 - 2), "; ".join(msgs), fontsize=7, fontname=CYR_FONTNAME,
                                     color=(1, 0, 0))
    # ---- Межабзацные интервалы (НОВАЯ ЛОГИКА) ----

    text_lines = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            if not ln.get("spans"):
                continue

            # пропускаем заголовки
            if any(detect_bold(s) for s in ln["spans"]) and ln["spans"][0]["size"] >= MAX_FONT:
                continue
            # пропускаем подписи рисунков
            if span_text_from_line(ln).strip().startswith("Рисунок"):
                continue

            h = ln["bbox"][3] - ln["bbox"][1]
            if h <= 0:
                continue

            text_lines.append({
                "bbox": ln["bbox"],
                "height": h
            })

    text_lines.sort(key=lambda x: x["bbox"][1])

    for i in range(1, len(text_lines)):
        prev = text_lines[i - 1]
        cur = text_lines[i]

        gap = cur["bbox"][1] - prev["bbox"][3]
        h = prev["height"]

        # межабзацный интервал считается нормальным около 1.2h–1.8h
        if gap > h * 1.8:
            # лишний интервал — помечаем
            y = (prev["bbox"][3] + cur["bbox"][1]) / 2
            x0 = max(prev["bbox"][0], cur["bbox"][0])
            x1 = min(prev["bbox"][2], cur["bbox"][2])
            if x1 > x0:
                page.draw_line(
                    (x0, y),
                    (x1, y),
                    color=(0.6, 0.0, 0.8),
                    width=2
                )

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()









