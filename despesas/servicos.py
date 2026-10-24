"""Regras de negócio: usuários, categorias, lançamentos e resumo mensal."""
from __future__ import annotations

import calendar
import re
import sqlite3
from datetime import date, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from . import money
from .db import agora, transacao

NIVEL = {"consulta": 1, "lancador": 2, "admin": 3}
PERFIS = {
    "admin": "Administrador",
    "lancador": "Lançador",
    "consulta": "Consulta",
}
SENHA_MIN = 8
DESCRICAO_MAX = 200
ANO_MIN, ANO_MAX = 2000, 2099

# hash fixo usado para gastar o mesmo tempo quando o usuário não existe
_HASH_FALSO = generate_password_hash("senha-falsa-para-igualar-tempo", method="pbkdf2:sha256")


class ErroNegocio(Exception):
    """Erro esperado, com mensagem em português para mostrar ao usuário."""


class SemPermissao(ErroNegocio):
    pass


# ------------------------------------------------------------------ utilidades
def tem_nivel(usuario, minimo: str) -> bool:
    return bool(usuario) and NIVEL.get(usuario["perfil"], 0) >= NIVEL[minimo]


def exigir_nivel(usuario, minimo: str) -> None:
    if not tem_nivel(usuario, minimo):
        raise SemPermissao("Você não tem permissão para esta ação.")


def pode_alterar(usuario, lancamento) -> bool:
    """Admin altera qualquer lançamento; lançador só os que ele mesmo criou."""
    if not usuario:
        return False
    if usuario["perfil"] == "admin":
        return True
    return usuario["perfil"] == "lancador" and lancamento["criado_por"] == usuario["id"]


def registrar_auditoria(conn, usuario_txt: str, acao: str, lancamento_id=None, detalhe: str = "") -> None:
    conn.execute(
        "INSERT INTO auditoria (quando, usuario, acao, lancamento_id, detalhe) VALUES (?,?,?,?,?)",
        (agora(), usuario_txt, acao, lancamento_id, detalhe),
    )


def validar_senha(senha: str) -> None:
    if senha is None or len(senha) < SENHA_MIN:
        raise ErroNegocio(f"A senha deve ter pelo menos {SENHA_MIN} caracteres.")
    if len(senha) > 200:
        raise ErroNegocio("Senha muito longa.")


def _hash(senha: str) -> str:
    return generate_password_hash(senha, method="pbkdf2:sha256")


# -------------------------------------------------------------------- usuários
def criar_usuario(conn, usuario: str, nome: str, senha: str, perfil: str,
                  trocar_senha: bool = True, autor: str = "sistema") -> int:
    usuario = (usuario or "").strip()
    nome = (nome or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", usuario):
        raise ErroNegocio("Usuário deve ter de 3 a 30 caracteres: letras, números, ponto, hífen ou _.")
    if not 1 <= len(nome) <= 80:
        raise ErroNegocio("Informe o nome (até 80 caracteres).")
    if perfil not in NIVEL:
        raise ErroNegocio("Perfil inválido.")
    validar_senha(senha)
    try:
        with transacao(conn):
            cur = conn.execute(
                "INSERT INTO usuarios (usuario, nome, senha_hash, perfil, trocar_senha, criado_em) "
                "VALUES (?,?,?,?,?,?)",
                (usuario, nome, _hash(senha), perfil, int(trocar_senha), agora()),
            )
            registrar_auditoria(conn, autor, "usuario_criado", None, f"{usuario} ({perfil})")
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ErroNegocio(f"Já existe um usuário '{usuario}'.")


def autenticar(conn, usuario: str, senha: str, max_falhas: int, bloqueio_min: int):
    """Retorna a linha do usuário ou levanta ErroNegocio. Bloqueia após falhas seguidas."""
    generico = ErroNegocio("Usuário ou senha inválidos.")
    u = conn.execute("SELECT * FROM usuarios WHERE usuario = ?", ((usuario or "").strip(),)).fetchone()
    if u is None or not u["ativo"]:
        check_password_hash(_HASH_FALSO, senha or "")
        raise generico
    if u["bloqueado_ate"] and u["bloqueado_ate"] > agora():
        raise ErroNegocio("Acesso temporariamente bloqueado por excesso de tentativas. Aguarde alguns minutos.")
    if check_password_hash(u["senha_hash"], senha or ""):
        if u["falhas"] or u["bloqueado_ate"]:
            with transacao(conn):
                conn.execute("UPDATE usuarios SET falhas=0, bloqueado_ate=NULL WHERE id=?", (u["id"],))
        return u
    with transacao(conn):
        falhas = u["falhas"] + 1
        if falhas >= max_falhas:
            ate = (datetime.now() + timedelta(minutes=bloqueio_min)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE usuarios SET falhas=0, bloqueado_ate=? WHERE id=?", (ate, u["id"]))
            registrar_auditoria(conn, u["usuario"], "login_bloqueado", None, f"{falhas} tentativas erradas")
        else:
            conn.execute("UPDATE usuarios SET falhas=? WHERE id=?", (falhas, u["id"]))
    raise generico


def alterar_senha(conn, usuario_id: int, nova: str, trocar_senha: bool = False, autor: str = "") -> None:
    validar_senha(nova)
    with transacao(conn):
        cur = conn.execute(
            "UPDATE usuarios SET senha_hash=?, trocar_senha=?, falhas=0, bloqueado_ate=NULL WHERE id=?",
            (_hash(nova), int(trocar_senha), usuario_id),
        )
        if cur.rowcount == 0:
            raise ErroNegocio("Usuário não encontrado.")
        alvo = conn.execute("SELECT usuario FROM usuarios WHERE id=?", (usuario_id,)).fetchone()["usuario"]
        registrar_auditoria(conn, autor or alvo, "senha_alterada", None, alvo)


def listar_usuarios(conn):
    return conn.execute("SELECT * FROM usuarios ORDER BY usuario COLLATE NOCASE").fetchall()


def atualizar_usuario(conn, ator, usuario_id: int, nome: str, perfil: str, ativo: bool) -> None:
    exigir_nivel(ator, "admin")
    nome = (nome or "").strip()
    if not 1 <= len(nome) <= 80:
        raise ErroNegocio("Informe o nome (até 80 caracteres).")
    if perfil not in NIVEL:
        raise ErroNegocio("Perfil inválido.")
    with transacao(conn):
        alvo = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        if alvo is None:
            raise ErroNegocio("Usuário não encontrado.")
        if alvo["id"] == ator["id"] and (perfil != "admin" or not ativo):
            raise ErroNegocio("Você não pode remover seu próprio acesso de administrador.")
        if alvo["perfil"] == "admin" and (perfil != "admin" or not ativo):
            outros = conn.execute(
                "SELECT COUNT(*) FROM usuarios WHERE perfil='admin' AND ativo=1 AND id<>?", (usuario_id,)
            ).fetchone()[0]
            if outros == 0:
                raise ErroNegocio("Deve existir pelo menos um administrador ativo.")
        conn.execute(
            "UPDATE usuarios SET nome=?, perfil=?, ativo=? WHERE id=?",
            (nome, perfil, int(ativo), usuario_id),
        )
        registrar_auditoria(conn, ator["usuario"], "usuario_alterado", None,
                            f"{alvo['usuario']}: perfil={perfil}, ativo={int(ativo)}")


# ------------------------------------------------------------------ categorias
def listar_categorias(conn, apenas_ativas: bool = False):
    sql = "SELECT * FROM categorias"
    if apenas_ativas:
        sql += " WHERE ativa=1"
    return conn.execute(sql + " ORDER BY ordem, id").fetchall()


def _nome_categoria(nome: str) -> str:
    nome = re.sub(r"\s+", " ", (nome or "").strip())
    if not 1 <= len(nome) <= 40:
        raise ErroNegocio("O nome da categoria deve ter de 1 a 40 caracteres.")
    return nome


def criar_categoria(conn, ator, nome: str) -> None:
    exigir_nivel(ator, "admin")
    nome = _nome_categoria(nome)
    try:
        with transacao(conn):
            prox = conn.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM categorias").fetchone()[0]
            conn.execute("INSERT INTO categorias (nome, ordem) VALUES (?,?)", (nome, prox))
            registrar_auditoria(conn, ator["usuario"], "categoria_criada", None, nome)
    except sqlite3.IntegrityError:
        raise ErroNegocio(f"Já existe a categoria '{nome}'.")


def renomear_categoria(conn, ator, cat_id: int, nome: str) -> None:
    exigir_nivel(ator, "admin")
    nome = _nome_categoria(nome)
    try:
        with transacao(conn):
            antigo = conn.execute("SELECT nome FROM categorias WHERE id=?", (cat_id,)).fetchone()
            if antigo is None:
                raise ErroNegocio("Categoria não encontrada.")
            conn.execute("UPDATE categorias SET nome=? WHERE id=?", (nome, cat_id))
            registrar_auditoria(conn, ator["usuario"], "categoria_renomeada", None, f"{antigo['nome']} -> {nome}")
    except sqlite3.IntegrityError:
        raise ErroNegocio(f"Já existe a categoria '{nome}'.")


def definir_ativa(conn, ator, cat_id: int, ativa: bool) -> None:
    exigir_nivel(ator, "admin")
    with transacao(conn):
        cat = conn.execute("SELECT * FROM categorias WHERE id=?", (cat_id,)).fetchone()
        if cat is None:
            raise ErroNegocio("Categoria não encontrada.")
        if not ativa:
            restantes = conn.execute(
                "SELECT COUNT(*) FROM categorias WHERE ativa=1 AND id<>?", (cat_id,)
            ).fetchone()[0]
            if restantes == 0:
                raise ErroNegocio("Deve existir pelo menos uma categoria ativa.")
        conn.execute("UPDATE categorias SET ativa=? WHERE id=?", (int(ativa), cat_id))
        registrar_auditoria(conn, ator["usuario"], "categoria_ativada" if ativa else "categoria_desativada",
                            None, cat["nome"])


def definir_mostrar_resumo(conn, ator, cat_id: int, mostrar: bool) -> None:
    """Define se a categoria aparece nos cards de resumo do mês."""
    exigir_nivel(ator, "admin")
    with transacao(conn):
        cat = conn.execute("SELECT * FROM categorias WHERE id=?", (cat_id,)).fetchone()
        if cat is None:
            raise ErroNegocio("Categoria não encontrada.")
        conn.execute("UPDATE categorias SET mostrar_resumo=? WHERE id=?", (int(mostrar), cat_id))
        registrar_auditoria(conn, ator["usuario"],
                            "categoria_resumo_ativado" if mostrar else "categoria_resumo_desativado",
                            None, cat["nome"])


def mover_categoria(conn, ator, cat_id: int, direcao: str) -> None:
    """direcao: 'sobe' ou 'desce' (troca a ordem com a vizinha)."""
    exigir_nivel(ator, "admin")
    with transacao(conn):
        todas = conn.execute("SELECT id FROM categorias ORDER BY ordem, id").fetchall()
        ids = [r["id"] for r in todas]
        if cat_id not in ids:
            raise ErroNegocio("Categoria não encontrada.")
        i = ids.index(cat_id)
        j = i - 1 if direcao == "sobe" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
        for ordem, cid in enumerate(ids, start=1):
            conn.execute("UPDATE categorias SET ordem=? WHERE id=?", (ordem, cid))


# ------------------------------------------------------------------ lançamentos
def _validar_dados(conn, data_txt, descricao, categoria_id, valor_txt, categoria_atual=None):
    try:
        d = date.fromisoformat((data_txt or "").strip())
    except ValueError:
        raise ErroNegocio("Data inválida.")
    if not ANO_MIN <= d.year <= ANO_MAX:
        raise ErroNegocio(f"O ano deve estar entre {ANO_MIN} e {ANO_MAX}.")
    descricao = re.sub(r"\s+", " ", (descricao or "").strip())
    if not descricao:
        raise ErroNegocio("Informe a descrição.")
    if len(descricao) > DESCRICAO_MAX:
        raise ErroNegocio(f"Descrição muito longa (máximo {DESCRICAO_MAX} caracteres).")
    if any(ord(ch) < 32 for ch in descricao):
        raise ErroNegocio("A descrição contém caracteres inválidos.")
    try:
        cid = int(categoria_id)
    except (TypeError, ValueError):
        raise ErroNegocio("Escolha a categoria.")
    cat = conn.execute("SELECT * FROM categorias WHERE id=?", (cid,)).fetchone()
    if cat is None:
        raise ErroNegocio("Categoria inválida.")
    if not cat["ativa"] and cid != categoria_atual:
        raise ErroNegocio(f"A categoria '{cat['nome']}' está desativada.")
    try:
        centavos = money.parse_valor(valor_txt)
    except ValueError as e:
        raise ErroNegocio(str(e))
    return d.isoformat(), descricao, cid, centavos


def criar_lancamento(conn, usuario, data_txt, descricao, categoria_id, valor_txt) -> int:
    exigir_nivel(usuario, "lancador")
    data, desc, cid, centavos = _validar_dados(conn, data_txt, descricao, categoria_id, valor_txt)
    with transacao(conn):
        cur = conn.execute(
            "INSERT INTO lancamentos (data, descricao, categoria_id, valor_centavos, criado_por, criado_em) "
            "VALUES (?,?,?,?,?,?)",
            (data, desc, cid, centavos, usuario["id"], agora()),
        )
        registrar_auditoria(conn, usuario["usuario"], "lancamento_criado", cur.lastrowid,
                            f"{data} | {desc} | cat={cid} | {money.formatar(centavos)}")
        return cur.lastrowid


def obter_lancamento(conn, lanc_id: int):
    return conn.execute(
        "SELECT l.*, c.nome AS categoria_nome, u.nome AS criador_nome, a.nome AS alterador_nome "
        "FROM lancamentos l JOIN categorias c ON c.id=l.categoria_id "
        "JOIN usuarios u ON u.id=l.criado_por LEFT JOIN usuarios a ON a.id=l.alterado_por "
        "WHERE l.id=?", (lanc_id,)
    ).fetchone()


def _carregar_para_alterar(conn, usuario, lanc_id, versao):
    atual = conn.execute("SELECT * FROM lancamentos WHERE id=?", (lanc_id,)).fetchone()
    if atual is None:
        raise ErroNegocio("Lançamento não encontrado.")
    if not pode_alterar(usuario, atual):
        raise SemPermissao("Você não tem permissão para alterar este lançamento.")
    if int(versao) != atual["versao"]:
        raise ErroNegocio("Este lançamento foi alterado por outra pessoa enquanto você o editava. "
                          "Confira os dados atuais e tente novamente.")
    return atual


def editar_lancamento(conn, usuario, lanc_id, versao, data_txt, descricao, categoria_id, valor_txt) -> None:
    exigir_nivel(usuario, "lancador")
    with transacao(conn):
        atual = _carregar_para_alterar(conn, usuario, lanc_id, versao)
        if atual["excluido"]:
            raise ErroNegocio("Este lançamento foi excluído.")
        data, desc, cid, centavos = _validar_dados(conn, data_txt, descricao, categoria_id, valor_txt,
                                                   categoria_atual=atual["categoria_id"])
        conn.execute(
            "UPDATE lancamentos SET data=?, descricao=?, categoria_id=?, valor_centavos=?, "
            "alterado_por=?, alterado_em=?, versao=versao+1 WHERE id=?",
            (data, desc, cid, centavos, usuario["id"], agora(), lanc_id),
        )
        registrar_auditoria(
            conn, usuario["usuario"], "lancamento_editado", lanc_id,
            f"antes: {atual['data']} | {atual['descricao']} | cat={atual['categoria_id']} | "
            f"{money.formatar(atual['valor_centavos'])} -> depois: {data} | {desc} | cat={cid} | "
            f"{money.formatar(centavos)}",
        )


def excluir_lancamento(conn, usuario, lanc_id, versao) -> None:
    exigir_nivel(usuario, "lancador")
    with transacao(conn):
        atual = _carregar_para_alterar(conn, usuario, lanc_id, versao)
        if atual["excluido"]:
            raise ErroNegocio("Este lançamento já foi excluído.")
        conn.execute(
            "UPDATE lancamentos SET excluido=1, excluido_por=?, excluido_em=?, versao=versao+1 WHERE id=?",
            (usuario["id"], agora(), lanc_id),
        )
        registrar_auditoria(conn, usuario["usuario"], "lancamento_excluido", lanc_id,
                            f"{atual['data']} | {atual['descricao']} | {money.formatar(atual['valor_centavos'])}")


def restaurar_lancamento(conn, usuario, lanc_id, versao) -> None:
    exigir_nivel(usuario, "admin")
    with transacao(conn):
        atual = _carregar_para_alterar(conn, usuario, lanc_id, versao)
        if not atual["excluido"]:
            raise ErroNegocio("Este lançamento não está excluído.")
        conn.execute(
            "UPDATE lancamentos SET excluido=0, excluido_por=NULL, excluido_em=NULL, "
            "alterado_por=?, alterado_em=?, versao=versao+1 WHERE id=?",
            (usuario["id"], agora(), lanc_id),
        )
        registrar_auditoria(conn, usuario["usuario"], "lancamento_restaurado", lanc_id,
                            f"{atual['data']} | {atual['descricao']}")


# ---------------------------------------------------------------------- resumo
def limites_mes(ano: int, mes: int) -> tuple[str, str]:
    ini = date(ano, mes, 1)
    prox = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return ini.isoformat(), prox.isoformat()


def resumo_mes(conn, ano: int, mes: int, incluir_excluidos: bool = False) -> dict:
    """Tudo o que a tela e os relatórios precisam de um mês.

    colunas: categorias ativas (na ordem configurada) + inativas que tenham lançamento no mês.
    linhas: lançamentos não excluídos, por data e ordem de inclusão.
    totais: centavos por categoria (id). total_geral: soma de todos os lançamentos.
    """
    if not (ANO_MIN <= ano <= ANO_MAX and 1 <= mes <= 12):
        raise ErroNegocio("Mês/ano inválido.")
    ini, fim = limites_mes(ano, mes)
    rows = conn.execute(
        "SELECT l.id, l.data, l.descricao, l.categoria_id, l.valor_centavos AS valor, l.versao, "
        "l.criado_por, l.criado_em, l.alterado_em, l.excluido, l.excluido_em, "
        "u.nome AS criador_nome, x.nome AS excluidor_nome "
        "FROM lancamentos l JOIN usuarios u ON u.id=l.criado_por "
        "LEFT JOIN usuarios x ON x.id=l.excluido_por "
        "WHERE l.data >= ? AND l.data < ? ORDER BY l.data, l.valor_centavos DESC, l.id", (ini, fim)
    ).fetchall()
    linhas, excluidos = [], []
    for r in rows:
        d = dict(r)
        d["dia"] = int(d["data"][8:10])
        (excluidos if d["excluido"] else linhas).append(d)
    usadas = {l["categoria_id"] for l in linhas}
    colunas = [dict(c) for c in listar_categorias(conn) if c["ativa"] or c["id"] in usadas]
    totais = {c["id"]: 0 for c in colunas}
    for l in linhas:
        totais[l["categoria_id"]] += l["valor"]
    resultado = {
        "ano": ano,
        "mes": mes,
        "colunas": colunas,
        "linhas": linhas,
        "totais": totais,
        "total_geral": sum(totais.values()),
    }
    if incluir_excluidos:
        resultado["excluidos"] = excluidos
    return resultado


def mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def mes_seguinte(ano: int, mes: int) -> tuple[int, int]:
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def ultimo_dia(ano: int, mes: int) -> int:
    return calendar.monthrange(ano, mes)[1]
