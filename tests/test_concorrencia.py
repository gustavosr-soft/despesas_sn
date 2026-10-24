"""Servidor real (waitress) com vários "computadores" lançando ao mesmo tempo."""
import http.cookiejar
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest
from waitress.server import create_server

from despesas import backup, servicos
from tests.conftest import categoria_id, pegar


class Cliente:
    def __init__(self, base):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, caminho):
        with self.op.open(self.base + caminho, timeout=60) as r:
            return r.status, r.read()

    def csrf(self, caminho):
        _, corpo = self.get(caminho)
        return re.search(rb'name="csrf" value="([^"]+)"', corpo).group(1).decode()

    def post(self, caminho, token_de, **dados):
        dados["csrf"] = self.csrf(token_de)
        req = urllib.request.Request(self.base + caminho, urllib.parse.urlencode(dados).encode())
        with self.op.open(req, timeout=60) as r:
            return r.status, r.read()

    def entrar(self, usuario, senha):
        return self.post("/login", "/login", usuario=usuario, senha=senha)


@pytest.fixture()
def servidor(app):
    srv = create_server(app, host="127.0.0.1", port=0, threads=8)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.effective_port}"
    srv.close()
    t.join(timeout=5)


def test_varios_computadores_lancando_ao_mesmo_tempo(servidor, conn, usuarios, cfg):
    cat = categoria_id(conn, "Serviços")
    n_clientes, por_cliente = 8, 25
    erros = []

    def trabalhar(i):
        try:
            c = Cliente(servidor)
            c.entrar("ana" if i % 2 == 0 else "bia", "senha-1234")
            for k in range(por_cliente):
                status, _ = c.post("/lancamentos", "/mes/2026/11", data="2026-11-15",
                                   descricao=f"cliente {i} item {k}", categoria_id=cat, valor="10,00")
                assert status == 200  # após o redirect para o mês
                if k % 5 == 0:
                    c.get("/mes/2026/11")
                    c.get("/relatorio/2026/11.xlsx")
        except Exception as e:  # noqa: BLE001
            erros.append(repr(e))

    # backups no meio da escrita também não podem quebrar nada
    parar = threading.Event()
    falhas_backup = []

    def backups():
        while not parar.is_set():
            try:
                backup.fazer_backup(cfg)
            except Exception as e:  # noqa: BLE001
                falhas_backup.append(repr(e))

    tb = threading.Thread(target=backups)
    tb.start()
    ts = [threading.Thread(target=trabalhar, args=(i,)) for i in range(n_clientes)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    parar.set()
    tb.join()

    assert erros == [] and falhas_backup == []
    r = servicos.resumo_mes(conn, 2026, 11)
    assert len(r["linhas"]) == n_clientes * por_cliente  # nenhum lançamento perdido ou duplicado
    assert r["total_geral"] == n_clientes * por_cliente * 1000
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    ids = [l["id"] for l in r["linhas"]]
    assert len(set(ids)) == len(ids)


def test_edicao_simultanea_do_mesmo_lancamento(servidor, conn, usuarios):
    admin = pegar(conn, "admin")
    cat = categoria_id(conn, "Outros")
    lid = servicos.criar_lancamento(conn, admin, "2026-11-01", "original", cat, "1,00")
    # dois envios com a mesma versão do lançamento: só o primeiro vence
    c1, c2 = Cliente(servidor), Cliente(servidor)
    c1.entrar("admin", "senha-1234")
    c2.entrar("admin", "senha-1234")
    s1, b1 = c1.post(f"/lancamentos/{lid}/editar", "/mes/2026/11", versao="1", data="2026-11-01",
                     descricao="primeiro", categoria_id=cat, valor="2,00")
    with pytest.raises(urllib.error.HTTPError) as e:
        c2.post(f"/lancamentos/{lid}/editar", "/mes/2026/11", versao="1", data="2026-11-01",
                descricao="segundo (versão velha)", categoria_id=cat, valor="3,00")
    assert e.value.code == 422 and "alterado por outra pessoa" in e.value.read().decode()
    assert servicos.obter_lancamento(conn, lid)["descricao"] == "primeiro"
