"""Aplicação web (Flask): login, lançamentos, relatórios e administração."""
from __future__ import annotations

import hmac
import logging
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request, session,
                   url_for)

from . import __version__, backup, db, money, reports, servicos
from .config import Config
from .servicos import ErroNegocio, SemPermissao

log = logging.getLogger("despesas.web")

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def criar_app(cfg: Config) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=cfg.chave_secreta,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=cfg.sessao_minutos),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cfg.cookie_seguro,
        MAX_CONTENT_LENGTH=64 * 1024,
        TEMPLATES_AUTO_RELOAD=False,
    )
    app.config["CFG"] = cfg
    caminho_abs = Path(cfg.db_path).resolve()
    status = db.iniciar(cfg.db_path)
    if status == "criado":
        log.warning("Servidor iniciado com um BANCO NOVO E VAZIO em: %s", caminho_abs)
    else:
        log.info("Servidor iniciado. Banco (%s): %s", status, caminho_abs)

    # ------------------------------------------------------------ infraestrutura
    def conexao() -> sqlite3.Connection:
        if "db" not in g:
            g.db = db.conectar(cfg.db_path)
        return g.db

    @app.teardown_appcontext
    def fechar(_exc):
        c = g.pop("db", None)
        if c is not None:
            c.close()

    def csrf_token() -> str:
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    @app.before_request
    def antes():
        g.usuario = None
        if request.endpoint in (None, "static", "saude"):
            return
        uid = session.get("uid")
        if uid:
            u = conexao().execute("SELECT * FROM usuarios WHERE id=? AND ativo=1", (uid,)).fetchone()
            if u:
                g.usuario = u
                session.permanent = True
            else:
                session.clear()
        if request.method == "POST":
            enviado = request.form.get("csrf", "")
            esperado = session.get("csrf", "")
            if not esperado or not hmac.compare_digest(enviado, esperado):
                abort(400)
        if g.usuario is None:
            if request.endpoint != "login":
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
        elif g.usuario["trocar_senha"] and request.endpoint not in ("senha", "sair"):
            return redirect(url_for("senha"))

    @app.after_request
    def depois(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'self'; object-src 'self'"
        )
        if resp.mimetype == "application/pdf":  # o leitor de PDF do navegador não gosta de CSP restritiva
            resp.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        if request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def contexto():
        return {
            "csrf_token": csrf_token,
            "usuario": g.get("usuario"),
            "pode": lambda nivel: servicos.tem_nivel(g.get("usuario"), nivel),
            "pode_alterar": lambda l: servicos.pode_alterar(g.get("usuario"), l),
            "meses": MESES,
            "empresa": cfg.empresa,
            "versao": __version__,
            "perfis": servicos.PERFIS,
        }

    @app.template_filter("brl")
    def brl(v):
        return money.formatar(v)

    @app.template_filter("campo_valor")
    def campo_valor(v):
        return money.para_campo(v)

    @app.template_filter("datahora")
    def datahora(v):
        if not v:
            return ""
        try:
            return datetime.strptime(v, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return v

    @app.template_filter("databr")
    def databr(v):
        try:
            return date.fromisoformat(v).strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return v

    def requer(nivel: str):
        def deco(f):
            @wraps(f)
            def interno(*a, **kw):
                if not servicos.tem_nivel(g.usuario, nivel):
                    abort(403)
                return f(*a, **kw)
            return interno
        return deco

    def checar_mes(ano: int, mes: int):
        if not (servicos.ANO_MIN <= ano <= servicos.ANO_MAX and 1 <= mes <= 12):
            abort(404)

    def destino_seguro(alvo: str | None) -> str:
        if alvo:
            p = urlparse(alvo)
            if not p.scheme and not p.netloc and alvo.startswith("/") and not alvo.startswith("//"):
                return alvo
        return url_for("inicio")

    # ------------------------------------------------------------------- acesso
    @app.get("/saude")
    def saude():
        try:
            db.conectar(cfg.db_path).execute("SELECT 1").fetchone()
            return Response("ok", mimetype="text/plain")
        except Exception:
            return Response("erro", status=503, mimetype="text/plain")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.usuario:
            return redirect(url_for("inicio"))
        if request.method == "POST":
            usuario = request.form.get("usuario", "")
            try:
                u = servicos.autenticar(conexao(), usuario, request.form.get("senha", ""),
                                        cfg.tentativas_max, cfg.bloqueio_minutos)
            except ErroNegocio as e:
                log.warning("Login recusado para '%s' (%s): %s", usuario[:40], request.remote_addr, e)
                flash(str(e), "erro")
                return render_template("login.html", usuario_digitado=usuario), 401
            session.clear()
            session["uid"] = u["id"]
            session.permanent = True
            log.info("Login: %s (%s)", u["usuario"], request.remote_addr)
            return redirect(destino_seguro(request.args.get("next")))
        return render_template("login.html", usuario_digitado="")

    @app.post("/sair")
    def sair():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/senha", methods=["GET", "POST"])
    def senha():
        if request.method == "POST":
            atual = request.form.get("atual", "")
            nova = request.form.get("nova", "")
            if nova != request.form.get("confirma", ""):
                flash("A confirmação não confere com a nova senha.", "erro")
            elif not servicos.check_password_hash(g.usuario["senha_hash"], atual):
                flash("Senha atual incorreta.", "erro")
            elif nova == atual:
                flash("A nova senha deve ser diferente da atual.", "erro")
            else:
                try:
                    servicos.alterar_senha(conexao(), g.usuario["id"], nova, False, g.usuario["usuario"])
                    flash("Senha alterada.", "ok")
                    return redirect(url_for("inicio"))
                except ErroNegocio as e:
                    flash(str(e), "erro")
        return render_template("senha.html")

    # --------------------------------------------------------------- lançamentos
    @app.get("/")
    def inicio():
        h = date.today()
        return redirect(url_for("mes", ano=h.year, mes=h.month))

    @app.get("/mes")
    def mes_redirect():
        h = date.today()
        try:
            ano = int(request.args.get("ano", h.year))
            m = int(request.args.get("mes", h.month))
        except ValueError:
            abort(404)
        checar_mes(ano, m)
        return redirect(url_for("mes", ano=ano, mes=m))

    def pagina_mes(ano: int, m: int, form: dict | None = None, status: int = 200):
        checar_mes(ano, m)
        ver_excluidos = request.args.get("excluidos") == "1" and servicos.tem_nivel(g.usuario, "admin")
        r = servicos.resumo_mes(conexao(), ano, m, incluir_excluidos=ver_excluidos)
        hoje = date.today()
        padrao = hoje if (hoje.year, hoje.month) == (ano, m) else date(ano, m, 1)
        form = form or {"data": padrao.isoformat(), "descricao": "", "categoria_id": "", "valor": ""}
        return render_template(
            "mes.html", r=r, form=form, ano=ano, mes=m,
            categorias=servicos.listar_categorias(conexao(), apenas_ativas=True),
            anterior=servicos.mes_anterior(ano, m), seguinte=servicos.mes_seguinte(ano, m),
            ver_excluidos=ver_excluidos,
            min_data=f"{ano:04d}-{m:02d}-01", max_data=f"{ano:04d}-{m:02d}-{servicos.ultimo_dia(ano, m):02d}",
        ), status

    @app.get("/mes/<int:ano>/<int:mes>")
    def mes(ano, mes):
        return pagina_mes(ano, mes)

    def mes_da_data(texto: str):
        try:
            d = date.fromisoformat(texto)
            if servicos.ANO_MIN <= d.year <= servicos.ANO_MAX:
                return d.year, d.month
        except ValueError:
            pass
        h = date.today()
        return h.year, h.month

    @app.post("/lancamentos")
    @requer("lancador")
    def lancamento_criar():
        f = request.form
        dados = {"data": f.get("data", ""), "descricao": f.get("descricao", ""),
                 "categoria_id": f.get("categoria_id", ""), "valor": f.get("valor", "")}
        ano, m = mes_da_data(dados["data"])
        try:
            servicos.criar_lancamento(conexao(), g.usuario, dados["data"], dados["descricao"],
                                      dados["categoria_id"], dados["valor"])
        except SemPermissao:
            abort(403)
        except ErroNegocio as e:
            flash(str(e), "erro")
            return pagina_mes(ano, m, form=dados, status=422)
        flash("Lançamento salvo.", "ok")
        return redirect(url_for("mes", ano=ano, mes=m))

    @app.route("/lancamentos/<int:lid>/editar", methods=["GET", "POST"])
    @requer("lancador")
    def lancamento_editar(lid):
        l = servicos.obter_lancamento(conexao(), lid)
        if l is None:
            abort(404)
        if not servicos.pode_alterar(g.usuario, l):
            abort(403)
        ano, m = int(l["data"][:4]), int(l["data"][5:7])
        if request.method == "POST":
            f = request.form
            try:
                servicos.editar_lancamento(conexao(), g.usuario, lid, f.get("versao", "0"), f.get("data", ""),
                                           f.get("descricao", ""), f.get("categoria_id", ""), f.get("valor", ""))
            except SemPermissao:
                abort(403)
            except ErroNegocio as e:
                flash(str(e), "erro")
                dados = {"data": f.get("data", ""), "descricao": f.get("descricao", ""),
                         "categoria_id": f.get("categoria_id", ""), "valor": f.get("valor", "")}
                return render_template("editar.html", l=l, form=dados, ano=ano, mes=m,
                                       categorias=_cats_para_edicao(l)), 422
            flash("Lançamento atualizado.", "ok")
            novo = servicos.obter_lancamento(conexao(), lid)
            return redirect(url_for("mes", ano=int(novo["data"][:4]), mes=int(novo["data"][5:7])))
        if l["excluido"]:
            flash("Este lançamento foi excluído.", "erro")
            return redirect(url_for("mes", ano=ano, mes=m))
        dados = {"data": l["data"], "descricao": l["descricao"], "categoria_id": str(l["categoria_id"]),
                 "valor": money.para_campo(l["valor_centavos"])}
        return render_template("editar.html", l=l, form=dados, ano=ano, mes=m, categorias=_cats_para_edicao(l))

    def _cats_para_edicao(l):
        return [c for c in servicos.listar_categorias(conexao()) if c["ativa"] or c["id"] == l["categoria_id"]]

    def _acao_lancamento(lid: int, funcao, mensagem: str):
        l = servicos.obter_lancamento(conexao(), lid)
        if l is None:
            abort(404)
        ano, m = int(l["data"][:4]), int(l["data"][5:7])
        try:
            funcao(conexao(), g.usuario, lid, request.form.get("versao", "0"))
            flash(mensagem, "ok")
        except SemPermissao:
            abort(403)
        except ErroNegocio as e:
            flash(str(e), "erro")
        extra = {"excluidos": "1"} if request.form.get("ver_excluidos") == "1" else {}
        return redirect(url_for("mes", ano=ano, mes=m, **extra))

    @app.post("/lancamentos/<int:lid>/excluir")
    @requer("lancador")
    def lancamento_excluir(lid):
        return _acao_lancamento(lid, servicos.excluir_lancamento, "Lançamento excluído.")

    @app.post("/lancamentos/<int:lid>/restaurar")
    @requer("admin")
    def lancamento_restaurar(lid):
        return _acao_lancamento(lid, servicos.restaurar_lancamento, "Lançamento restaurado.")

    # --------------------------------------------------------------- relatórios
    def resumo_para_relatorio(ano, m):
        checar_mes(ano, m)
        return servicos.resumo_mes(conexao(), ano, m)

    @app.get("/relatorio/<int:ano>/<int:mes>.xlsx")
    def rel_xlsx(ano, mes):
        r = resumo_para_relatorio(ano, mes)
        dados = reports.gerar_xlsx(r, cfg.empresa)
        return Response(dados, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{reports.nome_arquivo(r, "xlsx")}"'})

    @app.get("/relatorio/<int:ano>/<int:mes>.pdf")
    def rel_pdf(ano, mes):
        r = resumo_para_relatorio(ano, mes)
        estilo = request.args.get("estilo", reports.ESTILO_PADRAO)
        if estilo not in reports.ESTILOS_PDF:
            estilo = reports.ESTILO_PADRAO
        dados = reports.gerar_pdf(r, cfg.empresa, g.usuario["nome"],
                                  datetime.now().strftime("%d/%m/%Y %H:%M"), estilo=estilo)
        return Response(dados, mimetype="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{reports.nome_arquivo(r, "pdf")}"'})

    @app.get("/relatorio/<int:ano>/<int:mes>/imprimir")
    def rel_imprimir(ano, mes):
        """Imprime o MESMO PDF escolhido na tela do mês (estilo selecionado)."""
        resumo_para_relatorio(ano, mes)  # valida mês/ano e permissão
        estilo = request.args.get("estilo", reports.ESTILO_PADRAO)
        if estilo not in reports.ESTILOS_PDF:
            estilo = reports.ESTILO_PADRAO
        return render_template("imprimir.html", ano=ano, mes=mes, estilo=estilo,
                               titulo=f"Despesas {mes:02d}/{ano}",
                               pdf_url=url_for("rel_pdf", ano=ano, mes=mes, estilo=estilo))

    # ---------------------------------------------------------------- administração
    @app.route("/admin/usuarios", methods=["GET", "POST"])
    @requer("admin")
    def adm_usuarios():
        if request.method == "POST":
            f = request.form
            try:
                servicos.criar_usuario(conexao(), f.get("usuario", ""), f.get("nome", ""), f.get("senha", ""),
                                       f.get("perfil", ""), trocar_senha=True, autor=g.usuario["usuario"])
                flash("Usuário criado. Ele deverá trocar a senha no primeiro acesso.", "ok")
                return redirect(url_for("adm_usuarios"))
            except ErroNegocio as e:
                flash(str(e), "erro")
        return render_template("usuarios.html", lista=servicos.listar_usuarios(conexao()))

    @app.post("/admin/usuarios/<int:uid>")
    @requer("admin")
    def adm_usuario_atualizar(uid):
        f = request.form
        try:
            servicos.atualizar_usuario(conexao(), g.usuario, uid, f.get("nome", ""), f.get("perfil", ""),
                                       f.get("ativo") == "1")
            nova = f.get("nova_senha", "")
            if nova:
                servicos.alterar_senha(conexao(), uid, nova, True, g.usuario["usuario"])
            flash("Usuário atualizado.", "ok")
        except ErroNegocio as e:
            flash(str(e), "erro")
        return redirect(url_for("adm_usuarios"))

    @app.route("/admin/categorias", methods=["GET", "POST"])
    @requer("admin")
    def adm_categorias():
        if request.method == "POST":
            try:
                servicos.criar_categoria(conexao(), g.usuario, request.form.get("nome", ""))
                flash("Categoria criada.", "ok")
                return redirect(url_for("adm_categorias"))
            except ErroNegocio as e:
                flash(str(e), "erro")
        return render_template("categorias.html", lista=servicos.listar_categorias(conexao()))

    @app.post("/admin/categorias/<int:cid>")
    @requer("admin")
    def adm_categoria_atualizar(cid):
        f = request.form
        acao = f.get("acao", "")
        try:
            if acao == "renomear":
                servicos.renomear_categoria(conexao(), g.usuario, cid, f.get("nome", ""))
            elif acao in ("ativar", "desativar"):
                servicos.definir_ativa(conexao(), g.usuario, cid, acao == "ativar")
            elif acao in ("sobe", "desce"):
                servicos.mover_categoria(conexao(), g.usuario, cid, acao)
            elif acao in ("mostrar_resumo", "ocultar_resumo"):
                servicos.definir_mostrar_resumo(conexao(), g.usuario, cid, acao == "mostrar_resumo")
            else:
                abort(400)
            flash("Categoria atualizada.", "ok")
        except ErroNegocio as e:
            flash(str(e), "erro")
        return redirect(url_for("adm_categorias"))

    @app.route("/admin/backup", methods=["GET", "POST"])
    @requer("admin")
    def adm_backup():
        if request.method == "POST":
            try:
                arq = backup.fazer_backup(cfg)
                servicos.registrar_auditoria(conexao(), g.usuario["usuario"], "backup_manual", None, arq.name)
                flash(f"Backup criado: {arq.name}", "ok")
            except Exception as e:  # mostra o motivo (ex.: pasta inacessível)
                log.exception("Falha no backup manual")
                flash(f"Falha ao criar o backup: {e}", "erro")
            return redirect(url_for("adm_backup"))

        # ---- status do servidor (diagnóstico rápido, sem precisar abrir .bat/log) ----
        conn = conexao()
        caminho_abs = cfg.db_path.resolve()
        versao_schema = conn.execute("PRAGMA user_version").fetchone()[0]
        integridade = conn.execute("PRAGMA integrity_check").fetchone()[0]
        n_usuarios = conn.execute("SELECT COUNT(*) FROM usuarios WHERE ativo=1").fetchone()[0]
        n_categorias = conn.execute("SELECT COUNT(*) FROM categorias WHERE ativa=1").fetchone()[0]
        n_lancamentos = conn.execute("SELECT COUNT(*) FROM lancamentos WHERE excluido=0").fetchone()[0]
        tamanho_kb = round(caminho_abs.stat().st_size / 1024) if caminho_abs.exists() else 0

        log_linhas = []
        try:
            arq_log = cfg.logs_dir / "despesas.log"
            if arq_log.is_file():
                with open(arq_log, encoding="utf-8", errors="replace") as f:
                    log_linhas = f.readlines()[-25:]
        except OSError:
            pass

        return render_template(
            "backup.html", lista=backup.listar_backups(cfg), pasta=str(cfg.backup_dir),
            ativo=cfg.backup_ativo, hora=cfg.backup_hora, manter=cfg.backup_manter,
            versao=__version__, caminho_banco=str(caminho_abs), versao_schema=versao_schema,
            schema_atual=db.VERSAO_SCHEMA, integridade=integridade, n_usuarios=n_usuarios,
            n_categorias=n_categorias, n_lancamentos=n_lancamentos, tamanho_kb=tamanho_kb,
            host=cfg.host, porta=cfg.porta, log_linhas=log_linhas,
        )

    @app.get("/admin/auditoria")
    @requer("admin")
    def adm_auditoria():
        linhas = conexao().execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT 300").fetchall()
        return render_template("auditoria.html", lista=linhas)

    # --------------------------------------------------------------------- erros
    def erro(codigo: int, titulo: str, texto: str):
        return render_template("erro.html", codigo=codigo, titulo=titulo, texto=texto), codigo

    @app.errorhandler(400)
    def e400(_e):
        return erro(400, "Formulário inválido ou sessão expirada",
                    "Volte à página anterior, recarregue e tente de novo. Se persistir, entre novamente.")

    @app.errorhandler(403)
    def e403(_e):
        return erro(403, "Sem permissão", "Seu perfil não permite esta ação.")

    @app.errorhandler(404)
    def e404(_e):
        return erro(404, "Página não encontrada", "O endereço não existe ou o item foi removido.")

    @app.errorhandler(413)
    def e413(_e):
        return erro(413, "Dados grandes demais", "O formulário enviado excede o tamanho permitido.")

    @app.errorhandler(500)
    def e500(_e):
        return erro(500, "Erro interno", "Algo deu errado. O erro foi registrado no log do servidor.")

    return app
