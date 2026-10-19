import asyncio
import inspect
import json
import os
import random
from fractions import Fraction

import flet as ft

# =====================================================================
#  ЛОГИКА
# =====================================================================

DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
MAX_FRAC = 12  # максимум знаков после точки
OP_CHARS = "+-−*×/÷()"


class Incomplete(ValueError):
    """Ввод ещё не закончен (например, '5+'). Ошибку при этом не показываем."""


def parse_number(text, base):
    """Строка -> Fraction в заданной системе."""
    s = text.strip().replace(",", ".").replace(" ", "")
    if not s or s == ".":
        raise Incomplete("Введи число")

    sign = 1
    if s[0] in "+-−":
        if s[0] != "+":
            sign = -1
        s = s[1:]
    if not s or s == ".":
        raise Incomplete("Введи число")
    if s.count(".") > 1:
        raise ValueError("Слишком много точек")

    int_part, _, frac_part = s.partition(".")
    value = Fraction(0)

    for ch in int_part.lower():
        d = DIGITS.find(ch)
        if d == -1 or d >= base:
            raise ValueError(f"Символ «{ch.upper()}» не подходит для системы {base}")
        value = value * base + d

    for i, ch in enumerate(frac_part.lower(), start=1):
        d = DIGITS.find(ch)
        if d == -1 or d >= base:
            raise ValueError(f"Символ «{ch.upper()}» не подходит для системы {base}")
        value += Fraction(d, base ** i)

    return sign * value


def format_number(value, base):
    """Fraction -> (строка в системе base, приблизительно ли)."""
    sign = ""
    if value < 0:
        sign = "-"
        value = -value

    int_val = value.numerator // value.denominator
    frac = value - int_val

    if int_val == 0:
        int_str = "0"
    else:
        chars = []
        while int_val:
            int_val, r = divmod(int_val, base)
            chars.append(DIGITS[r])
        int_str = "".join(reversed(chars)).upper()

    frac_str = ""
    approx = False
    if frac:
        chars = []
        for _ in range(MAX_FRAC):
            frac *= base
            d = int(frac)
            chars.append(DIGITS[d])
            frac -= d
            if frac == 0:
                break
        frac_str = "." + "".join(chars).upper()
        approx = frac != 0

    return sign + int_str + frac_str, approx


# ---------- выражения: 1011 + 110, (A+3)*2 и т.д. ----------

def tokenize(text, base):
    s = text.strip().replace(",", ".").replace(" ", "")
    tokens = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "+":
            tokens.append("+")
            i += 1
        elif ch in "-−":
            tokens.append("-")
            i += 1
        elif ch in "*×":
            tokens.append("*")
            i += 1
        elif ch in "/÷":
            tokens.append("/")
            i += 1
        elif ch in "()":
            tokens.append(ch)
            i += 1
        else:
            j = i
            while j < len(s) and s[j] not in OP_CHARS:
                j += 1
            tokens.append(parse_number(s[i:j], base))
            i = j
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expr(self):
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.next()
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def term(self):
        v = self.factor()
        while self.peek() in ("*", "/"):
            op = self.next()
            r = self.factor()
            if op == "*":
                v = v * r
            else:
                if r == 0:
                    raise ValueError("Деление на ноль")
                v = v / r
        return v

    def factor(self):
        tok = self.next()
        if tok is None:
            raise Incomplete("Выражение не закончено")
        if isinstance(tok, Fraction):
            return tok
        if tok == "-":
            return -self.factor()
        if tok == "+":
            return self.factor()
        if tok == "(":
            v = self.expr()
            if self.next() != ")":
                raise Incomplete("Не хватает закрывающей скобки")
            return v
        raise ValueError("Лишний знак в выражении")


def evaluate(text, base):
    """-> (значение Fraction или None, это выражение?)"""
    if not text.strip():
        return None, False
    tokens = tokenize(text, base)
    plain = (
        len(tokens) == 1
        or (len(tokens) == 2 and tokens[0] in ("+", "-") and isinstance(tokens[1], Fraction))
    )
    p = _Parser(tokens)
    value = p.expr()
    if p.peek() is not None:
        raise ValueError("Проверь выражение: лишний символ")
    return value, not plain


# ---------- пошаговое объяснение ----------

def fmt_dec(x):
    if x.denominator == 1:
        return str(x.numerator)
    return f"{float(x):.10g}"


def division_lines(n, b):
    if n == 0:
        return ["0 в любой системе это 0"]
    lines = []
    digits = []
    cur = n
    count = 0
    while cur:
        q, r = divmod(cur, b)
        rs = str(r) if r < 10 else f"{r} ({DIGITS[r].upper()})"
        if count < 30:
            lines.append(f"{cur} ÷ {b} = {q}, остаток {rs}")
        digits.append(DIGITS[r].upper())
        cur = q
        count += 1
    if count > 30:
        lines.append(f"… ещё {count - 30} шагов")
    lines.append("Остатки читаем снизу вверх: " + "".join(reversed(digits)))
    return lines


def fraction_lines(frac, b):
    lines = []
    digits = []
    for _ in range(MAX_FRAC):
        prod = frac * b
        d = int(prod)
        lines.append(f"{fmt_dec(frac)} × {b} = {fmt_dec(prod)} → цифра {DIGITS[d].upper()}")
        digits.append(DIGITS[d].upper())
        frac = prod - d
        if frac == 0:
            break
    lines.append("Цифры читаем сверху вниз: 0." + "".join(digits) + ("…" if frac else ""))
    return lines


def expansion_line(text, fb, dec_str, sign):
    s = text.strip().replace(",", ".").replace(" ", "").lstrip("+-−")
    ip, _, fp = s.partition(".")
    terms = []
    for idx, ch in enumerate(ip.lower()):
        terms.append(f"{DIGITS.find(ch)}·{fb}^{len(ip) - 1 - idx}")
    for i, ch in enumerate(fp.lower(), start=1):
        terms.append(f"{DIGITS.find(ch)}·{fb}^-{i}")
    if len(terms) > 10:
        terms = terms[:10] + ["…"]
    return f"{s.upper()} = " + " + ".join(terms) + f" = {sign}{dec_str}"


def explain(text, val, is_expr, fb, tb):
    if not is_expr and fb == tb:
        return ["Системы одинаковые, число не меняется."]

    neg = val < 0
    a = -val if neg else val
    dec_str, _ = format_number(a, 10)
    sign = "−" if neg else ""
    lines = []
    step = 1

    if is_expr:
        lines.append(f"Значение выражения в десятичной системе: {sign}{dec_str}")
    elif fb != 10:
        lines.append(f"Шаг {step}. Из системы {fb} в десятичную:")
        step += 1
        lines.append(expansion_line(text, fb, dec_str, sign))

    if tb != 10:
        lines.append(f"Шаг {step}. Из десятичной ({sign}{dec_str}) в систему {tb}:")
        int_val = a.numerator // a.denominator
        frac = a - int_val
        if int_val or not frac:
            lines += division_lines(int_val, tb)
        if frac:
            lines.append("Дробная часть (умножаем на основание):")
            lines += fraction_lines(frac, tb)
        res, _ = format_number(val, tb)
        lines.append(f"Ответ: {res}")
    elif not is_expr:
        lines.append(f"Ответ: {sign}{dec_str}")

    return lines


# ---------- текст <-> двоичный код ----------

BYTE_FMT = {2: ("08b", 8), 8: ("03o", 3), 10: (None, 0), 16: ("02X", 2)}


def text_to_code(s, base):
    data = s.encode("utf-8")
    if base == 10:
        return " ".join(str(b) for b in data)
    fmt = BYTE_FMT[base][0]
    return " ".join(format(b, fmt) for b in data)


def code_to_text(s, base):
    s = s.strip()
    if not s:
        return ""
    tokens = s.split()
    width = BYTE_FMT[base][1]
    if len(tokens) == 1 and width and len(tokens[0]) > width:
        t = tokens[0]
        if len(t) % width:
            raise Incomplete(f"Слитный код: длина должна делиться на {width}")
        tokens = [t[i:i + width] for i in range(0, len(t), width)]
    out = []
    for tok in tokens:
        try:
            v = int(tok, base)
        except ValueError:
            raise ValueError(f"«{tok}» не подходит для системы {base}")
        if not 0 <= v <= 255:
            raise ValueError(f"«{tok}» больше одного байта (максимум 255)")
        out.append(v)
    try:
        return bytes(out).decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Это не похоже на текст (UTF-8). Проверь код")


# ---------- дополнительный код (отрицательные числа) ----------

def twos_range(bits):
    return -(1 << (bits - 1)), (1 << (bits - 1)) - 1


def group4(b):
    return " ".join(b[i:i + 4] for i in range(0, len(b), 4))


def twos_encode(text, bits):
    """Десятичное число -> (код без пробелов, строки объяснения)."""
    s = text.strip().replace(" ", "")
    if s in ("", "-", "−", "+"):
        raise Incomplete("Введи число")
    neg = s[0] in "-−"
    body = s[1:] if s[0] in "+-−" else s
    if not body or any(c not in "0123456789" for c in body):
        raise ValueError("Нужно целое число без точек и букв")
    n = int(body) * (-1 if neg else 1)

    lo, hi = twos_range(bits)
    if not lo <= n <= hi:
        raise ValueError(f"Не помещается в {bits} бит. Можно от {lo} до {hi}")

    mask = (1 << bits) - 1
    code = format(n & mask, f"0{bits}b")

    if n >= 0:
        lines = [
            f"Число положительное, поэтому код это просто двоичная запись, "
            f"дополненная нулями слева до {bits} бит.",
            f"Ответ: {group4(code)}",
        ]
    else:
        a = -n
        a_bits = format(a, f"0{bits}b")
        inv = format(~a & mask, f"0{bits}b")
        lines = [
            f"Шаг 1. Берём число без минуса ({a}) и пишем в двоичной на {bits} бит:",
            group4(a_bits),
            "Шаг 2. Переворачиваем все цифры (0 → 1, 1 → 0):",
            group4(inv),
            "Шаг 3. Прибавляем 1:",
            group4(code),
            f"Ответ: {group4(code)}",
        ]
    return code, lines


def twos_decode(text, bits):
    """Двоичный код -> (число, строки объяснения)."""
    s = text.replace(" ", "")
    if not s:
        raise Incomplete("Введи двоичный код")
    if any(c not in "01" for c in s):
        raise ValueError("В двоичном коде только 0 и 1")
    if len(s) > bits:
        raise ValueError(f"Слишком длинный код: должно быть {bits} цифр")
    if len(s) < bits:
        raise Incomplete(f"Нужно ровно {bits} цифр, сейчас {len(s)}")

    if s[0] == "0":
        n = int(s, 2)
        lines = [
            "Первая цифра 0, значит число положительное.",
            "Читаем как обычное двоичное число.",
            f"Ответ: {n}",
        ]
    else:
        inv = "".join("1" if c == "0" else "0" for c in s)
        mag = int(inv, 2) + 1
        n = -mag
        lines = [
            "Первая цифра 1, значит число отрицательное.",
            "Шаг 1. Переворачиваем все цифры (0 → 1, 1 → 0):",
            group4(inv),
            "Шаг 2. Прибавляем 1:",
            group4(format(mag, f"0{bits}b")),
            f"Шаг 3. Это двоичная запись числа {mag}, а нам нужен минус:",
            f"Ответ: {n}",
        ]
    return n, lines


# ---------- история (хранится в файле) ----------

def data_path(name):
    base = os.getenv("FLET_APP_STORAGE_DATA") or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def load_json(name, default):
    try:
        with open(data_path(name), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def save_json(name, data):
    try:
        path = data_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def load_history():
    return load_json("history.json", [])


def save_history(items):
    save_json("history.json", items)


# =====================================================================
#  ИНТЕРФЕЙС
# =====================================================================

THEMES = {
    "dark": dict(bg="#0F1117", card="#1A1D27", chip="#262A38", text="#FFFFFF",
                 muted="#8A8FA3", err="#FF6B6B", accent="#6C63FF", ok="#4ADE80"),
    "light": dict(bg="#F2F3F8", card="#FFFFFF", chip="#E6E8F2", text="#1A1D27",
                  muted="#6B7085", err="#D63A3A", accent="#6C63FF", ok="#16A34A"),
}

QUICK_BASES = (2, 8, 10, 16)
BASE_NAMES = {2: "BIN", 8: "OCT", 10: "DEC", 16: "HEX"}
WHITE = "#FFFFFF"


async def set_clipboard(page, text):
    try:
        if hasattr(page, "set_clipboard_async"):
            await page.set_clipboard_async(text)
            return True
        if hasattr(page, "set_clipboard"):
            r = page.set_clipboard(text)
            if inspect.isawaitable(r):
                await r
            return True
        if hasattr(ft, "Clipboard"):
            await ft.Clipboard().set(text)
            return True
    except Exception:
        pass
    return False


def main(page: ft.Page):
    page.title = "Системы счисления"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    try:
        page.window.width = 400
        page.window.height = 860
    except Exception:
        pass

    try:
        is_mobile = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
    except Exception:
        is_mobile = False

    stats = load_json("trainer.json", {})
    state = {
        "mode": "num",      # num | text
        "theme": "dark",
        "from": 10,
        "to": 2,
        "steps": False,
        "result": "",
        "last_val": None,
        "num_text": "",
        "tdir": "to_code",  # to_code | to_text
        "tbase": 2,
        "txt_text": "",
        "tresult": "",
        # доп. код
        "cdir": "to_code",  # to_code | to_num
        "cbits": 8,
        "c_text": "",
        "cresult": "",
        "craw": "",
        # тренажёр
        "tr_level": "easy",
        "tr_value": None,
        "tr_from": 10,
        "tr_to": 2,
        "tr_answered": False,
        "tr_hint": False,
        "tr_feedback": "",
        "tr_ok": False,
        "tr_streak": 0,
        "tr_best": int(stats.get("best", 0) or 0),
        "tr_correct": int(stats.get("correct", 0) or 0),
        "tr_total": int(stats.get("total", 0) or 0),
        # столбик в тренажёре
        "col_on": False,
        "col_cur": 0,
        "col_phase": "q",   # q = частное, r = остаток
        "col_q": 0,
        "col_rows": [],
        "col_done": False,
        "col_msg": "",
    }
    ui = {}
    refreshers = {}
    history = load_history()

    # -----------------------------------------------------------------
    def build():
        C = THEMES[state["theme"]]
        page.theme_mode = ft.ThemeMode.DARK if state["theme"] == "dark" else ft.ThemeMode.LIGHT
        page.bgcolor = C["bg"]
        ui["C"] = C
        refreshers.clear()

        def card(content, padding=16):
            return ft.Container(bgcolor=C["card"], border_radius=20, padding=padding, content=content)

        def label(text):
            return ft.Text(text, size=13, color=C["muted"])

        def key(text, on_click, w=60, bg=None, fg=None):
            return ft.Container(
                content=ft.Text(text, size=18, weight=ft.FontWeight.W_600, color=fg or C["text"]),
                width=w,
                height=48,
                border_radius=12,
                bgcolor=bg or C["chip"],
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=on_click,
            )

        def make_chip_row(values, labels, get, on_pick, w=64):
            chips = {}

            def refresh():
                for v, c in chips.items():
                    active = v == get()
                    c.bgcolor = C["accent"] if active else C["chip"]
                    c.content.color = WHITE if active else C["muted"]

            for v in values:
                kw = {"width": w} if w else {"expand": True}
                chips[v] = ft.Container(
                    content=ft.Text(labels[v], size=13, weight=ft.FontWeight.BOLD, color=C["muted"]),
                    height=38,
                    border_radius=12,
                    bgcolor=C["chip"],
                    alignment=ft.Alignment(0, 0),
                    ink=True,
                    on_click=lambda e, v=v: on_pick(v),
                    **kw,
                )
            refresh()
            row = ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                spacing=8,
                controls=list(chips.values()),
            )
            return row, refresh

        def big_button(icon, text, on_click, bg=None, expand=False):
            return ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, color=WHITE if bg else C["text"], size=18),
                     ft.Text(text, color=WHITE if bg else C["text"], size=14,
                             weight=ft.FontWeight.W_600)],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                height=46,
                border_radius=14,
                bgcolor=bg or C["chip"],
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=on_click,
                expand=expand,
            )

        def make_copy_button(get_text, before=None):
            label_t = ft.Text("Копировать", color=WHITE, size=14, weight=ft.FontWeight.W_600)

            async def click(e):
                t = get_text()
                if not t:
                    return
                if before:
                    before()
                ok = await set_clipboard(page, t)
                label_t.value = "Скопировано ✓" if ok else "Не вышло, выдели текст"
                page.update()
                await asyncio.sleep(1.5)
                label_t.value = "Копировать"
                page.update()

            return ft.Container(
                content=ft.Row(
                    [ft.Icon(ft.Icons.COPY, color=WHITE, size=18), label_t],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                height=46,
                border_radius=14,
                bgcolor=C["accent"],
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=click,
                expand=True,
            )

        # ---------- шапка ----------
        def toggle_theme(e):
            state["theme"] = "light" if state["theme"] == "dark" else "dark"
            rebuild()

        header = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text("Системы счисления", size=24, weight=ft.FontWeight.BOLD, color=C["text"]),
                ft.IconButton(
                    icon=ft.Icons.LIGHT_MODE if state["theme"] == "dark" else ft.Icons.DARK_MODE,
                    icon_color=C["text"],
                    on_click=toggle_theme,
                ),
            ],
        )

        # ---------- переключатель режимов ----------
        def set_mode(key):
            state["mode"] = key
            rebuild()

        def seg(text, key):
            active = state["mode"] == key
            return ft.Container(
                content=ft.Text(text, color=WHITE if active else C["muted"],
                                weight=ft.FontWeight.BOLD, size=12),
                expand=True,
                height=42,
                border_radius=12,
                bgcolor=C["accent"] if active else C["chip"],
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=lambda e, k=key: set_mode(k),
            )

        mode_row = ft.Row(
            spacing=6,
            controls=[seg("Числа", "num"), seg("Текст", "text"),
                      seg("Доп. код", "twos"), seg("Тренажёр", "train")],
        )

        # =============================================================
        #  РЕЖИМ «ЧИСЛА»
        # =============================================================
        def build_num():
            # --- поле ввода ---
            inp = ft.TextField(
                label="Число или выражение",
                hint_text="255   или   1011 + 110",
                value=state["num_text"],
                text_size=24,
                filled=True,
                bgcolor=C["card"],
                color=C["text"],
                border_radius=16,
                border_color=C["chip"],
                focused_border_color=C["accent"],
                read_only=is_mobile,
                on_change=lambda e: convert_num(),
            )
            ui["inp"] = inp
            ui["err"] = ft.Text("", color=C["err"], size=14)

            # --- выбор систем ---
            def make_selector(side, title):
                value_text = ft.Text(str(state[side]), size=30, weight=ft.FontWeight.BOLD, color=C["text"])

                def set_base(b):
                    state[side] = max(2, min(36, b))
                    refresh()
                    if side == "from":
                        ui["digits_row"].controls = digit_keys()
                    convert_num()

                row, refresh_chips = make_chip_row(
                    QUICK_BASES, BASE_NAMES, lambda: state[side], set_base
                )

                def refresh():
                    value_text.value = str(state[side])
                    refresh_chips()

                refreshers[side] = refresh

                return card(
                    ft.Column(
                        spacing=10,
                        controls=[
                            label(title),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.IconButton(icon=ft.Icons.REMOVE, icon_color=C["text"],
                                                  on_click=lambda e: set_base(state[side] - 1)),
                                    value_text,
                                    ft.IconButton(icon=ft.Icons.ADD, icon_color=C["text"],
                                                  on_click=lambda e: set_base(state[side] + 1)),
                                ],
                            ),
                            row,
                        ],
                    )
                )

            from_card = make_selector("from", "Из системы (2–36)")
            to_card = make_selector("to", "В систему (2–36)")

            def swap(e):
                state["from"], state["to"] = state["to"], state["from"]
                if state["last_val"] is not None:
                    txt, _ = format_number(state["last_val"], state["from"])
                    ui["inp"].value = txt
                for r in refreshers.values():
                    r()
                ui["digits_row"].controls = digit_keys()
                convert_num()

            swap_btn = big_button(ft.Icons.SWAP_VERT, "Поменять местами", swap)

            # --- история ---
            def add_history():
                text = (ui["inp"].value or "").strip()
                if not state["result"] or not text:
                    return
                item = {"in": text, "from": state["from"], "to": state["to"], "out": state["result"]}
                if history and history[0] == item:
                    return
                history.insert(0, item)
                del history[30:]
                save_history(history)
                refresh_history()

            def restore(item):
                state["from"] = item["from"]
                state["to"] = item["to"]
                ui["inp"].value = item["in"]
                for r in refreshers.values():
                    r()
                ui["digits_row"].controls = digit_keys()
                convert_num()

            def clear_history(e):
                history.clear()
                save_history(history)
                refresh_history()
                page.update()

            def refresh_history():
                col = ui["hist_col"]
                if not history:
                    col.controls = [ft.Text("Пока пусто", size=13, color=C["muted"])]
                    return
                col.controls = [
                    ft.Container(
                        content=ft.Text(
                            f"{it['in']} ({it['from']})  →  {it['out']} ({it['to']})",
                            size=13, color=C["text"],
                        ),
                        bgcolor=C["chip"],
                        border_radius=12,
                        padding=10,
                        ink=True,
                        on_click=lambda e, it=it: restore(it),
                    )
                    for it in history[:10]
                ]

            ui["hist_col"] = ft.Column(spacing=8)
            history_card = card(
                ft.Column(
                    spacing=10,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                label("История (нажми, чтобы вернуть)"),
                                ft.Container(
                                    content=ft.Text("Очистить", size=13, color=C["accent"],
                                                    weight=ft.FontWeight.BOLD),
                                    ink=True,
                                    padding=4,
                                    on_click=clear_history,
                                ),
                            ],
                        ),
                        ui["hist_col"],
                    ],
                )
            )
            refresh_history()

            # --- клавиатура ---
            def press(ch):
                ui["inp"].value = (ui["inp"].value or "") + ch
                convert_num()

            def backspace(e):
                ui["inp"].value = (ui["inp"].value or "")[:-1]
                convert_num()

            def clear(e):
                ui["inp"].value = ""
                convert_num()

            def equals(e):
                if state["last_val"] is None:
                    return
                add_history()
                txt, _ = format_number(state["last_val"], state["from"])
                ui["inp"].value = txt
                convert_num()

            def digit_keys():
                return [
                    key(DIGITS[i].upper(), lambda e, ch=DIGITS[i].upper(): press(ch))
                    for i in range(state["from"])
                ]

            ops_row = ft.Row(
                wrap=True, spacing=6, run_spacing=6,
                controls=[
                    key(sym, lambda e, s=sym: press(s), w=42, fg=C["accent"])
                    for sym in ("+", "−", "×", "÷", "(", ")")
                ],
            )
            ui["digits_row"] = ft.Row(wrap=True, spacing=8, run_spacing=8, controls=digit_keys())
            ctrl_row = ft.Row(
                wrap=True, spacing=8, run_spacing=8,
                controls=[
                    key(".", lambda e: press(".")),
                    key("⌫", backspace),
                    key("C", clear, fg=C["err"]),
                    key("=", equals, bg=C["accent"], fg=WHITE),
                ],
            )
            keypad_card = card(
                ft.Column(spacing=10, controls=[label("Клавиатура"), ops_row, ui["digits_row"], ctrl_row])
            )

            # --- результат ---
            ui["result"] = ft.Text("—", size=34, weight=ft.FontWeight.BOLD,
                                   color=C["accent"], selectable=True)

            def toggle_steps(e):
                state["steps"] = not state["steps"]
                ui["steps_label"].value = "Скрыть шаги" if state["steps"] else "Показать шаги"
                ui["steps_card"].visible = state["steps"]
                convert_num()

            ui["steps_label"] = ft.Text(
                "Скрыть шаги" if state["steps"] else "Показать шаги",
                color=C["text"], size=14, weight=ft.FontWeight.W_600,
            )
            steps_btn = ft.Container(
                content=ft.Row(
                    [ft.Icon(ft.Icons.LIST, color=C["text"], size=18), ui["steps_label"]],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                height=46,
                border_radius=14,
                bgcolor=C["chip"],
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=toggle_steps,
                expand=True,
            )

            result_card = card(
                ft.Column(
                    spacing=12,
                    controls=[
                        label("Результат"),
                        ui["result"],
                        ft.Row(spacing=8, controls=[
                            make_copy_button(lambda: state["result"], before=lambda: (add_history())),
                            steps_btn,
                        ]),
                    ],
                )
            )

            # --- шаги ---
            ui["steps_col"] = ft.Column(spacing=6)
            ui["steps_card"] = card(
                ft.Column(spacing=10, controls=[label("Как получился результат"), ui["steps_col"]])
            )
            ui["steps_card"].visible = state["steps"]

            # --- все системы ---
            ui["all_vals"] = {
                b: ft.Text("—", size=16, color=C["text"], selectable=True) for b in QUICK_BASES
            }
            all_rows = [
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Text(BASE_NAMES[b], size=13, color=C["muted"], weight=ft.FontWeight.BOLD),
                        ft.Container(content=ui["all_vals"][b], expand=True,
                                     alignment=ft.Alignment(1, 0)),
                    ],
                )
                for b in QUICK_BASES
            ]
            all_card = card(
                ft.Column(spacing=10, controls=[label("Во всех популярных системах")] + all_rows)
            )

            return [
                from_card, to_card, swap_btn,
                inp, ui["err"],
                result_card,
                keypad_card,
                ui["steps_card"],
                all_card,
                history_card,
            ]

        # =============================================================
        #  РЕЖИМ «ТЕКСТ ↔ КОД»
        # =============================================================
        def build_text():
            def set_dir(v):
                state["tdir"] = v
                refresh_dir()
                ui["tinp"].label = "Текст" if v == "to_code" else "Код"
                ui["tinp"].hint_text = (
                    "Привет, мир!" if v == "to_code" else "01001000 01101001"
                )
                convert_text()

            def set_tbase(v):
                state["tbase"] = v
                refresh_tbase()
                convert_text()

            dir_row, refresh_dir = make_chip_row(
                ("to_code", "to_text"),
                {"to_code": "Текст → код", "to_text": "Код → текст"},
                lambda: state["tdir"], set_dir, w=None,
            )
            base_row, refresh_tbase = make_chip_row(
                QUICK_BASES, BASE_NAMES, lambda: state["tbase"], set_tbase,
            )

            to_code = state["tdir"] == "to_code"
            tinp = ft.TextField(
                label="Текст" if to_code else "Код",
                hint_text="Привет, мир!" if to_code else "01001000 01101001",
                value=state["txt_text"],
                multiline=True,
                min_lines=3,
                max_lines=8,
                text_size=20,
                filled=True,
                bgcolor=C["card"],
                color=C["text"],
                border_radius=16,
                border_color=C["chip"],
                focused_border_color=C["accent"],
                on_change=lambda e: convert_text(),
            )
            ui["tinp"] = tinp
            ui["terr"] = ft.Text("", color=C["err"], size=14)
            ui["tout"] = ft.Text("—", size=20, weight=ft.FontWeight.BOLD,
                                 color=C["accent"], selectable=True)

            def tswap(e):
                out = state["tresult"]
                if out:
                    ui["tinp"].value = out
                    state["tdir"] = "to_text" if state["tdir"] == "to_code" else "to_code"
                    refresh_dir()
                    ui["tinp"].label = "Текст" if state["tdir"] == "to_code" else "Код"
                    convert_text()

            out_card = card(
                ft.Column(
                    spacing=12,
                    controls=[
                        label("Результат"),
                        ui["tout"],
                        make_copy_button(lambda: state["tresult"]),
                    ],
                )
            )
            info = ft.Text(
                "Текст кодируется в UTF-8: латинские буквы занимают 1 байт, русские 2. "
                "Код можно писать через пробел или слитно.",
                size=12, color=C["muted"],
            )
            return [
                card(ft.Column(spacing=10, controls=[label("Направление"), dir_row,
                                                      label("Система кода"), base_row])),
                tinp, ui["terr"],
                out_card,
                big_button(ft.Icons.SWAP_VERT, "Поменять местами", tswap),
                info,
            ]

        # =============================================================
        #  РЕЖИМ «ДОПОЛНИТЕЛЬНЫЙ КОД»
        # =============================================================
        def build_twos():
            def range_text():
                lo, hi = twos_range(state["cbits"])
                return f"Для {state['cbits']} бит можно от {lo} до {hi}"

            def set_labels():
                to_code = state["cdir"] == "to_code"
                ui["cinp"].label = "Число (десятичное)" if to_code else "Двоичный код"
                ui["cinp"].hint_text = "-5" if to_code else "11111011"

            def set_cdir(v):
                state["cdir"] = v
                refresh_cdir()
                set_labels()
                convert_twos()

            def set_cbits(v):
                state["cbits"] = v
                refresh_cbits()
                ui["crange"].value = range_text()
                convert_twos()

            dir_row, refresh_cdir = make_chip_row(
                ("to_code", "to_num"),
                {"to_code": "Число → код", "to_num": "Код → число"},
                lambda: state["cdir"], set_cdir, w=None,
            )
            bits_row, refresh_cbits = make_chip_row(
                (4, 8, 16, 32),
                {4: "4 бит", 8: "8 бит", 16: "16 бит", 32: "32 бит"},
                lambda: state["cbits"], set_cbits,
            )

            to_code = state["cdir"] == "to_code"
            cinp = ft.TextField(
                label="Число (десятичное)" if to_code else "Двоичный код",
                hint_text="-5" if to_code else "11111011",
                value=state["c_text"],
                text_size=22,
                filled=True,
                bgcolor=C["card"],
                color=C["text"],
                border_radius=16,
                border_color=C["chip"],
                focused_border_color=C["accent"],
                on_change=lambda e: convert_twos(),
            )
            ui["cinp"] = cinp
            ui["crange"] = ft.Text(range_text(), size=12, color=C["muted"])
            ui["cerr"] = ft.Text("", color=C["err"], size=14)
            ui["cout"] = ft.Text("—", size=26, weight=ft.FontWeight.BOLD,
                                 color=C["accent"], selectable=True)
            ui["chex"] = ft.Text("", size=14, color=C["muted"], selectable=True)
            ui["csteps_col"] = ft.Column(spacing=6)

            def cswap(e):
                raw = state["craw"]
                if not raw:
                    return
                ui["cinp"].value = raw
                state["cdir"] = "to_num" if state["cdir"] == "to_code" else "to_code"
                refresh_cdir()
                set_labels()
                convert_twos()

            out_card = card(
                ft.Column(
                    spacing=10,
                    controls=[
                        label("Результат"),
                        ui["cout"],
                        ui["chex"],
                        make_copy_button(lambda: state["cresult"]),
                    ],
                )
            )
            steps_card = card(ft.Column(spacing=10, controls=[label("Как получилось"), ui["csteps_col"]]))
            info = ft.Text(
                "Дополнительный код это способ, которым компьютер хранит отрицательные числа. "
                "Если первая цифра кода 1, число отрицательное.",
                size=12, color=C["muted"],
            )
            return [
                card(ft.Column(spacing=10, controls=[label("Направление"), dir_row,
                                                      label("Размер числа"), bits_row,
                                                      ui["crange"]])),
                cinp, ui["cerr"],
                out_card,
                steps_card,
                big_button(ft.Icons.SWAP_VERT, "Поменять местами", cswap),
                info,
            ]

        # =============================================================
        #  РЕЖИМ «ТРЕНАЖЁР»
        # =============================================================
        def build_trainer():
            if state["tr_value"] is None:
                new_question()

            def set_level(v):
                state["tr_level"] = v
                refresh_lvl()
                new_question()
                ui["tr_inp"].value = ""
                ui["col_inp"].value = ""
                refresh_trainer()

            lvl_row, refresh_lvl = make_chip_row(
                ("easy", "medium", "hard"),
                {"easy": "Лёгкий", "medium": "Средний", "hard": "Сложный"},
                lambda: state["tr_level"], set_level, w=None,
            )

            ui["tr_q"] = ft.Text("", size=40, weight=ft.FontWeight.BOLD,
                                 color=C["accent"], selectable=True)
            ui["tr_sub"] = ft.Text("", size=14, color=C["muted"])
            ui["tr_stats"] = ft.Text("", size=13, color=C["muted"])
            ui["tr_inp"] = ft.TextField(
                label="Твой ответ",
                text_size=24,
                filled=True,
                bgcolor=C["card"],
                color=C["text"],
                border_radius=16,
                border_color=C["chip"],
                focused_border_color=C["accent"],
                read_only=is_mobile,
                autofocus=not is_mobile,
                on_submit=lambda e: tr_check(),
            )
            ui["tr_fb"] = ft.Text("", size=16, weight=ft.FontWeight.BOLD, color=C["ok"])
            ui["tr_btn_label"] = ft.Text("Проверить", color=WHITE, size=14,
                                         weight=ft.FontWeight.W_600)
            ui["tr_digits"] = ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[])
            ui["tr_steps_col"] = ft.Column(spacing=6)

            def make_digits():
                return [
                    key(DIGITS[i].upper(), lambda e, ch=DIGITS[i].upper(): tr_press(ch))
                    for i in range(digit_count())
                ]

            ui["tr_make_digits"] = make_digits

            check_btn = ft.Container(
                content=ft.Row([ui["tr_btn_label"]], alignment=ft.MainAxisAlignment.CENTER),
                height=46,
                border_radius=14,
                bgcolor=C["accent"],
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=lambda e: tr_check(),
                expand=True,
            )
            hint_btn = big_button(ft.Icons.HELP_OUTLINE, "Подсказка", lambda e: tr_hint(), expand=True)

            question_card = card(
                ft.Column(
                    spacing=6,
                    controls=[ui["tr_sub"], ui["tr_q"], ui["tr_stats"]],
                )
            )

            # --- столбик ---
            ui["col_btn"] = big_button(ft.Icons.LIST, "Решить в столбик", lambda e: col_start())
            ui["col_btn"].visible = False
            ui["col_log"] = ft.Column(spacing=4)
            ui["col_prompt"] = ft.Text("", size=16, weight=ft.FontWeight.BOLD, color=C["text"])
            ui["col_msg"] = ft.Text("", size=13, color=C["err"])
            ui["col_inp"] = ft.TextField(
                label="Частное",
                text_size=22,
                filled=True,
                bgcolor=C["chip"],
                color=C["text"],
                border_radius=14,
                border_color=C["chip"],
                focused_border_color=C["accent"],
                read_only=is_mobile,
                on_submit=lambda e: col_submit(),
            )
            ui["col_ok"] = ft.Container(
                content=ft.Row(
                    [ft.Text("Ок", color=WHITE, size=14, weight=ft.FontWeight.W_600)],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                height=44,
                border_radius=14,
                bgcolor=C["accent"],
                alignment=ft.Alignment(0, 0),
                ink=True,
                on_click=lambda e: col_submit(),
            )
            ui["col_card"] = card(
                ft.Column(
                    spacing=10,
                    controls=[
                        label("Решение в столбик (делим на основание)"),
                        ui["col_log"],
                        ui["col_prompt"],
                        ui["col_inp"],
                        ui["col_msg"],
                        ui["col_ok"],
                    ],
                )
            )
            ui["col_card"].visible = False
            keypad_card = card(
                ft.Column(
                    spacing=10,
                    controls=[
                        label("Клавиатура"),
                        ui["tr_digits"],
                        ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[
                            key("⌫", lambda e: tr_back()),
                            key("C", lambda e: tr_clear(), fg=C["err"]),
                        ]),
                    ],
                )
            )
            ui["tr_steps_card"] = card(
                ft.Column(spacing=10, controls=[label("Как решать"), ui["tr_steps_col"]])
            )
            ui["tr_steps_card"].visible = False

            return [
                card(ft.Column(spacing=10, controls=[label("Сложность"), lvl_row])),
                question_card,
                ui["tr_inp"],
                ui["tr_fb"],
                ft.Row(spacing=8, controls=[check_btn, hint_btn]),
                ui["col_btn"],
                ui["col_card"],
                keypad_card,
                ui["tr_steps_card"],
            ]

        builders = {"num": build_num, "text": build_text, "twos": build_twos, "train": build_trainer}
        body = builders[state["mode"]]()
        return ft.SafeArea(
            ft.Column(spacing=14, controls=[header, mode_row] + body)
        )

    # -----------------------------------------------------------------
    #  Пересчёт
    # -----------------------------------------------------------------
    def fill_steps(lines, key="steps_col"):
        C = ui["C"]
        if not lines:
            lines = ["Введи число, и здесь появятся шаги."]
        controls = []
        for ln in lines:
            head = ln.startswith(("Шаг", "Значение", "Ответ"))
            controls.append(
                ft.Text(
                    ln, size=13, selectable=True,
                    color=C["accent"] if head else C["text"],
                    weight=ft.FontWeight.BOLD if head else ft.FontWeight.NORMAL,
                )
            )
        ui[key].controls = controls

    def convert_num():
        text = ui["inp"].value or ""
        state["num_text"] = text

        def reset(msg=""):
            ui["err"].value = msg
            ui["result"].value = "—"
            state["result"] = ""
            state["last_val"] = None
            for t in ui["all_vals"].values():
                t.value = "—"
            if state["steps"]:
                fill_steps([])
            page.update()

        try:
            val, is_expr = evaluate(text, state["from"])
        except Incomplete:
            reset()
            return
        except ValueError as ex:
            reset(str(ex))
            return

        if val is None:
            reset()
            return

        ui["err"].value = ""
        res, approx = format_number(val, state["to"])
        ui["result"].value = ("≈ " if approx else "") + res
        state["result"] = res
        state["last_val"] = val
        for b, t in ui["all_vals"].items():
            r, a = format_number(val, b)
            t.value = ("≈ " if a else "") + r
        if state["steps"]:
            fill_steps(explain(text, val, is_expr, state["from"], state["to"]))
        page.update()

    def convert_text():
        s = ui["tinp"].value or ""
        state["txt_text"] = s
        out = ""
        ui["terr"].value = ""
        try:
            if state["tdir"] == "to_code":
                out = text_to_code(s, state["tbase"])
            else:
                out = code_to_text(s, state["tbase"])
        except Incomplete:
            out = ""
        except ValueError as ex:
            out = ""
            ui["terr"].value = str(ex)
        state["tresult"] = out
        ui["tout"].value = out if out else "—"
        page.update()

    def convert_twos():
        C = ui["C"]
        s = ui["cinp"].value or ""
        state["c_text"] = s
        bits = state["cbits"]
        ui["cerr"].value = ""
        ui["cerr"].color = C["err"]
        out = ""
        raw = ""
        hexs = ""
        lines = []
        try:
            if state["cdir"] == "to_code":
                code, lines = twos_encode(s, bits)
                out = group4(code)
                raw = code
                hexs = "HEX: " + format(int(code, 2), f"0{max(bits // 4, 1)}X")
            else:
                n, lines = twos_decode(s, bits)
                out = str(n)
                raw = str(n)
        except Incomplete as ex:
            if s.strip():
                ui["cerr"].value = str(ex)
                ui["cerr"].color = C["muted"]
        except ValueError as ex:
            ui["cerr"].value = str(ex)
        state["cresult"] = out
        state["craw"] = raw
        ui["cout"].value = out if out else "—"
        ui["chex"].value = hexs
        fill_steps(lines or ["Введи число, и здесь появятся шаги."], "csteps_col")
        page.update()

    # ---------- тренажёр ----------
    def new_question():
        lvl = state["tr_level"]
        if lvl == "easy":
            pairs = [(10, 2), (2, 10)]
            mx = 31
        elif lvl == "medium":
            pairs = [(10, 2), (2, 10), (10, 8), (8, 10), (10, 16), (16, 10)]
            mx = 255
        else:
            bases = (2, 8, 10, 16)
            pairs = [(a, b) for a in bases for b in bases if a != b]
            mx = 1023
        fb, tb = random.choice(pairs)
        state["tr_from"] = fb
        state["tr_to"] = tb
        state["tr_value"] = random.randint(2, mx)
        state["tr_answered"] = False
        state["tr_hint"] = False
        state["tr_feedback"] = ""
        state["tr_ok"] = False
        state["col_on"] = False
        state["col_rows"] = []
        state["col_done"] = False
        state["col_msg"] = ""

    def refresh_trainer():
        C = ui["C"]
        fb, tb = state["tr_from"], state["tr_to"]
        val = Fraction(state["tr_value"])
        q_text, _ = format_number(val, fb)
        ui["tr_q"].value = q_text
        ui["tr_sub"].value = f"Переведи из {BASE_NAMES[fb]} ({fb}) в {BASE_NAMES[tb]} ({tb})"
        ui["tr_digits"].controls = ui["tr_make_digits"]()
        ui["tr_stats"].value = (
            f"Серия: {state['tr_streak']}   Рекорд: {state['tr_best']}   "
            f"Верно: {state['tr_correct']} из {state['tr_total']}"
        )
        ui["tr_fb"].value = state["tr_feedback"]
        ui["tr_fb"].color = C["ok"] if state["tr_ok"] else C["err"]
        ui["tr_btn_label"].value = "Дальше" if state["tr_answered"] else "Проверить"
        applicable = fb == 10 and tb != 10
        ui["col_btn"].visible = applicable and not state["tr_answered"] and not state["col_on"]
        ui["col_card"].visible = state["col_on"] and applicable
        if state["col_on"]:
            rows = []
            for cur, q, r in state["col_rows"]:
                rs = str(r) if r < 10 else f"{r} ({DIGITS[r].upper()})"
                rows.append(ft.Text(f"{cur} ÷ {tb} = {q}, остаток {rs}", size=14, color=C["text"]))
            ui["col_log"].controls = rows
            done = state["col_done"]
            ui["col_inp"].visible = not done
            ui["col_ok"].visible = not done
            if done:
                ui["col_prompt"].value = "Готово: остатки читаем снизу вверх"
            elif state["col_phase"] == "q":
                ui["col_prompt"].value = f"{state['col_cur']} ÷ {tb} = ?  (сколько целых, это частное)"
                ui["col_inp"].label = "Частное"
            else:
                ui["col_prompt"].value = f"Остаток: {state['col_cur']} − {state['col_q']} × {tb} = ?"
                ui["col_inp"].label = "Остаток"
            ui["col_msg"].value = state["col_msg"]
            ui["col_msg"].color = C["ok"] if done else C["err"]

        show_steps = state["tr_hint"] or (state["tr_answered"] and not state["tr_ok"])
        ui["tr_steps_card"].visible = show_steps
        if show_steps:
            fill_steps(explain(q_text, val, False, fb, tb), "tr_steps_col")
        page.update()

    def tr_next():
        new_question()
        ui["tr_inp"].value = ""
        ui["col_inp"].value = ""
        refresh_trainer()

    def tr_check():
        if state["tr_answered"]:
            tr_next()
            return
        ans = (ui["tr_inp"].value or "").strip()
        if not ans:
            return
        try:
            v = parse_number(ans, state["tr_to"])
        except Incomplete:
            return
        except ValueError as ex:
            state["tr_feedback"] = str(ex)
            state["tr_ok"] = False
            refresh_trainer()
            return

        expected = Fraction(state["tr_value"])
        right, _ = format_number(expected, state["tr_to"])
        ok = v == expected
        state["tr_answered"] = True
        state["tr_ok"] = ok
        if state["tr_hint"]:
            state["tr_feedback"] = (
                "Верно! Но с подсказкой очко не засчитывается."
                if ok else f"Неверно. Правильный ответ: {right}"
            )
        else:
            state["tr_total"] += 1
            if ok:
                state["tr_correct"] += 1
                state["tr_streak"] += 1
                state["tr_best"] = max(state["tr_best"], state["tr_streak"])
                state["tr_feedback"] = "Верно! ✓"
            else:
                state["tr_streak"] = 0
                state["tr_feedback"] = f"Неверно. Правильный ответ: {right}"
            save_json("trainer.json", {
                "best": state["tr_best"],
                "correct": state["tr_correct"],
                "total": state["tr_total"],
            })
        refresh_trainer()

    def tr_hint():
        if state["tr_answered"]:
            return
        state["tr_hint"] = True
        refresh_trainer()

    def digit_count():
        if state["col_on"] and not state["col_done"] and not state["tr_answered"]:
            return max(10, state["tr_to"])
        return state["tr_to"]

    def tr_target():
        if state["col_on"] and not state["col_done"]:
            return ui["col_inp"]
        return ui["tr_inp"]

    def tr_press(ch):
        if state["tr_answered"]:
            return
        t = tr_target()
        t.value = (t.value or "") + ch
        page.update()

    def tr_back():
        if state["tr_answered"]:
            return
        t = tr_target()
        t.value = (t.value or "")[:-1]
        page.update()

    def tr_clear():
        if state["tr_answered"]:
            return
        tr_target().value = ""
        page.update()

    def col_start():
        if state["tr_answered"] or state["tr_from"] != 10 or state["tr_to"] == 10:
            return
        state["col_on"] = True
        state["col_cur"] = int(state["tr_value"])
        state["col_phase"] = "q"
        state["col_q"] = 0
        state["col_rows"] = []
        state["col_done"] = False
        state["col_msg"] = ""
        ui["col_inp"].value = ""
        refresh_trainer()

    def col_submit():
        if not state["col_on"] or state["col_done"] or state["tr_answered"]:
            return
        s = (ui["col_inp"].value or "").strip()
        if not s:
            return
        b = state["tr_to"]
        cur = state["col_cur"]
        if state["col_phase"] == "q":
            if not s.isdigit():
                state["col_msg"] = "Частное это целое число, например 14"
            elif int(s) != cur // b:
                state["col_msg"] = f"Не то. Сколько раз {b} целиком помещается в {cur}?"
            else:
                state["col_q"] = int(s)
                state["col_phase"] = "r"
                state["col_msg"] = ""
                ui["col_inp"].value = ""
        else:
            rem = cur % b
            ok = (s.isdigit() and int(s) == rem) or (len(s) == 1 and DIGITS.find(s.lower()) == rem)
            if not ok:
                state["col_msg"] = f"Не то. Остаток = {cur} − {state['col_q']} × {b}"
            else:
                state["col_rows"].append((cur, state["col_q"], rem))
                state["col_cur"] = state["col_q"]
                state["col_phase"] = "q"
                state["col_msg"] = ""
                ui["col_inp"].value = ""
                if state["col_q"] == 0:
                    state["col_done"] = True
                    digits = "".join(DIGITS[r].upper() for _, _, r in reversed(state["col_rows"]))
                    ui["tr_inp"].value = digits
                    state["col_msg"] = "Ответ уже в поле выше, нажми «Проверить»."
        refresh_trainer()

    def rebuild():
        try:
            page.clean()
        except Exception:
            page.controls.clear()
        page.add(build())
        refreshers_by_mode = {
            "num": convert_num,
            "text": convert_text,
            "twos": convert_twos,
            "train": refresh_trainer,
        }
        refreshers_by_mode[state["mode"]]()

    rebuild()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
