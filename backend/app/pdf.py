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
    ):
        super().__init__(orientation="L" if landscape else "P", format="A4")
        self.report_title = title
        self.report_subtitle = subtitle
        self.org = org
        self.note = note
        self.created = as_local(now_utc())
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
        self.set_font(self.font_name, "", 9)
        self.set_text_color(*MUTED)
        generated = self.created.strftime("%d.%m.%Y %H:%M")
        self.cell(self.epw / 2, 5, self.org, align="L")
        self.cell(self.epw / 2, 5, generated, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*NAVY)
        self.set_font(self.font_name, "B", 14)
        self.cell(self.epw, 8, self.report_title, new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.font_name, "", 10)
        self.set_text_color(*MUTED)
        self.cell(self.epw, 5, self.report_subtitle, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font(self.font_name, "", 8)
        self.set_text_color(*MUTED)
        self.cell(self.epw, 6, f"{PRODUCT_NAME}  ·  Seite {self.page_no()}/{{nb}}", align="C")

    def _fit(self, text: str, width: float) -> str:
        ellipsis = "..."
        if self.get_string_width(text) <= width - 1.4:
            return text
        while text and self.get_string_width(text + ellipsis) > width - 1.4:
            text = text[:-1]
        return text + ellipsis

    def _column_header(
        self,
        headers: list[str],
        widths: list[float],
        aligns: list[str],
        groups: list[tuple[str, int]] | None = None,
        height: float = 6.5,
    ):
        self.set_font(self.font_name, "B", 7)
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        self.set_draw_color(*NAVY)
        if groups:
            index = 0
            for title, span in groups:
                width = sum(widths[index : index + span])
                self.cell(width, 6, self._fit(title, width), border=0, fill=True, align="C")
                index += span
            self.ln()
        for title, width, align in zip(headers, widths, aligns):
            self.cell(width, height, self._fit(title, width), border=0, fill=True, align=align)
        self.ln()

    def table(
        self,
        columns: list[tuple[str, float, str]],
        rows: list[list[str]],
        totals: list[str] | None = None,
        groups: list[tuple[str, int]] | None = None,
        note: str | None = None,
        row_height: float | None = None,
        allow_break: bool = True,
    ):
        row_h = 6.2 if row_height is None else row_height
        head_h = 6.5 if row_h >= 5.8 else max(5.0, row_h + 0.5)
        body_font = 8 if row_h >= 5.2 else 7
        usable = self.epw
        widths = [max(10.0, usable * share) for _, share, _ in columns]
        widths[0] += usable - sum(widths)
        aligns = [align for _, _, align in columns]
        headers = [title for title, _, _ in columns]
        self._column_header(headers, widths, aligns, groups, height=head_h)
        self.set_draw_color(*LINE)
        for index, row in enumerate(rows):
            if allow_break and self.will_page_break(row_h):
                self.add_page()
                self._column_header(headers, widths, aligns, groups, height=head_h)
            fill = index % 2 == 1
            self.set_font(self.font_name, "", body_font)
            self.set_text_color(*NAVY)
            self.set_fill_color(*(ROW_ALT if fill else (255, 255, 255)))
            for value, width, align in zip(row, widths, aligns):
                self.cell(width, row_h, self._fit(str(value), width), border="B", fill=True, align=align)
            self.ln()
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
            ("Verplant", 0.18, "R"),
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
        account_rows: list[list[str]],
        note: str = "",
    ):
        """Pack the day table and Konten footer onto the current page."""
        n_day = max(len(day_rows), 1)
        n_acc = max(len(account_rows), 1)
        acc_row_h = 5.0
        day_head = 5.4
        acc_head = 5.4
        reserve = day_head + 2.0 + 5.0 + acc_head + n_acc * acc_row_h + (9.0 if note else 0.0) + 1.5
        avail = self.page_break_trigger - self.get_y() - reserve
        row_h = min(6.0, max(3.6, avail / n_day))
        self.table(day_columns, day_rows, note="", row_height=row_h, allow_break=False)
        self.accounts_table(account_rows, note=note, compact=True)

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
