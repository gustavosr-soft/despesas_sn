# Sistema de Despesas

Sistema web para registro e acompanhamento de despesas mensais, desenvolvido para funcionar em **rede local Windows**. O programa roda em um computador (servidor) e os demais acessam pelo navegador — nada precisa ser instalado nos outros computadores.

## Funcionalidades

- **Lançamentos de despesas** por dia, com descrição, categoria e valor
- **Categorias configuráveis** — crie, renomeie, reordene e desative categorias
- **Visualização mensal** no formato da planilha original, com totais por categoria e total geral
- **Relatórios** em Excel (.xlsx com fórmulas), PDF (A4 paisagem) e impressão direta pelo navegador
- **3 perfis de acesso**: Administrador, Lançador e Consulta
- **Controle de concorrência** — edições simultâneas são tratadas sem perda de dados
- **Exclusão lógica** com possibilidade de restauração pelo administrador
- **Auditoria** — histórico completo de todas as alterações
- **Backup automático** diário com retenção configurável
- **Início automático** silencioso com o Windows

## Requisitos

- **Servidor**: Windows 10/11 ou Windows Server
- **Python**: 3.9 ou mais novo (recomendado 3.11+)
- **Internet**: apenas durante a instalação (para baixar as bibliotecas)
- **Clientes**: qualquer computador da rede com navegador (Chrome, Edge, Firefox)

## Instalação Rápida

> **Modo rápido** — um único script faz tudo:

1. Instale o [Python](https://www.python.org/downloads/windows/) marcando **"Add python.exe to PATH"**
2. Copie a pasta do sistema para o servidor (ex.: `C:\Despesas`)
3. Clique com o botão direito em **`PREPARAR_SERVIDOR.bat`** → **Executar como administrador**
4. Siga as instruções na tela (ele instala tudo, cria o admin, libera o firewall e configura o início automático)
5. Acesse pelo navegador: `http://IP-DO-SERVIDOR:8080`

> **[Documentação completa de instalação →](https://gustavosr-soft.github.io/despesas_sn/)**

## Instalação Passo a Passo

### 1. Instalar o Python

Baixe o Python em [python.org/downloads](https://www.python.org/downloads/windows/).

Na **primeira tela** do instalador, marque:
- ✅ **Add python.exe to PATH**
- ✅ **Install for all users** (recomendado)

### 2. Copiar os arquivos

Copie a pasta do sistema para um **disco local** do servidor. Exemplo:
```
C:\Despesas\
```

> **Importante**: o banco de dados ficará dentro desta pasta. **Não compartilhe essa pasta na rede** — os outros computadores acessam pelo navegador, não pelos arquivos.

### 3. Configurar (opcional)

Abra o `config.ini` no Bloco de Notas e ajuste conforme necessário:

```ini
[servidor]
host = 0.0.0.0       # aceita conexões de outros computadores
porta = 8080          # porta de acesso

[backup]
pasta = backups       # ideal: outro disco (ex.: E:\BackupDespesas)
hora = 22:00          # horário do backup automático
manter = 30           # quantos backups manter

[relatorios]
empresa =             # nome que aparece nos relatórios
```

### 4. Instalar dependências

Clique com o botão direito em **`INSTALAR.bat`** → **Executar como administrador**.

Ele irá:
- Criar o ambiente virtual (`.venv`)
- Instalar as bibliotecas (Flask, Waitress, openpyxl, ReportLab)
- Criar o banco de dados
- Pedir o nome e a senha do administrador (mínimo 8 caracteres)
- Liberar a porta no Firewall do Windows

**Sem internet no servidor?** Em outro PC com internet, rode:
```batch
pip download -r requirements.txt -d pacotes
```
Copie a pasta `pacotes` para junto do `INSTALAR.bat` — ele a usará automaticamente.

### 5. Iniciar o servidor

**Com janela visível** (para ver mensagens):
```
INICIAR.bat
```

**Silencioso** (sem janela, saída em `logs\console.txt`):
```
INICIAR_SILENCIOSO.vbs
```

A tela mostra os endereços:
```
Neste computador:    http://localhost:8080
Outros computadores: http://192.168.x.x:8080
```

### 6. Início automático com o Windows

Rode como administrador:
```
INSTALAR_INICIO_AUTOMATICO.bat
```

O servidor passa a iniciar silenciosamente toda vez que o Windows ligar, mesmo sem ninguém logado.

Para remover: `REMOVER_INICIO_AUTOMATICO.bat`

### 7. Acessar nos outros computadores

Abra o navegador e digite o endereço mostrado no passo 5 (ex.: `http://192.168.1.100:8080`). Salve nos favoritos.

## Uso

### Tela do mês

A tela principal mostra as despesas do mês no formato da planilha: uma linha por lançamento, o valor na coluna da categoria, linha **TOTAIS** e **TOTAL GERAL** (sempre calculados).

### Lançamentos

- **Novo**: preencha data, descrição, categoria e valor (ex.: `1.234,56`)
- Vários lançamentos no mesmo dia são permitidos
- **Editar / Excluir**: links ao lado de cada linha
- Exclusão é lógica — o administrador pode restaurar

### Perfis de acesso

| Perfil | Permissões |
|--------|-----------|
| **Administrador** | Tudo: usuários, categorias, backup, auditoria, restaurar exclusões |
| **Lançador** | Cria lançamentos; edita e exclui apenas os seus |
| **Consulta** | Visualiza meses e gera relatórios; não altera nada |

### Relatórios

- **Excel** (.xlsx) — com fórmulas de soma, pronto para usar
- **PDF** — A4 paisagem, com cabeçalho repetido e paginação
- **Imprimir** — abre a janela de impressão do navegador no computador do usuário

### Categorias

O administrador pode criar, renomear, reordenar e desativar categorias no menu **Categorias**. Categorias padrão:

Funcionários · Impostos · Imobilizados · Serviços · Manutenção · Aluguel · Outros · Veículos

## Backup e Restauração

### Backup automático
- 1 por dia a partir das 22:00 (configurável)
- Mantém os 30 mais recentes
- Roda mesmo durante o uso do sistema

### Backup manual
- Menu **Backup** → **Fazer backup agora**
- Ou rode `BACKUP_AGORA.bat`

### Restaurar
1. Pare o servidor: `PARAR_SERVIDOR.bat`
2. Rode `RESTAURAR_BACKUP.bat` e informe o arquivo
3. Inicie novamente: `INICIAR.bat`

> **Recomendação**: troque a pasta de backup para **outro disco** no `config.ini`. Backup no mesmo disco não protege contra defeito do disco.

## Segurança

- Senhas armazenadas com PBKDF2-SHA256
- Bloqueio após 5 tentativas erradas (5 minutos)
- Sessão expira após 60 minutos sem uso
- Proteção CSRF em todos os formulários
- Headers de segurança (CSP, X-Frame-Options, etc.)
- Acesso por HTTP simples — adequado para rede interna confiável

## Arquitetura

```
Flask 3.x  ──►  Waitress (WSGI)  ──►  SQLite (WAL mode)
                  │
          rede local (HTTP)
                  │
        navegadores dos clientes
```

- **Flask**: framework web
- **Waitress**: servidor WSGI de produção (multi-thread)
- **SQLite**: banco de dados embutido (WAL mode, sem instalação)
- **openpyxl**: geração de Excel
- **ReportLab**: geração de PDF

O banco é acessado **somente pelo processo do servidor**. Os clientes usam apenas o navegador.

## Scripts disponíveis

| Script | Função |
|--------|--------|
| `PREPARAR_SERVIDOR.bat` | Faz tudo de uma vez (instala, admin, firewall, início automático) |
| `INSTALAR.bat` | Instala dependências e cria admin |
| `INICIAR.bat` | Inicia com janela visível |
| `INICIAR_SILENCIOSO.vbs` | Inicia sem janela (VBS) |
| `INICIAR_OCULTO.bat` | Inicia sem janela (pythonw) |
| `INSTALAR_INICIO_AUTOMATICO.bat` | Configura início com o Windows |
| `REMOVER_INICIO_AUTOMATICO.bat` | Remove início automático |
| `PARAR_SERVIDOR.bat` | Para o servidor |
| `CRIAR_ADMIN.bat` | Cria ou redefine admin |
| `LIBERAR_FIREWALL.bat` | Libera a porta no firewall |
| `BACKUP_AGORA.bat` | Backup manual imediato |
| `RESTAURAR_BACKUP.bat` | Restaura um backup |
| `VERIFICAR.bat` | Verifica configuração e banco |
| `CRIAR_ATALHO.bat` | Cria atalho na área de trabalho do Windows |

## Problemas comuns

| Problema | Solução |
|----------|---------|
| "Porta já em uso" | Mude `porta` no `config.ini` e rode `LIBERAR_FIREWALL.bat` |
| Esqueci a senha do admin | Rode `CRIAR_ADMIN.bat` com o mesmo nome de usuário |
| Outros PCs não acessam | Rode `LIBERAR_FIREWALL.bat`; confira se a rede está como "Privada" |
| Servidor não inicia | Veja a mensagem na janela e os arquivos em `logs\` |

## Testes

O sistema inclui 67 testes automatizados:

```bash
# Ativar o ambiente virtual
.venv\Scripts\activate

# Rodar todos os testes
python -m pytest tests/ -v
```

Os testes cobrem: valores monetários, regras de negócio, permissões, login, relatórios Excel/PDF, backup/restauração e concorrência (8 usuários simultâneos).

## Licença

Uso interno — todos os direitos reservados.
