# Dashboard de vendas Férias Sem Caverna

Dashboard **100% na nuvem** do **funil de vendas Férias Sem Caverna**. Cruza o
investimento de mídia paga (**Meta Ads**, puxado pelo Adveronix) com a lista de
**Compradores** e mostra Leads, Vendas e Faturamento atribuídos por
campanha/conjunto/anúncio. É publicado no **GitHub Pages** e reconstruído a cada
~30 min pelo **cron-job.org**, sem depender de nenhum PC ligado.

**URL pública:** `https://adryanfelipet.github.io/dashboard-feriassemcaverna/`

---

## O que ela mostra

- **KPIs**: Gasto, Impressões, Cliques, Page Views, Leads, CPL, Checkouts, Vendas, CAC, Faturamento, Receita, ROAS.
- **Evolução diária** e tabela diária com heatmap.
- **Tabelas hierárquicas** Campanha → Conjunto → Anúncio, com filtro cruzado.
- **Aba Relatório**: painel de metas + Top/Piores anúncios + Insights de Tráfego.
- **Toggle de imposto da mídia paga** e **modo claro/escuro**.

Este funil não tem critério de MQL: essas métricas aparecem como "–".

## Fontes de dados (somente leitura)

Planilha `Dashboard | Férias sem caverna`
(`1oj4VyTlGs0DjwEbRf2AvpiVM2Wk_Tb-lZgHWr1-iR-g`):

| Aba | gid | Uso |
|-----|-----|-----|
| Leads | `0` | Meta Ads via Adveronix (nível anúncio, diário): gasto, impressões, cliques, LP views, Initiate Checkouts e **Leads** |
| Compradores | `649461939` | 1 linha por venda; conta só Status aprovado (ou vazio). Atribuição: `utm_campaign` → campanha, `utm_medium` → conjunto, `utm_content` → anúncio |

O build lê as abas via **export CSV público**. **Nada é escrito de volta.**
Não renomeie nem recrie essas abas (o gid mudaria).

## Arquitetura

```
cron-job.org ──(POST workflow_dispatch a cada 30 min)──▶ GitHub Actions
                                                           │
                        build/build.py lê os CSVs ◀────────┘
                                 ▼
                        dist/index.html ──▶ deploy ──▶ GitHub Pages
```

**Cache-bust:** a página usa `Cache-Control: no-cache`, mostra o horário do último
build, tem botão **Atualizar** e se recarrega sozinha (`?t=timestamp`).

## Rodar localmente (opcional)

```bash
python build/build.py --out dist/index.html
python build/build.py --meta-file meta.csv --sales-file compradores.csv --out dist/index.html
```

## Ativação e cron-job.org

Veja **`SETUP-CRON.md`**.

> ⚠️ Nunca comite tokens. Use um token *fine-grained* só com **Actions: read/write**
> neste repositório, cadastrado apenas no cron-job.org.

## Sigla do funil

`MAIN_PRODUCT_PREFIX` em `build/build.py` está vazio (todas as campanhas entram).
Preencha com a sigla quando ela for definida para filtrar só este funil.
