"""Backup consistente do banco (API de backup do SQLite), retenção e restauração."""
from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import Config

log = logging.getLogger("despesas.backup")
PADRAO = re.compile(r"^despesas_(\d{8})_(\d{6})(?:_(\d+))?\.db$")
_trava = threading.Lock()


def fazer_backup(cfg: Config) -> Path:
    """Gera um arquivo de backup íntegro, mesmo com o sistema em uso. Retorna o caminho."""
    with _trava:
        cfg.backup_dir.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = cfg.backup_dir / f"despesas_{carimbo}.db"
        n = 1
        while destino.exists():
            n += 1
            destino = cfg.backup_dir / f"despesas_{carimbo}_{n}.db"
        temporario = destino.with_suffix(".tmp")
        origem = sqlite3.connect(str(cfg.db_path), timeout=30)
        copia = sqlite3.connect(str(temporario))
        try:
            origem.backup(copia)
            resultado = copia.execute("PRAGMA integrity_check").fetchone()[0]
            if resultado != "ok":
                raise RuntimeError(f"Backup falhou na verificação de integridade: {resultado}")
        finally:
            copia.close()
            origem.close()
        os.replace(temporario, destino)
        log.info("Backup criado: %s", destino)
        aplicar_retencao(cfg)
        return destino


def listar_backups(cfg: Config) -> list[dict]:
    if not cfg.backup_dir.is_dir():
        return []
    itens = []
    for p in cfg.backup_dir.iterdir():
        if p.is_file() and PADRAO.match(p.name):
            st = p.stat()
            itens.append({"nome": p.name, "tamanho": st.st_size,
                          "quando": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M:%S")})
    return sorted(itens, key=lambda i: i["nome"], reverse=True)


def aplicar_retencao(cfg: Config) -> None:
    """Mantém os N backups mais recentes (nunca apaga todos)."""
    itens = listar_backups(cfg)
    for antigo in itens[max(cfg.backup_manter, 1):]:
        try:
            (cfg.backup_dir / antigo["nome"]).unlink()
            log.info("Backup antigo removido: %s", antigo["nome"])
        except OSError as e:
            log.warning("Não foi possível remover %s: %s", antigo["nome"], e)


def _ja_tem_hoje(cfg: Config) -> bool:
    hoje = datetime.now().strftime("%Y%m%d")
    return any(i["nome"].startswith(f"despesas_{hoje}_") for i in listar_backups(cfg))


def _verificar_agendado(cfg: Config) -> None:
    agora = datetime.now()
    hh, mm = (int(x) for x in cfg.backup_hora.split(":"))
    if (agora.hour, agora.minute) >= (hh, mm) and not _ja_tem_hoje(cfg):
        try:
            fazer_backup(cfg)
        except Exception:
            log.exception("Falha no backup automático")


def iniciar_agendador(cfg: Config) -> None:
    """Thread que faz 1 backup por dia, a partir do horário configurado (e ao iniciar, se perdeu o horário)."""
    if not cfg.backup_ativo:
        log.info("Backup automático desativado no config.ini")
        return

    def laco():
        while True:
            _verificar_agendado(cfg)
            time.sleep(60)

    threading.Thread(target=laco, name="backup-agendado", daemon=True).start()
    log.info("Backup automático diário a partir das %s em %s", cfg.backup_hora, cfg.backup_dir)


def restaurar(cfg: Config, arquivo: str | Path) -> Path:
    """Substitui o banco atual pelo backup informado. O servidor deve estar parado.

    O banco atual é preservado em dados/antes_restauracao_<data>.db.
    """
    origem = Path(arquivo)
    if not origem.is_file():
        origem = cfg.backup_dir / str(arquivo)
    if not origem.is_file():
        raise FileNotFoundError(f"Backup não encontrado: {arquivo}")
    chk = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    try:
        if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("O arquivo de backup está corrompido; restauração cancelada.")
        chk.execute("SELECT COUNT(*) FROM lancamentos").fetchone()
    finally:
        chk.close()

    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    guarda = None
    if cfg.db_path.exists():
        # se o servidor estiver rodando, não conseguimos o lock exclusivo
        teste = sqlite3.connect(str(cfg.db_path), timeout=1)
        try:
            teste.execute("BEGIN EXCLUSIVE")
            teste.execute("ROLLBACK")
        except sqlite3.OperationalError:
            raise RuntimeError("O banco está em uso. Pare o servidor antes de restaurar.")
        finally:
            teste.close()
        guarda = cfg.db_path.parent / f"antes_restauracao_{datetime.now():%Y%m%d_%H%M%S}.db"
        src = sqlite3.connect(str(cfg.db_path))
        dst = sqlite3.connect(str(guarda))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    for sufixo in ("-wal", "-shm"):
        extra = Path(str(cfg.db_path) + sufixo)
        if extra.exists():
            extra.unlink()
    shutil.copyfile(origem, cfg.db_path)
    log.info("Banco restaurado de %s (anterior guardado em %s)", origem, guarda)
    return guarda or cfg.db_path
