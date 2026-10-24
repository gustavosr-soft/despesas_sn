import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from despesas import db, servicos  # noqa: E402
from despesas.config import carregar  # noqa: E402
from despesas.web import criar_app  # noqa: E402

INI = """
[servidor]
host = 127.0.0.1
porta = 8099
[banco]
caminho = dados/despesas.db
[backup]
pasta = backups
manter = 3
[logs]
pasta = logs
[seguranca]
tentativas_max = 3
bloqueio_minutos = 5
[relatorios]
empresa = Mercado Exemplo
"""


@pytest.fixture()
def cfg(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text(INI, encoding="utf-8")
    return carregar(ini)


@pytest.fixture()
def conn(cfg):
    db.iniciar(cfg.db_path)
    c = db.conectar(cfg.db_path)
    yield c
    c.close()


@pytest.fixture()
def usuarios(conn):
    ids = {}
    for nome, perfil in (("admin", "admin"), ("ana", "lancador"), ("bia", "lancador"), ("cida", "consulta")):
        ids[nome] = servicos.criar_usuario(conn, nome, nome.title(), "senha-1234", perfil, trocar_senha=False)
    return ids


def pegar(conn, nome):
    return conn.execute("SELECT * FROM usuarios WHERE usuario=?", (nome,)).fetchone()


@pytest.fixture()
def app(cfg, usuarios):
    a = criar_app(cfg)
    a.config["TESTING"] = True
    return a


@pytest.fixture()
def cliente(app):
    return app.test_client()


def token(cliente):
    cliente.get("/login")
    with cliente.session_transaction() as s:
        return s["csrf"]


def entrar(cliente, usuario="admin", senha="senha-1234"):
    t = token(cliente)
    return cliente.post("/login", data={"usuario": usuario, "senha": senha, "csrf": t})


def post(cliente, url, **dados):
    with cliente.session_transaction() as s:
        t = s.get("csrf", "")
    if not t:  # o navegador teria aberto uma página (que gera o token) antes de enviar o formulário
        cliente.get("/senha")
        with cliente.session_transaction() as s:
            t = s.get("csrf", "")
    dados["csrf"] = t
    return cliente.post(url, data=dados)


def categoria_id(conn, nome):
    return conn.execute("SELECT id FROM categorias WHERE nome=?", (nome,)).fetchone()["id"]


EXEMPLO_NOV_2026 = [
    ("2026-11-05", "Pag", "Funcionários", "30.000,00"),
    ("2026-11-20", "icms", "Impostos", "40.000,00"),
    ("2026-11-20", "Fatiadora 1/36", "Imobilizados", "500,00"),
    ("2026-11-20", "Viva sist", "Serviços", "1.800,00"),
    ("2026-11-20", "dechadura", "Manutenção", "50,00"),
    ("2026-11-20", "luzia", "Aluguel", "6.000,00"),
    ("2026-11-20", "veículo", "Veículos", "25,00"),
]


def carregar_exemplo(conn, usuario):
    for data, desc, cat, valor in EXEMPLO_NOV_2026:
        servicos.criar_lancamento(conn, usuario, data, desc, categoria_id(conn, cat), valor)
