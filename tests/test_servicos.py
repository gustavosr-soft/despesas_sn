import pytest

from despesas import servicos
from despesas.servicos import ErroNegocio, SemPermissao
from tests.conftest import carregar_exemplo, categoria_id, pegar


def test_resumo_exemplo_imagem_2(conn, usuarios):
    carregar_exemplo(conn, pegar(conn, "admin"))
    r = servicos.resumo_mes(conn, 2026, 11)
    nomes = [c["nome"] for c in r["colunas"]]
    assert nomes == ["Funcionários", "Impostos", "Imobilizados", "Serviços", "Manutenção", "Aluguel", "Outros", "Veículos"]
    por_nome = {c["nome"]: r["totais"][c["id"]] for c in r["colunas"]}
    assert por_nome["Funcionários"] == 3_000_000 and por_nome["Veículos"] == 2500 and por_nome["Outros"] == 0
    # o TOTAL GERAL da foto (100.000,00) estava errado: a soma real é 78.375,00
    assert r["total_geral"] == 7_837_500
    assert [l["dia"] for l in r["linhas"]] == [5, 20, 20, 20, 20, 20, 20]


def test_varios_lancamentos_no_mesmo_dia_e_ordem(conn, usuarios):
    u = pegar(conn, "ana")
    cat = categoria_id(conn, "Outros")
    for desc in ("c", "a", "b"):
        servicos.criar_lancamento(conn, u, "2026-03-10", desc, cat, "1,00")
    servicos.criar_lancamento(conn, u, "2026-03-02", "antes", cat, "1,00")
    r = servicos.resumo_mes(conn, 2026, 3)
    assert [l["descricao"] for l in r["linhas"]] == ["antes", "c", "a", "b"]  # data, depois ordem de inclusão


def test_meses_isolados_e_limites(conn, usuarios):
    u = pegar(conn, "ana")
    cat = categoria_id(conn, "Outros")
    servicos.criar_lancamento(conn, u, "2026-01-31", "jan", cat, "10,00")
    servicos.criar_lancamento(conn, u, "2026-02-01", "fev", cat, "20,00")
    servicos.criar_lancamento(conn, u, "2026-12-31", "dez", cat, "30,00")
    servicos.criar_lancamento(conn, u, "2027-01-01", "prox", cat, "40,00")
    assert servicos.resumo_mes(conn, 2026, 1)["total_geral"] == 1000
    assert servicos.resumo_mes(conn, 2026, 2)["total_geral"] == 2000
    assert servicos.resumo_mes(conn, 2026, 12)["total_geral"] == 3000
    assert servicos.resumo_mes(conn, 2027, 1)["total_geral"] == 4000


def test_validacoes(conn, usuarios):
    u = pegar(conn, "ana")
    cat = categoria_id(conn, "Outros")
    ruins = [("2026-02-30", "x", cat, "1,00"), ("", "x", cat, "1,00"), ("2026-01-01", "  ", cat, "1,00"),
             ("2026-01-01", "x" * 201, cat, "1,00"), ("2026-01-01", "x", 9999, "1,00"),
             ("2026-01-01", "x", "", "1,00"), ("2026-01-01", "x", cat, "0"), ("1999-01-01", "x", cat, "1,00"),
             ("2026-01-01", "a\x00b", cat, "1,00")]
    for args in ruins:
        with pytest.raises(ErroNegocio):
            servicos.criar_lancamento(conn, u, *args)
    assert servicos.resumo_mes(conn, 2026, 1)["linhas"] == []


def test_permissoes(conn, usuarios):
    ana, bia, cida, admin = (pegar(conn, n) for n in ("ana", "bia", "cida", "admin"))
    cat = categoria_id(conn, "Outros")
    with pytest.raises(SemPermissao):
        servicos.criar_lancamento(conn, cida, "2026-01-01", "x", cat, "1,00")
    lid = servicos.criar_lancamento(conn, ana, "2026-01-01", "da ana", cat, "1,00")
    with pytest.raises(SemPermissao):  # lançador não mexe no lançamento de outro
        servicos.editar_lancamento(conn, bia, lid, 1, "2026-01-01", "x", cat, "2,00")
    with pytest.raises(SemPermissao):
        servicos.excluir_lancamento(conn, bia, lid, 1)
    servicos.editar_lancamento(conn, admin, lid, 1, "2026-01-01", "admin editou", cat, "2,00")  # admin pode
    with pytest.raises(SemPermissao):
        servicos.restaurar_lancamento(conn, ana, lid, 2)
    with pytest.raises(SemPermissao):
        servicos.criar_categoria(conn, ana, "Nova")


def test_conflito_de_edicao_por_versao(conn, usuarios):
    ana = pegar(conn, "ana")
    cat = categoria_id(conn, "Outros")
    lid = servicos.criar_lancamento(conn, ana, "2026-01-01", "x", cat, "1,00")
    servicos.editar_lancamento(conn, ana, lid, 1, "2026-01-01", "primeira edição", cat, "2,00")
    with pytest.raises(ErroNegocio, match="alterado por outra pessoa"):
        servicos.editar_lancamento(conn, ana, lid, 1, "2026-01-01", "edição velha", cat, "3,00")
    with pytest.raises(ErroNegocio, match="alterado por outra pessoa"):
        servicos.excluir_lancamento(conn, ana, lid, 1)
    assert servicos.obter_lancamento(conn, lid)["descricao"] == "primeira edição"


def test_exclusao_logica_e_restauracao(conn, usuarios):
    ana, admin = pegar(conn, "ana"), pegar(conn, "admin")
    cat = categoria_id(conn, "Outros")
    lid = servicos.criar_lancamento(conn, ana, "2026-01-05", "x", cat, "10,00")
    servicos.excluir_lancamento(conn, ana, lid, 1)
    r = servicos.resumo_mes(conn, 2026, 1, incluir_excluidos=True)
    assert r["total_geral"] == 0 and r["linhas"] == [] and len(r["excluidos"]) == 1
    with pytest.raises(ErroNegocio):
        servicos.excluir_lancamento(conn, ana, lid, 2)
    servicos.restaurar_lancamento(conn, admin, lid, 2)
    assert servicos.resumo_mes(conn, 2026, 1)["total_geral"] == 1000
    acoes = [a["acao"] for a in conn.execute("SELECT acao FROM auditoria WHERE lancamento_id=? ORDER BY id", (lid,))]
    assert acoes == ["lancamento_criado", "lancamento_excluido", "lancamento_restaurado"]


def test_categorias_configuraveis(conn, usuarios):
    admin, ana = pegar(conn, "admin"), pegar(conn, "ana")
    outros, veic = categoria_id(conn, "Outros"), categoria_id(conn, "Veículos")
    lid = servicos.criar_lancamento(conn, ana, "2026-11-01", "gasolina", veic, "100,00")
    servicos.definir_ativa(conn, admin, veic, False)
    nomes = [c["nome"] for c in servicos.resumo_mes(conn, 2026, 11)["colunas"]]
    assert "Veículos" in nomes  # inativa, mas usada no mês: continua aparecendo
    assert "Veículos" not in [c["nome"] for c in servicos.resumo_mes(conn, 2026, 10)["colunas"]]
    with pytest.raises(ErroNegocio, match="desativada"):
        servicos.criar_lancamento(conn, ana, "2026-11-02", "x", veic, "1,00")
    servicos.editar_lancamento(conn, ana, lid, 1, "2026-11-01", "gasolina 2", veic, "110,00")  # mantém a atual
    servicos.renomear_categoria(conn, admin, outros, "Diversas")
    assert servicos.listar_categorias(conn)[6]["nome"] == "Diversas"
    with pytest.raises(ErroNegocio, match="Já existe"):
        servicos.criar_categoria(conn, admin, "diversas")
    servicos.mover_categoria(conn, admin, outros, "sobe")
    assert [c["nome"] for c in servicos.listar_categorias(conn)][5] == "Diversas"
    for c in servicos.listar_categorias(conn, apenas_ativas=True)[:-1]:
        servicos.definir_ativa(conn, admin, c["id"], False)
    with pytest.raises(ErroNegocio, match="pelo menos uma"):
        servicos.definir_ativa(conn, admin, servicos.listar_categorias(conn, apenas_ativas=True)[0]["id"], False)


def test_usuarios_regras(conn, usuarios):
    admin = pegar(conn, "admin")
    with pytest.raises(ErroNegocio, match="próprio"):
        servicos.atualizar_usuario(conn, admin, admin["id"], "Admin", "consulta", True)
    with pytest.raises(ErroNegocio, match="Já existe"):
        servicos.criar_usuario(conn, "ANA", "x", "senha-1234", "consulta")
    with pytest.raises(ErroNegocio):
        servicos.criar_usuario(conn, "novo", "x", "curta", "consulta")
    with pytest.raises(ErroNegocio):
        servicos.criar_usuario(conn, "a b", "x", "senha-1234", "consulta")
    outro = servicos.criar_usuario(conn, "chefe2", "Chefe 2", "senha-1234", "admin", trocar_senha=False)
    servicos.atualizar_usuario(conn, admin, outro, "Chefe 2", "lancador", True)  # há outro admin: ok
    with pytest.raises(ErroNegocio, match="próprio"):
        servicos.atualizar_usuario(conn, admin, admin["id"], "Admin", "admin", False)


def test_bloqueio_apos_tentativas(conn, usuarios):
    for _ in range(3):
        with pytest.raises(ErroNegocio, match="inválidos"):
            servicos.autenticar(conn, "ana", "errada", 3, 5)
    with pytest.raises(ErroNegocio, match="bloqueado"):
        servicos.autenticar(conn, "ana", "senha-1234", 3, 5)  # mesmo com a senha certa
    conn.execute("UPDATE usuarios SET bloqueado_ate='2000-01-01 00:00:00' WHERE usuario='ana'")
    assert servicos.autenticar(conn, "ana", "senha-1234", 3, 5)["usuario"] == "ana"
    with pytest.raises(ErroNegocio, match="inválidos"):
        servicos.autenticar(conn, "inexistente", "x", 3, 5)
