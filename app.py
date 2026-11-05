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

# Constantes globais vinculadas à sua planilha e conta de serviço
SHEET_URL = "https://docs.google.com/spreadsheets/d/1LEgZ6JxbhbQ6JpHYlPf5PmO7fzEhiQQF6Au2dbzeG80/edit"
SHEET_TAB_NAME = "Página1"
SERVICE_ACCOUNT_EMAIL = "app2-606@app2-513815.iam.gserviceaccount.com"

COLUNAS_PLANILHA = ["Data", "Descrição", "Categoria", "Valor (R$)"]
CATEGORIAS = ["Casa", "Crianças", "Alimentação", "Carro", "Compras", "Viagens", "Saúde"]
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
    if pd.isna(valor_str) or str(valor_str).strip() == "":
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
    """Autentica na API do Google Sheets buscando credenciais em st.secrets."""
    escopos = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    credenciais_dict = None
    
    # 1. Tenta no formato padrão exigido: st.secrets["google"]["credenciais"]
    if "google" in st.secrets and "credenciais" in st.secrets["google"]:
        raw = st.secrets["google"]["credenciais"]
        if isinstance(raw, str):
            credenciais_dict = json.loads(raw, strict=False)
        else:
            credenciais_dict = dict(raw)
            
    # 2. Tenta caso o usuário tenha colocado as chaves TOML direto dentro de [google]
    elif "google" in st.secrets and "private_key" in st.secrets["google"]:
        credenciais_dict = dict(st.secrets["google"])
        
    # 3. Tenta caso esteja na raiz como st.secrets["credenciais"]
    elif "credenciais" in st.secrets:
        raw = st.secrets["credenciais"]
        if isinstance(raw, str):
            credenciais_dict = json.loads(raw, strict=False)
        else:
            credenciais_dict = dict(raw)
            
    # 4. Tenta caso o JSON tenha sido colado como TOML direto na raiz
    elif "private_key" in st.secrets:
        credenciais_dict = dict(st.secrets)
        
    if not credenciais_dict:
        raise KeyError(
            "Credenciais não encontradas em st.secrets['google']['credenciais']."
        )
        
    # Corrige quebras de linha na private_key caso tenham sido escapadas
    if "private_key" in credenciais_dict and isinstance(credenciais_dict["private_key"], str):
        credenciais_dict["private_key"] = credenciais_dict["private_key"].replace("\\n", "\n")
        
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credenciais_dict, escopos)
    return gspread.authorize(creds)

def obter_planilha():
    """Abre a planilha pela URL exata e seleciona a aba 'Página1' (ou a primeira aba)."""
    cliente = obter_cliente_google_sheets()
    planilha = cliente.open_by_url(SHEET_URL)
    try:
        return planilha.worksheet(SHEET_TAB_NAME)
    except Exception:
        return planilha.sheet1

@st.cache_data(ttl=60, show_spinner=False)
def carregar_dados():
    """Carrega os dados da planilha de forma resiliente e converte tipos com Pandas."""
    ws = obter_planilha()
    valores = ws.get_all_values()
    
    # Se a planilha estiver totalmente vazia, cria a linha de cabeçalho automaticamente
    if not valores:
        ws.append_row(COLUNAS_PLANILHA, value_input_option="USER_ENTERED")
        return pd.DataFrame(columns=COLUNAS_PLANILHA)
    
    # Verifica se a primeira linha já é o cabeçalho esperado
    primeira_linha = [str(c).strip() for c in valores[0]]
    
    if "Data" not in primeira_linha and "Valor (R$)" not in primeira_linha:
        # Se a planilha estiver em branco na linha 1, escreve o cabeçalho
        if all(c == "" for c in primeira_linha):
            ws.update("A1:D1", [COLUNAS_PLANILHA], value_input_option="USER_ENTERED")
            dados_linhas = valores[1:]
        else:
            ws.insert_row(COLUNAS_PLANILHA, index=1, value_input_option="USER_ENTERED")
            dados_linhas = valores
    else:
        dados_linhas = valores[1:]
        
    # Filtra linhas totalmente em branco
    dados_validos = []
    for linha in dados_linhas:
        if any(str(celula).strip() != "" for celula in linha):
            # Garante exatamente 4 colunas na linha
            linha_ajustada = (list(linha) + ["", "", "", ""])[:4]
            dados_validos.append(linha_ajustada)
            
    if not dados_validos:
        return pd.DataFrame(columns=COLUNAS_PLANILHA)
        
    df = pd.DataFrame(dados_validos, columns=COLUNAS_PLANILHA)
    
    # Conversão das colunas para numérico e datetime (formato dd/mm/aaaa) usando Pandas
    df["Valor (R$)"] = df["Valor (R$)"].apply(converter_para_float)
    df["Data"] = pd.to_datetime(df["Data"], format="%d/%m/%Y", dayfirst=True, errors="coerce")
    
    return df

# ==============================================================================
# 4. INICIALIZAÇÃO E DIAGNÓSTICO DE CONEXÃO
# ==============================================================================
try:
    df_raw = carregar_dados()
except Exception as e:
    st.error(f"⚠️ Não foi possível carregar a planilha: {str(e)}")
    st.markdown(
        f"""
        ### 🛠️ Checklist Rápido de Verificação:
        1. **Compartilhamento da Planilha:**  
           Abra a sua [Planilha no Google Sheets]({SHEET_URL}), clique em **Compartilhar** e confirme que o e-mail abaixo está adicionado como **Editor**:  
           `{SERVICE_ACCOUNT_EMAIL}`
        2. **APIs Ativadas no Projeto (`app2-513815`):**  
           Certifique-se de que a **Google Sheets API** e a **Google Drive API** estão ativadas no Google Cloud Console.
        3. **Configuração dos Secrets no Streamlit Cloud:**  
           No menu do app no Streamlit Cloud (**Settings > Secrets**), verifique se está configurado com `[google]` e `credenciais`.
        """
    )
    st.stop()

# ==============================================================================
# 5. CABEÇALHO DO APLICATIVO
# ==============================================================================
st.title("💸 Controle de Gastos")
st.caption("Gerenciador financeiro integrado ao Google Sheets com análise visual e lançamentos recorrentes.")

# Criação das 3 Abas
aba_novo, aba_historico, aba_dashboard = st.tabs(["➕ Novo", "📋 Histórico", "📊 Dashboard"])

# ==============================================================================
# ABA 1: NOVO (Lançamentos de Gastos)
# ==============================================================================
with aba_novo:
    st.subheader("Registrar Nova Despesa")
    st.write("Preencha os campos abaixo para gravar um novo lançamento na planilha.")
    
    with st.form("form_novo_lancamento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            data_input = st.date_input(
                "Data",
                value=date.today(),
                format="DD/MM/YYYY",
                help="Data do lançamento (formato dd/mm/aaaa)."
            )
            descricao_input = st.text_input(
                "Descrição",
                placeholder="Ex: Supermercado, Combustível, Farmácia...",
                help="Informe uma descrição para identificar o gasto."
            )
            
        with col2:
            categoria_input = st.selectbox(
                "Categoria",
                options=CATEGORIAS,
                help="Selecione a categoria da despesa."
            )
            valor_input = st.text_input(
                "Valor (R$)",
                placeholder="Ex: 15,50",
                help="Digite o valor usando vírgula para centavos (ex: 15,50)."
            )
            
        st.markdown("---")
        st.markdown("##### 🔄 Lançamento Recorrente (Opcional)")
        col_rec1, col_rec2 = st.columns(2)
        with col_rec1:
            recorrente = st.checkbox(
                "Repetir esta despesa para mais de um mês?",
                help="Marque para lançar automaticamente a despesa nos meses seguintes."
            )
        with col_rec2:
            meses_recorrencia = st.number_input(
                "Quantidade de meses (Total de parcelas/meses)",
                min_value=1,
                max_value=60,
                value=1,
                step=1,
                help="Se quiser lançar apenas no mês atual, deixe 1. Para mais meses, marque a caixa ao lado e escolha a quantidade (ex: 3, 6, 12)."
            )
            
        btn_salvar_novo = st.form_submit_button("💾 Registrar Lançamento", type="primary", use_container_width=True)
        
        if btn_salvar_novo:
            erros = []
            if not descricao_input.strip():
                erros.append("O campo **Descrição** é obrigatório.")
                
            valor_texto = valor_input.strip().replace("R$", "").strip()
            valor_convertido = None
            if not valor_texto:
                erros.append("O campo **Valor (R$)** é obrigatório.")
            else:
                try:
                    if "," in valor_texto:
                        valor_limpo = valor_texto.replace(".", "").replace(",", ".")
                    else:
                        valor_limpo = valor_texto
                    valor_convertido = float(valor_limpo)
                    if valor_convertido <= 0:
                        erros.append("O **Valor** deve ser maior que zero.")
                except ValueError:
                    erros.append("Formato de **Valor** inválido. Digite apenas números e vírgula (ex: `15,50`).")
                    
            if erros:
                for erro in erros:
                    st.error(f"❌ {erro}")
            else:
                try:
                    total_meses = int(meses_recorrencia) if (recorrente or meses_recorrencia > 1) else 1
                    novas_linhas = []
                    data_base = pd.to_datetime(data_input)
                    
                    for i in range(total_meses):
                        data_lancamento = (data_base + pd.DateOffset(months=i)).strftime("%d/%m/%Y")
                        desc_final = descricao_input.strip()
                        if total_meses > 1:
                            desc_final = f"{desc_final} ({i+1}/{total_meses})"
                            
                        novas_linhas.append([
                            data_lancamento,
                            desc_final,
                            categoria_input,
                            round(valor_convertido, 2)
                        ])
                        
                    ws = obter_planilha()
                    # Verifica se a planilha precisa do cabeçalho antes de inserir
                    if not ws.get_all_values():
                        ws.append_row(COLUNAS_PLANILHA, value_input_option="USER_ENTERED")
                        
                    ws.append_rows(novas_linhas, value_input_option="USER_ENTERED")
                    st.cache_data.clear()
                    st.success(f"✅ {len(novas_linhas)} lançamento(s) gravado(s) com sucesso!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Erro ao gravar na planilha: {str(ex)}")

# ==============================================================================
# ABA 2: HISTÓRICO (Gerenciamento)
# ==============================================================================
with aba_historico:
    st.subheader("Histórico e Gerenciamento de Gastos")
    
    if df_raw.empty or df_raw["Valor (R$)"].dropna().empty:
        st.info("ℹ️ A planilha ainda não possui lançamentos cadastrados. Utilize a aba '➕ Novo' para registrar seu primeiro gasto.")
    else:
        # 1. Filtro por mês de lançamento e Totalizador
        df_hist = df_raw.dropna(subset=["Data"]).copy()
        df_hist["Mes_Ano"] = df_hist["Data"].dt.strftime("%m/%Y")
        df_hist["Ordem_Ano_Mes"] = df_hist["Data"].dt.strftime("%Y-%m")
        
        periodos_df = (
            df_hist[["Mes_Ano", "Ordem_Ano_Mes"]]
            .drop_duplicates()
            .sort_values(by="Ordem_Ano_Mes", ascending=False)
        )
        lista_meses = ["Todos os Meses"] + periodos_df["Mes_Ano"].tolist()
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filtro_mes_hist = st.selectbox("Filtrar por Mês de Lançamento:", options=lista_meses)
            
        if filtro_mes_hist == "Todos os Meses":
            df_filtrado_hist = df_raw.copy()
        else:
            df_filtrado_hist = df_hist[df_hist["Mes_Ano"] == filtro_mes_hist][COLUNAS_PLANILHA].copy()
            
        soma_filtrada = df_filtrado_hist["Valor (R$)"].sum()
        soma_total_geral = df_raw["Valor (R$)"].sum()
        
        with col_f2:
            st.metric(
                label=f"Total do Período ({filtro_mes_hist})",
                value=formatar_moeda(soma_filtrada)
            )
        with col_f3:
            st.metric(
                label="Total Geral (Todos os Lançamentos)",
                value=formatar_moeda(soma_total_geral)
            )
            
        st.markdown("---")
        
        # 2. Tabela interativa st.data_editor para editar todos os lançamentos
        st.markdown("#### ✏️ Editar Lançamentos")
        st.caption(
            "Edite valores, datas, descrições ou categorias diretamente na tabela abaixo. "
            "Você também pode adicionar ou remover linhas e clicar em **Salvar Alterações**."
        )
        
        df_para_editar = df_raw.copy()
        df_para_editar["Data"] = pd.to_datetime(df_para_editar["Data"]).dt.date
        
        config_colunas = {
            "Data": st.column_config.DateColumn(
                "Data",
                format="DD/MM/YYYY",
                required=True
            ),
            "Descrição": st.column_config.TextColumn(
                "Descrição",
                required=True
            ),
            "Categoria": st.column_config.SelectboxColumn(
                "Categoria",
                options=CATEGORIAS,
                required=True
            ),
            "Valor (R$)": st.column_config.NumberColumn(
                "Valor (R$)",
                format="R$ %.2f",
                min_value=0.0,
                required=True
            )
        }
        
        df_editado = st.data_editor(
            df_para_editar,
            column_config=config_colunas,
            num_rows="dynamic",
            use_container_width=True,
            key="tabela_editor_historico"
        )
        
        if st.button("Salvar Alterações", type="primary"):
            try:
                df_salvar = df_editado.copy()
                # Remove linhas onde a descrição e o valor estejam vazios
                df_salvar = df_salvar.dropna(how="all")
                
                df_salvar["Data"] = pd.to_datetime(df_salvar["Data"]).dt.strftime("%d/%m/%Y").fillna("")
                df_salvar["Descrição"] = df_salvar["Descrição"].fillna("").astype(str)
                df_salvar["Categoria"] = df_salvar["Categoria"].fillna(CATEGORIAS[0]).astype(str)
                df_salvar["Valor (R$)"] = df_salvar["Valor (R$)"].apply(converter_para_float).round(2)
                
                ws = obter_planilha()
                ws.clear()
                
                dados_atualizados = [COLUNAS_PLANILHA] + df_salvar[COLUNAS_PLANILHA].values.tolist()
                ws.update(dados_atualizados, value_input_option="USER_ENTERED")
                
                st.cache_data.clear()
                st.success("✅ Alterações salvas e sincronizadas com a planilha!")
                st.rerun()
            except Exception as ex:
                st.error(f"Erro ao salvar alterações: {str(ex)}")
                
        st.markdown("---")
        
        # 3. Histórico separado por Categoria (cada categoria com sua tabela e totais separados)
        st.markdown(f"#### 📂 Lançamentos Separados por Categoria ({filtro_mes_hist})")
        
        for categoria in CATEGORIAS:
            df_cat = df_filtrado_hist[df_filtrado_hist["Categoria"] == categoria].copy()
            total_cat = df_cat["Valor (R$)"].sum()
            
            st.markdown(f"##### 📌 {categoria} — Total: **{formatar_moeda(total_cat)}**")
            if df_cat.empty:
                st.info(f"Nenhum lançamento na categoria **{categoria}** para o filtro selecionado.")
            else:
                df_cat_view = df_cat.copy()
                df_cat_view["Data"] = pd.to_datetime(df_cat_view["Data"]).dt.strftime("%d/%m/%Y")
                st.dataframe(
                    df_cat_view,
                    column_config={
                        "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")
                    },
                    use_container_width=True,
                    hide_index=True
                )

# ==============================================================================
# ABA 3: DASHBOARD (Gráficos)
# ==============================================================================
with aba_dashboard:
    st.subheader("Dashboard de Gastos")
    
    df_dash = df_raw.dropna(subset=["Data", "Valor (R$)"]).copy()
    
    if df_dash.empty or df_dash["Valor (R$)"].sum() == 0:
        st.info("ℹ️ A planilha ainda não possui dados suficientes para exibir o Dashboard. Cadastre lançamentos na aba '➕ Novo'.")
    else:
        df_dash["Mes"] = df_dash["Data"].dt.month
        df_dash["Ano"] = df_dash["Data"].dt.year
        
        meses_existentes = sorted(df_dash["Mes"].dropna().unique().astype(int))
        anos_existentes = sorted(df_dash["Ano"].dropna().unique().astype(int), reverse=True)
        
        # 1. Filtros lado a lado para Mês e Ano
        col_mes, col_ano = st.columns(2)
        with col_mes:
            mes_dash = st.selectbox(
                "Selecione o Mês:",
                options=meses_existentes,
                format_func=lambda m: f"{m:02d} - {NOMES_MESES.get(m, str(m))}"
            )
        with col_ano:
            ano_dash = st.selectbox(
                "Selecione o Ano:",
                options=anos_existentes
            )
            
        df_mes_ano = df_dash[(df_dash["Mes"] == mes_dash) & (df_dash["Ano"] == ano_dash)].copy()
        total_mes = df_mes_ano["Valor (R$)"].sum()
        nome_mes_atual = NOMES_MESES.get(mes_dash, str(mes_dash))
        
        st.markdown("---")
        
        # 2. Card de métrica mostrando o Total Gasto do mês filtrado
        st.metric(
            label=f"Total Gasto em {nome_mes_atual}/{ano_dash}",
            value=formatar_moeda(total_mes)
        )
        
        if df_mes_ano.empty or total_mes == 0:
            st.info(f"ℹ️ Nenhum gasto encontrado para **{nome_mes_atual} de {ano_dash}**.")
        else:
            # 3. Gráfico de Pizza em formato Rosca (Donut Chart) com plotly.express
            df_agrupado = (
                df_mes_ano.groupby("Categoria", as_index=False)["Valor (R$)"]
                .sum()
                .sort_values(by="Valor (R$)", ascending=False)
            )
            
            fig = px.pie(
                df_agrupado,
                values="Valor (R$)",
                names="Categoria",
                hole=0.4,
                title=f"Distribuição de Gastos por Categoria ({nome_mes_atual}/{ano_dash})"
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>Total: R$ %{value:,.2f}<br>Percentual: %{percent}<extra></extra>"
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            # 4. Resumo com os valores totais de cada categoria e o total geral
            st.markdown(f"#### 📊 Resumo por Categoria — {nome_mes_atual}/{ano_dash}")
            
            linhas_resumo = []
            for cat in CATEGORIAS:
                soma_cat = df_mes_ano[df_mes_ano["Categoria"] == cat]["Valor (R$)"].sum()
                perc_cat = (soma_cat / total_mes * 100) if total_mes > 0 else 0.0
                linhas_resumo.append({
                    "Categoria": cat,
                    "Total da Categoria": formatar_moeda(soma_cat),
                    "Participação (%)": f"{perc_cat:.1f}%"
                })
                
            df_resumo_final = pd.DataFrame(linhas_resumo)
            st.dataframe(df_resumo_final, use_container_width=True, hide_index=True)
            
            st.success(f"💰 **Total Geral ({nome_mes_atual}/{ano_dash}): {formatar_moeda(total_mes)}**")
