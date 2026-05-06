import streamlit as st
import pandas as pd
import json
import os
import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="KGDB · Projeção vs Realidade", layout="wide", page_icon="📊")
PASTA = "data"

st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 4px solid #7c3aed;
        margin-bottom: 8px;
    }
    .metric-label { color: #a0aec0; font-size: 12px; font-weight: 600; text-transform: uppercase; }
    .metric-value { color: #f0f0f0; font-size: 22px; font-weight: 700; margin-top: 4px; }
    .win  { border-left-color: #22c55e !important; }
    .loss { border-left-color: #ef4444 !important; }
    .neu  { border-left-color: #3b82f6 !important; }
    .warn { border-left-color: #f59e0b !important; }
    .tag-approved { background:#22c55e22; color:#22c55e; border:1px solid #22c55e;
                    border-radius:6px; padding:2px 10px; font-size:13px; font-weight:700; }
    .tag-rejected { background:#ef444422; color:#ef4444; border:1px solid #ef4444;
                    border-radius:6px; padding:2px 10px; font-size:13px; font-weight:700; }
</style>
""", unsafe_allow_html=True)

def ler_html(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            html = f.read()
        m = re.search(r"window\.__report\s*=\s*(\{.*?\});", html, re.DOTALL)
        if not m:
            st.error("Padrao window.__report nao encontrado no HTML.")
            return None
        return json.loads(m.group(1))
    except Exception as e:
        st.error(f"Erro ao ler HTML: {e}")
        return None

def ler_json(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao ler JSON: {e}")
        return None

def detectar_formato(data: dict) -> str:
    """
    Retorna o tipo do JSON:
      - 'backtest'      → backtest_trades_*   (tem stats.trades)
      - 'walkforward'   → walkforward_*_vs_backtest (tem backtest{} e walkforward{})
      - 'experiments'   → quant_experiments_* (tem best_experiment e rows)
      - 'desconhecido'
    """
    if "best_experiment" in data and "rows" in data:
        return "experiments"
    if "backtest" in data and "walkforward" in data:
        return "walkforward"
    if "stats" in data:
        stats = data["stats"]
        if isinstance(stats, dict) and "trades" in stats:
            return "backtest"
        # stats vazio ou sem trades → backtest sem dados
        return "backtest_vazio"
    return "desconhecido"

def processar_html(data: dict):
    chart_bal = data["balance"]["chart"]
    df_balance = pd.DataFrame({
        "Data":   pd.to_datetime([p["x"] for p in chart_bal], unit="s"),
        "Saldo":  [p["y"][0] for p in chart_bal],
        "Equity": [p["y"][1] if len(p["y"]) > 1 else p["y"][0] for p in chart_bal],
    })

    growth_series = data["growth"]["chart"][0]
    df_growth = pd.DataFrame({
        "Data":        pd.to_datetime([p["x"] for p in growth_series], unit="s"),
        "Crescimento": [p["y"][0] * 100 for p in growth_series],
    })

    acc   = data["account"]
    bal   = data["balance"]
    summ  = data["summary"]
    proft = data["profitTotal"]
    si    = data["summaryIndicators"]
    lsi   = data["longShortIndicators"]

    saldo_inicial = df_balance["Saldo"].iloc[0]
    saldo_final   = bal["balance"]
    lucro_liq     = proft["profit"] + proft["loss"]
    total_trades  = lsi["trades"][0] + lsi["trades"][1]
    total_wins    = lsi["win_trades"][0] + lsi["win_trades"][1]
    win_rate      = (total_wins / total_trades * 100) if total_trades else 0

    metricas = {
        "conta":           acc["name"],
        "broker":          acc["broker"],
        "tipo":            acc["type"],
        "saldo_inicial":   saldo_inicial,
        "saldo_final":     saldo_final,
        "lucro_liquido":   lucro_liq,
        "crescimento_pct": summ["gain"] * 100,
        "profit_factor":   si["profit_factor"],
        "drawdown_pct":    si["drawdown"] * 100,
        "total_trades":    total_trades,
        "win_rate":        win_rate,
    }
    return df_balance, df_growth, metricas

def processar_backtest(data: dict):
    """Formato backtest_trades_* — tem lista de trades individuais."""
    stats  = data["stats"]
    trades = stats["trades"]
    df = pd.DataFrame(trades)
    df["Data"]   = pd.to_datetime(df["entry_time"].str.replace(" UTC", "", regex=False))
    df["R_acum"] = df["r_multiple"].cumsum()

    return {
        "formato":       "backtest",
        "df_trades":     df,
        "total_trades":  stats["total_trades"],
        "win_rate":      stats["win_rate_pct"],
        "profit_factor": stats["profit_factor"],
        "avg_r":         stats["avg_r"],
        "r_final":       df["R_acum"].iloc[-1],
        "max_win":       stats["max_win_pips"],
        "max_loss":      stats["max_loss_pips"],
    }

def processar_walkforward(data: dict):
    """Formato walkforward_*_vs_backtest — métricas resumidas de backtest e walkforward."""
    bt = data["backtest"]
    wf = data["walkforward"]
    res = data["result"]

    return {
        "formato":          "walkforward",
        "simbolo":          data["symbol"],
        "aprovado":         res["approved"],
        # backtest
        "bt_trades":        bt["total_trades"],
        "bt_win_rate":      bt["win_rate_pct"],
        "bt_profit_factor": bt["profit_factor"],
        "bt_total_r":       bt["total_r"],
        "bt_avg_r":         bt["avg_r"],
        "bt_wins":          bt["winning_trades"],
        "bt_losses":        bt["losing_trades"],
        # walkforward (período real fora da amostra)
        "wf_trades":        wf["total_trades"],
        "wf_win_rate":      wf["win_rate_pct"],
        "wf_profit_factor": wf["profit_factor"],
        "wf_total_r":       wf["total_r"],
        "wf_avg_r":         wf["avg_r"],
        "wf_wins":          wf["winning_trades"],
        "wf_losses":        wf["losing_trades"],
        # melhoria
        "delta_win_rate":   data["delta"]["win_rate_pct"],
        "delta_pf":         data["delta"]["profit_factor"],
        "delta_r":          data["delta"]["total_r"],
    }

def processar_experiments(data: dict):
    """Formato quant_experiments_* — resultado de otimização de parâmetros."""
    best = data["best_experiment"]
    rows = data["rows"]

    df_rows = pd.DataFrame(rows)

    return {
        "formato":          "experiments",
        "simbolo":          data["symbol"],
        "melhor_exp":       best["experiment"],
        "aprovado":         best.get("all_gates_passed", False),
        "baseline_wr":      best["baseline_test_win_rate"] * 100,
        "best_wr":          best["best_test_win_rate"] * 100,
        "baseline_pf":      best["baseline_test_profit_factor"],
        "best_pf":          best["best_test_profit_factor"],
        "baseline_r":       best["baseline_test_total_r"],
        "best_r":           best["best_test_total_r"],
        "best_trades":      best["best_test_trades"],
        "df_rows":          df_rows,
        "gate_wr":          best.get("target_test_win_rate_ok", None),
        "gate_mc":          best.get("stability_mc_p5_ok", None),
        "gate_dsr":         best.get("dsr_ok", None),
        "gate_recovery":    best.get("recovery_ok", None),
    }

def processar_json(data: dict, nome: str):
    fmt = detectar_formato(data)
    if fmt == "backtest":
        return processar_backtest(data)
    elif fmt == "walkforward":
        return processar_walkforward(data)
    elif fmt == "experiments":
        return processar_experiments(data)
    elif fmt == "backtest_vazio":
        return {"formato": "backtest_vazio", "simbolo": nome}
    else:
        return {"formato": "desconhecido"}

def card(label, value, classe="neu"):
    st.markdown(f"""
    <div class="metric-card {classe}">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
    </div>""", unsafe_allow_html=True)

def fmt_brl(v):  return f"R$ {v:,.2f}"
def fmt_pct(v):  return f"{v:.2f}%"
def fmt_r(v):    return f"{v:.3f} R"
def gate_icon(v):
    if v is None: return "—"
    return "✅" if v else "❌"

if not os.path.exists(PASTA):
    st.error(f"Pasta '{PASTA}' nao encontrada. Crie-a e coloque os arquivos la.")
    st.stop()

arquivos   = os.listdir(PASTA)
lista_html = sorted([f for f in arquivos if f.lower().endswith(".html")])
lista_json = sorted([f for f in arquivos if f.lower().endswith(".json")])

if not lista_html:
    st.error("Nenhum arquivo .html encontrado em data/")
    st.stop()
if not lista_json:
    st.error("Nenhum arquivo .json encontrado em data/")
    st.stop()

def extrair_label(nome: str, data: dict = None) -> str:
    n = nome.lower().replace(".json", "")

    # Símbolo vem após 'trades_' ou 'experiments_'
    m = re.search(r'(?:trades_|experiments_)([a-z0-9]+)', n)
    simbolo = m.group(1).upper() if m else None

    # Se não achou no nome (ex: quant_experiments_report), tenta pegar do JSON
    if not simbolo or simbolo == "REPORT":
        simbolo = (data or {}).get("symbol", "?").upper()

    if "walkforward" in n and "vs_backtest" in n:
        tipo = "Walkforward"
    elif "backtest" in n:
        tipo = "Backtest"
    elif "experiments" in n or "experiment" in n:
        tipo = "Experimentos"
    else:
        tipo = "Simulacao"

    return f"{simbolo} · {tipo}"

def _ler_rapido(nome):
    try:
        with open(os.path.join(PASTA, nome)) as fh:
            return json.load(fh)
    except Exception:
        return {}

mapa_json = {extrair_label(f, _ler_rapido(f)): f for f in lista_json}

with st.sidebar:
    st.title("Painel de Controle")
    st.caption("Escolha qual simulacao comparar com a conta real.")
    st.divider()
    label_escolhido = st.selectbox("Qual resultado voce quer ver?", list(mapa_json.keys()))
    json_escolhido  = mapa_json[label_escolhido]
    html_escolhido  = lista_html[0]
    st.divider()
    st.caption("Arquivos devem estar na pasta `data/` do projeto.")

dados_html = ler_html(os.path.join(PASTA, html_escolhido))
dados_json = ler_json(os.path.join(PASTA, json_escolhido))

if dados_html is None or dados_json is None:
    st.stop()

df_balance, df_growth, met_real = processar_html(dados_html)
resultado_json = processar_json(dados_json, json_escolhido)
fmt = resultado_json["formato"]

st.title("Como foi na pratica vs o que a gente esperava")
st.caption(f"Simulacao: {label_escolhido}  ·  Conta: {met_real['conta']} ({met_real['broker']})")
st.divider()

def bloco_conta_real(met):
    st.subheader("O que aconteceu de verdade")
    st.caption(f"{met['conta']} · {met['broker']} · {met['tipo'].upper()}")
    c1, c2 = st.columns(2)
    lucro = met["lucro_liquido"]
    with c1:
        card("Quanto ganhou",    fmt_brl(lucro),                       "win" if lucro >= 0 else "loss")
        card("Dinheiro inicial", fmt_brl(met["saldo_inicial"]),         "neu")
        card("Crescimento",      fmt_pct(met["crescimento_pct"]),       "win" if met["crescimento_pct"] >= 0 else "loss")
        card("% de acertos",     fmt_pct(met["win_rate"]),              "win" if met["win_rate"] >= 50 else "loss")
    with c2:
        card("Dinheiro final",   fmt_brl(met["saldo_final"]),           "neu")
        card("Lucro vs Prejuizo",f"{met['profit_factor']:.3f}",         "win" if met["profit_factor"] >= 1 else "loss")
        card("Pior queda",       fmt_pct(met["drawdown_pct"]),          "loss")
        card("Operacoes feitas", str(met["total_trades"]),              "neu")

if fmt == "backtest_vazio":
    bloco_conta_real(met_real)
    st.divider()
    st.warning("⚠️ Este backtest nao possui operacoes registradas — o arquivo esta vazio.")

elif fmt == "desconhecido":
    bloco_conta_real(met_real)
    st.divider()
    st.error("Formato de JSON nao reconhecido.")

elif fmt == "backtest":
    r  = resultado_json
    df = r["df_trades"]

    col_real, col_bt = st.columns(2)

    with col_real:
        bloco_conta_real(met_real)

    with col_bt:
        st.subheader("O que a simulacao previa")
        st.caption("Backtest — simulado, nao dinheiro real")
        c1, c2 = st.columns(2)
        with c1:
            r_final = r["r_final"]
            card("Pontuacao final (R)",  fmt_r(r_final),           "win" if r_final >= 0 else "loss")
            card("% de acertos",         fmt_pct(r["win_rate"]),   "win" if r["win_rate"] >= 50 else "loss")
            card("Lucro vs Prejuizo",    f"{r['profit_factor']:.3f}", "win" if r["profit_factor"] >= 1 else "loss")
            card("Pontuacao media",      fmt_r(r["avg_r"]),        "win" if r["avg_r"] >= 0 else "loss")
        with c2:
            card("Operacoes simuladas",  str(r["total_trades"]),   "neu")
            card("Melhor operacao",      f"{r['max_win']:.1f} pts","win")
            card("Pior operacao",        f"{r['max_loss']:.1f} pts","loss")

    st.divider()
    st.subheader("Como o dinheiro foi evoluindo")

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=False,
        subplot_titles=("Saldo da conta real (R$)", "Pontuacao acumulada da simulacao"),
        vertical_spacing=0.14,
        row_heights=[0.5, 0.5],
    )
    fig.add_trace(go.Scatter(
        x=df_balance["Data"], y=df_balance["Saldo"],
        mode="lines", name="Saldo",
        line=dict(color="#22c55e", width=2),
        fill="tozeroy", fillcolor="rgba(34,197,94,0.08)",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df_balance["Data"], y=df_balance["Equity"],
        mode="lines", name="Equity",
        line=dict(color="#3b82f6", width=1.5, dash="dot"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df["Data"], y=df["R_acum"],
        mode="lines+markers", name="R Acumulado",
        line=dict(color="#a78bfa", width=2),
        marker=dict(size=3),
    ), row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", row=2, col=1)
    fig.update_layout(
        template="plotly_dark", height=620,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=40),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
    )
    fig.update_xaxes(gridcolor="#1f2937", zeroline=False)
    fig.update_yaxes(gridcolor="#1f2937", zeroline=False)
    st.plotly_chart(fig, width='stretch')

    st.divider()
    col_g, col_dist = st.columns([1.4, 1])
    with col_g:
        st.subheader("Quanto a conta cresceu (%)")
        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(
            x=df_growth["Data"], y=df_growth["Crescimento"],
            mode="lines", line=dict(color="#f59e0b", width=2),
            fill="tozeroy", fillcolor="rgba(245,158,11,0.10)",
        ))
        fig_g.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
        fig_g.update_layout(
            template="plotly_dark", height=320, margin=dict(t=20, b=30),
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            yaxis=dict(gridcolor="#1f2937", ticksuffix="%"),
            xaxis=dict(gridcolor="#1f2937"),
        )
        st.plotly_chart(fig_g, width='stretch')

    with col_dist:
        st.subheader("Como os trades se saíram na simulacao")
        fig_h = go.Figure()
        fig_h.add_trace(go.Histogram(
            x=df["r_multiple"], nbinsx=30,
            marker_color="#7c3aed", opacity=0.85,
        ))
        fig_h.add_vline(x=0, line_dash="dash", line_color="rgba(255,255,255,0.4)")
        fig_h.update_layout(
            template="plotly_dark", height=320, margin=dict(t=20, b=30),
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            xaxis=dict(gridcolor="#1f2937", title="Pontuacao R"),
            yaxis=dict(gridcolor="#1f2937", title="Frequencia"),
            showlegend=False,
        )
        st.plotly_chart(fig_h, width='stretch')

    st.divider()
    st.subheader("Resumo: conta real vs simulacao")
    tabela = pd.DataFrame({
        "O que estamos medindo": ["Acertos (%)", "Lucro vs Prejuizo", "Pior queda do saldo", "Operacoes feitas", "Resultado final"],
        "Conta Real": [
            fmt_pct(met_real["win_rate"]),
            f"{met_real['profit_factor']:.3f}",
            fmt_pct(met_real["drawdown_pct"]),
            str(met_real["total_trades"]),
            fmt_brl(met_real["lucro_liquido"]),
        ],
        f"Simulacao": [
            fmt_pct(r["win_rate"]),
            f"{r['profit_factor']:.3f}",
            "sem dado",
            str(r["total_trades"]),
            fmt_r(r["r_final"]),
        ],
    })
    st.dataframe(tabela, width='stretch', hide_index=True)

    st.divider()
    with st.expander("Ver lista completa de operacoes da simulacao"):
        cols = ["Data", "action", "result", "r_multiple", "entry_price", "exit_price", "mode", "confidence"]
        cols = [c for c in cols if c in df.columns]
        df_show = df[cols].copy()
        renomear = {
            "action": "Direcao", "result": "Resultado", "r_multiple": "Pontuacao R",
            "entry_price": "Entrada", "exit_price": "Saida", "mode": "Modo",
            "confidence": "Confianca", "Data": "Data",
        }
        df_show.columns = [renomear.get(c, c) for c in cols]
        st.dataframe(df_show, width='stretch', height=400)

elif fmt == "walkforward":
    r = resultado_json

    aprovado_html = (
        '<span class="tag-approved">✅ APROVADO</span>'
        if r["aprovado"] else
        '<span class="tag-rejected">❌ NAO APROVADO</span>'
    )
    st.markdown(f"**Status da estrategia:** {aprovado_html}", unsafe_allow_html=True)
    st.divider()

    col_real, col_wf, col_bt = st.columns(3)

    with col_real:
        bloco_conta_real(met_real)

    with col_wf:
        st.subheader("Walkforward")
        st.caption("Periodo fora da amostra — mais proximo da realidade")
        c1, c2 = st.columns(2)
        with c1:
            card("% de acertos",     fmt_pct(r["wf_win_rate"]),      "win" if r["wf_win_rate"] >= 50 else "loss")
            card("Lucro vs Prejuizo",f"{r['wf_profit_factor']:.3f}", "win" if r["wf_profit_factor"] >= 1 else "loss")
        with c2:
            card("Pontuacao total",  fmt_r(r["wf_total_r"]),         "win" if r["wf_total_r"] >= 0 else "loss")
            card("Operacoes",        str(r["wf_trades"]),             "neu")
        card("Pontuacao media",      fmt_r(r["wf_avg_r"]),           "win" if r["wf_avg_r"] >= 0 else "loss")

    with col_bt:
        st.subheader("Backtest base")
        st.caption("Periodo dentro da amostra — so referencia")
        c1, c2 = st.columns(2)
        with c1:
            card("% de acertos",     fmt_pct(r["bt_win_rate"]),      "win" if r["bt_win_rate"] >= 50 else "warn")
            card("Lucro vs Prejuizo",f"{r['bt_profit_factor']:.3f}", "win" if r["bt_profit_factor"] >= 1 else "warn")
        with c2:
            card("Pontuacao total",  fmt_r(r["bt_total_r"]),         "win" if r["bt_total_r"] >= 0 else "warn")
            card("Operacoes",        str(r["bt_trades"]),             "neu")
        card("Pontuacao media",      fmt_r(r["bt_avg_r"]),           "win" if r["bt_avg_r"] >= 0 else "warn")

    st.divider()

    col_graf, col_delta = st.columns([1.6, 1])

    with col_graf:
        st.subheader("Quanto a conta real cresceu")
        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(
            x=df_balance["Data"], y=df_balance["Saldo"],
            mode="lines", name="Saldo",
            line=dict(color="#22c55e", width=2),
            fill="tozeroy", fillcolor="rgba(34,197,94,0.08)",
        ))
        fig_g.update_layout(
            template="plotly_dark", height=350, margin=dict(t=20, b=30),
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            xaxis=dict(gridcolor="#1f2937"),
            yaxis=dict(gridcolor="#1f2937"),
        )
        st.plotly_chart(fig_g, width='stretch')

    with col_delta:
        st.subheader("Melhoria do Walkforward sobre o Backtest")
        st.caption("O quanto a estrategia melhorou apos a otimizacao")

        delta_wr = r["delta_win_rate"]
        delta_pf = r["delta_pf"]
        delta_r  = r["delta_r"]

        card("Melhoria em acertos",      f"{delta_wr:+.2f}%",  "win" if delta_wr > 0 else "loss")
        card("Melhoria lucro/prejuizo",  f"{delta_pf:+.3f}",   "win" if delta_pf > 0 else "loss")
        card("Ganho em pontuacao (R)",   fmt_r(delta_r),        "win" if delta_r > 0 else "loss")

    st.divider()

    st.subheader("Resumo: conta real vs walkforward vs backtest")
    tabela = pd.DataFrame({
        "O que estamos medindo": ["Acertos (%)", "Lucro vs Prejuizo", "Pontuacao total", "Pontuacao media", "Operacoes"],
        "Conta Real":  [
            fmt_pct(met_real["win_rate"]),
            f"{met_real['profit_factor']:.3f}",
            fmt_brl(met_real["lucro_liquido"]),
            "—",
            str(met_real["total_trades"]),
        ],
        "Walkforward": [
            fmt_pct(r["wf_win_rate"]),
            f"{r['wf_profit_factor']:.3f}",
            fmt_r(r["wf_total_r"]),
            fmt_r(r["wf_avg_r"]),
            str(r["wf_trades"]),
        ],
        "Backtest base": [
            fmt_pct(r["bt_win_rate"]),
            f"{r['bt_profit_factor']:.3f}",
            fmt_r(r["bt_total_r"]),
            fmt_r(r["bt_avg_r"]),
            str(r["bt_trades"]),
        ],
    })
    st.dataframe(tabela, width='stretch', hide_index=True)

elif fmt == "experiments":
    r = resultado_json

    aprovado_html = (
        '<span class="tag-approved">✅ APROVADO</span>'
        if r["aprovado"] else
        '<span class="tag-rejected">❌ NAO APROVADO</span>'
    )
    st.markdown(f"**Melhor experimento:** `{r['melhor_exp']}`  &nbsp; {aprovado_html}", unsafe_allow_html=True)
    st.divider()

    col_real, col_exp = st.columns(2)

    with col_real:
        bloco_conta_real(met_real)

    with col_exp:
        st.subheader("O que o melhor experimento encontrou")
        st.caption("Resultado do modelo otimizado — ainda nao dinheiro real")

        c1, c2 = st.columns(2)
        with c1:
            melhora_wr = r["best_wr"] - r["baseline_wr"]
            card("% de acertos (antes)",  fmt_pct(r["baseline_wr"]), "neu")
            card("% de acertos (depois)", fmt_pct(r["best_wr"]),     "win" if r["best_wr"] >= 50 else "warn")
            card("Melhoria em acertos",   f"{melhora_wr:+.2f}%",    "win" if melhora_wr > 0 else "loss")
        with c2:
            melhora_pf = r["best_pf"] - r["baseline_pf"]
            card("Lucro/Prejuizo (antes)",  f"{r['baseline_pf']:.3f}", "neu")
            card("Lucro/Prejuizo (depois)", f"{r['best_pf']:.3f}",     "win" if r["best_pf"] >= 1 else "warn")
            card("Melhoria",               f"{melhora_pf:+.3f}",      "win" if melhora_pf > 0 else "loss")

        st.divider()
        st.caption("Criterios de aprovacao do experimento:")
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Meta acertos",  gate_icon(r["gate_wr"]))
        g2.metric("Estabilidade",  gate_icon(r["gate_mc"]))
        g3.metric("Sharpe",        gate_icon(r["gate_dsr"]))
        g4.metric("Recuperacao",   gate_icon(r["gate_recovery"]))

    st.divider()

    col_graf, col_tab = st.columns([1.6, 1])

    with col_graf:
        st.subheader("Quanto a conta real cresceu")
        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(
            x=df_balance["Data"], y=df_balance["Saldo"],
            mode="lines", name="Saldo",
            line=dict(color="#22c55e", width=2),
            fill="tozeroy", fillcolor="rgba(34,197,94,0.08)",
        ))
        fig_g.update_layout(
            template="plotly_dark", height=350, margin=dict(t=20, b=30),
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            xaxis=dict(gridcolor="#1f2937"),
            yaxis=dict(gridcolor="#1f2937"),
        )
        st.plotly_chart(fig_g, width='stretch')

    with col_tab:
        st.subheader("Comparativo dos experimentos")
        df_rows = r["df_rows"]
        cols_show = ["experiment", "best_test_win_rate", "best_test_profit_factor",
                     "best_test_total_r", "all_gates_passed"]
        cols_show = [c for c in cols_show if c in df_rows.columns]
        df_show = df_rows[cols_show].copy()
        df_show.columns = ["Experimento", "Acertos", "L/P", "R Total", "Aprovado"][:len(cols_show)]
        if "Acertos" in df_show.columns:
            df_show["Acertos"] = (df_show["Acertos"] * 100).map("{:.1f}%".format)
        if "L/P" in df_show.columns:
            df_show["L/P"] = df_show["L/P"].map("{:.3f}".format)
        if "R Total" in df_show.columns:
            df_show["R Total"] = df_show["R Total"].map("{:.2f}".format)
        st.dataframe(df_show, width='stretch', hide_index=True)

    st.divider()
    st.subheader("Resumo: conta real vs melhor experimento")
    tabela = pd.DataFrame({
        "O que estamos medindo": ["Acertos (%)", "Lucro vs Prejuizo", "Pontuacao total", "Operacoes", "Resultado final"],
        "Conta Real": [
            fmt_pct(met_real["win_rate"]),
            f"{met_real['profit_factor']:.3f}",
            "—",
            str(met_real["total_trades"]),
            fmt_brl(met_real["lucro_liquido"]),
        ],
        "Melhor Experimento": [
            fmt_pct(r["best_wr"]),
            f"{r['best_pf']:.3f}",
            fmt_r(r["best_r"]),
            str(r["best_trades"]),
            "—",
        ],
    })
    st.dataframe(tabela, width='stretch', hide_index=True)
