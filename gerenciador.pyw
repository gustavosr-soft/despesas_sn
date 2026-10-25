"""Gerenciador do Sistema de Despesas (janela).

Abra pelo GERENCIAR.bat ou com duplo clique neste arquivo. Rode NO COMPUTADOR SERVIDOR.
Também funciona em texto:  python gerenciador.pyw ligar | desligar | reiniciar | status | backup
Qualquer erro é gravado em logs\\gerenciador.log e mostrado na tela (a janela não fecha sozinha).
"""
import os
import sys
import threading
import traceback
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))


def _erro_fatal(texto: str) -> None:
    try:
        pasta = AQUI / "logs"
        pasta.mkdir(exist_ok=True)
        with open(pasta / "gerenciador_erro.log", "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    except OSError:
        pass
    try:
        import tkinter
        from tkinter import messagebox
        r = tkinter.Tk()
        r.withdraw()
        messagebox.showerror("Gerenciador de Despesas", texto[-1800:])
    except Exception:
        print(texto)


def modo_texto(args) -> int:
    from despesas.gerenciador import ErroGerenciador, Gerenciador
    g = Gerenciador(AQUI)
    acoes = {"ligar": g.ligar, "desligar": g.desligar, "reiniciar": g.reiniciar,
             "backup": lambda: f"Backup criado: {g.backup_agora()}",
             "consulta": lambda: f"Copia para consulta (DBeaver): {g.copia_para_consulta()}",
             "mover": lambda: g.mover_dados(args[1])}
    try:
        if args[0] == "status":
            s = g.status()
            print("LIGADO" if s.rodando else "DESLIGADO", "| saude:", "ok" if s.saude_ok else "-", "| pid:", s.pid)
            i = g.info_banco()
            print(f"Banco: {i.caminho} existe={i.existe} schema={i.schema} usuarios={i.usuarios} "
                  f"lancamentos={i.lancamentos} integridade={i.integridade}")
        else:
            print(acoes[args[0]]())
        return 0
    except ErroGerenciador as e:
        print("ERRO:", e)
        return 1
    except KeyError:
        print(__doc__)
        return 2


def janela() -> None:
    import queue
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox, scrolledtext, ttk

    from despesas import db
    from despesas.gerenciador import ErroGerenciador, Gerenciador

    g = Gerenciador(AQUI)
    raiz = tk.Tk()
    raiz.title("Sistema de Despesas - Gerenciador" + (" (via rede)" if g.eh_pasta_de_rede() else ""))
    raiz.geometry("760x640")
    raiz.minsize(700, 560)
    fila: "queue.Queue" = queue.Queue()
    ocupado = {"v": False}

    def erro_tk(exc, val, tb):
        texto = "".join(traceback.format_exception(exc, val, tb))
        g.registrar("ERRO na janela:\n" + texto)
        messagebox.showerror("Erro", f"{val}\n\n(Detalhes em logs\\gerenciador.log)")
    raiz.report_callback_exception = erro_tk

    # ---------------------------------------------------------- aparência
    topo = tk.Frame(raiz, pady=10)
    topo.pack(fill="x")
    lb_status = tk.Label(topo, text="Verificando...", font=("Segoe UI", 20, "bold"))
    lb_status.pack()
    lb_end = tk.Label(topo, text="", font=("Segoe UI", 10), fg="#444")
    lb_end.pack()

    quadro = ttk.LabelFrame(raiz, text=" Banco de dados ")
    quadro.pack(fill="x", padx=12, pady=6)
    lb_banco = tk.Label(quadro, text="", justify="left", anchor="w", font=("Consolas", 9))
    lb_banco.pack(fill="x", padx=8, pady=6)

    def botao(pai, texto, cmd, cor=None, largura=22):
        b = tk.Button(pai, text=texto, command=cmd, width=largura, height=2,
                      bg=cor or "#f0f0f0", relief="groove", font=("Segoe UI", 10, "bold" if cor else "normal"))
        return b

    linha1 = tk.Frame(raiz)
    linha1.pack(pady=4)
    linha2 = tk.Frame(raiz)
    linha2.pack(pady=4)
    linha3 = tk.Frame(raiz)
    linha3.pack(pady=4)

    caixa = scrolledtext.ScrolledText(raiz, height=12, font=("Consolas", 9), state="disabled")
    caixa.pack(fill="both", expand=True, padx=12, pady=8)

    def escrever(texto: str) -> None:
        caixa.configure(state="normal")
        caixa.insert("end", texto.rstrip() + "\n")
        caixa.see("end")
        caixa.configure(state="disabled")

    # ------------------------------------------------- execução em segundo plano
    def em_thread(trabalho, depois=None, titulo=""):
        if ocupado["v"]:
            messagebox.showinfo("Aguarde", "Outra operação ainda está em andamento.")
            return
        ocupado["v"] = True
        escrever(f"> {titulo}..." if titulo else "> ...")

        def corpo():
            try:
                resultado = trabalho()
                fila.put(("ok", resultado, depois))
            except ErroGerenciador as e:
                g.registrar(f"{titulo}: {e}")
                fila.put(("erro", str(e), None))
            except Exception as e:
                g.registrar_erro()
                fila.put(("erro", f"Erro inesperado: {e}\n(Detalhes em logs\\gerenciador.log)", None))
        threading.Thread(target=corpo, daemon=True).start()

    def bombear():
        try:
            while True:
                tipo, dado, depois = fila.get_nowait()
                if tipo == "estado":
                    mostrar_estado(*dado)
                    continue
                ocupado["v"] = False
                if tipo == "ok":
                    if dado:
                        escrever(str(dado))
                    if depois:
                        depois()
                else:
                    escrever("ERRO: " + dado)
                    messagebox.showerror("Não foi possível", dado)
                atualizar()
        except queue.Empty:
            pass
        raiz.after(300, bombear)

    def mostrar_estado(st, info, erro):
        if erro:
            lb_status.configure(text="⚠ Problema", fg="#b3261e")
            lb_end.configure(text=erro)
            lb_banco.configure(text="")
            return
        if st.rodando and st.saude_ok:
            lb_status.configure(text="● SERVIDOR LIGADO", fg="#1b6e3a")
        elif st.rodando:
            lb_status.configure(text="● Ligado, mas não responde direito", fg="#c77700")
        else:
            lb_status.configure(text="● SERVIDOR DESLIGADO", fg="#b3261e")
        lb_end.configure(text=f"Porta {st.porta}" + (f"  |  processo {st.pid}" if st.pid else ""))
        if not info.existe:
            txt = f"{info.caminho}\nARQUIVO NÃO ENCONTRADO"
            if g.banco_ausente_com_backups():
                txt += "\nHá backups: use 'Restaurar backup'. Nada será criado por cima."
        else:
            aviso = "" if info.schema in (0, db.VERSAO_SCHEMA) else f"  (esperado {db.VERSAO_SCHEMA}: será atualizado ao ligar)"
            txt = (f"{info.caminho}  ({info.tamanho_kb} KB)\n"
                   f"Schema {info.schema}{aviso}  |  {info.usuarios} usuário(s)  |  "
                   f"{info.lancamentos} lançamento(s)  |  integridade: {info.integridade or info.erro}")
        lb_banco.configure(text=txt)

    def atualizar():
        def trabalho():
            try:
                fila.put(("estado", (g.status(), g.info_banco(), ""), None))
            except ErroGerenciador as e:
                fila.put(("estado", (None, None, str(e)), None))
            except Exception as e:
                g.registrar_erro()
                fila.put(("estado", (None, None, f"Erro: {e}"), None))
        threading.Thread(target=trabalho, daemon=True).start()

    def auto():
        if not ocupado["v"]:
            atualizar()
        raiz.after(4000, auto)

    # ---------------------------------------------------------------- ações
    def ligar():
        em_thread(g.ligar, titulo="Ligando o servidor")

    def desligar():
        if messagebox.askyesno("Desligar", "Desligar o servidor?\nQuem estiver usando perde a conexão.\n"
                               "Um backup de segurança será feito."):
            em_thread(g.desligar, titulo="Desligando o servidor")

    def reiniciar():
        if messagebox.askyesno("Reiniciar", "Reiniciar o servidor?"):
            em_thread(g.reiniciar, titulo="Reiniciando o servidor")

    def backup_agora():
        em_thread(lambda: f"Backup criado: {g.backup_agora()}", titulo="Fazendo backup")

    def restaurar():
        try:
            lista = g.listar_backups()
        except ErroGerenciador as e:
            messagebox.showerror("Erro", str(e))
            return
        if not lista:
            messagebox.showinfo("Restaurar", "Não há backups.")
            return
        top = tk.Toplevel(raiz)
        top.title("Restaurar backup")
        top.geometry("520x360")
        top.transient(raiz)
        tk.Label(top, text="Escolha o backup (o mais recente fica no topo):", pady=6).pack()
        lb = tk.Listbox(top, font=("Consolas", 10), activestyle="dotbox")
        for b in lista:
            lb.insert("end", f"{b['nome']}   {b['quando']}   {round(b['tamanho'] / 1024)} KB")
        lb.selection_set(0)
        lb.pack(fill="both", expand=True, padx=10)

        def confirmar():
            sel = lb.curselection()
            if not sel:
                return
            nome = lista[sel[0]]["nome"]
            msg = (f"Substituir os dados ATUAIS por este backup?\n\n{nome}\n\n"
                   "O banco atual é guardado antes (pasta dados\\antes_restauracao_...).\n"
                   "O servidor será desligado se estiver ligado.")
            if not messagebox.askyesno("Confirmar restauração", msg, icon="warning"):
                return
            top.destroy()

            def trabalho():
                if not g.supervisor_vivo() and g.status().rodando:
                    g.desligar(backup_antes=False)
                guarda = g.restaurar(nome)
                if isinstance(guarda, str):  # via supervisor: a mensagem já vem pronta
                    return guarda
                return f"Restaurado: {nome}\nBanco anterior guardado em: {guarda}\nClique em 'Ligar servidor'."
            em_thread(trabalho, titulo="Restaurando backup")
        tk.Button(top, text="Restaurar o selecionado", command=confirmar, bg="#fff3cd", height=2).pack(pady=8)

    def navegador():
        try:
            webbrowser.open(f"http://{g.host() if g.eh_pasta_de_rede() else 'localhost'}:{g.porta()}")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def abrir_pasta(pasta):
        try:
            Path(pasta).mkdir(parents=True, exist_ok=True)
            os.startfile(str(pasta))  # só Windows
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def instalar():
        if messagebox.askyesno("Instalar", "Instalar/atualizar as bibliotecas?\n"
                               "Isto não apaga nem altera os dados."):
            saidas = []
            em_thread(lambda: (g.instalar_dependencias(saidas.append), "\n".join(saidas))[1],
                      titulo="Instalando dependências")

    def consulta():
        em_thread(lambda: f"Cópia criada (abra esta no DBeaver, não o banco real):\n{g.copia_para_consulta()}",
                  titulo="Gerando cópia para consulta")

    def mover():
        from tkinter import filedialog
        pasta = filedialog.askdirectory(title="Escolha a pasta FORA do sistema (ex.: C:\\DespesasDados)",
                                        initialdir="C:\\")
        if not pasta:
            return
        if not messagebox.askyesno("Mover dados", f"Mover banco, chave e backups para:\n{pasta}\n\n"
                                   "O servidor será desligado (se estiver ligado). Nada é apagado: a pasta\n"
                                   "antiga fica renomeada e o config.ini antigo é guardado.", icon="warning"):
            return

        def trabalho():
            if g.status().rodando:
                g.desligar()
            return g.mover_dados(pasta)
        em_thread(trabalho, titulo="Movendo dados")

    def verificar_log():
        pasta = g.pasta_logs()
        for nome in ("despesas.log", "servidor_saida.log"):
            arq = pasta / nome
            if arq.exists():
                escrever(f"--- {nome} (últimas linhas) ---\n" + g._ultimas_linhas(arq, 20))

    # ---------------------------------------------------------------- botões
    botao(linha1, "▶  Ligar servidor", ligar, "#c8e6c9").grid(row=0, column=0, padx=6)
    botao(linha1, "■  Desligar servidor", desligar, "#ffcdd2").grid(row=0, column=1, padx=6)
    botao(linha1, "⟳  Reiniciar", reiniciar, "#fff9c4").grid(row=0, column=2, padx=6)
    botao(linha2, "Fazer backup agora", backup_agora).grid(row=0, column=0, padx=6)
    botao(linha2, "Restaurar backup...", restaurar).grid(row=0, column=1, padx=6)
    botao(linha2, "Abrir o sistema no navegador", navegador).grid(row=0, column=2, padx=6)
    pequeno = dict(width=22, height=1)
    for i, (t, c) in enumerate([
        ("Instalar / atualizar dependências", instalar),
        ("Liberar firewall", lambda: em_thread(g.liberar_firewall, titulo="Liberando firewall")),
        ("Ativar supervisor (liga sozinho + rede)", lambda: em_thread(g.ativar_supervisor, titulo="Ativando supervisor")),
        ("Desativar supervisor", lambda: em_thread(g.desativar_supervisor, titulo="Desativando supervisor")),
        ("Atualizar supervisor (pós-update)", lambda: em_thread(g.reiniciar_supervisor, titulo="Atualizando supervisor")),
        ("Ver logs", verificar_log),
        ("Abrir pasta de backups", lambda: abrir_pasta(g.pasta_backups() or (g.base / "backups"))),
        ("Cópia p/ consulta (DBeaver)", consulta),
        ("Mover dados p/ outra pasta...", mover),
    ]):
        tk.Button(linha3, text=t, command=c, **pequeno).grid(row=i // 3, column=i % 3, padx=6, pady=2)

    if g.eh_pasta_de_rede():
        if g.supervisor_vivo():
            escrever("MODO REDE: os comandos vão ao supervisor do servidor. Instalar, firewall e mover dados\n"
                     "só no próprio servidor.")
        else:
            escrever(g.MSG_SUPERVISOR)
    elif not g.supervisor_vivo():
        escrever("Dica: clique em 'Ativar supervisor' para o sistema ligar sozinho com o Windows, religar se\n"
                 "cair e poder ser controlado por outros computadores da rede.")
    escrever("Pronto. Nenhuma ação aqui apaga o banco de dados.")
    bombear()
    atualizar()
    raiz.after(4000, auto)
    raiz.mainloop()


def main() -> int:
    if len(sys.argv) > 1:
        return modo_texto(sys.argv[1:])
    try:
        janela()
    except Exception:
        _erro_fatal("O gerenciador encontrou um erro:\n\n" + traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
