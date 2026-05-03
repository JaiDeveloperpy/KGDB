import streamlit as st
import pandas as pd
import json
import os
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Trading Lab Quant", 
    layout="wide", 
    page_icon="📈"
)

# --- ESTILIZAÇÃO DARK MODE (CSS) ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { 
        background-color: #161b22; 
        border-radius: 10px; 
        padding: 15px; 
        border: 1px solid #30363d; 
    }
    [data-testid="stMetricValue"] { color: #58a6ff; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 Dashboard de Análise Quantitativa")
st.markdown("---")

PASTA_DADOS = "data"

# --- FUNÇÃO DE CARGA DE DADOS ---
def carregar_dados(caminho):
    try:
        if caminho.endswith('.csv'):
            df = pd.read_csv(caminho)
            return df if not df.empty else None
        
        with open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
            # Verifica se o JSON tem conteúdo mínimo
            if not dados or (isinstance(dados, dict) and not dados):
                return None
            return dados
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return None

# --- LÓGICA DA BARRA LATERAL ---
if not os.path.exists(PASTA_DADOS):
    st.error(f"⚠️ Pasta '{PASTA_DADOS}' não encontrada no seu CachyOS!")
else:
    # Lista arquivos JSON e CSV
    arquivos = sorted([f for f in os.listdir(PASTA_DADOS) if f.endswith(('.json', '.csv'))])
    arquivo_sel = st.sidebar.selectbox("📂 Selecione o Relatório", arquivos)
    caminho_completo = os.path.join(PASTA_DADOS, arquivo_sel)
    
    dados = carregar_dados(caminho_completo)

    # 0. Tratamento para arquivos vazios ou sem trades
    if dados is None:
        st.warning(f"📭 O arquivo '{arquivo_sel}' não contém dados processáveis.")
    
    # --- TIPO A: Relatórios de Trades (Walkforward/Backtest) ---
    elif isinstance(dados, dict) and ("stats" in dados or "estatisticas_descritivas" in dados):
        # Normalização de chaves EN/PT
        stats = dados.get("stats") or dados.get("estatisticas_descritivas")
        trades_list = dados.get("trades") or (dados.get("stats", {}).get("trades") if isinstance(dados.get("stats"), dict) else None)
        
        st.subheader(f"🔍 Ativo: {dados.get('symbol', arquivo_sel)}")

        # Verificação de segurança para métricas zeradas
        if not stats or stats.get('total_trades') == 0 or stats.get('total_operacoes') == 0:
            st.info("ℹ️ Este relatório está com as estatísticas zeradas.")
        
        # Cards de Métricas
        c1, c2, c3, c4 = st.columns(4)
        wr = stats.get('win_rate_pct', 0)
        c1.metric("Win Rate", f"{wr:.2f}%")
        pf = stats.get('fator_lucro') or stats.get('profit_factor', 0)
        c2.metric("Profit Factor", f"{pf:.2f}")
        total_t = stats.get('total_operacoes') or stats.get('total_trades', 0)
        c3.metric("Total Trades", int(total_t))
        pnl = stats.get('total_pnl_pips') or stats.get('resultado_total_pips', 0)
        c4.metric("PNL Total", f"{pnl:,.0f} pips")

        # Processamento do Gráfico e Tabela
        if trades_list and len(trades_list) > 0:
            df_trades = pd.DataFrame(trades_list)
            
            # Formatação de Datas
            df_trades['entry_time'] = pd.to_datetime(df_trades['entry_time'])
            df_trades['Data Formatada'] = df_trades['entry_time'].dt.strftime('%d/%m/%Y %H:%M')
            
            # Cálculo da Equidade Acumulada (R)
            df_trades['Equity_R'] = df_trades['r_multiple'].cumsum()

            # Visualização Gráfica
            fig = px.area(df_trades, x='entry_time', y='Equity_R',
                          title="Evolução Patrimonial (Acumulado R)",
                          hover_data={'Data Formatada': True, 'entry_time': False, 'Equity_R': ':.2f'})
            
            fig.update_layout(template="plotly_dark", hovermode="x unified")
            fig.update_xaxes(title="Tempo", tickformat="%d/%m/%y")
            fig.update_yaxes(title="Saldo Acumulado (R)")
            
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📄 Ver Lista de Operações Detalhada"):
                # Seleciona apenas colunas relevantes para não poluir
                colunas_view = ['Data Formatada', 'action', 'r_multiple', 'result', 'pnl_pips']
                st.dataframe(df_trades[colunas_view], use_container_width=True)
        else:
            st.info("Sem lista de trades individuais para este arquivo.")

    # --- TIPO B: Comparação (Backtest vs Walkforward) ---
    elif isinstance(dados, dict) and "delta" in dados:
        st.subheader("⚖️ Validação: Treino vs Teste")
        
        # Monta DataFrame comparativo extraindo dados de backtest e walkforward
        comp_data = {
            "Métrica": ["Win Rate %", "Profit Factor", "Total R"],
            "Backtest (Treino)": [
                dados['backtest'].get('win_rate_pct', 0), 
                dados['backtest'].get('profit_factor', 0), 
                dados['backtest'].get('total_r', 0)
            ],
            "Walkforward (Teste)": [
                dados['walkforward'].get('win_rate_pct', 0), 
                dados['walkforward'].get('profit_factor', 0), 
                dados['walkforward'].get('total_r', 0)
            ]
        }
        st.table(pd.DataFrame(comp_data))
        
        with st.expander("Ver Diferenças (Delta)"):
            st.json(dados['delta'])

    # --- TIPO C: Experimentos de Otimização (CSV/JSON rows) ---
    elif isinstance(dados, pd.DataFrame) or (isinstance(dados, dict) and "rows" in dados):
        st.subheader("🧬 Comparativo de Experimentos")
        
        df_exp = dados if isinstance(dados, pd.DataFrame) else pd.DataFrame(dados["rows"])
        
        # Gráfico de Barras Comparativo
        fig_exp = px.bar(df_exp, x='experiment', y='best_test_total_r', 
                         color='all_gates_passed',
                         labels={'best_test_total_r': 'Retorno Total (R)', 'experiment': 'Experimento'},
                         title="Retorno por Estratégia Otimizada",
                         color_discrete_map={True: '#2ea043', False: '#f85149'})
        
        fig_exp.update_layout(template="plotly_dark")
        st.plotly_chart(fig_exp, use_container_width=True)
        
        st.dataframe(df_exp, use_container_width=True)

    else:
        st.error("❌ Formato de arquivo não suportado ou dados mal estruturados.")