import socket
import subprocess
import sys
from pathlib import Path

import pytest

from despesas.gerenciador import ErroGerenciador, Gerenciador

RAIZ = Path(__file__).resolve().parent.parent


def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def ger(tmp_path):
    porta = _porta_livre()
    cfg = tmp_path / "config.ini"
    cfg.write_text(f"[servidor]\nhost = 0.0.0.0\nporta = {porta}\n", encoding="utf-8")
    return Gerenciador(RAIZ, cfg)


def _run(ger, *args):
    return subprocess.run([sys.executable, str(RAIZ / "run.py"), "--config", str(ger.config_path), *args],
                          capture_output=True, text=True)


def test_ciclo_ligar_desligar_backup(ger):
    r = _run(ger, "criar-admin", "--usuario", "admin", "--nome", "Admin", "--senha", "senha-1234")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not ger.status().rodando
    try:
        ger.ligar()
        st = ger.status()
        assert st.rodando and st.saude_ok
        assert "já está ligado" in ger.ligar()
        info = ger.info_banco()
        assert info.existe and info.usuarios == 1 and info.integridade == "ok"
        msg = ger.desligar()
        assert "desligado" in msg and "Backup" in msg
        assert not ger.status().rodando
    finally:
        if ger.status().rodando:
            ger.desligar(backup_antes=False)
    assert len(ger.listar_backups()) >= 1
    assert ger.info_banco().existe  # desligar nunca apaga o banco


def test_nao_liga_sem_banco_havendo_backups(ger):
    _run(ger, "criar-admin", "--usuario", "admin", "--nome", "A", "--senha", "senha-1234")
    ger.backup_agora()
    ger.cfg().db_path.unlink()
    with pytest.raises(ErroGerenciador, match="NÃO foi encontrado"):
        ger.ligar()
    assert not ger.cfg().db_path.exists()  # nada criado por cima


def test_run_py_recusa_banco_vazio_com_backups(ger):
    _run(ger, "criar-admin", "--usuario", "admin", "--nome", "A", "--senha", "senha-1234")
    ger.backup_agora()
    ger.cfg().db_path.unlink()
    r = _run(ger, "verificar")
    assert r.returncode == 3 and "PARADO POR SEGURANCA" in r.stdout
    assert not ger.cfg().db_path.exists()
    r = _run(ger, "--criar-novo", "verificar")
    assert r.returncode == 0 and ger.cfg().db_path.exists()


def test_copia_para_consulta_e_mover_dados(ger, tmp_path):
    import sqlite3
    _run(ger, "criar-admin", "--usuario", "admin", "--nome", "A", "--senha", "senha-1234")
    copia = ger.copia_para_consulta()
    assert copia.exists() and copia.parent.name == "consulta"
    c = sqlite3.connect(copia)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 1
    c.close()
    ger.backup_agora()
    destino = tmp_path / "fora"
    msg = ger.mover_dados(destino)
    assert "Dados movidos" in msg
    cfg = ger.cfg()
    assert cfg.db_path.resolve() == (destino / "dados" / "despesas.db").resolve()
    assert cfg.db_path.exists() and len(ger.listar_backups()) == 1
    assert ger.info_banco().usuarios == 1
    assert (ger.config_path.parent / "config.ini.antes_mover").exists()
    assert "porta" in ger.config_path.read_text()  # resto do config intacto


# ------------------------------------------------------------ supervisor / modo rede
import time


@pytest.fixture
def sup(ger):
    _run(ger, "criar-admin", "--usuario", "admin", "--nome", "A", "--senha", "senha-1234")
    proc = subprocess.Popen([sys.executable, str(RAIZ / "run.py"), "--config", str(ger.config_path), "supervisor"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ger._proc = proc
    try:
        limite = time.time() + 40
        while time.time() < limite and not (ger.supervisor_vivo() and ger.status().rodando):
            time.sleep(0.3)
        assert ger.supervisor_vivo() and ger.status().rodando, "supervisor não subiu o servidor"
        yield ger
    finally:
        try:
            if ger.supervisor_vivo():
                ger._comando("sair")
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_controle_pela_rede_via_supervisor(sup, ger):
    rede = Gerenciador(RAIZ, ger.config_path, forcar_rede=True)  # simula abrir por \\servidor\...
    assert rede.status().rodando and rede.status().saude_ok
    info = rede.info_banco()
    assert info.existe and info.usuarios == 1 and info.integridade == "ok"
    assert "desligado" in rede.desligar()
    assert not rede.status().rodando
    assert "ligado" in rede.ligar() and rede.status().rodando
    assert "Backup criado" in f"Backup criado: {rede.backup_agora()}"
    rede._comando("backup")
    time.sleep(2.5)
    assert len(rede.listar_backups()) >= 2  # lista vem do estado publicado pelo supervisor
    assert rede.restaurar(rede.listar_backups()[0]["nome"]).startswith("Restaurado")
    assert not rede.status().rodando  # restaurar deixa desligado
    assert rede.ligar() and rede.status().rodando
    with pytest.raises(ErroGerenciador, match="só pode ser feita no próprio"):
        rede.mover_dados("/tmp/x")


def test_supervisor_religa_servidor_que_caiu(sup, ger):
    import os
    import signal
    pid = ger.estado_supervisor()["servidor_pid"]
    os.kill(pid, signal.SIGKILL)
    limite = time.time() + 30
    novo = None
    while time.time() < limite:
        est = ger.estado_supervisor() or {}
        if est.get("servidor_pid") and est["servidor_pid"] != pid and ger.status().saude_ok:
            novo = est["servidor_pid"]
            break
        time.sleep(0.5)
    assert novo, "o supervisor não religou o servidor"


def test_rede_sem_supervisor_explica_o_que_fazer(ger):
    rede = Gerenciador(RAIZ, ger.config_path, forcar_rede=True)
    with pytest.raises(ErroGerenciador, match="Ativar supervisor"):
        rede.ligar()


def test_consulta_e_atualizar_supervisor_pela_rede(sup, ger):
    rede = Gerenciador(RAIZ, ger.config_path, forcar_rede=True)
    copia = rede.copia_para_consulta()  # antes travava: o supervisor mandava o comando a si mesmo
    assert "despesas_consulta.db" in str(copia)
    antigo = ger.estado_supervisor()["supervisor_pid"]
    assert "reiniciando" in rede.reiniciar_supervisor()
    limite = time.time() + 45
    while time.time() < limite:
        ger._proc.poll()  # colhe o supervisor antigo (no Linux ele ficaria zumbi)
        est = ger.estado_supervisor() or {}
        if est.get("vivo") and est.get("supervisor_pid") != antigo and ger.status().saude_ok:
            break
        time.sleep(0.5)
    else:
        raise AssertionError("o novo supervisor não assumiu")
    assert ger.estado_supervisor()["supervisor_pid"] != antigo


def test_estado_json_resiste_a_leitor_com_arquivo_aberto(tmp_path, monkeypatch):
    from despesas import supervisor
    destino = tmp_path / "estado.json"

    def nega(*a, **k):
        raise PermissionError("Acesso negado (arquivo aberto por outro processo)")
    monkeypatch.setattr(supervisor.os, "replace", nega)
    monkeypatch.setattr(supervisor.time, "sleep", lambda s: None)
    supervisor._escrever_json(destino, {"quando": time.time(), "x": 1})
    assert destino.exists() and not (tmp_path / "estado.json.tmp").exists()
    assert supervisor.ler_estado(tmp_path / "config.ini") is None  # pasta controle inexistente: sem erro
