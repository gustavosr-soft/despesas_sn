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
    cfg.write_text(f"[servidor]\nhost = 127.0.0.1\nporta = {porta}\n", encoding="utf-8")
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
