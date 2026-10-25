"""Supervisor do servidor: mantém o sistema ligado e recebe comandos pela pasta `controle`.

Roda NO COMPUTADOR SERVIDOR (iniciado com o Windows). O gerenciador, aberto neste computador
ou de outro pela rede (\\\\servidor\\C\\despesas\\sistema), escreve um pedido em
`controle/cmd_<id>.json`; o supervisor executa e responde em `controle/resp_<id>.json`.
O estado (ligado, pid, banco, backups...) fica em `controle/estado.json`.

Só biblioteca padrão. Nada aqui apaga ou recria o banco de dados.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import backup, config

NT = os.name == "nt"
SEM_JANELA = 0x08000000 if NT else 0
INTERVALO_ESTADO = 2.0
INTERVALO_BANCO = 30.0
VIVO_SEGUNDOS = 20.0


def pasta_controle(config_path: Path) -> Path:
    return Path(config_path).resolve().parent / "controle"


def _escrever_json(destino: Path, dados: dict) -> None:
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, destino)


def ler_estado(config_path: Path) -> dict | None:
    """Estado publicado pelo supervisor (ou None). Acrescenta 'vivo' (bateu ponto há pouco?)."""
    try:
        est = json.loads((pasta_controle(config_path) / "estado.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    est["vivo"] = (time.time() - float(est.get("quando", 0))) < VIVO_SEGUNDOS
    return est


def _ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class Supervisor:
    def __init__(self, app_dir: str | Path, config_path: str | Path):
        self.app_dir = Path(app_dir).resolve()
        self.config_path = Path(config_path).resolve()
        self.pasta = pasta_controle(self.config_path)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.filho: subprocess.Popen | None = None
        self.desejado = "ligado"
        self.sair = False
        self.erro = ""
        self._falhas = 0
        self._proxima_tentativa = 0.0
        self._inicio_filho = 0.0
        self._banco: dict = {}
        self._banco_em = 0.0
        self._estado_em = 0.0

    # ------------------------------------------------------------------ util
    def cfg(self) -> config.Config:
        return config.carregar(self.config_path)

    def log(self, texto: str) -> None:
        try:
            pasta = self.app_dir / "logs"
            pasta.mkdir(parents=True, exist_ok=True)
            with open(pasta / "gerenciador.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [supervisor] {texto}\n")
        except OSError:
            pass

    def _python(self) -> str:
        scripts = self.app_dir / ".venv" / ("Scripts" if NT else "bin")
        nome = "pythonw.exe" if NT and (scripts / "pythonw.exe").exists() else ("python.exe" if NT else "python")
        p = scripts / nome
        return str(p) if p.exists() else sys.executable

    def _gerenciador(self):
        from .gerenciador import Gerenciador
        return Gerenciador(self.app_dir, self.config_path, direto=True)

    def _porta_aberta(self, porta: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=0.7):
                return True
        except OSError:
            return False

    # -------------------------------------------------------- servidor (filho)
    def filho_vivo(self) -> bool:
        return self.filho is not None and self.filho.poll() is None

    def iniciar_filho(self) -> None:
        cfg = self.cfg()
        g = self._gerenciador()
        if g.banco_ausente_com_backups():
            self.erro = (f"Banco não encontrado em {cfg.db_path}, mas existem backups. "
                         "Não vou criar um banco vazio: use Restaurar backup.")
            self.log(self.erro)
            self._proxima_tentativa = time.time() + 60
            return
        cfg.logs_dir.mkdir(parents=True, exist_ok=True)
        saida = open(cfg.logs_dir / "servidor_saida.log", "ab")
        saida.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} iniciando (supervisor) ===\n".encode())
        saida.flush()
        cmd = [self._python(), str(self.app_dir / "run.py")]
        if self.config_path != self.app_dir / "config.ini":
            cmd += ["--config", str(self.config_path)]
        cmd.append("servir")
        kw = {"creationflags": SEM_JANELA} if NT else {"start_new_session": True}
        self.filho = subprocess.Popen(cmd, cwd=str(self.app_dir), stdin=subprocess.DEVNULL,
                                      stdout=saida, stderr=subprocess.STDOUT, close_fds=True, **kw)
        saida.close()
        self._inicio_filho = time.time()
        self.erro = ""
        self.log(f"Servidor iniciado (pid {self.filho.pid}).")

    def parar_filho(self) -> None:
        if not self.filho_vivo():
            self.filho = None
            return
        pid = self.filho.pid
        if NT:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                           creationflags=SEM_JANELA)
        else:
            self.filho.terminate()
        try:
            self.filho.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.filho.kill()
            self.filho.wait(timeout=5)
        self.log(f"Servidor parado (pid {pid}).")
        self.filho = None

    def aguardar_porta(self, esperar: float = 25.0) -> None:
        porta = self.cfg().porta
        limite = time.time() + esperar
        while time.time() < limite:
            if not self.filho_vivo():
                saida = self.app_dir / "logs" / "servidor_saida.log"
                raise RuntimeError("O servidor não conseguiu iniciar. Últimas linhas:\n\n"
                                   + self._gerenciador()._ultimas_linhas(saida))
            if self._porta_aberta(porta):
                return
            self.publicar_estado()  # continua "batendo ponto" durante operações demoradas
            time.sleep(0.4)
        raise RuntimeError("O servidor foi iniciado mas a porta não abriu a tempo (veja logs\\servidor_saida.log).")

    # --------------------------------------------------------------- comandos
    def executar(self, acao: str, arg: str = "") -> str:
        if acao == "ligar":
            self.desejado = "ligado"
            if self._porta_aberta(self.cfg().porta) and self.filho_vivo():
                return "O servidor já está ligado."
            if not self.filho_vivo():
                self.iniciar_filho()
                if not self.filho_vivo():
                    raise RuntimeError(self.erro or "Não foi possível iniciar o servidor.")
            self.aguardar_porta()
            return f"Servidor ligado (porta {self.cfg().porta})."
        if acao == "desligar":
            self.desejado = "desligado"
            self.parar_filho()
            extra = ""
            try:
                extra = f" Backup de segurança: {backup.fazer_backup(self.cfg()).name}."
            except Exception as e:
                extra = f" (Sem backup de segurança: {e})"
            return "Servidor desligado." + extra
        if acao == "reiniciar":
            a = self.executar("desligar")
            return a + "\n" + self.executar("ligar")
        if acao == "backup":
            return f"Backup criado: {backup.fazer_backup(self.cfg()).name}"
        if acao == "consulta":
            return f"Cópia criada: {self._gerenciador().copia_para_consulta()}"
        if acao == "restaurar":
            self.desejado = "desligado"
            self.parar_filho()
            guarda = backup.restaurar(self.cfg(), arg)
            return (f"Restaurado: {arg}\nBanco anterior guardado em: {guarda}\n"
                    "O servidor ficou desligado: clique em 'Ligar servidor'.")
        if acao == "reiniciar_supervisor":
            self.desejado = "desligado"
            self.parar_filho()
            cmd = [self._python(), str(self.app_dir / "run.py")]
            if self.config_path != self.app_dir / "config.ini":
                cmd += ["--config", str(self.config_path)]
            cmd.append("supervisor")
            env = dict(os.environ, DESPESAS_AGUARDAR_PID=str(os.getpid()))
            kw = {"creationflags": SEM_JANELA | 0x00000008 | 0x00000200} if NT else {"start_new_session": True}
            subprocess.Popen(cmd, cwd=str(self.app_dir), env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)
            self.sair = True
            return "Supervisor reiniciando com o código atual; o servidor volta em alguns segundos."
        if acao == "sair":
            self.desejado = "desligado"
            self.parar_filho()
            self.sair = True
            return "Supervisor encerrado (o servidor foi desligado)."
        raise RuntimeError(f"Comando desconhecido: {acao}")

    def processar_comandos(self) -> None:
        try:
            pedidos = sorted(self.pasta.glob("cmd_*.json"))
        except OSError:
            return
        for arq in pedidos:
            try:
                ped = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                ped = None
            try:
                arq.unlink()
            except OSError:
                pass
            if not isinstance(ped, dict) or not ped.get("id"):
                continue
            if time.time() - float(ped.get("quando", time.time())) > 300:
                continue  # pedido velho demais: ninguém mais está esperando
            try:
                msg = self.executar(str(ped.get("acao", "")), str(ped.get("arg", "")))
                resp = {"ok": True, "msg": msg}
            except Exception as e:
                self.log("ERRO no comando %s: %s\n%s" % (ped.get("acao"), e, traceback.format_exc()))
                resp = {"ok": False, "msg": str(e)}
            self.log(f"Comando {ped.get('acao')}: {'ok' if resp['ok'] else 'FALHOU'}")
            _escrever_json(self.pasta / f"resp_{ped['id']}.json", resp)
            self.publicar_estado(forcar_banco=True)

    # ----------------------------------------------------------------- estado
    def _info_banco(self) -> dict:
        try:
            g = self._gerenciador()
            i = g.info_banco()
            cfg = self.cfg()
            return {"caminho": str(i.caminho), "existe": i.existe, "tamanho_kb": i.tamanho_kb,
                    "schema": i.schema, "usuarios": i.usuarios, "lancamentos": i.lancamentos,
                    "integridade": i.integridade, "erro": i.erro,
                    "pasta_backups": str(cfg.backup_dir), "backups": backup.listar_backups(cfg)[:60]}
        except Exception as e:
            return {"erro": str(e), "existe": False, "caminho": "?", "backups": []}

    def publicar_estado(self, forcar_banco: bool = False) -> None:
        agora = time.time()
        if forcar_banco or agora - self._banco_em > INTERVALO_BANCO:
            self._banco = self._info_banco()
            self._banco_em = agora
        try:
            cfg = self.cfg()
            porta = cfg.porta
            aberta = self._porta_aberta(porta)
        except Exception as e:
            porta, aberta = 0, False
            self.erro = str(e)
        _escrever_json(self.pasta / "estado.json", {
            "quando": agora, "supervisor_pid": os.getpid(), "host": socket.gethostname(), "ip": _ip_local(),
            "porta": porta, "desejado": self.desejado, "servidor_pid": self.filho.pid if self.filho_vivo() else None,
            "servidor_rodando": aberta, "erro": self.erro, "banco": self._banco, "app_dir": str(self.app_dir),
        })
        self._estado_em = agora

    # ------------------------------------------------------------------ laço
    def _vigiar_filho(self) -> None:
        if self.desejado != "ligado" or self.filho_vivo() or time.time() < self._proxima_tentativa:
            if self.filho_vivo() and time.time() - self._inicio_filho > 120:
                self._falhas = 0
            return
        if self.filho is not None:  # caiu sozinho
            self.log(f"Servidor caiu (código {self.filho.returncode}); religando.")
            self._falhas += 1
            self.filho = None
        espera = min(3 * (2 ** max(self._falhas - 1, 0)), 60)
        self._proxima_tentativa = time.time() + espera
        try:
            self.iniciar_filho()
        except Exception as e:
            self.erro = str(e)
            self.log(f"Não foi possível iniciar: {e}")

    def rodar(self) -> int:
        antigo = os.environ.get("DESPESAS_AGUARDAR_PID")  # troca de supervisor: espera o anterior sair
        if antigo and antigo.isdigit():
            limite = time.time() + 40
            while time.time() < limite and _pid_vivo(int(antigo)):
                time.sleep(0.5)
        atual = ler_estado(self.config_path)
        if atual and atual.get("vivo") and atual.get("supervisor_pid") != os.getpid() and _pid_vivo(atual.get("supervisor_pid")):
            print("Já existe um supervisor ativo neste servidor.")
            return 1
        self.log(f"Supervisor iniciado (pid {os.getpid()}).")
        try:
            while not self.sair:
                try:
                    self.processar_comandos()
                    self._vigiar_filho()
                    if time.time() - self._estado_em >= INTERVALO_ESTADO:
                        self.publicar_estado()
                except Exception:
                    self.log("ERRO no laço:\n" + traceback.format_exc())
                time.sleep(0.5)
        finally:
            try:
                (self.pasta / "estado.json").unlink()
            except OSError:
                pass
            self.log("Supervisor encerrado.")
        return 0


def _pid_vivo(pid) -> bool:
    if not pid:
        return False
    if NT:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                           creationflags=SEM_JANELA, errors="replace")
        return str(pid) in r.stdout
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def enviar_comando(config_path: Path, acao: str, arg: str = "", timeout: float = 60.0) -> str:
    """Usado pelo gerenciador (local ou pela rede). Levanta RuntimeError se falhar."""
    import uuid
    pasta = pasta_controle(config_path)
    est = ler_estado(config_path)
    if not est or not est.get("vivo"):
        raise RuntimeError("O supervisor não está ativo no servidor.")
    pid = uuid.uuid4().hex[:12]
    _escrever_json(pasta / f"cmd_{pid}.json", {"id": pid, "acao": acao, "arg": arg, "quando": time.time()})
    resp_arq = pasta / f"resp_{pid}.json"
    limite = time.time() + timeout
    while time.time() < limite:
        if resp_arq.exists():
            try:
                resp = json.loads(resp_arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                time.sleep(0.2)
                continue
            try:
                resp_arq.unlink()
            except OSError:
                pass
            if not resp.get("ok"):
                raise RuntimeError(resp.get("msg", "Falhou."))
            return resp.get("msg", "")
        time.sleep(0.3)
    try:
        (pasta / f"cmd_{pid}.json").unlink()
    except OSError:
        pass
    raise RuntimeError("O servidor não respondeu a tempo. Confira se o computador servidor está ligado.")
