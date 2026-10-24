"""Relatório mensal em Excel (.xlsx) e PDF, no formato da planilha de papel."""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import money

MIN_LINHAS = 15  # como a folha de papel: completa com linhas em branco


def titulo(r: dict) -> str:
    return f"DESPESAS {r['mes']:02d}/{r['ano']}"


def nome_arquivo(r: dict, extensao: str) -> str:
    return f"despesas_{r['ano']}-{r['mes']:02d}.{extensao}"


def linhas_com_branco(r: dict) -> list:
    """Lançamentos + linhas em branco até MIN_LINHAS (None = linha em branco)."""
    linhas = list(r["linhas"])
    return linhas + [None] * max(0, MIN_LINHAS - len(linhas))


# ----------------------------------------------------------------------- Excel
def gerar_xlsx(r: dict, empresa: str = "") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"{r['mes']:02d}-{r['ano']}"
    cols = r["colunas"]
    ncol = 2 + len(cols)
    fino = Side(style="thin", color="000000")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)
    cinza = PatternFill("solid", fgColor="E8E8E8")
    fmt_valor = "#,##0.00"

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    ws["A1"] = titulo(r)
    ws["A1"].font = Font(bold=True, size=16)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
    ws["A2"] = empresa
    ws["A2"].alignment = Alignment(horizontal="center")
    ws["A2"].font = Font(size=10, italic=True)

    cab = 3
    for i, nome in enumerate(["DIA", "DESCRIÇÃO"] + [c["nome"].upper() for c in cols], start=1):
        c = ws.cell(row=cab, column=i, value=nome)
        c.font = Font(bold=True, size=10)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.fill = cinza
        c.border = borda
    ws.row_dimensions[cab].height = 24

    linhas = linhas_com_branco(r)
    primeira = cab + 1
    for i, l in enumerate(linhas):
        linha = primeira + i
        for col in range(1, ncol + 1):
            ws.cell(row=linha, column=col).border = borda
        if l is None:
            continue
        c = ws.cell(row=linha, column=1, value=l["dia"])
        c.number_format = "00"
        c.alignment = Alignment(horizontal="center")
        d = ws.cell(row=linha, column=2, value=l["descricao"])
        if str(l["descricao"]).startswith("="):
            d.data_type = "s"  # nunca interpretar texto do usuário como fórmula
        d.alignment = Alignment(wrap_text=True, vertical="top")
        idx = [c_["id"] for c_ in cols].index(l["categoria_id"])
        v = ws.cell(row=linha, column=3 + idx, value=round(l["valor"] / 100, 2))
        v.number_format = fmt_valor
    ultima = primeira + len(linhas) - 1

    tot = ultima + 1
    ws.cell(row=tot, column=1).border = borda
    t = ws.cell(row=tot, column=2, value="TOTAIS")
    t.font = Font(bold=True, size=12)
    t.alignment = Alignment(horizontal="center")
    t.border = borda
    for i in range(len(cols)):
        letra = get_column_letter(3 + i)
        c = ws.cell(row=tot, column=3 + i, value=f"=SUM({letra}{primeira}:{letra}{ultima})")
        c.number_format = fmt_valor
        c.font = Font(bold=True)
        c.border = borda
        c.fill = cinza

    geral = tot + 2
    g = ws.cell(row=geral, column=2, value="TOTAL GERAL")
    g.font = Font(bold=True, size=13)
    g.alignment = Alignment(horizontal="right")
    primeiro_letra, ultima_letra = get_column_letter(3), get_column_letter(ncol)
    v = ws.cell(row=geral, column=3, value=f"=SUM({primeiro_letra}{tot}:{ultima_letra}{tot})")
    v.number_format = fmt_valor
    v.font = Font(bold=True, size=13)
    v.border = Border(bottom=fino)

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 38
    for i in range(len(cols)):
        ws.column_dimensions[get_column_letter(3 + i)].width = 15

    ws.freeze_panes = ws.cell(row=primeira, column=1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{cab}:{cab}"
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
    ws.oddFooter.center.text = "Página &P de &N"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------------- PDF
def _canvas_numerado(rodape_esq: str):
    class NumeradoCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._paginas = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self.setFont("Helvetica", 8)
                self.setFillColor(colors.grey)
                largura, _ = self._pagesize
                self.drawString(12 * mm, 8 * mm, rodape_esq)
                self.drawRightString(largura - 12 * mm, 8 * mm, f"Página {self._pageNumber} de {total}")
                super().showPage()
            super().save()

    return NumeradoCanvas


def gerar_pdf(r: dict, empresa: str = "", usuario: str = "", gerado_em: str = "") -> bytes:
    cols = r["colunas"]
    n = len(cols)
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=15 * mm, title=titulo(r), author="Sistema de Despesas",
    )
    fonte = 9 if n <= 9 else 7.5
    est_cab = ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=fonte - 1.5, alignment=TA_CENTER,
                             leading=fonte)
    est_txt = ParagraphStyle("txt", fontName="Helvetica", fontSize=fonte, alignment=TA_LEFT, leading=fonte + 2)
    est_num = ParagraphStyle("num", fontName="Helvetica", fontSize=fonte, alignment=TA_RIGHT, leading=fonte + 2)
    est_tot = ParagraphStyle("tot", fontName="Helvetica-Bold", fontSize=fonte, alignment=TA_RIGHT,
                             leading=fonte + 2)
    est_titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=18, alignment=TA_CENTER, leading=22)
    est_emp = ParagraphStyle("emp", fontName="Helvetica-Oblique", fontSize=10, alignment=TA_CENTER, leading=12)

    cabecalho = [Paragraph("DIA", est_cab), Paragraph("DESCRIÇÃO", est_cab)]
    cabecalho += [Paragraph(escape(c["nome"].upper()), est_cab) for c in cols]
    dados = [cabecalho]
    for l in linhas_com_branco(r):
        if l is None:
            dados.append([""] * (2 + n))
            continue
        linha = [Paragraph(f"{l['dia']:02d}", ParagraphStyle("d", parent=est_txt, alignment=TA_CENTER)),
                 Paragraph(escape(l["descricao"]), est_txt)]
        for c in cols:
            linha.append(Paragraph(money.formatar(l["valor"]), est_num) if c["id"] == l["categoria_id"] else "")
        dados.append(linha)
    dados.append(["", Paragraph("<b>TOTAIS</b>", ParagraphStyle("t", parent=est_txt, alignment=TA_CENTER,
                                                                 fontSize=fonte + 2))]
                 + [Paragraph(money.formatar(r["totais"][c["id"]]), est_tot) for c in cols])
    linha_total = [""] * (2 + n)
    linha_total[1] = Paragraph("<b>TOTAL GERAL</b>", ParagraphStyle("tg", parent=est_txt, alignment=TA_RIGHT,
                                                                    fontSize=fonte + 3))
    linha_total[2] = Paragraph(money.formatar(r["total_geral"]),
                               ParagraphStyle("tgv", parent=est_tot, alignment=TA_LEFT, fontSize=fonte + 3))
    dados.append(linha_total)

    w_dia, w_desc = 11 * mm, 62 * mm
    w_cat = (doc.width - w_dia - w_desc) / max(n, 1)
    largura_cols = [w_dia, w_desc] + [w_cat] * n
    tabela = Table(dados, colWidths=largura_cols, repeatRows=1)
    ultimo = len(dados) - 1
    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, ultimo - 1), 0.6, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
        ("BACKGROUND", (0, ultimo - 1), (-1, ultimo - 1), colors.HexColor("#F2F2F2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("SPAN", (2, ultimo), (-1, ultimo)),
        ("LINEBELOW", (2, ultimo), (-1, ultimo), 0.8, colors.black),
        ("TOPPADDING", (0, ultimo), (-1, ultimo), 10),
    ]))

    story = [Paragraph(titulo(r).replace("DESPESAS ", "DESPESAS &nbsp;&nbsp;"), est_titulo)]
    if empresa:
        story.append(Paragraph(escape(empresa), est_emp))
    story += [Spacer(1, 5 * mm), tabela]
    rodape = f"Gerado em {gerado_em}" + (f" por {usuario}" if usuario else "")
    doc.build(story, canvasmaker=_canvas_numerado(rodape))
    return buf.getvalue()
