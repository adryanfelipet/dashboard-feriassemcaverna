#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera a dashboard estatica (index.html) do funil de vendas "Ferias Sem Caverna"
a partir de 2 abas da planilha "Dashboard | Ferias sem caverna":

  - "Leads" (gid 0): dados do Meta Ads puxados pelo Adveronix (nivel anuncio,
    quebra diaria): gasto, impressoes, cliques, LP views, checkouts e LEADS.
    Os leads do dashboard vem da coluna "Leads" desta aba (nao ha lista de
    pessoas neste funil) — cada lead vira 1 registro em leads[].
  - "Compradores" (gid 649461939): 1 linha por venda (webhook do checkout).
    Atribuicao por UTM: utm_campaign -> campanha, utm_medium -> conjunto,
    utm_content -> anuncio (mesmos nomes do Meta via {{campaign.name}} etc.).
    So entram vendas com Status aprovado (ou Status vazio).

Neste funil nao ha criterio de MQL: as metricas de MQL ficam em "-".

Este script apenas LE as planilhas (export CSV publico) e emite os REGISTROS
BRUTOS (leads[], meta[] e sales[]) dentro do HTML. Todos os filtros,
agregacoes, KPIs, tabelas e graficos sao calculados no navegador. Nunca
escreve nada de volta.

Teste local: --meta-file / --sales-file apontando para CSVs baixados.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

SPREADSHEET_ID = "1oj4VyTlGs0DjwEbRf2AvpiVM2Wk_Tb-lZgHWr1-iR-g"
GID_META = "0"              # aba "Leads" (Meta Ads via Adveronix)
GID_SALES = "649461939"     # aba "Compradores"
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"

# Identificação do cliente/conta (usada só em textos/relatórios — não afeta o cruzamento de dados).
CLIENT_NAME = "Dashboard de vendas Férias Sem Caverna"
MAIN_PRODUCT = "Férias Sem Caverna"
# Sigla/prefixo comum às campanhas do funil. Vazio = todas as campanhas da conta
# entram no dashboard (nenhum filtro). Preencha quando a sigla for definida.
MAIN_PRODUCT_PREFIX = ""

# Status da aba Compradores que contam como venda (comparação sem acento/caixa,
# por substring). Status vazio também conta.
APPROVED_STATUS = ("aprovad", "approved", "paid", "pago", "complet", "concluid")

BRT = timezone(timedelta(hours=-3))   # horario de Brasilia (exibicao)
TAX_FACTOR = 1.13806   # fator padrão de imposto/taxa sobre o gasto de mídia paga (Meta Ads) = 13,806%.
                       # Default do template para toda nova dash criada a partir dele; ajuste apenas
                       # se o cliente tiver um fator diferente, ou use 1.0 se não houver imposto.

# --------------------------------------------------------------------------- #
# Regras da aba Relatório (Top/Piores anúncios)
# --------------------------------------------------------------------------- #
# Amostra mínima para julgar um anúncio como "vencedor" ou "ruim". Abaixo disso
# ele entra como "Em observação" (dado insuficiente) — nunca é classificado só
# porque teve 1 resultado com pouco investimento. Ajuste conforme o ticket/CAC.
SAMPLE_MIN_SPEND = 100.0   # gasto mínimo (R$) para amostra relevante
SAMPLE_MIN_MQLS = 3        # MQLs mínimos para julgar qualidade profunda
TOP_ADS_N = 10             # nº de linhas em Top / Piores anúncios

# Metas & parâmetros da conta (DEFAULTS do painel editável da aba Relatório).
# São só o valor inicial: o usuário edita no navegador (persistido em
# localStorage) e as tabelas de anúncios recoram CPMQL/CAC e reavaliam a
# amostra ao vivo. None = "meta não definida" (métrica aparece sem cor até o
# gestor preencher).
META_CPMQL = None          # meta de CPMQL (R$/MQL); None = não definida
META_CAC = None            # meta de CAC (R$/venda); None = não definida
VOLUME_MIN_AMOSTRAL = SAMPLE_MIN_MQLS  # conversões (MQLs) mínimas p/ amostra confiável
N_DIAS_CORTE = 5           # dias consecutivos acima do teto p/ considerar corte


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
FETCH_RETRIES = 3       # tentativas totais em caso de timeout/erro de rede no export CSV
FETCH_RETRY_DELAY = 15  # segundos entre tentativas (o Google Sheets às vezes trava a resposta)


def fetch_csv(url: str) -> list[list[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "dash-template-bot/1.0"})
    last_err: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return list(csv.reader(io.StringIO(raw)))
        except (TimeoutError, urllib.error.URLError) as exc:
            last_err = exc
            if attempt < FETCH_RETRIES:
                print(f"[fetch_csv] tentativa {attempt}/{FETCH_RETRIES} falhou ({exc!r}); "
                      f"tentando de novo em {FETCH_RETRY_DELAY}s...", file=sys.stderr)
                time.sleep(FETCH_RETRY_DELAY)
    raise last_err


def read_csv_file(path: str) -> list[list[str]]:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.reader(f))


def load_rows(url: str, local: str | None) -> list[list[str]]:
    return read_csv_file(local) if local else fetch_csv(url)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str | None) -> str:
    return strip_accents((s or "").strip().lower())


def to_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v).strip())
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(v: str) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d/%m/%y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def is_test_lead(rowtext: str) -> bool:
    return "<test lead" in rowtext.lower()


def is_approved(status: str | None) -> bool:
    """Venda conta se o Status estiver vazio ou indicar aprovação."""
    st = norm(status)
    return not st or any(k in st for k in APPROVED_STATUS)


def campaign_allowed(camp: str) -> bool:
    """Filtro pela sigla do funil (MAIN_PRODUCT_PREFIX). Vazio = tudo entra."""
    return not MAIN_PRODUCT_PREFIX or norm(MAIN_PRODUCT_PREFIX) in norm(camp)


def pretty_specialty(v: str) -> str:
    s = (v or "").strip()
    return s if s else "Sem resposta"


def mask_email(e: str) -> str:
    e = (e or "").strip()
    if "@" not in e:
        return "—"
    user, dom = e.split("@", 1)
    keep = user[:2] if len(user) > 2 else user[:1]
    return f"{keep}****@{dom}"


def mask_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p or "")
    return f"…{digits[-4:]}" if len(digits) >= 4 else "—"


def norm_phone(p: str) -> str:
    return re.sub(r"\D", "", p or "")


def canon_phone(p: str) -> str:
    """Chave CANÔNICA de telefone p/ cruzar Compradores × Conversas, robusta às
    3 variações que faziam o mesmo número não bater quando comparado só por
    dígitos (norm_phone):
      - DDI "55" presente de um lado e ausente do outro
        (5511988887777 vs 11988887777);
      - 9º dígito do celular presente/ausente
        (11988887777 vs 1188887777);
      - máscara/espacos/parênteses (já removidos por norm_phone).
    Estratégia: remove o DDI 55 (quando sobra DDD+número) e usa DDD (2 díg.) +
    ÚLTIMOS 8 DÍGITOS — que é o mesmo com ou sem o 9. Devolve chave de 10 díg.
    (DDD+8). Números curtos/estrangeiros (< 10 díg. após limpar) voltam como
    estão, pra não colidir à toa."""
    d = norm_phone(p)
    if len(d) > 11 and d.startswith("55"):
        d = d[2:]            # tira DDI do Brasil, sobrando DDD + local
    if len(d) >= 10:
        return d[:2] + d[-8:]   # DDD + últimos 8 (drop do 9º dígito, se houver)
    return d


def first_last_initial(name: str) -> str:
    parts = (name or "").strip().split()
    if not parts:
        return "—"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][:1]}."


def valid_utm(campaign: str) -> bool:
    c = norm(campaign)
    return bool(c) and c not in ("-", "—", "nao encontrado")


# --------------------------------------------------------------------------- #
# Indexacao das colunas
# --------------------------------------------------------------------------- #
def header_index(header, wanted, fallback):
    idx = {}
    hn = [norm(h) for h in header]
    for key, aliases in wanted.items():
        found = None
        for a in aliases:
            a = norm(a)
            for i, h in enumerate(hn):
                if h == a or (a and a in h):
                    found = i
                    break
            if found is not None:
                break
        idx[key] = found if found is not None else fallback.get(key)
    return idx


def cell(row, i):
    if i is None or i < 0 or i >= len(row):
        return ""
    return (row[i] or "").strip()


# --------------------------------------------------------------------------- #
# Compradores -> vendas atribuidas por UTM
# --------------------------------------------------------------------------- #
def build_sales(sales_rows):
    """1 registro por linha APROVADA da aba Compradores, na data real da compra.
    camp/adset/ad vem das UTMs (utm_campaign/utm_medium/utm_content). Sem
    utm_campaign valida, a venda conta nos totais como "(sem campanha)"/org."""
    header = sales_rows[0] if sales_rows else []
    idx = header_index(
        header,
        {"date": ["data"], "status": ["status"], "faturamento": ["faturamento"], "receita": ["receita"],
         "campaign": ["utm_campaign"], "adset": ["utm_medium"], "ad": ["utm_content"]},
        {},
    )
    sales, skipped = [], 0
    for row in sales_rows[1:]:
        if not any((c or "").strip() for c in row):
            continue
        if not is_approved(cell(row, idx["status"])):
            skipped += 1
            continue
        camp_raw = cell(row, idx["campaign"])
        ok = valid_utm(camp_raw)
        sales.append({
            "d": parse_date(cell(row, idx["date"])),
            "src": "meta" if ok else "org",
            "camp": camp_raw if ok else "(sem campanha)",
            "adset": (cell(row, idx["adset"]) or "(sem conjunto)") if ok else "(sem conjunto)",
            "ad": (cell(row, idx["ad"]) or "(sem anúncio)") if ok else "(sem anúncio)",
            "vendas": 1,
            "fat": round(to_float(cell(row, idx["faturamento"])), 2),
            "receita": round(to_float(cell(row, idx["receita"])), 2),
        })
    sem = sum(1 for x in sales if x["src"] == "org")
    print(f"  compradores: {len(sales)} venda(s) aprovada(s), {sem} sem UTM de campanha, "
          f"{skipped} ignorada(s) por status", file=sys.stderr)
    return sales


# --------------------------------------------------------------------------- #
# Processamento -> registros brutos
# --------------------------------------------------------------------------- #
def name_key(s):
    """Chave de agrupamento de nomes de campanha/conjunto/anúncio: ignora caixa,
    acentos, espaços extras/invisíveis e a diferença entre `_`, `-` e espaço —
    o mesmo anúncio chega da Conversas e do Meta Ads com grafias levemente
    diferentes e, sem isso, vira linhas duplicadas na dash."""
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[​-‍﻿]", "", t).casefold()
    return re.sub(r"[\s_\-]+", " ", t).strip()


def unify_names(meta, leads, sales, ad_links):
    """Troca camp/adset/ad por um nome canônico por name_key (preferindo a grafia
    do Meta Ads, que é a do gerenciador) em leads[]/meta[]/sales[]/ad_links."""
    for field in ("camp", "adset", "ad"):
        canon = {}
        for rec in meta + leads + sales:  # meta primeiro => grafia do Meta vence
            v = rec.get(field)
            if v:
                canon.setdefault(name_key(v), re.sub(r"\s+", " ", v).strip())
        for rec in meta + leads + sales:
            v = rec.get(field)
            if v:
                rec[field] = canon[name_key(v)]
        if field == "ad":
            fixed = {}
            for k, link in ad_links.items():
                fixed.setdefault(canon.get(name_key(k), k), link)
            ad_links.clear()
            ad_links.update(fixed)


def process(meta_rows, sales_rows):
    sales = build_sales(sales_rows)

    mheader = meta_rows[0] if meta_rows else []
    midx = header_index(
        mheader,
        {"day": ["day", "data"], "campaign": ["campaign name", "campaign"], "adset": ["ad set name", "adset"],
         "ad": ["ad name"], "spent": ["amount spent", "valor gasto", "gasto"], "impr": ["impressions", "impress"],
         "clicks": ["link clicks", "clicks", "cliques"], "leads": ["leads"],
         "pv": ["landing page views", "page views", "pageviews"],
         # Checkouts = "Initiate Checkouts" do Meta (Adveronix).
         "chk": ["initiate checkout", "adds to cart", "add to cart", "checkouts iniciados", "checkouts"],
         # Link do criativo (ex. Instagram) — coluna opcional adicionada pelo cliente
         # na aba de mídia. Usada na aba Relatório (Top/Piores anúncios) para linkar
         # o anúncio. Aliases cobrem variações do cabeçalho.
         "link": ["creative instagram permalink", "instagram permalink", "permalink",
                  "creative link", "link do anuncio", "link do criativo"]},
        {"day": 0, "campaign": 2, "adset": 3, "ad": 4, "spent": 5, "impr": 6, "clicks": 7, "leads": None, "pv": 8},
    )

    meta = []
    # Anúncio (nome) -> 1 permalink do criativo. "Qualquer um correlato" ao
    # anúncio serve (o mesmo criativo pode rodar em vários dias/conjuntos);
    # guardamos o primeiro link não-vazio encontrado para cada anúncio.
    ad_links = {}
    for row in meta_rows[1:]:
        if not any((c or "").strip() for c in row):
            continue
        ad = cell(row, midx["ad"]) or "(sem anúncio)"
        link = cell(row, midx["link"])
        if link and ad not in ad_links:
            ad_links[ad] = link
        camp_name = cell(row, midx["campaign"]) or "(sem campanha)"
        if not campaign_allowed(camp_name):
            continue
        meta.append({
            "d": parse_date(cell(row, midx["day"])),
            "camp": cell(row, midx["campaign"]) or "(sem campanha)",
            "adset": cell(row, midx["adset"]) or "(sem conjunto)",
            "ad": ad,
            "sp": round(to_float(cell(row, midx["spent"])), 4),
            "im": to_float(cell(row, midx["impr"])),
            "cl": to_float(cell(row, midx["clicks"])),
            "pv": to_float(cell(row, midx["pv"])),
            "ck": to_float(cell(row, midx["chk"])),
            "ml": to_float(cell(row, midx["leads"])),
        })

    # Leads: neste funil vêm da coluna "Leads" do Meta Ads (não há lista de
    # pessoas). Cada lead vira 1 registro em leads[] (q=0: sem critério de MQL),
    # para o front contar/filtrar/agrupar igual ao template.
    leads = []
    for m in meta:
        for _ in range(int(round(m["ml"]))):
            leads.append({"d": m["d"], "src": "meta", "plat": "ig", "camp": m["camp"],
                          "adset": m["adset"], "ad": m["ad"], "prof": "Meta Ads", "bucket": "Meta Ads",
                          "q": 0, "utm": 1, "nm": "—", "em": "—", "ph": "—"})
    sales = [x for x in sales if x["src"] == "org" or campaign_allowed(x["camp"])]
    leads_lp_total = 0

    unify_names(meta, leads, sales, ad_links)

    dates = sorted({d for d in (
        [l["d"] for l in leads if l["d"]] + [m["d"] for m in meta if m["d"]] + [s["d"] for s in sales if s["d"]]
    )})
    now_brt = datetime.now(BRT)
    return {
        "build": {
            "generated_at_brt": now_brt.strftime("%d/%m/%Y %H:%M"),
            "build_id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "today": now_brt.strftime("%Y-%m-%d"),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "tax_factor": TAX_FACTOR,
            # config da aba Relatório (lida pelo front)
            "sample_min_spend": SAMPLE_MIN_SPEND,
            "sample_min_mqls": SAMPLE_MIN_MQLS,
            "top_ads_n": TOP_ADS_N,
            # metas & parâmetros (defaults do painel editável; None = não definida)
            "meta_cpmql": META_CPMQL,
            "meta_cac": META_CAC,
            "volume_min_amostral": VOLUME_MIN_AMOSTRAL,
            "n_dias_corte": N_DIAS_CORTE,
            # referência apenas (não usado na UI): total da fonte antiga "Leads LP".
            "leads_lp_total": leads_lp_total,
        },
        "leads": leads,
        "meta": meta,
        "sales": sales,
        # Anúncio -> permalink do criativo (aba Relatório).
        "ad_links": ad_links,
        # Insights de Tráfego (texto pré-escrito, lido de relatorios.json). Preenchido
        # em main() via load_briefings(); fica {} se relatorios.json não existir.
        "briefings": {},
    }


# --------------------------------------------------------------------------- #
# Insights de Tráfego (aba Relatório)
# --------------------------------------------------------------------------- #
def load_briefings(path: str) -> dict:
    """Lê build/relatorios.json. Estrutura:
        {"generated_at": "...", "periodos": {"<preset>": {"html": "..."}, ...}}
    Retorna o dict inteiro (ou {} se o arquivo não existir/for inválido).
    A geração NÃO acontece aqui — este build só lê o texto já pronto, sem
    chamar nenhuma API (custo zero no build/no navegador)."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except (ValueError, OSError):
        return {}


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(data, template_path):
    # A dashboard e montada a partir de arquivos separados (visual x logica):
    #   template.html          -> esqueleto HTML (placeholders __STYLES__/__APP_JS__)
    #   identidade-visual.css  -> TODAS as cores (edite aqui p/ mexer so em cor)
    #   estilos.css            -> layout/componentes
    #   app.js                 -> logica + renderizacao
    # Esta funcao so COSTURA os arquivos e injeta os dados; nao altera nada deles.
    base = os.path.dirname(os.path.abspath(template_path))

    def readf(name):
        with open(os.path.join(base, name), "r", encoding="utf-8") as f:
            return f.read()

    with open(template_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    styles = readf("identidade-visual.css") + "\n" + readf("estilos.css")
    tpl = tpl.replace("__STYLES__", styles)
    tpl = tpl.replace("__APP_JS__", readf("app.js"))
    tpl = tpl.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))
    tpl = tpl.replace("__BUILD_ID__", data["build"]["build_id"])
    tpl = tpl.replace("__GENERATED_BRT__", data["build"]["generated_at_brt"])
    return tpl


def load_data(meta_file=None, sales_file=None):
    """Lê as 2 abas (ou CSVs locais) e devolve o dict de dados do process()."""
    meta_rows = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID, gid=GID_META), meta_file)
    sales_rows = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID, gid=GID_SALES), sales_file)
    return process(meta_rows, sales_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta-file", help="CSV local da aba Leads (Meta Ads / Adveronix)")
    ap.add_argument("--sales-file", help="CSV local da aba Compradores")
    ap.add_argument("--template", default="build/template.html")
    ap.add_argument("--out", default="dist/index.html")
    args = ap.parse_args()

    data = load_data(args.meta_file, args.sales_file)

    # Insights de Tráfego (texto pré-escrito) — lidos do arquivo versionado ao
    # lado do template. Sem chamada de API no build.
    briefings_path = os.path.join(os.path.dirname(os.path.abspath(args.template)), "relatorios.json")
    data["briefings"] = load_briefings(briefings_path)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(data, args.template))

    b = data["build"]
    vd = sum(s["vendas"] for s in data["sales"])
    fat = sum(s["fat"] for s in data["sales"])
    print("== build ok ==", file=sys.stderr)
    print(f"  periodo   : {b['date_min']} -> {b['date_max']}", file=sys.stderr)
    print(f"  leads (Meta): {len(data['leads'])}", file=sys.stderr)
    print(f"  vendas    : {vd}  faturamento: R$ {fat:,.2f}", file=sys.stderr)
    print(f"  meta      : {len(data['meta'])} linhas", file=sys.stderr)
    print(f"  out       : {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
