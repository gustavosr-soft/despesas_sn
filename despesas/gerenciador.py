"""Lógica do gerenciador do servidor (ligar, desligar, backup, restaurar...).

Só usa a biblioteca padrão: funciona com qualquer Python, mesmo antes de instalar
as dependências. Nada aqui apaga ou recria o banco de dados.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import configparser

from . import backup, config, db, supervisor

NT = os.name == "nt"
SEM_JANELA = 0x08000000 if NT else 0          # CREATE_NO_WINDOW
DESTACADO = (0x00000008 | 0x00000200) if NT else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
TAREFAS = ("SistemaDespesas", "DespesasNascimento")


class ErroGerenciador(Exception):
    """Problema que o usuário precisa ver (mensagem pronta, em português)."""


@dataclass
class Status:
    porta_aberta: bool
    saude_ok: bool
    pid: int | None
    porta: int

    @property
    def rodando(self) -> bool:
        return self.porta_aberta


@dataclass
class InfoBanco:
    caminho: Path | str
    existe: bool
    tamanho_kb: int = 0
    schema: int = 0
    usuarios: int = 0
    lancamentos: int = 0
    integridade: str = ""
    erro: str = ""


def _rodar(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """subprocess.run sem abrir janela e sem nunca levantar por saída estranha."""
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                          creationflags=SEM_JANELA, **kw)


class Gerenciador:
    def __init__(self, app_dir: str | Path | None = None, config_path: str | Path | None = None,
                 forcar_rede: bool = False):
        self.forcar_rede = forcar_rede
        self.app_dir = Path(app_dir or Path(__file__).resolve().parent.parent).resolve()
        self.config_path = Path(config_path) if config_path else self.app_dir / "config.ini"
        self.base = self.config_path.resolve().parent
        self.pid_file = self.base / "servidor.pid"

    # ------------------------------------------------------------------ infra
    def cfg(self) -> config.Config:
        try:
            return config.carregar(self.config_path)
        except config.ErroConfig as e:
            raise ErroGerenciador(str(e))

    def registrar(self, texto: str) -> None:
        """Anota em logs/gerenciador.log. Nunca levanta erro."""
        try:
            pasta = self.base / "logs"
            pasta.mkdir(parents=True, exist_ok=True)
            with open(pasta / "gerenciador.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {texto}\n")
        except OSError:
            pass

    def registrar_erro(self) -> None:
        self.registrar("ERRO:\n" + traceback.format_exc())

    def eh_pasta_de_rede(self) -> bool:
        """True quando o gerenciador foi aberto por uma pasta de rede (outro computador)."""
        if self.forcar_rede:
            return True
        if not NT:
            return False
        raiz = str(self.app_dir)
        if raiz.startswith("\\\\"):
            return True
        try:
            import ctypes
            return ctypes.windll.kernel32.GetDriveTypeW(os.path.splitdrive(raiz)[0] + "\\") == 4
        except Exception:
            return False

    MSG_SUPERVISOR = (
        "O supervisor não está ativo no servidor, então não dá para controlar o sistema pela rede.\n\n"
        "Uma única vez, NO COMPUTADOR SERVIDOR (pasta C:\\despesas\\sistema), abra o gerenciador e "
        "clique em 'Ativar supervisor'. Depois disso funciona de qualquer computador da rede.")

    def _exigir_servidor(self) -> None:
        """Operações que só fazem sentido no próprio servidor (instalar, firewall, mover dados)."""
        if self.eh_pasta_de_rede():
            raise ErroGerenciador(
                "Esta ação só pode ser feita no próprio computador servidor (pasta local, ex.: "
                "C:\\despesas\\sistema). Pela rede estão disponíveis ligar, desligar, reiniciar, "
                "backup, restaurar e a cópia para consulta.")

    # --------------------------------------------- supervisor (controle local e pela rede)
    def estado_supervisor(self) -> dict | None:
        return supervisor.ler_estado(self.config_path)

    def supervisor_vivo(self) -> bool:
        est = self.estado_supervisor()
        return bool(est and est.get("vivo"))

    def _usar_supervisor(self) -> bool:
        """True = mandar o comando ao supervisor. Pela rede o supervisor é obrigatório."""
        if self.supervisor_vivo():
            return True
        if self.eh_pasta_de_rede():
            raise ErroGerenciador(self.MSG_SUPERVISOR)
        return False

    def _comando(self, acao: str, arg: str = "", timeout: float = 90.0) -> str:
        try:
            return supervisor.enviar_comando(self.config_path, acao, arg, timeout)
        except RuntimeError as e:
            raise ErroGerenciador(str(e))

    def _porta_leve(self) -> int:
        try:
            cp = configparser.ConfigParser(interpolation=None)
            cp.read(self.config_path, encoding="utf-8-sig")
            return int(cp.get("servidor", "porta", fallback="8080"))
        except (configparser.Error, ValueError, OSError):
            return 8080

    def _host_da_unc(self) -> str:
        try:
            real = os.path.realpath(str(self.app_dir)).replace("/", "\\")
            real = real.replace("\\\\?\\UNC\\", "\\\\")
            if real.startswith("\\\\"):
                return real[2:].split("\\")[0]
        except Exception:
            pass
        return ""

    def porta(self) -> int:
        est = self.estado_supervisor()
        if self.eh_pasta_de_rede():
            return int((est or {}).get("porta") or self._porta_leve())
        return self.cfg().porta

    def host(self) -> str:
        """Endereço para falar com o servidor: local = 127.0.0.1; pela rede = o do servidor."""
        if not self.eh_pasta_de_rede():
            return "127.0.0.1"
        est = self.estado_supervisor() or {}
        return est.get("ip") or self._host_da_unc() or "127.0.0.1"

    def pasta_logs(self) -> Path:
        return self.base / "logs" if self.eh_pasta_de_rede() else self.cfg().logs_dir

    def pasta_backups(self) -> Path | None:
        if self.eh_pasta_de_rede():
            return None
        return self.cfg().backup_dir

    def python(self, com_janela: bool = False) -> str:
        scripts = self.app_dir / ".venv" / ("Scripts" if NT else "bin")
        nome = "python.exe" if NT else "python"
        if NT and not com_janela and (scripts / "pythonw.exe").exists():
            nome = "pythonw.exe"
        p = scripts / nome
        if p.exists():
            return str(p)
        exe = Path(sys.executable)
        if NT and com_janela and exe.name.lower() == "pythonw.exe":
            exe = exe.with_name("python.exe")
        return str(exe)

    def _dependencias_ok(self) -> bool:
        r = _rodar([self.python(True), "-c", "import flask, waitress, openpyxl, reportlab"])
        return r.returncode == 0

    # ----------------------------------------------------------------- status
    def _porta_aberta(self, porta: int, host: str = "127.0.0.1") -> bool:
        try:
            with socket.create_connection((host, porta), timeout=1.5 if host != "127.0.0.1" else 0.7):
                return True
        except OSError:
            return False

    def _saude(self, porta: int, host: str = "127.0.0.1") -> bool:
        try:
            with urllib.request.urlopen(f"http://{host}:{porta}/saude", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def _pid_vivo(self, pid: int) -> bool:
        if NT:
            r = _rodar(["tasklist", "/FI", f"PID eq {pid}", "/NH"])
            return str(pid) in r.stdout
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _pid_do_arquivo(self) -> int | None:
        try:
            pid = int(self.pid_file.read_text().strip())
        except (OSError, ValueError):
            return None
        return pid if self._pid_vivo(pid) else None

    def _pids_na_porta(self, porta: int) -> set[int]:
        pids: set[int] = set()
        if NT:
            r = _rodar(["netstat", "-ano", "-p", "TCP"])
            for linha in r.stdout.splitlines():
                p = linha.split()
                if len(p) >= 5 and p[3].upper() == "LISTENING" and p[1].endswith(f":{porta}"):
                    if p[4].isdigit():
                        pids.add(int(p[4]))
        else:
            r = _rodar(["ss", "-ltnp"]) if _tem("ss") else None
            if r:
                import re
                for linha in r.stdout.splitlines():
                    if f":{porta} " in linha:
                        pids.update(int(x) for x in re.findall(r"pid=(\d+)", linha))
        return pids

    def _linha_de_comando(self, pid: int) -> str:
        if NT:
            r = _rodar(["powershell", "-NoProfile", "-Command",
                        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"])
            return r.stdout
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            return ""

    def status(self) -> Status:
        if self.eh_pasta_de_rede():
            est = self.estado_supervisor() or {}
            host, porta = self.host(), self.porta()
            aberta = self._porta_aberta(porta, host)
            return Status(aberta, aberta and self._saude(porta, host), est.get("servidor_pid"), porta)
        cfg = self.cfg()
        aberta = self._porta_aberta(cfg.porta)
        pid = self._pid_do_arquivo()
        if aberta and pid is None:
            for cand in self._pids_na_porta(cfg.porta):
                if "run.py" in self._linha_de_comando(cand):
                    pid = cand
        return Status(aberta, aberta and self._saude(cfg.porta), pid, cfg.porta)

    # ------------------------------------------------------------ banco/dados
    def info_banco(self) -> InfoBanco:
        if self.eh_pasta_de_rede():  # nunca abrir o SQLite pela rede (WAL não funciona em pasta compartilhada)
            est = self.estado_supervisor()
            if not est or not est.get("vivo"):
                return InfoBanco("(supervisor inativo: sem informação do banco)", False, erro="supervisor inativo")
            b = est.get("banco") or {}
            return InfoBanco(b.get("caminho", "?"), bool(b.get("existe")), b.get("tamanho_kb", 0),
                             b.get("schema", 0), b.get("usuarios", 0), b.get("lancamentos", 0),
                             b.get("integridade", ""), b.get("erro", ""))
        cfg = self.cfg()
        info = InfoBanco(cfg.db_path, cfg.db_path.exists())
        if not info.existe:
            return info
        info.tamanho_kb = round(cfg.db_path.stat().st_size / 1024)
        try:
            conn = sqlite3.connect(f"file:{cfg.db_path.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                info.schema = conn.execute("PRAGMA user_version").fetchone()[0]
                info.integridade = conn.execute("PRAGMA quick_check").fetchone()[0]
                if info.schema >= 1:
                    info.usuarios = conn.execute("SELECT COUNT(*) FROM usuarios WHERE ativo=1").fetchone()[0]
                    info.lancamentos = conn.execute(
                        "SELECT COUNT(*) FROM lancamentos WHERE excluido=0").fetchone()[0]
            finally:
                conn.close()
        except sqlite3.Error as e:
            info.erro = str(e)
        return info

    def banco_ausente_com_backups(self) -> bool:
        if self.eh_pasta_de_rede():
            return False
        cfg = self.cfg()
        return not cfg.db_path.exists() and bool(backup.listar_backups(cfg))

    def listar_backups(self) -> list[dict]:
        if self.eh_pasta_de_rede():
            return list(((self.estado_supervisor() or {}).get("banco") or {}).get("backups") or [])
        return backup.listar_backups(self.cfg())

    def backup_agora(self) -> Path | str:
        if self._usar_supervisor():
            return self._comando("backup").replace("Backup criado: ", "")
        cfg = self.cfg()
        if not cfg.db_path.exists():
            raise ErroGerenciador(f"Não há banco para copiar em {cfg.db_path}.")
        destino = backup.fazer_backup(cfg)
        self.registrar(f"Backup criado: {destino}")
        return destino

    def restaurar(self, nome: str) -> Path | str:
        if self._usar_supervisor():
            return self._comando("restaurar", nome, timeout=180)
        if self.status().rodando:
            raise ErroGerenciador("Desligue o servidor antes de restaurar um backup.")
        cfg = self.cfg()
        try:
            guarda = backup.restaurar(cfg, nome)
        except (RuntimeError, FileNotFoundError) as e:
            raise ErroGerenciador(str(e))
        self.registrar(f"Backup restaurado: {nome} (banco anterior guardado em {guarda})")
        return guarda

    # --------------------------------------------------------- ligar/desligar
    def _ultimas_linhas(self, arquivo: Path, n: int = 15) -> str:
        try:
            return "".join(arquivo.read_text(encoding="utf-8", errors="replace").splitlines(True)[-n:])
        except OSError:
            return ""

    def ligar(self, esperar: float = 25.0) -> str:
        if self._usar_supervisor():
            return self._comando("ligar")
        cfg = self.cfg()
        if self.status().rodando:
            return "O servidor já está ligado."
        if self.banco_ausente_com_backups():
            raise ErroGerenciador(
                f"O banco de dados NÃO foi encontrado em:\n{cfg.db_path}\n\n"
                "Existem backups, então NÃO vou criar um banco vazio por cima.\n"
                "Use 'Restaurar backup' ou confira o caminho em config.ini.")
        if not self._dependencias_ok():
            raise ErroGerenciador(
                "Faltam as bibliotecas do sistema (flask, waitress...).\n"
                "Use o botão 'Instalar / atualizar dependências' (não mexe nos dados).")
        cfg.logs_dir.mkdir(parents=True, exist_ok=True)
        saida_log = cfg.logs_dir / "servidor_saida.log"
        cmd = [self.python(False), str(self.app_dir / "run.py")]
        if self.config_path != self.app_dir / "config.ini":
            cmd += ["--config", str(self.config_path)]
        cmd.append("servir")
        with open(saida_log, "ab") as saida:
            saida.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} iniciando ===\n".encode())
            kw = {"creationflags": SEM_JANELA | DESTACADO} if NT else {"start_new_session": True}
            proc = subprocess.Popen(cmd, cwd=str(self.app_dir), stdin=subprocess.DEVNULL,
                                    stdout=saida, stderr=subprocess.STDOUT, close_fds=True, **kw)
        self.pid_file.write_text(str(proc.pid))
        limite = time.time() + esperar
        while time.time() < limite:
            if proc.poll() is not None:
                self.pid_file.unlink(missing_ok=True)
                raise ErroGerenciador(
                    "O servidor não conseguiu iniciar. Últimas linhas:\n\n" + self._ultimas_linhas(saida_log))
            if self._porta_aberta(cfg.porta):
                self.registrar(f"Servidor ligado (pid {proc.pid}).")
                return f"Servidor ligado (porta {cfg.porta})."
            time.sleep(0.4)
        raise ErroGerenciador(
            "O servidor foi iniciado mas a porta não abriu a tempo. Últimas linhas:\n\n"
            + self._ultimas_linhas(saida_log))

    def _matar(self, pid: int) -> None:
        if NT:
            _rodar(["taskkill", "/PID", str(pid), "/T", "/F"])
        else:
            import signal
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                except OSError:
                    return
                for _ in range(20):
                    if not self._pid_vivo(pid):
                        return
                    time.sleep(0.1)

    def desligar(self, backup_antes: bool = True) -> str:
        if self._usar_supervisor():
            return self._comando("desligar")
        return self._desligar_direto(backup_antes)

    def _desligar_direto(self, backup_antes: bool = True) -> str:
        cfg = self.cfg()
        if NT:
            for t in TAREFAS:
                _rodar(["schtasks", "/End", "/TN", t])
        alvos: set[int] = set()
        pid = self._pid_do_arquivo()
        if pid:
            alvos.add(pid)
        for cand in self._pids_na_porta(cfg.porta):
            if "run.py" in self._linha_de_comando(cand):  # nunca mata outro programa
                alvos.add(cand)
        if self._porta_aberta(cfg.porta) and not alvos:
            raise ErroGerenciador(
                f"A porta {cfg.porta} está em uso por um programa que não parece ser o sistema de "
                "despesas; não vou encerrá-lo.")
        for p in alvos:
            self._matar(p)
        limite = time.time() + 10
        while time.time() < limite and self._porta_aberta(cfg.porta):
            time.sleep(0.3)
        if self._porta_aberta(cfg.porta):
            raise ErroGerenciador("O servidor não encerrou. Tente de novo ou reinicie o computador.")
        self.pid_file.unlink(missing_ok=True)
        msg = "Servidor desligado."
        if backup_antes and cfg.db_path.exists():
            try:
                msg += f" Backup de segurança: {backup.fazer_backup(cfg).name}."
            except Exception as e:  # o desligamento já deu certo; só avisa
                self.registrar_erro()
                msg += f" (Não foi possível fazer o backup de segurança: {e})"
        self.registrar(msg)
        return msg

    def reiniciar(self) -> str:
        if self._usar_supervisor():
            return self._comando("reiniciar", timeout=150)
        a = self.desligar()
        return a + "\n" + self.ligar()

    # ------------------------------------------------- consulta (DBeaver etc.)
    def copia_para_consulta(self) -> Path:
        """Gera uma cópia CONSISTENTE e independente do banco, para abrir no DBeaver/Excel.

        Funciona com o servidor ligado (usa a API de backup do SQLite). A cópia fica em
        modo normal (sem arquivos -wal/-shm), então qualquer programa lê sem travar,
        e mexer nela não afeta o banco real.
        """
        if self._usar_supervisor():
            return self._comando("consulta").replace("Cópia criada: ", "")
        cfg = self.cfg()
        if not cfg.db_path.exists():
            raise ErroGerenciador(f"Não há banco em {cfg.db_path}.")
        pasta = cfg.db_path.parent.parent / "consulta"
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / "despesas_consulta.db"
        tmp = pasta / "despesas_consulta.tmp"
        for f in (tmp, destino, Path(str(destino) + "-wal"), Path(str(destino) + "-shm")):
            f.unlink(missing_ok=True)
        origem = sqlite3.connect(f"file:{cfg.db_path.as_posix()}?mode=ro", uri=True, timeout=15)
        try:
            copia = sqlite3.connect(tmp)
            try:
                origem.backup(copia)
                copia.execute("PRAGMA journal_mode=DELETE")
                copia.commit()
            finally:
                copia.close()
        finally:
            origem.close()
        tmp.replace(destino)
        self.registrar(f"Cópia para consulta criada: {destino}")
        return destino

    def ativar_supervisor(self) -> str:
        """No servidor: faz o supervisor iniciar com o Windows e o inicia agora (liga o sistema)."""
        self._exigir_servidor()
        self.cfg()  # valida o config antes
        if self.supervisor_vivo():
            return "O supervisor já está ativo."
        aviso = ""
        if NT:
            try:
                self.inicio_automatico(True)
            except ErroGerenciador as e:
                aviso = f"\nAtenção: não consegui configurar o início com o Windows ({e})"
        if self.status().rodando and not self.supervisor_vivo():
            self._desligar_direto()  # o supervisor passa a ser o dono do servidor
        cmd = [self.python(False), str(self.app_dir / "run.py")]
        if self.config_path != self.app_dir / "config.ini":
            cmd += ["--config", str(self.config_path)]
        cmd.append("supervisor")
        kw = {"creationflags": SEM_JANELA | DESTACADO} if NT else {"start_new_session": True}
        subprocess.Popen(cmd, cwd=str(self.app_dir), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, **kw)
        limite = time.time() + 40
        while time.time() < limite:
            if self.supervisor_vivo() and self.status().rodando:
                self.registrar("Supervisor ativado.")
                return "Supervisor ativo e servidor ligado. Agora o gerenciador funciona pela rede." + aviso
            time.sleep(0.5)
        raise ErroGerenciador("O supervisor não respondeu a tempo. Veja logs\\gerenciador.log e "
                              "logs\\servidor_saida.log." + aviso)

    def desativar_supervisor(self) -> str:
        self._exigir_servidor()
        msg = self._comando("sair") if self.supervisor_vivo() else "O supervisor já estava parado."
        if NT:
            for t in TAREFAS:
                _rodar(["schtasks", "/Delete", "/TN", t, "/F"])
        return msg + "\nO sistema não liga mais sozinho. Use 'Ativar supervisor' para voltar."

    def mover_dados(self, pasta_destino: str | Path) -> str:
        """Move banco, chave e backups para FORA da pasta do sistema. Servidor deve estar desligado.

        Copia, confere e só então troca o config.ini. A pasta antiga é apenas renomeada
        (dados_movido_AAAAMMDD_HHMMSS), nunca apagada.
        """
        import re
        import shutil
        self._exigir_servidor()
        if self.status().rodando:
            raise ErroGerenciador("Desligue o servidor antes de mover os dados.")
        cfg = self.cfg()
        destino = Path(pasta_destino).resolve()
        if not cfg.db_path.exists():
            raise ErroGerenciador(f"Não há banco em {cfg.db_path} para mover.")
        novo_db = destino / "dados" / "despesas.db"
        novos_bk = destino / "backups"
        if novo_db.resolve() == cfg.db_path.resolve():
            return "Os dados já estão nessa pasta. Nada a fazer."
        if novo_db.exists():
            raise ErroGerenciador(f"Já existe um banco em {novo_db}. Não vou sobrescrever.")
        antigo_dir = cfg.db_path.parent
        if destino == self.app_dir or self.app_dir in destino.parents:
            raise ErroGerenciador("Escolha uma pasta FORA da pasta do sistema (esse é o objetivo).")
        novo_db.parent.mkdir(parents=True, exist_ok=True)
        novos_bk.mkdir(parents=True, exist_ok=True)
        try:
            origem = sqlite3.connect(f"file:{cfg.db_path.as_posix()}?mode=ro", uri=True, timeout=15)
            try:
                n_orig = origem.execute("SELECT COUNT(*) FROM lancamentos").fetchone()[0]
                copia = sqlite3.connect(novo_db)
                try:
                    origem.backup(copia)
                finally:
                    copia.close()
            finally:
                origem.close()
            conf = sqlite3.connect(novo_db)
            try:
                ok = conf.execute("PRAGMA integrity_check").fetchone()[0]
                n_novo = conf.execute("SELECT COUNT(*) FROM lancamentos").fetchone()[0]
            finally:
                conf.close()
            if ok != "ok" or n_novo != n_orig:
                raise ErroGerenciador("A cópia não passou na conferência; nada foi alterado.")
            chave = antigo_dir / "chave_secreta.txt"
            if chave.exists():
                shutil.copy2(chave, novo_db.parent / "chave_secreta.txt")
            for b in backup.listar_backups(cfg):
                shutil.copy2(cfg.backup_dir / b["nome"], novos_bk / b["nome"])
        except ErroGerenciador:
            raise
        except Exception as e:
            self.registrar_erro()
            raise ErroGerenciador(f"Falha ao copiar (nada foi alterado no sistema): {e}")
        # troca o config.ini (com cópia de segurança) só depois de tudo conferido
        texto = self.config_path.read_text(encoding="utf-8-sig")
        self.config_path.with_name("config.ini.antes_mover").write_text(texto, encoding="utf-8")

        def trocar(txt, secao, chave_ini, valor):
            padrao = re.compile(rf"(\[{secao}\][^\[]*?^[ \t]*{chave_ini}[ \t]*=)[^\n]*", re.M)
            novo, n = padrao.subn(lambda m: m.group(1) + " " + valor.replace("\\", "/"), txt, count=1)
            if n != 1:  # chave ausente (config mínimo): acrescenta a seção no fim
                novo = txt.rstrip("\n") + f"\n\n[{secao}]\n{chave_ini} = " + valor.replace("\\", "/") + "\n"
            return novo
        texto = trocar(texto, "banco", "caminho", str(novo_db))
        texto = trocar(texto, "backup", "pasta", str(novos_bk))
        self.config_path.write_text(texto, encoding="utf-8")
        try:
            self.cfg()  # confere que o config novo é válido
        except ErroGerenciador:
            self.config_path.write_text(self.config_path.with_name("config.ini.antes_mover")
                                        .read_text(encoding="utf-8"), encoding="utf-8")
            raise
        renomeada = antigo_dir.with_name(f"{antigo_dir.name}_movido_{datetime.now():%Y%m%d_%H%M%S}")
        try:
            antigo_dir.rename(renomeada)
        except OSError:
            renomeada = antigo_dir  # em uso: tudo bem, o config já aponta para o novo
        msg = (f"Dados movidos para {destino}.\nBanco: {novo_db}\nBackups: {novos_bk}\n"
               f"A pasta antiga foi preservada em: {renomeada}\nAgora clique em 'Ligar servidor'.")
        self.registrar(msg)
        return msg

    # ------------------------------------------------------------ manutenção
    def instalar_dependencias(self, saida=print) -> None:
        """Cria/atualiza APENAS a pasta .venv. Não toca em dados, backups nem config."""
        self._exigir_servidor()
        venv = self.app_dir / ".venv"
        py_venv = venv / ("Scripts/python.exe" if NT else "bin/python")
        if not py_venv.exists():
            base = Path(sys.executable)
            if NT and base.name.lower() == "pythonw.exe":
                base = base.with_name("python.exe")
            saida("Criando ambiente virtual (.venv)...")
            r = _rodar([str(base), "-m", "venv", str(venv)])
            saida(r.stdout + r.stderr)
            if r.returncode != 0:
                raise ErroGerenciador("Não foi possível criar o ambiente virtual.")
        saida("Instalando bibliotecas (pode demorar)...")
        r = _rodar([str(py_venv), "-m", "pip", "install", "-r", str(self.app_dir / "requirements.txt")])
        saida(r.stdout[-1500:] + r.stderr[-1500:])
        if r.returncode != 0:
            raise ErroGerenciador("Falha ao instalar as bibliotecas (veja o texto acima).")
        saida("Pronto. Os dados do sistema não foram alterados.")

    def liberar_firewall(self) -> str:
        porta = self.cfg().porta
        _rodar(["netsh", "advfirewall", "firewall", "delete", "rule", "name=SistemaDespesas"])
        r = _rodar(["netsh", "advfirewall", "firewall", "add", "rule", "name=SistemaDespesas",
                    "dir=in", "action=allow", "protocol=TCP", f"localport={porta}"])
        if r.returncode != 0:
            raise ErroGerenciador("Falha ao liberar o firewall. Abra o gerenciador como Administrador.")
        return f"Firewall liberado para a porta {porta}."

    def inicio_automatico(self, ativar: bool) -> str:
        if not NT:
            raise ErroGerenciador("Disponível só no Windows.")
        if ativar:
            cmd = f'"{self.python(False)}" "{self.app_dir / "run.py"}" supervisor'
            r = _rodar(["schtasks", "/Create", "/TN", TAREFAS[0], "/SC", "ONSTART", "/RU", "SYSTEM",
                        "/RL", "HIGHEST", "/F", "/TR", cmd])
            if r.returncode != 0:
                raise ErroGerenciador("Não foi possível criar a tarefa. Abra o gerenciador como Administrador.")
            return "O supervisor (e o sistema) vão ligar sozinhos quando o computador for ligado."
        for t in TAREFAS:
            _rodar(["schtasks", "/Delete", "/TN", t, "/F"])
        return "Início automático removido."


def _tem(programa: str) -> bool:
    from shutil import which
    return which(programa) is not None
