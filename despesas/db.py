"""Banco SQLite (modo WAL). Apenas o processo do servidor deve abrir este arquivo."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

VERSAO_SCHEMA = 1

CATEGORIAS_INICIAIS = [
    "Funcionários",
    "Impostos",
    "Imobilizados",
    "Serviços",
    "Manutenção",
    "Aluguel",
    "Outros",
    "Veículos",
]

SCHEMA = [
    """CREATE TABLE usuarios (
        id INTEGER PRIMARY KEY,
        usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
        nome TEXT NOT NULL,
        senha_hash TEXT NOT NULL,
        perfil TEXT NOT NULL CHECK (perfil IN ('admin','lancador','consulta')),
        ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
        falhas INTEGER NOT NULL DEFAULT 0,
        bloqueado_ate TEXT,
        trocar_senha INTEGER NOT NULL DEFAULT 0 CHECK (trocar_senha IN (0,1)),
        criado_em TEXT NOT NULL
    )""",
    """CREATE TABLE categorias (
        id INTEGER PRIMARY KEY,
        nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
        ordem INTEGER NOT NULL,
        ativa INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0,1))
    )""",
    """CREATE TABLE lancamentos (
        id INTEGER PRIMARY KEY,
        data TEXT NOT NULL CHECK (data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
        descricao TEXT NOT NULL,
        categoria_id INTEGER NOT NULL REFERENCES categorias(id),
        valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
        criado_por INTEGER NOT NULL REFERENCES usuarios(id),
        criado_em TEXT NOT NULL,
        alterado_por INTEGER REFERENCES usuarios(id),
        alterado_em TEXT,
        versao INTEGER NOT NULL DEFAULT 1,
        excluido INTEGER NOT NULL DEFAULT 0 CHECK (excluido IN (0,1)),
        excluido_por INTEGER REFERENCES usuarios(id),
        excluido_em TEXT
    )""",
    "CREATE INDEX ix_lancamentos_data ON lancamentos (data, id)",
    """CREATE TABLE auditoria (
        id INTEGER PRIMARY KEY,
        quando TEXT NOT NULL,
        usuario TEXT NOT NULL,
        acao TEXT NOT NULL,
        lancamento_id INTEGER,
        detalhe TEXT NOT NULL DEFAULT ''
    )""",
]


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conectar(caminho: str | Path) -> sqlite3.Connection:
    """Abre uma conexão (autocommit; transações explícitas via transacao())."""
    conn = sqlite3.connect(str(caminho), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


@contextmanager
def transacao(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK se der erro): escritores se enfileiram."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def iniciar(caminho: str | Path) -> None:
    """Cria a pasta e o banco (se não existirem) e aplica o schema."""
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conn = conectar(caminho)
    try:
        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        if versao > VERSAO_SCHEMA:
            raise RuntimeError(
                f"O banco foi criado por uma versão mais nova do sistema (schema {versao})."
            )
        if versao == 0:
            with transacao(conn):
                for sql in SCHEMA:
                    conn.execute(sql)
                for i, nome in enumerate(CATEGORIAS_INICIAIS, start=1):
                    conn.execute("INSERT INTO categorias (nome, ordem) VALUES (?, ?)", (nome, i))
                conn.execute(f"PRAGMA user_version = {VERSAO_SCHEMA}")
    finally:
        conn.close()
