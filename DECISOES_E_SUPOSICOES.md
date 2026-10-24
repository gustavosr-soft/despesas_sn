# Sistema de Despesas — decisões e suposições da implementação

Data: 24/10/2026. Pedido: seguir o `PLANEJAMENTO_DESPESAS.md`, adotando opções simples e seguras nas pendências, sem parar para perguntar. Tudo abaixo pode ser mudado depois; a coluna "Como mudar" diz onde.

## Tecnologia (seção 5/7 do planejamento)
Python + Flask (aplicação web), Waitress (servidor para Windows), **SQLite em modo WAL** acessado só pelo servidor, openpyxl (Excel), ReportLab (PDF). DuckDB **não** foi usado (sem vantagem para este volume e uso transacional). Os outros PCs usam apenas o navegador.

## Pendências da seção 3.2 e o que foi adotado
| # | Tema | Adotado | Como mudar |
|---|---|---|---|
| 3.1 | Outros × Veículos | **As duas existem e ficam ativas** (opção A): nenhum dado se perde e o relatório fica com 8 colunas. Nomes com acento (nas fotos estavam sem). | Menu Categorias: desativar/renomear. Meses já lançados mantêm a coluna desativada se ela tiver lançamentos. |
| 1 | Valores | Guardados em **centavos inteiros**; sempre **maiores que zero** (sem estorno/crédito); máximo 999.999.999,99; sem "R$" na planilha (como no papel). Entrada aceita `1.234,56`, `1234,56` ou `1234.56`. | `despesas/money.py` |
| 2 | Total geral | Sempre calculado. O "100.000,00" da Imagem 2 foi tratado como erro/exemplo: a soma real daquele exemplo é **78.375,00**. | — |
| 3 | Dia | **Data completa obrigatória**; não existe "dia vazio". | — |
| 4 | Vários por dia | **Permitido**, sem limite; ordem: data e depois ordem de inclusão. | — |
| 5 | Parcelas/recorrência | **Fora da v1**: "Fatiadora 1/36" e "Viva sist" são digitados a cada mês. | Etapa futura |
| 6 | Permissões | 3 perfis: Administrador (tudo), Lançador (cria; edita/exclui só os seus), Consulta (só vê e gera relatórios). Senha mínima de 8 caracteres, troca obrigatória no primeiro acesso, bloqueio de 5 min após 5 erros, sessão de 60 min. | `config.ini` [seguranca]; regras em `despesas/servicos.py` |
| 7 | Segurança de rede | **HTTP simples** (rede interna confiável), porta 8080, cookie sem flag "seguro". Proteções ativas: CSRF, hash de senha, cabeçalhos de segurança, texto escapado. | HTTPS exigiria certificado; fica como etapa futura |
| 8 | Backup | Diário a partir das 22:00 (se o servidor estava desligado, ao ligar), 30 mantidos, na pasta `backups` do servidor — **recomenda-se trocar para outro disco**. Restauração manual com o servidor parado. | `config.ini` [backup] |
| 9 | Impressão | Botão **Imprimir** abre visão A4 paisagem e chama a janela de impressão do navegador/Windows **no PC de quem clicou**. PDF abre no navegador. Sem impressão silenciosa. | — |
| 10 | Relatórios | Só **mensal** (escolha de mês e ano); mínimo de 15 linhas como na folha de papel (completa com linhas em branco); **sem resumo anual**; totais só no fim do relatório (várias páginas repetem o cabeçalho). | Etapa futura |
| 11 | Dados antigos | **Sem importação** de meses anteriores. | Etapa futura |
| 12 | Meses fechados | **Sem bloqueio** de mês; todo alterar/excluir fica no Histórico (menu, só administrador). | Etapa futura |
| 13 | Servidor | Assume Windows 10/11 ou Server com Python 3.9+ (o instalador orienta a instalar), IP fixo recomendado. | LEIA-ME seção 2 |
| 14 | Arquivo original | Layout copiado das fotos (título, colunas, TOTAIS, TOTAL GERAL). | — |
| 15 | Exclusão/edição | Exclusão **lógica** (restaurável pelo administrador); edição com controle de versão (aviso de conflito se duas pessoas editarem ao mesmo tempo). | — |

## Itens nomeados como "descrição" lidos nas fotos
Os exemplos da Imagem 2 (Pag, icms, Fatiadora 1/36, Viva sist, dechadura, luzia) foram usados só como dados de teste, com a grafia da foto. O valor de 25,00 em Veículos, que não tinha descrição visível, recebeu a descrição fictícia "veículo" apenas no teste.

## O que foi verificado e o que NÃO foi
Verificado (em Linux): 67 testes automáticos — valores, configuração, regras de negócio, permissões, CSRF, bloqueio de login, relatórios Excel (fórmulas recalculadas no LibreOffice: 78.375,00) e PDF (texto e paginação), backup/restauração, e **8 usuários lançando ao mesmo tempo contra um servidor Waitress real, com backups no meio, sem perder nem duplicar lançamentos**. Telas conferidas num navegador (Chromium).
**Não verificado em Windows:** os `.bat`/`.ps1` (instalação, firewall, início automático) foram escritos mas não executados num Windows; e a janela de impressão real do Windows com uma impressora física. Se algum script falhar, a mensagem de erro aparece na janela — me envie.
