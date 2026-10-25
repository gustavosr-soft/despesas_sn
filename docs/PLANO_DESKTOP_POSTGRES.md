# Plano: PostgreSQL + versão desktop do Sistema de Despesas

Data: 25/10/2026 · Base: versão web atual (Flask + SQLite), 83 testes, schema v3.

## 1. Resposta direta às duas perguntas

**"Desktop seria mais fácil de comunicar?"** Depende do que você chama de comunicação.
- Para o *usuário*: sim, um programa instalado dá sensação de app nativo, atalhos, janelas, impressão direta.
- Para a *operação*: não necessariamente. Hoje 1 pasta no servidor atualiza todo mundo; no desktop cada PC precisa instalar e atualizar o programa, e todos precisam falar a mesma versão de banco.
- O que os problemas recentes mostraram (banco zerado, DBeaver travando, gerenciador fechando) **não vieram da interface web**; vieram de banco em arquivo dentro da pasta do app e de operação manual. Isso já foi tratado (trava contra banco vazio, supervisor, cópia para consulta).

**"Servidor só com banco, PostgreSQL?"** Sim, é viável e é a arquitetura correta para vários PCs com app desktop: SQLite não serve para vários clientes pela rede (o modo WAL não funciona em pasta compartilhada). PostgreSQL resolve concorrência, consulta ao vivo no DBeaver e segurança por usuário. O custo é instalar/manter o PostgreSQL no servidor (senhas, porta, backup `pg_dump`, atualizações).

**Ponto de atenção (segurança):** com app desktop falando direto com o banco, a regra de negócio e a senha do banco ficam em cada PC. Quem abrir o config pode conectar no DBeaver e alterar tudo, sem passar pelas regras e pela auditoria do app. Por isso o plano prevê **permissões no próprio banco** (papéis + Row Level Security), não só no programa.

## 2. Arquiteturas possíveis

| | A) Web + PostgreSQL | B) Desktop direto no PostgreSQL | C) Desktop → API → PostgreSQL |
|---|---|---|---|
| Instalação nos PCs | nenhuma | instalar app em cada PC | instalar app em cada PC |
| Atualização | 1 lugar (servidor) | cada PC | cada PC (mais tolerante a versão) |
| Regra de negócio | no servidor | no cliente + banco | no servidor |
| Segurança | boa (já existe) | exige papéis + RLS no banco | boa |
| Esforço | baixo (dias) | alto (semanas) | o mais alto |
| Ganho para o usuário | DBeaver ao vivo, estabilidade | app nativo | app nativo + controle central |

**Recomendação:** executar em fases. **Fase 1 (A)** entrega estabilidade e DBeaver ao vivo com pouco risco. **Fase 2 (B)** só se o app nativo continuar sendo desejado; a Fase 1 já deixa o terreno pronto.

## 3. Fases

### Fase 0: Congelar a base atual (já feita)
Web estável, supervisor, backup portátil, relatórios por período, 83 testes. Critério: servidor rodando 1 semana sem intervenção.

### Fase 1: PostgreSQL por trás da versão atual (estimativa: 1-2 dias)
1. Instalar PostgreSQL 16 no servidor (instalador EDB), serviço automático, porta 5432 só na LAN.
2. Camada de banco com dois motores (config `[banco] tipo = sqlite|postgres`): adaptador de conexão com `?`→`%s`, `RETURNING id`, transação serializada por *advisory lock* (equivale ao `BEGIN IMMEDIATE`), `citext` para usuário/categoria sem diferenciar maiúsculas.
3. Comando `pg-preparar`: cria banco, papel do app, papel de leitura (DBeaver) e extensões; grava o config.
4. Backup continua em arquivo `.db` portátil (exporta/importa tabelas); agendamento já existe.
5. Comando `migrar-para-postgres`: copia SQLite → PostgreSQL, **confere contagens e totais por mês**, só então troca o `config.ini`. O SQLite antigo fica intacto como retorno.
6. Gerenciador/supervisor: status do PostgreSQL, restaurar e cópia para consulta adaptados.
7. Testes rodando nos dois motores (suíte completa contra PostgreSQL real).

Critério de aceite: totais de todos os meses idênticos antes/depois; DBeaver consulta ao vivo com o papel de leitura; derrubar o app não derruba o banco; restaurar backup funciona.
Rollback: voltar `tipo = sqlite` no config.

*(Parte deste trabalho foi iniciada e revertida em 24/10 por decisão do usuário; será retomada do zero se aprovado.)*

### Fase 2: Preparar o desktop (estimativa: 2-3 dias)
- Congelar a camada de serviços (`servicos.py`, `reports.py`, `money.py`, `db.py`) como biblioteca **sem dependência de Flask**; ela já é separada, falta só limpar.
- Papéis no PostgreSQL por perfil (`despesas_consulta`, `despesas_lancador`, `despesas_admin`) e **RLS**: lançador altera apenas os próprios lançamentos; consulta só lê; ninguém altera a tabela de auditoria diretamente (gatilhos gravam a auditoria no banco).
- Login: usuário do app ↔ papel do PostgreSQL (um papel por pessoa), eliminando a senha única compartilhada.
- Definir como o app descobre atualizações (campo `versao_minima` no banco: app mais velho recusa abrir).

### Fase 3: Aplicativo desktop (estimativa: 2-4 semanas)
Tecnologia sugerida: **Python + PySide6 (Qt)**, empacotado com PyInstaller em um instalador (.exe). Motivo: reaproveita 100% da camada de serviços e dos relatórios (reportlab/openpyxl); alternativa mais simples é um *shell* (pywebview/WebView2) em volta da web atual, que entrega "app" em dias mas continua exigindo o servidor web.

Tradução das telas (web → desktop):
1. Login e troca de senha
2. Tela do mês: grade de lançamentos, cartões de resumo, formulário de novo lançamento, editar/excluir, ver excluídos
3. Relatórios: período, filtros, prévia, PDF/Excel/impressão (reutiliza `resumo_periodo` e `reports`)
4. Administração: categorias, usuários, histórico, painel do servidor/backup
5. Impressão direta com a janela do Windows

Ordem de entrega: login → mês (leitura) → lançar/editar → relatórios → admin → instalador. Cada etapa é testável com o PostgreSQL real.

### Fase 4: Implantação e convivência
- Piloto com 1-2 PCs, web continuando ativa em paralelo por 2 semanas.
- Atualização do app: instalador novo + checagem de versão mínima.
- Desligar a web somente depois de 2 semanas sem pendências.

## 4. Riscos e respostas
| Risco | Resposta |
|---|---|
| PostgreSQL mal configurado/exposto | só LAN, `pg_hba.conf` restrito, papéis sem DDL, backup diário testado |
| Perda de dados na migração | cópia antes, conferência por totais, SQLite preservado, ensaio em cópia |
| Versões diferentes do app no mesmo banco | `versao_minima` no banco; schema versionado |
| Senha do banco nos PCs | papel por pessoa + RLS; nada de senha única de superusuário |
| Esforço do desktop maior que o ganho | decidir após a Fase 1; shell web é o plano B barato |

## 5. Decisões pendentes (do usuário)
1. Aprovar a Fase 1 (PostgreSQL por trás da web) agora?
2. Quantos PCs vão usar o sistema? (define se vale o esforço do desktop nativo)
3. Quem instala e mantém o PostgreSQL no servidor?
4. Desktop nativo (Qt) ou shell sobre a web como primeiro passo?
