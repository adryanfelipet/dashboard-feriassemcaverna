# CLAUDE.md — Dashboard de vendas Férias Sem Caverna

> Lido automaticamente pelo Claude Code ao abrir o repositório. Criado a partir do
> template de dashboard (High Ticket) e **adaptado para funil de vendas**: só 2
> abas (Meta Ads via Adveronix + Compradores), sem aba Conversas e sem MQL.

---

## O que é

Dashboard de **vendas Férias Sem Caverna** (funil de vendas) — um app de BI estático (HTML/CSS/JS
puro + Chart.js via CDN) publicado no **GitHub Pages**, que cruza a lista de
**Leads** com o gerenciador de mídia paga e se atualiza sozinho a cada ~30 min
(build 100% na nuvem via GitHub Actions, disparado externamente pelo cron-job.org).

- **URL pública:** `https://adryanfelipet.github.io/dashboard-feriassemcaverna/`
- **Somente leitura** das planilhas. Nunca escrever de volta.

## Fontes de dados (Google Sheets)

Spreadsheet ID: `1oj4VyTlGs0DjwEbRf2AvpiVM2Wk_Tb-lZgHWr1-iR-g` ("Dashboard | Férias sem caverna").

| Aba | gid | Colunas usadas |
|-----|-----|----------------|
| **Leads** (Meta Ads via Adveronix — nível anúncio, diário) | `0` | `Day` · `Campaign Name` · `Ad Set Name` · `Ad Name` · `Ad ID` · `Amount Spent` · `Impressions` · `Link Clicks` · `Landing Page Views` · `Initiate Checkouts` · `Leads` · `Purchases` |
| **Compradores** (webhook do checkout) | `649461939` | `Data` · `Nome` · `Email` · `Telefone` · `Produto` · `Oferta` · `Status` · `Faturamento` · `Receita` · `Método de Pagamento` · `utm_source` · `utm_medium` · `utm_campaign` · `utm_content` · `utm_term` · `src` · `sck` |

URL de export CSV: `https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>`
Não renomear/recriar as abas (o gid mudaria).

### Leads
Vêm da coluna `Leads` da aba de Meta Ads (não há lista de pessoas). `process()`
expande cada lead em 1 registro de `leads[]` (com camp/adset/ad e `q=0`) para o
front contar/filtrar igual ao template. **Sem critério de MQL** neste funil —
métricas de MQL aparecem "–".

### Vendas & Faturamento (aba Compradores)
`build.py` → `build_sales()`: 1 registro por linha com Status aprovado
(`APPROVED_STATUS`; Status vazio também conta), na data real da compra.
Atribuição por UTM: `utm_campaign` → campanha, `utm_medium` → conjunto,
`utm_content` → anúncio (Meta envia `{{campaign.name}}`/`{{adset.name}}`/`{{ad.name}}`;
`unify_names()` ignora caixa/acentos/espaços). Venda sem `utm_campaign` conta nos
totais como `(sem campanha)` / `src="org"`.

### Imposto da mídia paga
`TAX_FACTOR` em `build.py`, com **default `1.13806`** (13,806%) já configurado no
template — aplica-se somente ao gasto de **Meta Ads**. O toggle "Imposto Meta"
fica **ativo por padrão** (`STATE.tax=true` em `app.js`) e aplica o fator em
todo o gasto de mídia paga/derivados (CPL, CPMQL, CAC etc.) via `taxf()`, que só
multiplica `a.sp` (gasto do Meta Ads) — nunca outras fontes; desativar o toggle
volta ao gasto sem imposto. Se o cliente tiver um fator diferente, ajuste
`TAX_FACTOR`; se não houver imposto, use `TAX_FACTOR = 1.0`.

### Convenções de campanha (sigla do funil)
`MAIN_PRODUCT_PREFIX` em `build.py` está **vazio** → todas as campanhas da conta
entram. Quando a sigla for definida, preencha-a: `campaign_allowed()` passa a
manter só as campanhas (Meta e vendas) cujo nome contém a sigla.

## Arquitetura / arquivos

```
build/build.py            # lê os CSVs (read-only), emite REGISTROS BRUTOS (leads[]/meta[]/sales[]/ad_links); render() COSTURA os 4 arquivos abaixo
build/template.html       # esqueleto HTML. Placeholders __STYLES__, __APP_JS__, __DATA_JSON__, __BUILD_ID__, __GENERATED_BRT__
build/identidade-visual.css  # TODAS as cores (tema claro=padrão / escuro). Mexa AQUI p/ trocar só cor
build/estilos.css         # layout/componentes (sidebar, topbar, period-picker, funil, tabelas, gráficos, aba Relatório)
build/app.js              # lógica + renderização (KPIs, funil, tabelas, filtro cruzado, period-picker, heatmap, Relatório)
build/relatorios.json     # Insights de Tráfego por período (aba Relatório) — VERSIONADO; lido no build, sem API. Vazio no template ({}).
build/relatorios_dados.json      # números brutos por período (insumo p/ a Routine escrever relatorios.json) — não lido pelo site. Vazio no template ({}).
build/relatorio_lib.py           # datas/agregação compartilhadas (gerar_relatorios.py + coletar_dados_relatorio.py)
build/coletar_dados_relatorio.py # gera relatorios_dados.json (só números, sem texto) — roda no briefing.yml, 1x/dia
build/gerar_relatorios.py        # gera relatorios.json determinístico (sem IA) — fallback MANUAL, não roda mais sozinho
build/GUIA-RELATORIOS.md            # formato/estrutura dos Insights da aba Relatório (os 7 blocos) — preencher o contexto do funil
build/GUIA-INTERPRETACAO-METRICAS.md # regras de diagnóstico por métrica (High Ticket) — leitura obrigatória p/ redigir
.github/workflows/deploy.yml    # roda build.py e publica no Pages (workflow_dispatch + schedule + push)
.github/workflows/briefing.yml  # roda coletar_dados_relatorio.py e commita relatorios_dados.json na main (cron 1x/dia)
dist/index.html           # saída gerada (gitignored; o Actions reconstrói)
GUIA-REPLICACAO.md        # como replicar este modelo para outros relatórios/clientes
SETUP-CRON.md             # valores exatos do cron-job.org (com marcadores a preencher)
```

### Aba Relatório
Terceira página (sidebar, entre a de mídia paga e o rodapé). **Espelha a Visão
Geral** (mesmo funil/KPIs/gráficos/tabela diária, via `renderGeralCore(REL_IDS)`)
e, abaixo, acrescenta 3 blocos novos + um painel de metas editável:
- **Metas & parâmetros (painel editável)** — no topo da aba: Meta CPMQL, Meta CAC, Volume
  mínimo amostral (MQLs), N dias p/ corte. Persiste em `localStorage['dm_metas']`, default de
  `build.py` (`META_CPMQL`/`META_CAC`=None → "não definida"; `VOLUME_MIN_AMOSTRAL`/`N_DIAS_CORTE`).
  Editar recolore **CPMQL/CAC** nas tabelas de anúncio (verde ≤ meta · amarelo até +30% ·
  vermelho acima) e ajusta o badge Em observação/Avaliável, **tudo ao vivo**
  (`METAS` + `renderRelAds()` em `app.js`).
- **Top Anúncios** e **Piores Anúncios** — 17 colunas + coluna **Status** (Anúncio · Status ·
  Campanha · Conjunto · Gasto · Impr · CPM · CTR · Leads · CPL · MQLs · Tx‑MQL · CPMQL · ConvMQL ·
  Vendas · CAC · Faturamento · ROAS · **Link**). Anúncio, Status e Link ficam **sticky**.
  Ranking pelo **resultado mais profundo disponível** (Venda→MQL), amostra relevante primeiro;
  sem amostra → badge **"Em observação"**. Limiares em `build.py`: `SAMPLE_MIN_SPEND`,
  `SAMPLE_MIN_MQLS`, `TOP_ADS_N`.
- **Insights de Tráfego** — texto por período redigido pelo **Claude** (linguagem de
  gestor de tráfego), lido de `build/relatorios.json` (sem API no build/navegador —
  o site só exibe o texto já pronto). Formato em **4 quadrantes** por período. Cada
  período compara com o período anterior **correto para aquela janela** (regra em
  `relatorio_lib.previous_period`). Chaves de período fixas
  (`hoje/ontem/3d/7d/14d/30d/mes/mespass/todo`), tags `Escalar/Otimizar/Cortar/Observar`.
  Toda a aritmética é pré-calculada em `build/relatorios_dados.json` — a Routine só
  interpreta, nunca recalcula. Regras completas em `build/GUIA-RELATORIOS.md` +
  `build/GUIA-INTERPRETACAO-METRICAS.md`. `app.js` ainda reconhece o formato antigo
  (`{"html": "…"}`) como fallback.

### Briefing automático do gestor (Routine do Claude, sem chamada à API Anthropic)
`build/relatorios.json` pode ser escrito 1×/dia por uma **Routine do Claude**
(Claude Code Remote — mesma infraestrutura de sessão/agente deste repo, agendada;
não é chamada paga à API). Fluxo em 2 etapas, porque o ambiente da Routine não
alcança `docs.google.com` (só o runner do GitHub Actions alcança):
1. `build/coletar_dados_relatorio.py` (GitHub Actions, `.github/workflows/briefing.yml`,
   1×/dia) agrega **só números** em `build/relatorios_dados.json` e commita na `main`.
2. A Routine do Claude lê esse JSON + `build/GUIA-RELATORIOS.md` +
   `build/GUIA-INTERPRETACAO-METRICAS.md`, redige `build/relatorios.json` e faz
   commit/push direto na `main`, disparando o `deploy.yml`. **Precisa ser criada
   por cliente** (`create_trigger` apontando para o repo novo) — não vem pronta.

`build/gerar_relatorios.py` (gerador determinístico, sem IA) continua no repo só
como **fallback manual**. Limitação conhecida: usa os defaults de `build.py`
(`META_CPMQL`/`META_CAC`/`VOLUME_MIN_AMOSTRAL`/`N_DIAS_CORTE`), não o que o gestor
editou no painel (fica em `localStorage`).

Funil completo: `Impressões → Cliques → Leads → MQLs → Agendamentos → Reuniões
Realizadas → Vendas → Faturamento`. Enquanto só houver mídia paga × Leads, o funil
vai até MQL; Agendamentos/Reuniões/Vendas/Fat aparecem "-" até chegar a lista do
comercial.

### Link do criativo (aba de mídia paga)
`build.py` lê uma coluna opcional de permalink do criativo na aba de mídia →
mapa `ad_links` (anúncio → 1 permalink). Usado no "Link" das tabelas Top/Piores.
Sem a coluna, o link vira "—".

> **Layout modular:** o front-end é separado em `identidade-visual.css` + `estilos.css`
> + `app.js`, costurados por `render()` nos placeholders `__STYLES__`/`__APP_JS__`.
> Página 1 usa **funil vertical de leads** + KPIs secundários. Topbar tem
> **seletor de período em calendário** (default "Este mês"). **Heatmap** = cor FIXA
> por métrica (só opacidade varia): **Gasto=vermelho · Leads=azul · MQLs=ciano ·
> Vendas=verde · ROAS=amarelo** (`--heat-gasto/leads/mqls/vendas/roas`).

O `build.py` **não agrega**: exporta as linhas cruas e TODA a lógica (filtros de
data, filtro cruzado, KPIs, tabelas, gráficos, heatmap, imposto) roda no navegador.

## Rodar/testar local

```bash
python build/build.py --meta-file meta.csv --sales-file compradores.csv --out dist/index.html
# (o sandbox do agente NÃO alcança docs.google.com; use CSVs locais para testar.
#  O runner do GitHub Actions tem internet e busca os CSVs ao vivo.)
```

## Especificação funcional (resumo)

Três **páginas separadas** (sidebar):
1. **Visão Geral de Leads** — funil vertical (Gasto → Impressões → Cliques → Leads →
   MQLs → Vendas/Faturamento) + KPIs secundários; gráfico combinado diário +
   tabela diária com heatmap (todos os leads); barras por origem/faixa/plataforma/profissão.
2. **Captura mídia paga** — funil em etapas; combinado diário; barras por utm_content;
   tabela diária com heatmap (só mídia paga); 3 tabelas hierárquicas Campanha →
   Conjunto → Anúncio, cada uma com gráfico de linha embaixo.
3. **Relatório** — espelha a Visão Geral + painel de Metas editável + Top/Piores
   Anúncios (17 colunas + Status) + Insights de Tráfego. Ver `build/GUIA-RELATORIOS.md`.

**Ordem das colunas nas tabelas:** `Data · Dia · Gasto · CPM · CTR · ConvForm · Leads ·
CPL · Tx‑MQL · MQLs · CPMQL · ConvMQL · Vendas · CAC · Fat. · Receita · ROAS`. Nas
tabelas diárias entram também **Checkouts** e **VisCHK** (da coluna "Adds to Cart"
do Meta Ads, proxy de Checkout). Sem essas colunas, ficam "-".

**Melhorias portadas dos clientes (nov/2026):**
- **Tabelas Campanha/Conjunto/Anúncio (aba Meta Ads):** campo de **busca** por nome + botão
  "✕ Filtro" em cada uma (reseta busca + seleção cruzada; o "Remover Filtros" global também
  limpa as buscas), **heatmap** em Gasto/CPL/CPMQL/CAC/ROAS. Nas métricas de **custo**
  (CPL/CPMQL/CAC, também na tabela diária) o heatmap é **invertido** (`heatInv`: menor = mais
  vibrante). Cores `--heat-cpl/cpmql/cac` em `identidade-visual.css`.
- **Gráficos "por dia" das hierárquicas:** toggle **CPMQL / CPL / CAC** por painel
  (`STATE.chMetric`, `CHART_METRICS`). Gráfico combinado diário com **eixo próprio** para CPL/CPMQL.
- **Linhas "(sem campanha/conjunto/anúncio)"** ficam fora das tabelas/legendas (`isNoAttrib`),
  mas continuam nos totais. `build.py → unify_names()` unifica grafias equivalentes
  (caixa, acento, espaço/`_`/`-`) para não duplicar linhas.
- **Mobile:** menu hambúrguer corrigido (checkbox dentro de `#app`, backdrop + ✕), tabelas
  "fit" com scroll horizontal legível, ajustes ≤640px. Sidebar com ícones SVG.
- **Status do anúncio (Relatório):** `adRecommendation()` → Escalar/Manter/Observar/Cortar vs.
  metas CPMQL/CAC (CAC bom sozinho não escala: exige faturamento; sem venda julga pelo CPMQL;
  sem amostra/meta → Observar). Substitui Avaliável/Em observação.
- **deploy.yml:** `cancel-in-progress: true` + `timeout-minutes: 15` (run travado não bloqueia
  as atualizações periódicas).

**Regras obrigatórias das tabelas** (ver `GUIA-REPLICACAO.md`): cabeçalho sticky;
ordenação tri‑state; colunas redimensionáveis (persist localStorage); linha
"Total Geral" fixa; dimensão nunca truncada; seleção com toggle + Ctrl multi;
filtro cruzado bidirecional; tabela diária com último dia no topo; heatmap de cor
fixa por métrica.

## Lacunas de dados (comuns até o cliente enviar mais fontes)
- **Agendamentos / Reuniões Realizadas** → precisam da lista do comercial; aparecem "-".
- **Page Views, CR, CPV, ConvLP** → precisam de uma fonte de page views.
- Enquanto não vierem, essas métricas aparecem como "-".

## Publicação — problemas conhecidos
1. **Push:** se a integração GitHub da sessão for somente‑leitura (403), o caminho
   é `git push` direto para `github.com` com o **PAT do usuário**. Nunca gravar o
   token no `.git/config` (usar URL efêmera `https://x-access-token:<TOKEN>@github.com/...`).
2. **cron-job.org só funciona na `main`:** `workflow_dispatch` só existe na branch
   padrão. Levar `build/` + `.github/workflows/deploy.yml` para a `main`.
3. **Pages liga sozinho:** `actions/configure-pages@v5` com `enablement: true`
   (precisa `permissions: pages: write, id-token: write`).
4. **Proxy do sandbox:** o ambiente do agente costuma NÃO alcançar `docs.google.com`,
   `*.github.io` nem a API REST de Actions/Pages — mas o runner do Actions alcança tudo.
5. **Token exposto:** se um token foi colado no chat, **revogar e gerar um novo**.

## Branch / git
- Desenvolvimento na branch designada da sessão; manter sincronizada com `main`.
