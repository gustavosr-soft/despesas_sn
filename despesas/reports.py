"""Relatório mensal em Excel (.xlsx) e PDF."""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import money

MIN_LINHAS = 15  # Excel: completa com linhas em branco

MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def titulo(r: dict) -> str:
    return f"DESPESAS {r['mes']:02d}/{r['ano']}"


def titulo_extenso(r: dict) -> str:
    return f"Despesas — {MESES_PT[r['mes']]} de {r['ano']}"


def nome_arquivo(r: dict, extensao: str) -> str:
    return f"despesas_{r['ano']}-{r['mes']:02d}.{extensao}"


def _cols_com_dados(r: dict) -> list:
    """Retorna apenas colunas que possuem ao menos um lançamento no mês."""
    usadas = {l["categoria_id"] for l in r["linhas"]}
    return [c for c in r["colunas"] if c["id"] in usadas]


def linhas_com_branco(r: dict) -> list:
    """Lançamentos + linhas em branco até MIN_LINHAS (None = linha em branco)."""
    linhas = list(r["linhas"])
    return linhas + [None] * max(0, MIN_LINHAS - len(linhas))


# ----------------------------------------------------------------------- Excel
def gerar_xlsx(r: dict, empresa: str = "") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"{r['mes']:02d}-{r['ano']}"

    # Filtra colunas — só as que têm lançamentos
    cols = _cols_com_dados(r)

    if not cols:
        # Mês sem lançamentos
        ws["A1"] = titulo(r)
        ws["A1"].font = Font(bold=True, size=16)
        ws["A3"] = "Nenhum lançamento registrado neste mês."
        ws["A3"].font = Font(size=12, italic=True)
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    ncol = 2 + len(cols)
    fino = Side(style="thin", color="000000")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)
    cinza = PatternFill("solid", fgColor="E8E8E8")
    azul_cab = PatternFill("solid", fgColor="2B4C7E")
    branco = Font(bold=True, size=10, color="FFFFFF")
    fmt_valor = '#,##0.00;-#,##0.00;"—"'

    # Título e empresa
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    ws["A1"] = titulo(r)
    ws["A1"].font = Font(bold=True, size=16)
    ws["A1"].alignment = Alignment(horizontal="center")
    if empresa:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
        ws["A2"] = empresa
        ws["A2"].alignment = Alignment(horizontal="center")
        ws["A2"].font = Font(size=10, italic=True)

    cab = 3
    nomes_cab = ["DIA", "DESCRIÇÃO"] + [c["nome"].upper() for c in cols]
    for i, nome in enumerate(nomes_cab, start=1):
        c = ws.cell(row=cab, column=i, value=nome)
        c.font = branco
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.fill = azul_cab
        c.border = borda
    ws.row_dimensions[cab].height = 26

    linhas = linhas_com_branco(r)
    col_ids = [c_["id"] for c_ in cols]
    primeira = cab + 1
    zebra_claro = PatternFill("solid", fgColor="F5F7FA")
    for i, l in enumerate(linhas):
        linha = primeira + i
        for col in range(1, ncol + 1):
            cel = ws.cell(row=linha, column=col)
            cel.border = borda
            if i % 2 == 1:
                cel.fill = zebra_claro
        if l is None:
            continue
        c = ws.cell(row=linha, column=1, value=l["dia"])
        c.number_format = "00"
        c.alignment = Alignment(horizontal="center")
        d = ws.cell(row=linha, column=2, value=l["descricao"])
        if str(l["descricao"]).startswith("="):
            d.data_type = "s"
        d.alignment = Alignment(wrap_text=True, vertical="top")
        if l["categoria_id"] in col_ids:
            idx = col_ids.index(l["categoria_id"])
            v = ws.cell(row=linha, column=3 + idx, value=round(l["valor"] / 100, 2))
            v.number_format = fmt_valor
    ultima = primeira + len(linhas) - 1

    # Linha de totais
    tot = ultima + 1
    tot_fill = PatternFill("solid", fgColor="D6E4F0")
    ws.cell(row=tot, column=1).border = borda
    ws.cell(row=tot, column=1).fill = tot_fill
    t = ws.cell(row=tot, column=2, value="TOTAIS")
    t.font = Font(bold=True, size=12)
    t.alignment = Alignment(horizontal="center")
    t.border = borda
    t.fill = tot_fill
    for i in range(len(cols)):
        letra = get_column_letter(3 + i)
        c = ws.cell(row=tot, column=3 + i, value=f"=SUM({letra}{primeira}:{letra}{ultima})")
        c.number_format = fmt_valor
        c.font = Font(bold=True)
        c.border = borda
        c.fill = tot_fill

    # Total geral
    geral = tot + 2
    g = ws.cell(row=geral, column=2, value="TOTAL GERAL")
    g.font = Font(bold=True, size=13)
    g.alignment = Alignment(horizontal="right")
    primeiro_letra, ultima_letra = get_column_letter(3), get_column_letter(ncol)
    v = ws.cell(row=geral, column=3, value=f"=SUM({primeiro_letra}{tot}:{ultima_letra}{tot})")
    v.number_format = fmt_valor
    v.font = Font(bold=True, size=13)
    v.border = Border(bottom=fino)

    # Larguras
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 38
    for i in range(len(cols)):
        ws.column_dimensions[get_column_letter(3 + i)].width = 15

    # Impressão
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
COR_AZUL = colors.HexColor("#2B4C7E")
COR_AZUL_CLARO = colors.HexColor("#D6E4F0")
COR_CINZA_CLARO = colors.HexColor("#F5F7FA")
COR_CINZA = colors.HexColor("#888888")


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
                self.setFont("Helvetica", 7)
                self.setFillColor(COR_CINZA)
                largura, _ = self._pagesize
                self.drawString(15 * mm, 10 * mm, rodape_esq)
                self.drawRightString(largura - 15 * mm, 10 * mm,
                                     f"Página {self._pageNumber} de {total}")
                # Linha fina no rodapé
                self.setStrokeColor(colors.HexColor("#DDDDDD"))
                self.setLineWidth(0.3)
                self.line(15 * mm, 13 * mm, largura - 15 * mm, 13 * mm)
                super().showPage()
            super().save()

    return NumeradoCanvas


def gerar_pdf(r: dict, empresa: str = "", usuario: str = "", gerado_em: str = "") -> bytes:
    """PDF otimizado: layout em lista (Dia | Descrição | Categoria | Valor)
    com resumo por categoria no final. Formato retrato A4."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title=titulo(r), author="Sistema de Despesas",
    )

    # Estilos
    est_titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=16,
                                alignment=TA_CENTER, leading=20, textColor=COR_AZUL)
    est_sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=10,
                             alignment=TA_CENTER, leading=13, textColor=COR_CINZA)
    est_cab = ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=8.5,
                             alignment=TA_CENTER, leading=11, textColor=colors.white)
    est_txt = ParagraphStyle("txt", fontName="Helvetica", fontSize=9,
                             alignment=TA_LEFT, leading=12)
    est_num = ParagraphStyle("num", fontName="Helvetica", fontSize=9,
                             alignment=TA_RIGHT, leading=12)
    est_tot_label = ParagraphStyle("tot_l", fontName="Helvetica-Bold", fontSize=10,
                                   alignment=TA_LEFT, leading=13)
    est_tot_val = ParagraphStyle("tot_v", fontName="Helvetica-Bold", fontSize=10,
                                 alignment=TA_RIGHT, leading=13)
    est_geral_label = ParagraphStyle("gl", fontName="Helvetica-Bold", fontSize=12,
                                     alignment=TA_LEFT, leading=15, textColor=COR_AZUL)
    est_geral_val = ParagraphStyle("gv", fontName="Helvetica-Bold", fontSize=12,
                                   alignment=TA_RIGHT, leading=15, textColor=COR_AZUL)
    est_sec = ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=11,
                             alignment=TA_LEFT, leading=14, textColor=COR_AZUL,
                             spaceBefore=8, spaceAfter=4)
    est_vazio = ParagraphStyle("vazio", fontName="Helvetica-Oblique", fontSize=11,
                               alignment=TA_CENTER, leading=14, textColor=COR_CINZA)

    # Nome do mês por extenso
    story = [
        Paragraph(titulo_extenso(r), est_titulo),
    ]
    if empresa:
        story.append(Paragraph(escape(empresa), est_sub))
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COR_AZUL,
                             spaceBefore=2, spaceAfter=6))

    if not r["linhas"]:
        # Mês sem lançamentos
        story.append(Spacer(1, 20 * mm))
        story.append(Paragraph("Nenhum lançamento registrado neste mês.", est_vazio))
        rodape = f"Gerado em {gerado_em}" + (f" por {usuario}" if usuario else "")
        doc.build(story, canvasmaker=_canvas_numerado(rodape))
        return buf.getvalue()

    # Mapeamento categoria id -> nome
    cat_nomes = {c["id"]: c["nome"] for c in r["colunas"]}

    # ── Tabela de lançamentos (Dia | Descrição | Categoria | Valor) ──
    story.append(Paragraph("Lançamentos", est_sec))

    cabecalho = [
        Paragraph("DIA", est_cab),
        Paragraph("DESCRIÇÃO", est_cab),
        Paragraph("CATEGORIA", est_cab),
        Paragraph("VALOR (R$)", est_cab),
    ]
    dados = [cabecalho]
    for l in r["linhas"]:
        dados.append([
            Paragraph(f"{l['dia']:02d}", ParagraphStyle("d", parent=est_txt, alignment=TA_CENTER)),
            Paragraph(escape(l["descricao"]), est_txt),
            Paragraph(escape(cat_nomes.get(l["categoria_id"], "?")), est_txt),
            Paragraph(money.formatar(l["valor"]), est_num),
        ])

    w_dia = 12 * mm
    w_val = 28 * mm
    w_cat = 35 * mm
    w_desc = doc.width - w_dia - w_val - w_cat
    larguras = [w_dia, w_desc, w_cat, w_val]

    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    n_linhas = len(dados)
    estilos = [
        # Cabeçalho azul
        ("BACKGROUND", (0, 0), (-1, 0), COR_AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        # Zebra
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        # Linhas horizontais suaves
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, COR_AZUL),
    ]
    for i in range(1, n_linhas):
        if i % 2 == 0:
            estilos.append(("BACKGROUND", (0, i), (-1, i), COR_CINZA_CLARO))
        estilos.append(("LINEBELOW", (0, i), (-1, i), 0.3, colors.HexColor("#DDDDDD")))

    tabela.setStyle(TableStyle(estilos))
    story.append(tabela)
    story.append(Spacer(1, 6 * mm))

    # ── Resumo por categoria ──
    story.append(Paragraph("Resumo por Categoria", est_sec))

    cols_com_dados = _cols_com_dados(r)
    resumo_dados = []
    for c in cols_com_dados:
        resumo_dados.append([
            Paragraph(escape(c["nome"]), est_tot_label),
            Paragraph(money.formatar(r["totais"][c["id"]]), est_tot_val),
        ])

    w_res_nome = doc.width * 0.6
    w_res_val = doc.width * 0.4
    tab_resumo = Table(resumo_dados, colWidths=[w_res_nome, w_res_val])
    n_res = len(resumo_dados)
    estilos_res = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(n_res):
        if i % 2 == 0:
            estilos_res.append(("BACKGROUND", (0, i), (-1, i), COR_CINZA_CLARO))
        estilos_res.append(("LINEBELOW", (0, i), (-1, i), 0.3, colors.HexColor("#DDDDDD")))
    tab_resumo.setStyle(TableStyle(estilos_res))
    story.append(tab_resumo)

    # ── Total Geral ──
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=COR_AZUL,
                             spaceBefore=2, spaceAfter=4))
    tab_geral = Table(
        [[Paragraph("TOTAL GERAL", est_geral_label),
          Paragraph(money.formatar(r["total_geral"]), est_geral_val)]],
        colWidths=[w_res_nome, w_res_val],
    )
    tab_geral.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (-1, -1), COR_AZUL_CLARO),
    ]))
    story.append(tab_geral)

    rodape = f"Gerado em {gerado_em}" + (f" por {usuario}" if usuario else "")
    doc.build(story, canvasmaker=_canvas_numerado(rodape))
    return buf.getvalue()
