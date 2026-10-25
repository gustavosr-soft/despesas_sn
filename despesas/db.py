"""Banco SQLite (modo WAL). Apenas o processo do servidor deve abrir este arquivo."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

log = logging.getLogger("despesas.db")

VERSAO_SCHEMA = 2

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
        ativa INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0,1)),
        mostrar_resumo INTEGER NOT NULL DEFAULT 1 CHECK (mostrar_resumo IN (0,1))
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


def _copia_seguranca(caminho: Path, rotulo: str) -> Path:
    """Copia íntegra do banco (via API de backup do SQLite) antes de uma migração
    de schema, para nunca depender só da migração dando certo."""
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = caminho.with_name(f"{caminho.stem}_antes_{rotulo}_{carimbo}.db")
    origem = sqlite3.connect(str(caminho))
    copia = sqlite3.connect(str(destino))
    try:
        origem.backup(copia)
    finally:
        copia.close()
        origem.close()
    return destino


def iniciar(caminho: str | Path) -> str:
    """Cria a pasta e o banco (se não existirem) e aplica o schema.

    Retorna "criado" (banco novo e vazio), "migrado" (schema antigo atualizado)
    ou "ok" (já estava na versão atual) — para o chamador decidir o que avisar.
    Nunca apaga dados: ao migrar um schema existente, guarda uma cópia de
    segurança ao lado do banco antes de alterar a estrutura.
    """
    caminho = Path(caminho)
    era_novo = not caminho.exists()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = conectar(caminho)
    try:
        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        if versao > VERSAO_SCHEMA:
            raise RuntimeError(
                f"O banco foi criado por uma versão mais nova do sistema (schema {versao}, "
                f"esta versão só entende até {VERSAO_SCHEMA}). Caminho: {caminho}"
            )
        if versao == 0:
            with transacao(conn):
                for sql in SCHEMA:
                    conn.execute(sql)
                for i, nome in enumerate(CATEGORIAS_INICIAIS, start=1):
                    conn.execute("INSERT INTO categorias (nome, ordem) VALUES (?, ?)", (nome, i))
                conn.execute(f"PRAGMA user_version = {VERSAO_SCHEMA}")
            if era_novo:
                log.warning(
                    "BANCO NOVO E VAZIO criado em %s — se você esperava dados existentes, "
                    "PARE o servidor agora e confira o caminho 'banco > caminho' no config.ini: "
                    "pode estar apontando para a pasta errada.", caminho)
                return "criado"
            return "ok"
        if versao == 1:
            seguranca = _copia_seguranca(caminho, "migracao_v1_para_v2")
            log.info("Cópia de segurança antes da migração de schema: %s", seguranca)
            with transacao(conn):
                conn.execute("ALTER TABLE categorias ADD COLUMN mostrar_resumo INTEGER NOT NULL DEFAULT 1")
                conn.execute(f"PRAGMA user_version = {VERSAO_SCHEMA}")
            log.info("Banco migrado do schema 1 para o %s.", VERSAO_SCHEMA)
            return "migrado"
        return "ok"
    finally:
        conn.close()
