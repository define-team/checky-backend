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

        # вычисляем реальные границы строки
        line_left = min(sp["bbox"][0] for sp in spans)
        line_right = max(sp["bbox"][2] for sp in spans)

        # фильтруем выбросы:
        # строки длиной < 40pt — это либо маркеры списка, либо конец абзаца
        if (line_right - line_left) < 40:
            continue

        left_candidates.append(line_left)
        right_candidates.append(line_right)

    if not left_candidates:
        return None, None

    # Берём медиану, а не минимум/максимум → меньше ложных срабатываний
    import statistics
    return statistics.median(left_candidates), statistics.median(right_candidates)


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

# ---- Основная функция ----
def process_pdf(input_bytes: bytes) -> bytes:
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    for page in doc:
        page.insert_font(fontname=CYR_FONTNAME, fontbuffer=CYR_FONT.buffer)
        data = page.get_text("dict")
        page_width = page.rect.width

        for block in data.get("blocks", []):

            # -- картинки --
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

            # --- сбор строк и разбиение на абзацы ---
            lines = build_lines(block)
            if not lines:
                continue

            paragraphs = split_paragraphs(lines)

            # обход абзацев
            for par in paragraphs:
                # вычисляем медианную высоту строк абзаца
                heights = [ln["bbox"][3] - ln["bbox"][1] for ln in par]
                med_h = statistics.median(heights) if heights else 12

                # вычисляем левый и правый края абзаца (по всем span'ам)
                left_x, right_x = paragraph_margins(par)
                expected_right = page_width - RIGHT_MARGIN

                # определяем тип абзаца: список / заголовок / обычный
                first_text = span_text_from_line(par[0]) if par[0].get("spans") else ""
                is_list = is_list_line_text(first_text)
                is_bold_heading = any(detect_bold(sp) for sp in par[0]["spans"]) and (par[0]["spans"][0]["size"] >= MAX_FONT)
                # если заголовок — не ругаемся на правый край
                treat_right = not is_bold_heading

                # --- левый отступ для абзаца ---
                left_issue = False
                # Для списков допускаем табуляцию (если left_x > LEFT_MARGIN) — это ожидаемо
                if not is_list:
                    if left_x is not None and abs(left_x - LEFT_MARGIN) > LEFT_TOL_PT:
                        left_issue = True

                # --- правый отступ для абзаца ---
                right_issue = False
                if treat_right and right_x is not None and abs(right_x - expected_right) > RIGHT_TOL_PT:
                    # но если абзац явно justified — позволяем мелкие отличия
                    if not paragraph_is_justified(par, page_width):
                        right_issue = True

                # --- выравнивание по ширине ---
                align_issue = False
                if paragraph_is_justified(par, page_width):
                    # считаем оправданным, если плотность хорошая
                    pass
                else:
                    # если большая часть строк не доходят до expected_right — пометим как не-выравнено
                    # используем проверку только если par длиннее 1
                    if len(par) > 1:
                        # посчитаем долю строк, которые доходят почти до expected_right
                        cnt_ok = 0
                        for ln in par[:-1]:
                            ln_right = max((s["bbox"][2] for s in ln["spans"]), default=ln["bbox"][2])
                            if abs(ln_right - expected_right) <= RIGHT_TOL_PT:
                                cnt_ok += 1
                        frac = cnt_ok / max(1, len(par) - 1)
                        if frac < JUSTIFY_FRAC:
                            align_issue = True

                # --- межстрочный интервал по абзацу ---
                spacing_issues = [False] * len(par)
                prev_bottom = None
                for idx, ln in enumerate(par):
                    if prev_bottom is not None:
                        spacing = ln["bbox"][1] - prev_bottom
                        typical_size = ln["spans"][0]["size"] if ln["spans"] else MAX_FONT
                        expected_space = typical_size * 1.5
                        if abs(spacing - expected_space) > max(4, typical_size * 0.2):
                            spacing_issues[idx] = True
                    prev_bottom = ln["bbox"][3]

                # --- шрифт/размер/цвет на уровне span (будем подсвечивать span'ы индивидуально) ---
                span_issue_rects = []
                for ln in par:
                    for sp in ln["spans"]:
                        font = sp.get("font", "")
                        size = sp.get("size", 0)
                        color = sp.get("color", 0)
                        bbox = sp.get("bbox")
                        bad_font = not ("Times" in font or "Times" in font.lower())
                        bad_size = not (MIN_FONT <= size <= MAX_FONT)
                        bad_color = not is_black(color)
                        if bad_font or bad_size or bad_color:
                            # добавим прямоугольник под span — потом делаем annot
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
                        f"Левый отступ ≠ {LEFT_MARGIN_CM} см",
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
                        (line_x -80, y0 - 5),
                        f"Правый отступ ≠ {RIGHT_MARGIN_CM} см",
                        fontsize=8,
                        fontname=CYR_FONTNAME,
                        color=(0, 0, 0.6)
                    )

                # выравнивание по ширине
                if align_issue:
                    r = rect_for_lines(par)
                    page.insert_text((page_width - 220, r.y0), "Абзац не выровнен по ширине", fontsize=8, fontname=CYR_FONTNAME, color=(1,0,0))

                # межстрочные — группируем смежные строки с проблемой
                groups = group_line_issues(par, spacing_issues)
                for (sidx, eidx) in groups:
                    seg = par[sidx:eidx+1]
                    r = rect_for_lines(seg)
                    page.draw_rect(r, fill=(1,1,0.9), overlay=True)
                    page.insert_text((r.x0 + 6, r.y0), "Интервал не полуторный", fontsize=7, fontname=CYR_FONTNAME, color=(0.6,0,0))

                # подсветка span-level проблем (шрифт/размер/цвет) — делаем highlight + подпись у первого
                for bbox, bad_font, bad_size, bad_color, size in span_issue_rects:
                    hl = page.add_highlight_annot(fitz.Rect(bbox))
                    hl.set_colors(stroke=(1,1,0))
                    hl.set_opacity(0.4)
                    hl.update()
                # подписи для span-issues — чтобы не писать на каждую, сгруппируем по близости
                # (простая стратегия: если есть хоть одна span_issue в абзаце — пишем одно сообщение сверху)
                if span_issue_rects:
                    r = rect_for_lines(par)
                    msgs = []
                    if any(x[1] for x in span_issue_rects): msgs.append("Шрифт не Times New Roman")
                    if any(x[2] for x in span_issue_rects): msgs.append(f"Размер не в {MIN_FONT}-{MAX_FONT} pt")
                    if any(x[3] for x in span_issue_rects): msgs.append("Не чёрный цвет")
                    page.insert_text((r.x0, r.y0 - 10), "; ".join(msgs), fontsize=7, fontname=CYR_FONTNAME, color=(1,0,0))

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()

