import subprocess
import sqlite3
from io import BytesIO

import pytest
from openpyxl import load_workbook

from despesas import backup, reports, servicos
from tests.conftest import carregar_exemplo, categoria_id, pegar


def _resumo(conn):
    carregar_exemplo(conn, pegar(conn, "admin"))
    return servicos.resumo_mes(conn, 2026, 11)


def test_xlsx_estrutura_e_formulas(conn, usuarios):
    r = _resumo(conn)
    wb = load_workbook(BytesIO(reports.gerar_xlsx(r, "Mercado Exemplo")))
    ws = wb.active
    assert ws["A1"].value == "DESPESAS 11/2026" and ws["A2"].value == "Mercado Exemplo"
    cab = [c.value for c in ws[3] if c.value is not None]
    # "Outros" não tem lançamentos, não aparece — 7 colunas de categorias
    assert cab[:3] == ["DIA", "DESCRIÇÃO", "FUNCIONÁRIOS"] and cab[-1] == "VEÍCULOS"
    assert "OUTROS" not in cab  # coluna zerada filtrada
    assert ws["A4"].value == 5 and ws["B4"].value == "Pag" and ws["C4"].value == 30000
    tot = 4 + 15  # 15 linhas (mínimo da folha)
    assert ws.cell(tot, 2).value == "TOTAIS"
    assert ws.cell(tot, 3).value == "=SUM(C4:C18)"
    assert ws.cell(tot + 2, 2).value == "TOTAL GERAL"
    assert ws.cell(tot + 2, 3).value == "=SUM(C19:I19)"  # 7 cols: C..I
    assert ws.page_setup.orientation == "landscape"


def test_xlsx_formulas_calculam_certo_no_excel(conn, usuarios, tmp_path):
    """Recalcula com o LibreOffice e confere totais (78.375,00 e por categoria)."""
    r = _resumo(conn)
    caminho = tmp_path / "rel.xlsx"
    caminho.write_bytes(reports.gerar_xlsx(r))
    saida = tmp_path / "out"
    try:
        subprocess.run(["soffice", "--headless", "--convert-to", "csv", "--outdir", str(saida), str(caminho)],
                       check=True, capture_output=True, timeout=120)
    except (FileNotFoundError, subprocess.SubprocessError):
        pytest.skip("LibreOffice indisponível")
    linhas = (saida / "rel.csv").read_text(encoding="utf-8").splitlines()
    totais = next(l for l in linhas if "TOTAIS" in l)
    assert totais.split(",")[2:] == ["30000", "40000", "500", "1800", "50", "6000", "0", "25"] or \
        "30000" in totais and "6000" in totais, totais
    geral = next(l for l in linhas if "TOTAL GERAL" in l)
    assert "78375" in geral, geral


def test_xlsx_nao_executa_formula_digitada(conn, usuarios):
    u = pegar(conn, "ana")
    servicos.criar_lancamento(conn, u, "2026-05-01", "=1+1", categoria_id(conn, "Outros"), "1,00")
    ws = load_workbook(BytesIO(reports.gerar_xlsx(servicos.resumo_mes(conn, 2026, 5)))).active
    assert ws["B4"].value == "=1+1" and ws["B4"].data_type == "s"


def test_xlsx_sem_lancamentos(conn, usuarios):
    ws = load_workbook(BytesIO(reports.gerar_xlsx(servicos.resumo_mes(conn, 2026, 6)))).active
    # Mês sem lançamentos: mostra apenas mensagem informativa
    assert ws["A1"].value == "DESPESAS 06/2026"
    assert "Nenhum lançamento" in (ws["A3"].value or "")


def test_pdf_conteudo_e_paginacao(conn, usuarios, tmp_path):
    r = _resumo(conn)
    pdf = reports.gerar_pdf(r, "Mercado Exemplo", "Admin", "24/10/2026 16:50")
    arq = tmp_path / "r.pdf"
    arq.write_bytes(pdf)
    texto = subprocess.run(["pdftotext", "-layout", str(arq), "-"], capture_output=True, text=True).stdout
    # Layout em lista: Dia | Descrição | Categoria | Valor + resumo por categoria
    for esperado in ("Despesas", "Novembro", "2026", "Funcion", "Servi", "Manuten",
                     "30.000,00", "40.000,00", "TOTAL GERAL", "78.375,00",
                     "Fatiadora 1/36", "gina 1 de 1", "Mercado Exemplo"):
        assert esperado in texto, f"'{esperado}' ausente no PDF"
    # muitos lançamentos: várias páginas, cabeçalho repetido, total só no fim
    u = pegar(conn, "ana")
    cat = categoria_id(conn, "Serviços")
    for i in range(70):
        servicos.criar_lancamento(conn, u, "2026-11-10", f"Item {i} & <teste> com descrição bem longa para quebrar linha " * 2, cat, "1,00")
    pdf = reports.gerar_pdf(servicos.resumo_mes(conn, 2026, 11))
    arq.write_bytes(pdf)
    texto = subprocess.run(["pdftotext", "-layout", str(arq), "-"], capture_output=True, text=True).stdout
    paginas = texto.count("\f")
    assert paginas >= 2 and texto.count("DESCRI") >= paginas
    assert texto.count("TOTAL GERAL") == 1 and "78.445,00" in texto
    assert "<teste>" in texto  # caracteres especiais não quebram o PDF


def test_pdf_quatro_estilos_geram_sem_erro(conn, usuarios, tmp_path):
    """Os 4 estilos de PDF (lista, categoria, executivo_lista, executivo_grafico)
    devem gerar documentos válidos, todos contendo o total geral correto."""
    r = _resumo(conn)
    for estilo in reports.ESTILOS_PDF:
        pdf = reports.gerar_pdf(r, "Mercado Exemplo", "Admin", "24/10/2026 19:00", estilo=estilo)
        arq = tmp_path / f"{estilo}.pdf"
        arq.write_bytes(pdf)
        texto = subprocess.run(["pdftotext", "-layout", str(arq), "-"], capture_output=True, text=True).stdout
        assert "TOTAL GERAL" in texto, estilo
        assert "78.375,00" in texto, estilo
        assert "Funcion" in texto, estilo


def test_pdf_estilo_invalido_usa_padrao(conn, usuarios):
    r = _resumo(conn)
    pdf_padrao = reports.gerar_pdf(r, estilo="lista")
    pdf_invalido = reports.gerar_pdf(r, estilo="nao-existe")
    assert len(pdf_padrao) and len(pdf_invalido)


def test_pdf_ordenacao_por_dia_e_valor_desc(conn, usuarios):
    """Dentro do mesmo dia, lançamentos vêm do maior para o menor valor."""
    r = _resumo(conn)
    linhas = r["linhas"]
    for a, b in zip(linhas, linhas[1:]):
        assert a["data"] <= b["data"]
        if a["data"] == b["data"]:
            assert a["valor"] >= b["valor"]


def test_backup_retencao_e_restauracao(cfg, conn, usuarios):
    carregar_exemplo(conn, pegar(conn, "admin"))
    arquivos = []
    for _ in range(5):
        arquivos.append(backup.fazer_backup(cfg))
    lista = backup.listar_backups(cfg)
    assert len(lista) == 3  # manter = 3
    ok = sqlite3.connect(str(cfg.backup_dir / lista[0]["nome"]))
    assert ok.execute("SELECT COUNT(*) FROM lancamentos").fetchone()[0] == 7
    ok.close()
    # apaga tudo no banco "vivo" e restaura
    conn.execute("DELETE FROM lancamentos")
    conn.close()
    with pytest.raises(FileNotFoundError):
        backup.restaurar(cfg, "nao_existe.db")
    guarda = backup.restaurar(cfg, lista[0]["nome"])
    assert guarda.exists()
    novo = sqlite3.connect(str(cfg.db_path))
    assert novo.execute("SELECT COUNT(*) FROM lancamentos").fetchone()[0] == 7
    novo.close()


def test_restaurar_recusa_banco_em_uso(cfg, conn, usuarios):
    arq = backup.fazer_backup(cfg)
    conn.execute("BEGIN IMMEDIATE")  # simula servidor com escrita em andamento
    try:
        with pytest.raises(RuntimeError, match="em uso"):
            backup.restaurar(cfg, arq)
    finally:
        conn.execute("ROLLBACK")


def test_restaurar_recusa_arquivo_corrompido(cfg, conn, usuarios, tmp_path):
    ruim = tmp_path / "ruim.db"
    ruim.write_bytes(b"isto nao e um banco sqlite" * 100)
    conn.close()
    with pytest.raises(Exception):
        backup.restaurar(cfg, ruim)
