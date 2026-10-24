"""Leitura e validação do arquivo config.ini."""
from __future__ import annotations

import configparser
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path


class ErroConfig(Exception):
    """Problema no config.ini (mensagem já em português, pronta para mostrar)."""


PADROES = {
    "servidor": {"host": "0.0.0.0", "porta": "8080", "threads": "8"},
    "banco": {"caminho": "dados/despesas.db"},
    "backup": {"ativo": "sim", "pasta": "backups", "hora": "22:00", "manter": "30"},
    "logs": {"pasta": "logs", "nivel": "INFO"},
    "seguranca": {
        "sessao_minutos": "60",
        "tentativas_max": "5",
        "bloqueio_minutos": "5",
        "chave_secreta": "",
        "cookie_seguro": "nao",
    },
    "relatorios": {"empresa": ""},
}


@dataclass(frozen=True)
class Config:
    arquivo: Path
    base_dir: Path
    host: str
    porta: int
    threads: int
    db_path: Path
    backup_ativo: bool
    backup_dir: Path
    backup_hora: str
    backup_manter: int
    logs_dir: Path
    log_nivel: str
    sessao_minutos: int
    tentativas_max: int
    bloqueio_minutos: int
    chave_secreta: str
    cookie_seguro: bool
    empresa: str


def caminho_padrao() -> Path:
    env = os.environ.get("DESPESAS_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "config.ini"


def _inteiro(valor: str, nome: str, minimo: int, maximo: int) -> int:
    try:
        n = int(valor.strip())
    except ValueError:
        raise ErroConfig(f"config.ini: '{nome}' deve ser um número inteiro (valor atual: '{valor}').")
    if not minimo <= n <= maximo:
        raise ErroConfig(f"config.ini: '{nome}' deve estar entre {minimo} e {maximo} (valor atual: {n}).")
    return n


def _booleano(valor: str, nome: str) -> bool:
    v = valor.strip().lower()
    if v in ("sim", "s", "true", "1", "yes"):
        return True
    if v in ("nao", "não", "n", "false", "0", "no"):
        return False
    raise ErroConfig(f"config.ini: '{nome}' deve ser 'sim' ou 'nao' (valor atual: '{valor}').")


def carregar(caminho: str | Path | None = None) -> Config:
    arq = Path(caminho) if caminho else caminho_padrao()
    if not arq.is_file():
        raise ErroConfig(f"Arquivo de configuração não encontrado: {arq}")
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_dict(PADROES)
    try:
        cp.read(arq, encoding="utf-8-sig")
    except configparser.Error as e:
        raise ErroConfig(f"config.ini inválido: {e}")
    base = arq.resolve().parent

    def caminho_rel(valor: str, nome: str) -> Path:
        v = valor.strip()
        if not v:
            raise ErroConfig(f"config.ini: '{nome}' não pode ficar vazio.")
        p = Path(v)
        return p if p.is_absolute() else (base / p)

    hora = cp["backup"]["hora"].strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora):
        raise ErroConfig(f"config.ini: [backup] hora deve estar no formato HH:MM (valor atual: '{hora}').")

    nivel = cp["logs"]["nivel"].strip().upper()
    if nivel not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ErroConfig("config.ini: [logs] nivel deve ser DEBUG, INFO, WARNING ou ERROR.")

    db_path = caminho_rel(cp["banco"]["caminho"], "[banco] caminho")

    chave = cp["seguranca"]["chave_secreta"].strip()
    if not chave:
        chave = _chave_automatica(db_path.parent)

    return Config(
        arquivo=arq.resolve(),
        base_dir=base,
        host=cp["servidor"]["host"].strip() or "0.0.0.0",
        porta=_inteiro(cp["servidor"]["porta"], "[servidor] porta", 1, 65535),
        threads=_inteiro(cp["servidor"]["threads"], "[servidor] threads", 1, 64),
        db_path=db_path,
        backup_ativo=_booleano(cp["backup"]["ativo"], "[backup] ativo"),
        backup_dir=caminho_rel(cp["backup"]["pasta"], "[backup] pasta"),
        backup_hora=hora,
        backup_manter=_inteiro(cp["backup"]["manter"], "[backup] manter", 1, 3650),
        logs_dir=caminho_rel(cp["logs"]["pasta"], "[logs] pasta"),
        log_nivel=nivel,
        sessao_minutos=_inteiro(cp["seguranca"]["sessao_minutos"], "[seguranca] sessao_minutos", 5, 1440),
        tentativas_max=_inteiro(cp["seguranca"]["tentativas_max"], "[seguranca] tentativas_max", 3, 20),
        bloqueio_minutos=_inteiro(cp["seguranca"]["bloqueio_minutos"], "[seguranca] bloqueio_minutos", 1, 1440),
        chave_secreta=chave,
        cookie_seguro=_booleano(cp["seguranca"]["cookie_seguro"], "[seguranca] cookie_seguro"),
        empresa=cp["relatorios"]["empresa"].strip(),
    )


def _chave_automatica(pasta_dados: Path) -> str:
    """Gera (uma vez) e reutiliza uma chave secreta guardada ao lado do banco."""
    pasta_dados.mkdir(parents=True, exist_ok=True)
    arq = pasta_dados / "chave_secreta.txt"
    if arq.is_file():
        chave = arq.read_text(encoding="ascii").strip()
        if len(chave) >= 32:
            return chave
    chave = secrets.token_hex(32)
    arq.write_text(chave, encoding="ascii")
    return chave
