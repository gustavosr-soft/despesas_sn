"""Ponto de entrada do Sistema de Despesas.

Uso:
  python run.py                      inicia o servidor (usa config.ini)
  python run.py criar-admin          cria (ou redefine a senha de) um administrador
  python run.py backup               faz um backup agora
  python run.py restaurar ARQUIVO    restaura um backup (servidor parado)
  python run.py verificar            confere a configuração e o banco
  python run.py porta                mostra a porta configurada
"""
from __future__ import annotations

import argparse
import getpass
import logging
import socket
import sys
from logging.handlers import RotatingFileHandler

from despesas import __version__, backup, db, servicos
from despesas.config import ErroConfig, carregar


def configurar_logs(cfg, console: bool = True) -> None:
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    raiz = logging.getLogger()
    raiz.setLevel(cfg.log_nivel)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    arq = RotatingFileHandler(cfg.logs_dir / "despesas.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    arq.setFormatter(fmt)
    raiz.addHandler(arq)
    if console:
        h = logging.StreamHandler()
        h.setFormatter(fmt)
        raiz.addHandler(h)


def ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # não envia nada; só descobre a interface de rede
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "IP-DO-SERVIDOR"


def cmd_servir(cfg) -> int:
    from waitress import serve

    from despesas.web import criar_app

    configurar_logs(cfg)
    log = logging.getLogger("despesas")
    app = criar_app(cfg)
    conn = db.conectar(cfg.db_path)
    try:
        tem_admin = conn.execute("SELECT COUNT(*) FROM usuarios WHERE perfil='admin' AND ativo=1").fetchone()[0]
    finally:
        conn.close()
    if not tem_admin:
        log.error("Não há administrador cadastrado. Execute CRIAR_ADMIN.bat (ou: python run.py criar-admin).")
        print("\nERRO: nenhum administrador cadastrado. Rode CRIAR_ADMIN.bat primeiro.\n")
        return 2
    backup.iniciar_agendador(cfg)
    ip = ip_local() if cfg.host in ("0.0.0.0", "::") else cfg.host
    log.info("Sistema de Despesas v%s iniciado. Banco: %s", __version__, cfg.db_path)
    print("=" * 62)
    print(f" Sistema de Despesas v{__version__} — servidor em execução")
    print(f" Neste computador:   http://localhost:{cfg.porta}")
    print(f" Outros computadores: http://{ip}:{cfg.porta}")
    print(" Para encerrar: feche esta janela ou pressione Ctrl+C")
    print("=" * 62)
    serve(app, host=cfg.host, port=cfg.porta, threads=cfg.threads, ident="despesas",
          clear_untrusted_proxy_headers=True)
    return 0


def cmd_criar_admin(cfg, args) -> int:
    db.iniciar(cfg.db_path)
    usuario = args.usuario or input("Nome de usuário do administrador [admin]: ").strip() or "admin"
    nome = args.nome or input("Nome completo: ").strip() or usuario
    senha = args.senha
    if not senha:
        senha = getpass.getpass("Senha (mínimo 8 caracteres): ")
        if senha != getpass.getpass("Repita a senha: "):
            print("As senhas não conferem.")
            return 1
    conn = db.conectar(cfg.db_path)
    try:
        existente = conn.execute("SELECT id FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
        if existente:
            servicos.alterar_senha(conn, existente["id"], senha, False, "console")
            with db.transacao(conn):
                conn.execute("UPDATE usuarios SET perfil='admin', ativo=1 WHERE id=?", (existente["id"],))
            print(f"Usuário '{usuario}' já existia: senha redefinida e perfil de administrador garantido.")
        else:
            servicos.criar_usuario(conn, usuario, nome, senha, "admin", trocar_senha=False, autor="console")
            print(f"Administrador '{usuario}' criado.")
    except servicos.ErroNegocio as e:
        print(f"Erro: {e}")
        return 1
    finally:
        conn.close()
    return 0


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):  # nunca falhar por causa da página de código do console
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Sistema de Despesas")
    p.add_argument("--config", help="caminho do config.ini (padrão: o da pasta do sistema)")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("criar-admin")
    a.add_argument("--usuario")
    a.add_argument("--nome")
    a.add_argument("--senha", help="evite: aparece no histórico do console; prefira digitar quando pedido")
    sub.add_parser("backup")
    r = sub.add_parser("restaurar")
    r.add_argument("arquivo")
    sub.add_parser("verificar")
    sub.add_parser("servir")
    sub.add_parser("porta")
    args = p.parse_args(argv)

    try:
        cfg = carregar(args.config)
    except ErroConfig as e:
        print(f"ERRO DE CONFIGURAÇÃO: {e}")
        return 2

    cmd = args.cmd or "servir"
    if cmd == "porta":  # usado pelos .bat para abrir a porta no firewall
        print(cfg.porta)
        return 0
    if cmd == "servir":
        return cmd_servir(cfg)
    if cmd == "criar-admin":
        return cmd_criar_admin(cfg, args)
    configurar_logs(cfg, console=False)
    if cmd == "backup":
        db.iniciar(cfg.db_path)
        print(f"Backup criado: {backup.fazer_backup(cfg)}")
        return 0
    if cmd == "restaurar":
        try:
            guarda = backup.restaurar(cfg, args.arquivo)
        except (RuntimeError, FileNotFoundError) as e:
            print(f"Erro: {e}")
            return 1
        print(f"Banco restaurado. O banco anterior foi guardado em: {guarda}")
        return 0
    if cmd == "verificar":
        db.iniciar(cfg.db_path)
        conn = db.conectar(cfg.db_path)
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        usuarios = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        lanc = conn.execute("SELECT COUNT(*) FROM lancamentos WHERE excluido=0").fetchone()[0]
        conn.close()
        print(f"Configuração: {cfg.arquivo}")
        print(f"Banco: {cfg.db_path} (integridade: {ok}) — {usuarios} usuário(s), {lanc} lançamento(s)")
        print(f"Endereço: {cfg.host}:{cfg.porta} | Backups: {cfg.backup_dir} às {cfg.backup_hora}")
        return 0 if ok == "ok" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
