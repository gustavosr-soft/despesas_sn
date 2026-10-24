# Sistema de Despesas — Análise e Planejamento (Etapa 1)

Data: 24/10/2026 · Status: análise concluída; **implementação feita em `sistema/` — ver `DECISOES_E_SUPOSICOES.md` e `sistema/LEIA-ME.txt`.**
Fontes analisadas: as duas imagens da pasta `DESPESAS` (únicos arquivos nela):
- `WhatsApp Image 2026-10-22 at 13.37.33.jpeg` → "Imagem 1" (modelo em branco)
- `WhatsApp Image 2026-10-22 at 14.30.22.jpeg` → "Imagem 2" (exemplo preenchido)

As demais pastas de `D:\dev\Nascimento` pertencem à automação da cotação semanal e não têm relação com este sistema.

---

## 1. O que as imagens mostram

### 1.1 Claramente visível
| Item | Imagem 1 | Imagem 2 |
|---|---|---|
| Título | "DESPESAS 11/2026" | "DESPESAS 11/2026" |
| Colunas fixas | DIA, DESCRIÇÃO | DIA, DESCRIÇÃO |
| Colunas de categoria (na ordem) | FUNCIONARIOS, IMPOSTOS, IMOBILIZADOS, SERVIÇOS, MANUTENÇÃO, ALUGUEL, **OUTROS** | FUNCIONARIOS, IMPOSTOS, IMOBILIZADOS, SERVIÇOS, MANUTENÇÃO, ALUGUEL, **VEICULOS** |
| Linha de totais | "TOTAIS" (vazia) | "TOTAIS" com um valor por categoria |
| Total do mês | "TOTAL GERAL ____" (vazio) | "TOTAL GERAL 100.000,00" |
| Linhas de lançamento | ~15 linhas em branco (contagem aproximada pela foto) | 6 linhas preenchidas + linhas em branco |

Observações sobre o formato:
- **Uma folha por mês/ano**, com o mês/ano no título (formato `MM/AAAA`).
- **Cada linha tem um único valor, colocado na coluna da sua categoria.** Não há linha com dois valores.
- Valores no padrão brasileiro: ponto como separador de milhar, vírgula nos centavos, sempre 2 casas (`30.000,00`). **Não aparece o símbolo R$.**
- O dia aparece com dois dígitos (`05`, `20`), sem mês/ano (que vêm do título).
- Os totais por categoria da Imagem 2 batem com os lançamentos (cada categoria tem 1 lançamento).

### 1.2 Lançamentos lidos na Imagem 2 (leitura sujeita a confirmação)
A foto está inclinada (as linhas da tabela sobem para a direita), então o alinhamento linha ↔ coluna foi estimado pela inclinação.

| Dia | Descrição (como aparece) | Categoria | Valor |
|---|---|---|---|
| 05 | Pag | Funcionários | 30.000,00 |
| 20 | icms | Impostos | 40.000,00 |
| (vazio) | Fatiadora 1/36 | Imobilizados | 500,00 |
| (vazio) | Viva sist | Serviços | 1.800,00 |
| (vazio) | dechadura | Manutenção | 50,00 |
| (vazio) | luzia | Aluguel | 6.000,00 |
| (vazio) | **não há descrição visível** | Veículos | 25,00 |

### 1.3 Ambíguo, ilegível ou inconsistente
1. **"Outros" × "Veículos"** na última coluna (ver seção 3.1).
2. **TOTAL GERAL incorreto na Imagem 2:** a soma das categorias é **78.375,00** (30.000 + 40.000 + 500 + 1.800 + 50 + 6.000 + 25), mas a imagem mostra **100.000,00**. Pode ser valor digitado à mão/placeholder de exemplo. O sistema deve sempre calcular o total, nunca aceitá-lo digitado — confirmar se foi só exemplo.
3. **O valor 25,00 (Veículos) parece não ter descrição** (sobram 7 valores para 6 descrições). Pode ser efeito da inclinação da foto ou exemplo incompleto.
4. **Dia vazio** em 5 das 7 linhas. Não dá para saber se significa "mesmo dia da linha anterior", "dia ainda não definido" ou "não importa".
5. **Significado das descrições:** "Pag" (pagamento?), "luzia" (nome do locador?), "dechadura" (talvez "fechadura"), "Viva sist" (sistema Viva?), "Fatiadora 1/36" (parcela 1 de 36?). São interpretações minhas — não confirmadas. A grafia foi mantida como aparece.
6. **Acentuação:** os cabeçalhos "FUNCIONARIOS" e "VEICULOS" aparecem sem acento nas imagens.
7. **Origem do arquivo:** os marcadores de tabela (alça no canto superior esquerdo, quadrado no canto inferior direito) e os sublinhados vermelhos de ortografia sugerem que a "planilha" é uma tabela do **Word**, não do Excel. É uma inferência — confirmar. Se existir o arquivo original, ele ajuda a copiar o layout fielmente.
8. Quantidade exata de linhas por página: ~15 (estimativa pela foto).
9. Orientação da página: parece paisagem, mas só se vê parte da folha.

---

## 2. Requisitos identificados

### 2.1 Do seu pedido (certos)
- Registrar despesas por dia; consultar agrupado por mês.
- Lançamento = **data, descrição, categoria, valor**.
- Interface simples, **com login e controle básico de acesso**.
- Rede local Windows: um computador servidor, demais acessam pela rede.
- **Arquivo de configuração** (endereço, porta, caminhos etc.).
- Banco simples de instalar, confiável com vários computadores simultâneos.
- Relatórios em **Excel (.xlsx) e PDF**, com **botão de imprimir** na interface.
- Relatório mensal: lançamentos, totais por categoria, total geral, no visual da planilha; filtros por mês e ano.

### 2.2 Deduzidos das imagens (a confirmar)
- Categorias são **colunas fixas no relatório**, na ordem mostrada.
- Total por categoria e total geral são sempre **calculados**.
- Valores exibidos em pt-BR com 2 casas, sem R$.
- Descrição é texto livre e curto.

### 2.3 Ainda não definidos
Ver seção 3.

---

## 3. Dúvidas e decisões pendentes

### 3.1 Divergência "Outros" × "Veículos" — como tratar (sem escolher)
**Fato:** a mesma 7ª coluna se chama OUTROS na Imagem 1 e VEICULOS na Imagem 2. (Pelos nomes dos arquivos, a Imagem 1 é anterior — 13:37 — e a Imagem 2 posterior — 14:30 —, mas isso não prova qual é a vigente.)

**Proposta de tratamento técnico (vale para qualquer opção):** categorias **configuráveis** — cadastradas no banco, não escritas no código:
- Tela de administração: criar, renomear, reordenar, ativar/desativar categorias.
- Lançamentos guardam o **ID** da categoria (renomear não quebra histórico).
- Categoria já usada **não é apagada**, só desativada (some das novas entradas, continua nos meses antigos).
- As colunas do relatório saem da lista de categorias ativas, na ordem configurada.

**Opções de negócio (você decide):**
| Opção | Efeito |
|---|---|
| A. Manter as duas ("Outros" **e** "Veículos") | 8 categorias; relatório com 10 colunas no total (cabe em A4 paisagem) |
| B. Só "Veículos" | 7 categorias; despesas que não se encaixam em nenhuma precisam de outro destino |
| C. Só "Outros" | 7 categorias; veículos entram em "Outros" |
| D. Renomear "Outros" para "Veículos" | Igual a B, mas decidindo o que acontece com meses antigos: mostram o nome novo ou o antigo? |

Perguntas: qual é a vigente? Haverá outras categorias no futuro? Meses antigos devem manter o conjunto de colunas que tinham na época?

### 3.2 Demais pendências
| # | Tema | Pergunta | Por que importa |
|---|---|---|---|
| 1 | Formato dos valores | Sempre positivos? Existem estornos/créditos (valor negativo)? Precisa de R$ na tela/relatório? Limite máximo? | O sistema guardará valores em **centavos inteiros** (evita erro de arredondamento); negativos mudam validações e totais |
| 2 | Total geral | O "100.000,00" da Imagem 2 foi só exemplo? | O sistema sempre calcula |
| 3 | Dia | O que significa dia vazio? Dia deve ser obrigatório? | Você pediu "data" em cada lançamento; sugiro obrigatório |
| 4 | Mais de um lançamento por dia | Confirmar | Veja recomendação em 6.3 |
| 5 | Parcelas/recorrência | "Fatiadora 1/36" e "Viva sist" repetem todo mês? Quer lançamento automático/recorrente? | Define se entra na v1 ou fica para depois |
| 6 | Permissões | Quantas pessoas? Perfis? Quem pode editar/excluir? Cada um vê só o que lançou? | Seção 6.4 propõe um modelo inicial |
| 7 | Segurança de rede | Aceita HTTP simples na rede interna ou quer HTTPS? | HTTP envia senha sem criptografia na rede; HTTPS exige certificado (aviso do navegador se autoassinado) |
| 8 | Backup | Onde (outro PC, HD externo, nuvem)? Frequência? Retenção? Quem restaura? | Seção 6.6 |
| 9 | Impressão | Impressora do próprio PC de cada usuário ou a do servidor? Aceita a janela de impressão do Windows? | Seção 6.7 |
| 10 | Relatórios | Só mensal, ou também resumo anual (mês × categoria)? Quebra de página: totais só na última página? | Define o escopo |
| 11 | Dados antigos | Precisa importar meses anteriores (Word/Excel)? | Entra no plano como etapa opcional |
| 12 | Meses fechados | Bloquear edição de meses já conferidos? | Evita alteração acidental |
| 13 | Servidor | Versão do Windows, IP fixo ou reserva no roteador, PC fica ligado sempre? Python/.NET já instalado? Há antivírus/firewall corporativo? | Define implantação |
| 14 | Arquivo original | Pode anexar o arquivo Word/Excel original? | Copiar o layout com fidelidade |
| 15 | Tecnologia | Preferência de linguagem/ferramenta (seção 5.3)? | Aguardo sua escolha |

---

## 4. Plano de execução por etapas

| Etapa | O que acontece | Entregável / critério de pronto |
|---|---|---|
| 0 | **Requisitos** — você responde a seção 3 e envia o arquivo original | Decisões registradas neste documento |
| 1 | **Escolha de tecnologias** — você aprova a arquitetura da seção 5/7 | Stack definida por escrito |
| 2 | **Desenho** — modelo de dados, telas (login, mês no formato da planilha, formulário de lançamento, categorias, usuários, relatórios), exemplo de config | Protótipo/rascunho de telas e do relatório aprovados |
| 3 | **Núcleo** — banco, login e perfis, categorias configuráveis, CRUD de lançamentos com histórico, visão mensal com totais calculados | Lançar, editar, excluir e ver o mês; totais conferidos contra a Imagem 2 recalculada |
| 4 | **Relatórios** — Excel, PDF e visão de impressão, filtros mês/ano | Relatório de 11/2026 com os dados da Imagem 2 batendo com o visual da planilha |
| 5 | **Operação** — arquivo de configuração, logs, backup e restauração | Restauração testada de verdade |
| 6 | **Testes** — automatizados (totais, centavos, permissões) e de simultaneidade (2–3 PCs lançando ao mesmo tempo) | Sem perda/duplicidade; conflito de edição tratado |
| 7 | **Implantação** — instalar no servidor, iniciar com o Windows, liberar porta no firewall, testar de cada PC cliente | Acesso por `http://<servidor>:<porta>` em todos os PCs |
| 8 | **Uso assistido** — 1 mês em paralelo com a planilha atual, treinamento rápido | Totais do sistema = totais da planilha |
| 9 | **(Opcional)** importar meses antigos, lançamentos recorrentes, resumo anual | Conforme prioridade |

---

## 5. Arquiteturas e bancos de dados

### 5.1 Arquiteturas possíveis
| Arquitetura | Prós | Contras | Adequada? |
|---|---|---|---|
| **A. Aplicação web** no servidor + navegador nos clientes; **só o servidor acessa o banco** | Nada para instalar nos clientes; um único ponto de atualização/backup; impressão pelo navegador | Processo do servidor precisa estar sempre rodando; configurar firewall e IP | **Sim — melhor encaixe** |
| B. Programa desktop em cada PC + arquivo de banco numa pasta compartilhada | Aparentemente simples | Vários PCs abrindo o mesmo arquivo pela rede: risco de travamento/corrupção (SQLite, Access e DuckDB desaconselham) | **Não** |
| C. Programa desktop em cada PC + banco cliente/servidor (PostgreSQL etc.) | Robusto | Instalar e manter o programa em cada PC e administrar o banco | Possível, mais pesado |
| D. Aplicação web + banco cliente/servidor (PostgreSQL) | O mais robusto e escalável | Instalação e manutenção maiores; exagero para poucos usuários e poucos dados | Se for crescer muito |

### 5.2 Bancos de dados
Volume esperado: dezenas de lançamentos por mês — **muito pequeno**. O que pesa é confiabilidade e simplicidade, não desempenho.

| Banco | Instalação | Acesso simultâneo | Confiabilidade em rede | Backup | Observação |
|---|---|---|---|---|---|
| **SQLite** (modo WAL), acessado só pelo servidor | Nenhuma (embutido na linguagem; 1 arquivo) | Muitos leitores + 1 escritor por vez — de sobra para este uso | Boa **se só o servidor abrir o arquivo**. Pasta compartilhada: não | Cópia consistente pela API de backup do próprio SQLite | A documentação oficial diz que o WAL "não funciona em sistema de arquivos de rede" e recomenda um processo servidor na frente do banco — exatamente a arquitetura A |
| **DuckDB** | Nenhuma (biblioteca/1 arquivo) | **1 processo lê e escreve**; vários processos só leem (somente leitura). Dentro de um único processo, várias threads escrevem com controle otimista (conflito gera erro) | Boa **como na linha acima**; a documentação pede "cuidado extra" com arquivo em pasta compartilhada/NAS | Cópia do arquivo com o servidor parado ou pela exportação | Projetado para **análise** de grandes volumes (colunar). Aqui seu ponto forte quase não aparece; lançamentos linha a linha e edições são o caso comum, não o ideal dele. Existe um protocolo remoto (Quack) para escrita multi-processo, que eu não avaliei a fundo |
| PostgreSQL | Instalador + serviço + senha + porta | Excelente, nativo | Excelente | `pg_dump` agendado | Melhor se crescer; instalação e manutenção maiores |
| SQL Server Express | Instalador pesado | Excelente | Excelente | Nativo | Bom em ambiente Windows; avaliar licença e limites |
| MariaDB/MySQL | Instalador + serviço | Excelente | Excelente | `mysqldump` | Semelhante ao PostgreSQL |
| Firebird | Instalador + serviço | Bom | Bom | `gbak` | Você já opera Firebird no mercado; **não** colocar estes dados no banco do sistema do mercado |
| Microsoft Access (.accdb) em pasta compartilhada | Precisa do Access/driver | Fraco | Histórico de corrupção com muitos usuários | Cópia | Não recomendo |
| Excel/CSV compartilhado | — | Péssimo (um usuário bloqueia o arquivo) | Ruim | — | Não recomendo |

**Avaliação do DuckDB para este cenário:** funciona **desde que** haja um único processo servidor dono do arquivo (arquitetura A). Nesse caso, ele não é pior em confiabilidade, mas também não traz vantagem: o volume é minúsculo e o padrão de uso é transacional (inserir/editar/excluir linha a linha), onde SQLite e PostgreSQL são a escolha natural. Os tipos de consulta do projeto (soma por categoria e mês) são simples e rápidos em qualquer um deles. Fora da arquitetura A (por exemplo, cada PC abrindo o arquivo pela rede), o DuckDB **não** atende.

### 5.3 Opções de linguagem/pilha (para você escolher)
| Pilha | Prós | Contras |
|---|---|---|
| **Python** (Flask ou FastAPI, servidor Waitress, openpyxl para Excel, ReportLab para PDF) | Você já usa Python + openpyxl na automação da cotação; código simples de manter; Excel/PDF maduros | Precisa instalar Python (ou empacotar um executável); iniciar como serviço exige NSSM/Agendador de Tarefas |
| **.NET** (ASP.NET Core + ClosedXML + QuestPDF) | Publica em um único executável sem instalar runtime; roda como Serviço do Windows nativamente | Mais verboso; exige ambiente de desenvolvimento .NET |
| Node.js ou Go | Alternativas viáveis | Sem vantagem clara aqui |

---

## 6. Respostas às suas avaliações

### 6.1 Interface
Tela de login → tela do mês com **grade parecida com a planilha** (linhas de lançamento, valor na coluna da categoria, linha TOTAIS, TOTAL GERAL) → formulário de lançamento (data, descrição, categoria, valor). Seletor de mês/ano, botões Excel, PDF e Imprimir. Administração (admin): usuários e categorias.

### 6.2 Totais
Sempre calculados a partir dos lançamentos; nunca digitados.

### 6.3 Mais de um lançamento por dia — faz sentido?
**Sim.** A planilha já tem uma linha por despesa e vários itens podem cair no mesmo dia. Proposta: sem limite de lançamentos por dia, ordenados por data e depois por ordem de inclusão. Pendente (3.2 #3): o que significa o dia vazio.

### 6.4 Controle de acesso (proposta inicial, a confirmar)
- **Administrador:** tudo, incluindo usuários, categorias, backup.
- **Lançador:** cria lançamentos; edita/exclui conforme regra definida por você (ex.: só os próprios).
- **Consulta:** só visualiza e gera relatórios.
Senhas guardadas com hash (nunca em texto), bloqueio após tentativas erradas e expiração de sessão configurável.

### 6.5 Editar e excluir
- **Editar:** permitido conforme o perfil; registra quem alterou e quando. Se duas pessoas editam o mesmo lançamento ao mesmo tempo, o segundo recebe um aviso de conflito em vez de sobrescrever em silêncio.
- **Excluir:** pede confirmação e é uma **exclusão lógica** (o lançamento sai dos totais, mas fica registrado com quem excluiu e quando), permitindo desfazer. Exclusão definitiva só pelo administrador, se você quiser.
- Opcional: bloquear edição de meses fechados.

### 6.6 Backup (proposta)
Cópia automática diária do arquivo do banco para outra pasta/disco (feita pela função de backup do próprio banco, não por cópia simples do arquivo em uso), com retenção configurável, mais um teste de restauração documentado. Pendente: destino, frequência e retenção (3.2 #8). Backup no mesmo disco do servidor **não** protege contra falha do disco.

### 6.7 Impressão — como funcionaria e limitações
**Importante:** em aplicação web, a impressão acontece no **computador de quem está usando o navegador**. O servidor não imprime nas impressoras dos clientes.

Proposta de funcionamento: o botão **Imprimir** abre uma visão do relatório formatada para papel (A4 paisagem, cabeçalho repetido) e **chama a janela de impressão do Windows/navegador**, onde o usuário escolhe impressora, cópias e confirma. PDF e Excel são baixados normalmente.

Limitações que dependem da tecnologia:
- Por segurança, navegadores **não imprimem sem a janela de confirmação**. Existe uma opção avançada (Chrome/Edge em modo "kiosk printing"), mas ela exige configurar cada PC e imprime direto na impressora padrão.
- Imprimir o PDF dentro da página pode se comportar diferente entre Chrome, Edge e Firefox; alternativa segura: abrir o PDF numa aba e usar o botão de imprimir do visualizador. Precisa ser validado nos navegadores que vocês usam.
- Impressão automática na impressora do **servidor** é possível (comando de impressão no Windows), mas é outro recurso e só atende a impressora conectada a ele.
- A visão de impressão e o PDF podem ter pequenas diferenças visuais; para evitar duplicidade, a definição final do layout precisa ser feita uma vez só (decisão da etapa 2).

### 6.8 Arquivo de configuração (chaves propostas)
Endereço/IP de escuta e porta; caminho do banco; pasta de backup, frequência e retenção; pasta de relatórios/temporários; pasta de logs e nível; tempo de expiração da sessão; chave secreta da aplicação; nome da empresa para o cabeçalho dos relatórios; ativação de HTTPS e caminhos de certificado (se escolhido). Formato (INI, JSON ou TOML) a definir com a pilha.

### 6.9 Pontos práticos de rede Windows
- Servidor com **IP fixo** (ou reserva no roteador) e, de preferência, nome na rede.
- **Regra de entrada no Firewall do Windows** para a porta escolhida.
- Iniciar junto com o Windows, mesmo sem ninguém logado; desativar suspensão do PC.
- Sem acesso à internet para operar (apenas na instalação).

---

## 7. Recomendação inicial (aguardando sua escolha)

**Arquitetura:** aplicação web (A) hospedada no servidor Windows, com **SQLite em modo WAL**, aberto **somente** pelo processo do servidor; clientes usam o navegador. Categorias configuráveis no banco. Relatórios gerados no servidor em Excel (com fórmulas de soma) e PDF, mais visão de impressão pelo navegador. Backup automático diário com a função de backup do banco.

**Motivos:**
1. Atende à rede local sem instalar nada nos clientes.
2. SQLite não exige instalação, é um arquivo só, e é confiável quando só um processo o acessa, que é o que esta arquitetura garante. A própria documentação do SQLite recomenda esse desenho para acesso pela rede.
3. O volume é pequeno e o uso é transacional; DuckDB não oferece ganho e tem restrição maior de múltiplos processos.
4. PostgreSQL continua sendo o caminho de evolução se o uso crescer; usando uma camada de acesso a dados padrão, a troca é possível sem refazer a aplicação.
5. Pilha sugerida: **Python** (você já usa na cotação). Alternativa se preferir sem instalar runtime: **.NET**.

**Próximo passo:** me diga (a) as decisões das seções 3.1 e 3.2 — mesmo que só as principais: categorias, permissões, impressão, backup — e (b) a arquitetura/pilha escolhida. Só então começo a implementação.

---

## Fontes
- DuckDB — Concurrency: https://duckdb.org/docs/2.0/connect/concurrency.html
- SQLite — Uso em rede: https://sqlite.org/useovernet.html
- SQLite — Write-Ahead Logging: https://sqlite.org/wal.html
