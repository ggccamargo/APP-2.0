import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px
from datetime import datetime, date
import json

# ==============================================================================
# 1. CONFIGURAÇÃO GERAL DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Controle de Gastos Pessoais",
    page_icon="💰",
    layout="wide"
)

# Constantes globais
SHEET_URL = "https://docs.google.com/spreadsheets/d/1MxAYCiQEOUz7exr-ZHh2v2khgMdZQoFy9dFQZwo6roU/edit"
COLUNAS_PLANILHA = ["Data", "Descrição", "Categoria", "Valor (R$)"]
CATEGORIAS = ["Casa", "Crianças", "Alimentação", "Carro", "Compras", "Viagens"]
NOMES_MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

# ==============================================================================
# 2. FUNÇÕES AUXILIARES DE FORMATAÇÃO E PARSING
# ==============================================================================
def formatar_moeda(valor: float) -> str:
    """Formata um float no padrão monetário brasileiro (R$ 1.250,50)."""
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def converter_para_float(valor_str) -> float:
    """Converte entradas numéricas ou strings com vírgula para float."""
    if pd.isna(valor_str) or valor_str == "":
        return 0.0
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    
    limpo = str(valor_str).replace("R$", "").strip()
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0

# ==============================================================================
# 3. CONEXÃO E PERSISTÊNCIA (Google Sheets via gspread + oauth2client)
# ==============================================================================
@st.cache_resource(show_spinner=False)
def obter_cliente_google_sheets():
    """Autentica na API do Google Sheets usando credenciais em st.secrets."""
    escopos = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    if "google" not in st.secrets or "credenciais" not in st.secrets["google"]:
        raise KeyError(
            "Configuração ausente: certifique-se de que st.secrets['google']['credenciais'] "
            "contém o JSON da sua Conta de Serviço (Service Account)."
        )
    
    credenciais_raw = st.secrets["google"]["credenciais"]
    if isinstance(credenciais_raw, str):
        credenciais_dict = json.loads(credenciais_raw)
    else:
        credenciais_dict = dict(credenciais_raw)
        
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, escopos)
    return gspread.authorize(creds)

def obter_planilha():
    """Retorna a primeira aba da planilha configurada."""
    cliente = obter_cliente_google_sheets()
    planilha = cliente.open_by_url(SHEET_URL)
    return planilha.sheet1

@st.cache_data(ttl=60, show_spinner=False)
def carregar_dados():
    """Carrega os dados da planilha e trata tipos de dados com Pandas."""
    ws = obter_planilha()
    registros = ws.get_all_records()
    
    if not registros:
        # Se a planilha estiver totalmente em branco, inicializa os cabeçalhos
        valores = ws.get_all_values()
        if not valores: