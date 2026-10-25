import re

from despesas import servicos
from tests.conftest import carregar_exemplo, categoria_id, entrar, pegar, post, token


def test_exige_login(cliente):
    r = cliente.get("/mes/2026/11")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert cliente.get("/relatorio/2026/11.pdf").status_code == 302
    assert cliente.get("/admin/usuarios").status_code == 302
    assert cliente.get("/saude").data == b"ok"


def test_login_logout_e_cabecalhos(cliente):
    r = entrar(cliente, "admin", "senha-1234")
    assert r.status_code == 302
    pag = cliente.get("/mes/2026/11")
    assert pag.status_code == 200 and "DESPESAS 11/2026" in pag.get_data(as_text=True)
    assert pag.headers["X-Content-Type-Options"] == "nosniff"
    assert "script-src 'self'" in pag.headers["Content-Security-Policy"]
    assert pag.headers["Cache-Control"] == "no-store"
    assert post(cliente, "/sair").status_code == 302
    assert cliente.get("/mes/2026/11").status_code == 302


def test_login_errado_e_bloqueio(cliente):
    for _ in range(2):
        r = entrar(cliente, "ana", "errada")
        assert r.status_code == 401 and "inválidos" in r.get_data(as_text=True)
    entrar(cliente, "ana", "errada")
    r = entrar(cliente, "ana", "senha-1234")
    assert r.status_code == 401 and "bloqueado" in r.get_data(as_text=True)


def test_csrf_obrigatorio(cliente):
    entrar(cliente)
    assert cliente.post("/lancamentos", data={"data": "2026-11-01"}).status_code == 400
    assert cliente.post("/lancamentos", data={"csrf": "falso"}).status_code == 400
    assert cliente.post("/sair").status_code == 400
    # sem sessão alguma, o login também exige token
    outro = cliente.application.test_client()
    assert outro.post("/login", data={"usuario": "admin", "senha": "senha-1234"}).status_code == 400


def test_next_externo_ignorado(cliente):
    t = token(cliente)
    r = cliente.post("/login?next=https://malicioso.example/", data={"usuario": "admin", "senha": "senha-1234", "csrf": t})
    assert r.status_code == 302 and "malicioso" not in r.headers["Location"]
    cliente2 = cliente.application.test_client()
    t = token(cliente2)
    r = cliente2.post("/login?next=//malicioso.example", data={"usuario": "admin", "senha": "senha-1234", "csrf": t})
    assert "malicioso" not in r.headers["Location"]


def test_criar_editar_excluir_pela_interface(cliente, conn):
    entrar(cliente, "ana")
    cat = categoria_id(conn, "Aluguel")
    r = post(cliente, "/lancamentos", data="2026-11-20", descricao="<b>luzia</b>", categoria_id=cat, valor="6.000,00")
    assert r.status_code == 302
    html = cliente.get("/mes/2026/11").get_data(as_text=True)
    assert "&lt;b&gt;luzia&lt;/b&gt;" in html and "<b>luzia</b>" not in html  # texto escapado
    assert "6.000,00" in html
    lid = conn.execute("SELECT id FROM lancamentos").fetchone()["id"]
    r = post(cliente, f"/lancamentos/{lid}/editar", versao="1", data="2026-11-21", descricao="aluguel", categoria_id=cat, valor="6500,00")
    assert r.status_code == 302
    assert "6.500,00" in cliente.get("/mes/2026/11").get_data(as_text=True)
    r = post(cliente, f"/lancamentos/{lid}/excluir", versao="2")
    assert r.status_code == 302
    assert "Nenhum lançamento" in cliente.get("/mes/2026/11").get_data(as_text=True)


def test_erro_de_validacao_mantem_campos(cliente, conn):
    entrar(cliente, "ana")
    r = post(cliente, "/lancamentos", data="2026-11-20", descricao="teste", categoria_id="", valor="abc")
    html = r.get_data(as_text=True)
    assert r.status_code == 422 and "Escolha a categoria" in html and 'value="teste"' in html


def test_consulta_nao_altera(cliente, conn):
    entrar(cliente, "cida")
    cat = categoria_id(conn, "Outros")
    assert post(cliente, "/lancamentos", data="2026-11-20", descricao="x", categoria_id=cat, valor="1").status_code == 403
    html = cliente.get("/mes/2026/11").get_data(as_text=True)
    assert "Novo lançamento" not in html
    assert cliente.get("/admin/usuarios").status_code == 403
    assert cliente.get("/relatorio/2026/11.pdf").status_code == 200  # consulta gera relatórios


def test_lancador_so_edita_os_seus(cliente, conn):
    admin = pegar(conn, "admin")
    cat = categoria_id(conn, "Outros")
    lid = servicos.criar_lancamento(conn, admin, "2026-11-02", "do admin", cat, "5,00")
    entrar(cliente, "ana")
    assert cliente.get(f"/lancamentos/{lid}/editar").status_code == 403
    assert post(cliente, f"/lancamentos/{lid}/excluir", versao="1").status_code == 403
    html = cliente.get("/mes/2026/11").get_data(as_text=True)
    assert "do admin" in html and f"/lancamentos/{lid}/editar" not in html


def test_meses_invalidos(cliente):
    entrar(cliente)
    for url in ("/mes/2026/13", "/mes/2026/0", "/mes/1800/5", "/mes/2026/11x", "/relatorio/2026/13.pdf"):
        assert cliente.get(url).status_code == 404
    assert cliente.get("/mes?ano=2027&mes=3").headers["Location"].endswith("/mes/2027/3")


def test_relatorios_http(cliente, conn):
    carregar_exemplo(conn, pegar(conn, "admin"))
    entrar(cliente)
    x = cliente.get("/relatorio/2026/11.xlsx")
    assert x.status_code == 200 and x.data[:2] == b"PK" and "despesas_2026-11.xlsx" in x.headers["Content-Disposition"]
    p = cliente.get("/relatorio/2026/11.pdf")
    assert p.status_code == 200 and p.data[:5] == b"%PDF-"
    i = cliente.get("/relatorio/2026/11/imprimir?estilo=categoria").get_data(as_text=True)
    assert "/relatorio/2026/11.pdf?estilo=categoria" in i and "pdf-frame" in i
    assert "onclick" not in i  # sem scripts inline (CSP)
    i2 = cliente.get("/relatorio/2026/11/imprimir?estilo=invalido").get_data(as_text=True)
    assert "estilo=lista" in i2  # estilo inválido cai no padrão


def test_trocar_senha_obrigatorio_no_primeiro_acesso(cliente, conn):
    admin = pegar(conn, "admin")
    servicos.criar_usuario(conn, "novo", "Novo", "provisoria1", "lancador", trocar_senha=True)
    entrar(cliente, "novo", "provisoria1")
    assert cliente.get("/mes/2026/11").headers["Location"].endswith("/senha")
    r = post(cliente, "/senha", atual="provisoria1", nova="definitiva9", confirma="outra")
    assert "não confere" in r.get_data(as_text=True)
    r = post(cliente, "/senha", atual="provisoria1", nova="curta", confirma="curta")
    assert "pelo menos 8" in r.get_data(as_text=True)
    r = post(cliente, "/senha", atual="provisoria1", nova="definitiva9", confirma="definitiva9")
    assert r.status_code == 302
    assert cliente.get("/mes/2026/11").status_code == 200
    novo = cliente.application.test_client()
    assert entrar(novo, "novo", "definitiva9").status_code == 302


def test_painel_servidor_mostra_status(cliente, conn):
    carregar_exemplo(conn, pegar(conn, "admin"))
    entrar(cliente)
    html = cliente.get("/admin/backup").get_data(as_text=True)
    assert "Status do servidor" in html
    assert "Integridade do banco" in html
    assert "despesas.db" in html  # caminho absoluto do banco em uso
    assert "Lançamentos (não excluídos)" in html


def test_admin_paginas_funcionam(cliente, conn):
    carregar_exemplo(conn, pegar(conn, "admin"))
    entrar(cliente)
    for url in ("/admin/usuarios", "/admin/categorias", "/admin/backup", "/admin/auditoria", "/mes/2026/11?excluidos=1"):
        assert cliente.get(url).status_code == 200, url
    r = post(cliente, "/admin/categorias", nome="Telefone")
    assert r.status_code == 302 and "Telefone" in cliente.get("/admin/categorias").get_data(as_text=True)
    cid = categoria_id(conn, "Telefone")
    post(cliente, f"/admin/categorias/{cid}", acao="renomear", nome="Telefonia")
    assert categoria_id(conn, "Telefonia") == cid
    r = post(cliente, "/admin/usuarios", usuario="joao", nome="João", senha="provisoria1", perfil="consulta")
    assert r.status_code == 302 and "joao" in cliente.get("/admin/usuarios").get_data(as_text=True)
    uid = pegar(conn, "joao")["id"]
    post(cliente, f"/admin/usuarios/{uid}", nome="João S.", perfil="lancador", ativo="1", nova_senha="")
    assert pegar(conn, "joao")["perfil"] == "lancador"
    post(cliente, f"/admin/usuarios/{uid}", nome="João S.", perfil="lancador", ativo="0", nova_senha="")
    j = cliente.application.test_client()
    assert entrar(j, "joao", "provisoria1").status_code == 401  # desativado não entra


def test_sem_script_inline_e_pdf_com_csp_leve(cliente, conn):
    carregar_exemplo(conn, pegar(conn, "admin"))
    entrar(cliente)
    for url in ("/mes/2026/11", "/admin/backup", "/admin/categorias"):
        html = cliente.get(url).get_data(as_text=True)
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), url  # CSP bloqueia inline
    for estilo in ("lista", "categoria", "executivo_lista", "executivo_grafico"):
        p = cliente.get(f"/relatorio/2026/11.pdf?estilo={estilo}")
        assert p.status_code == 200 and p.data[:5] == b"%PDF-", estilo
        assert p.headers["Content-Security-Policy"] == "frame-ancestors 'self'"
