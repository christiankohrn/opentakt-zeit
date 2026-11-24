from __future__ import annotations

from datetime import date
from pathlib import Path

from fpdf import FPDF

from app.auth import as_local, now_utc
from app.branding import PRODUCT_NAME

FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
NAVY = (0, 34, 70)
MUTED = (90, 107, 125)
ROW_ALT = (242, 245, 249)
LINE = (213, 222, 234)


def de_date(value: date | str) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d.%m.%Y")


def de_hm(value: float, digits: int = 1, signed: bool = False) -> str:
    from app.balance import format_hm

    return format_hm(value, signed=signed)


def de_num(value: float, digits: int = 1, signed: bool = False) -> str:
    text = f"{value:.{digits}f}".replace(".", ",")
    if signed and value > 0:
        return f"+{text}"
    return text


def de_days(value: float | int | None, signed: bool = False) -> str:
    if value is None:
        return "-"
    number = float(value)
    if abs(number - round(number)) < 0.05:
        text = str(int(round(number)))
    else:
        text = f"{number:.1f}".replace(".", ",")
    if signed and number > 0:
        return f"+{text}"
    return text


def _font_pair() -> tuple[Path, Path] | None:
    if FONT_REGULAR.is_file() and FONT_BOLD.is_file():
        return FONT_REGULAR, FONT_BOLD
    return None


class ReportPDF(FPDF):
    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        org: str,
        landscape: bool = False,
        note: str = "",
        compact: bool = False,
    ):
        super().__init__(orientation="L" if landscape else "P", format="A4")
        self.report_title = title
        self.report_subtitle = subtitle
        self.org = org
        self.note = note
        self.compact = compact
        self.created = as_local(now_utc())
        if compact:
            self.set_margins(8, 10, 8)
            self.set_auto_page_break(auto=True, margin=10)
        else:
            self.set_margins(12, 18, 12)
            self.set_auto_page_break(auto=True, margin=16)
        fonts = _font_pair()
        if fonts:
            self.add_font("Report", "", str(fonts[0]))
            self.add_font("Report", "B", str(fonts[1]))
            self.font_name = "Report"
        else:
            self.font_name = "Helvetica"
        self.alias_nb_pages()
        self.add_page()

    def header(self):
        small = self.compact
        self.set_font(self.font_name, "", 7 if small else 9)
        self.set_text_color(*MUTED)
        generated = self.created.strftime("%d.%m.%Y %H:%M")
        self.cell(self.epw / 2, 4 if small else 5, self.org, align="L")
        self.cell(self.epw / 2, 4 if small else 5, generated, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*NAVY)
        self.set_font(self.font_name, "B", 11 if small else 14)
        self.cell(self.epw, 5 if small else 8, self.report_title, new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.font_name, "", 8 if small else 10)
        self.set_text_color(*MUTED)
        self.cell(self.epw, 4 if small else 5, self.report_subtitle, new_x="LMARGIN", new_y="NEXT")
        self.ln(1 if small else 2)

    def footer(self):
        if self.compact:
            self.set_y(-8)
            self.set_font(self.font_name, "", 6.5)
            self.set_text_color(*MUTED)
            self.cell(self.epw, 4, f"{PRODUCT_NAME}  ·  Seite {self.page_no()}/{{nb}}", align="C")
            return
        self.set_y(-12)
        self.set_font(self.font_name, "", 8)
        self.set_text_color(*MUTED)
        self.cell(self.epw, 6, f"{PRODUCT_NAME}  ·  Seite {self.page_no()}/{{nb}}", align="C")

    def _fit(self, text: str, width: float) -> str:
        if self.font_name != "Report":
            text = text.replace("\u2014", "-").replace("\u2013", "-")
        pad = 0.6 if self.compact else 1.4
        ellipsis = "..."
        if self.get_string_width(text) <= width - pad:
            return text
        while text and self.get_string_width(text + ellipsis) > width - pad:
            text = text[:-1]
        return text + ellipsis

    def _column_header(
        self,
        headers: list[str],
        widths: list[float],
        aligns: list[str],
        groups: list[tuple[str, int]] | None = None,
        height: float = 6.5,
        origin_x: float | None = None,
    ):
        start = self.l_margin if origin_x is None else origin_x
        self.set_x(start)
        self.set_font(self.font_name, "B", 6 if height <= 4.2 else 7)
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        self.set_draw_color(*NAVY)
        if groups:
            index = 0
            for title, span in groups:
                width = sum(widths[index : index + span])
                self.cell(width, height, self._fit(title, width), border=0, fill=True, align="C")
                index += span
            self.ln()
            self.set_x(start)
        for title, width, align in zip(headers, widths, aligns):
            self.cell(width, height, self._fit(title, width), border=0, fill=True, align=align)
        self.ln()
        self.set_x(start)

    def table(
        self,
        columns: list[tuple[str, float, str]],
        rows: list[list[str]],
        totals: list[str] | None = None,
        groups: list[tuple[str, int]] | None = None,
        note: str | None = None,
        row_height: float | None = None,
        allow_break: bool = True,
        compact: bool = False,
        emphasis: list[bool] | None = None,
        width: float | None = None,
        origin_x: float | None = None,
    ):
        row_h = 3.6 if compact else (6.2 if row_height is None else row_height)
        if row_height is not None and not compact:
            row_h = row_height
        head_h = 4.0 if compact else (6.5 if row_h >= 5.8 else max(5.0, row_h + 0.5))
        body_font = 6.5 if compact else (8 if row_h >= 5.2 else 7)
        usable = self.epw if width is None else width
        shares = [share for _, share, _ in columns]
        total = sum(shares) or 1.0
        widths = [usable * share / total for share in shares]
        aligns = [align for _, _, align in columns]
        headers = [title for title, _, _ in columns]
        start_x = self.l_margin if origin_x is None else origin_x
        self.set_x(start_x)
        self._column_header(headers, widths, aligns, groups, height=head_h, origin_x=start_x)
        self.set_draw_color(*LINE)
        strong_fill = (186, 208, 230)
        for index, row in enumerate(rows):
            if allow_break and self.will_page_break(row_h):
                self.add_page()
                self.set_x(start_x)
                self._column_header(headers, widths, aligns, groups, height=head_h, origin_x=start_x)
            strong = bool(emphasis and index < len(emphasis) and emphasis[index])
            fill = strong or index % 2 == 1
            self.set_x(start_x)
            self.set_font(self.font_name, "B" if strong else "", body_font)
            self.set_text_color(*NAVY)
            self.set_fill_color(*(strong_fill if strong else ROW_ALT if fill else (255, 255, 255)))
            for value, col_width, align in zip(row, widths, aligns):
                self.cell(col_width, row_h, self._fit(str(value), col_width), border="B", fill=True, align=align)
            self.ln()
            self.set_x(start_x)
        if totals:
            if allow_break and self.will_page_break(7):
                self.add_page()
                self._column_header(headers, widths, aligns, groups, height=head_h)
            self.set_font(self.font_name, "B", body_font)
            self.set_fill_color(*NAVY)
            self.set_text_color(255, 255, 255)
            for value, width, align in zip(totals, widths, aligns):
                self.cell(width, 7, self._fit(str(value), width), border=0, fill=True, align=align)
            self.ln()
        footer_note = self.note if note is None else note
        if footer_note:
            self.ln(2 if row_h < 5.8 else 3)
            self.set_font(self.font_name, "", 7 if row_h < 5.8 else 8)
            self.set_text_color(*MUTED)
            self.multi_cell(self.epw, 3.6 if row_h < 5.8 else 4, footer_note)

    def accounts_table(self, rows: list[list[str]], note: str = "", compact: bool = False):
        columns = [
            ("Salden", 0.28, "L"),
            ("Vormonat", 0.18, "R"),
            ("Aktuell", 0.18, "R"),
            ("Geplant", 0.18, "R"),
            ("Rest / Neu", 0.18, "R"),
        ]
        if not compact and self.will_page_break(6.5 * (2 + len(rows)) + 10):
            self.add_page()
        self.ln(2 if compact else 4)
        self.set_font(self.font_name, "B", 9 if compact else 10)
        self.set_text_color(*NAVY)
        self.cell(self.epw, 5 if compact else 6, "Konten", new_x="LMARGIN", new_y="NEXT")
        self.table(
            columns,
            rows,
            note=note,
            row_height=5.0 if compact else None,
            allow_break=not compact,
        )

    def journal_person(
        self,
        day_columns: list[tuple[str, float, str]],
        day_rows: list[list[str]],
        wage_rows: list[list[str]],
        account_rows: list[list[str]],
        note: str = "",
        emphasis: list[bool] | None = None,
    ):
        """Enges Hochformat: Stempelzeilen, Wochen- und Monatssumme hervorgehoben, Summen nebeneinander."""
        self.table(
            day_columns,
            day_rows,
            note="",
            allow_break=True,
            compact=True,
            emphasis=emphasis,
            groups=[
                ("", 1),
                ("Arbeitszeit", 3),
                ("", 1),
                ("Tag", 3),
                ("", 1),
                ("Lohnarten", 3),
                ("", 1),
            ],
        )
        self.ln(1.5)
        block_h = 28
        if self.will_page_break(block_h):
            self.add_page()
        gap = 3
        left_w = self.epw * 0.40
        right_w = self.epw - left_w - gap
        y = self.get_y()
        self.set_font(self.font_name, "B", 8)
        self.set_text_color(*NAVY)
        self.set_xy(self.l_margin, y)
        self.cell(left_w, 4, "Lohnarten")
        self.set_xy(self.l_margin + left_w + gap, y)
        self.cell(right_w, 4, "Konten")
        self.ln(4)
        top = self.get_y()
        self.table(
            [("Lohnart", 0.68, "L"), ("Stunden", 0.32, "R")],
            wage_rows,
            note="",
            compact=True,
            allow_break=False,
            width=left_w,
            origin_x=self.l_margin,
        )
        after_left = self.get_y()
        self.set_y(top)
        self.table(
            [
                ("Salden", 0.28, "L"),
                ("Vormonat", 0.18, "R"),
                ("Aktuell", 0.18, "R"),
                ("Geplant", 0.18, "R"),
                ("Rest / Neu", 0.18, "R"),
            ],
            account_rows,
            note="",
            compact=True,
            allow_break=False,
            width=right_w,
            origin_x=self.l_margin + left_w + gap,
        )
        self.set_y(max(self.get_y(), after_left))
        if note:
            self.ln(1)
            self.set_x(self.l_margin)
            self.set_font(self.font_name, "", 6.5)
            self.set_text_color(*MUTED)
            self.multi_cell(self.epw, 3.2, note)

    def bytes(self) -> bytes:
        return bytes(self.output())


def table_pdf(
    *,
    title: str,
    subtitle: str,
    org: str,
    columns: list[tuple[str, float, str]],
    rows: list[list[str]],
    totals: list[str] | None = None,
    landscape: bool = False,
    note: str = "",
    groups: list[tuple[str, int]] | None = None,
) -> bytes:
    pdf = ReportPDF(title=title, subtitle=subtitle, org=org, landscape=landscape, note=note)
    pdf.table(columns, rows, totals, groups=groups)
    return pdf.bytes()
