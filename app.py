import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
import re
import io
import base64

# Configuração inicial da página
st.set_page_config(page_title="Sistema de Gestão ADM", layout="wide", initial_sidebar_state="expanded")

# =========================================================
# ESTILIZAÇÃO CSS (OCULTA GERENCIAR APLICATIVO E RODAPÉ)
# =========================================================
st.markdown("""
    <style>
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    div[data-testid="stToolbar"] {visibility: hidden !important; display: none !important;}
    
    .main { background-color: #f8f9fa; }
    h1 { color: #1e3a8a; font-family: 'Segoe UI', sans-serif; font-weight: 700; margin-bottom: 20px; }
    h2, h3 { color: #1e40af; font-family: 'Segoe UI', sans-serif; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border: 1px solid #e5e7eb;
    }
    .stButton>button {
        background-color: #1e40af;
        color: white;
        border-radius: 8px;
        font-weight: 600;
        border: none;
        padding: 8px 16px;
    }
    .stButton>button:hover { background-color: #1d4ed8; color: white; }
    </style>
""", unsafe_allow_html=True)

DB_FILE = "gestao_empresa.db"

# ---------------------------------------------------------
# BANCO DE DADOS - INICIALIZAÇÃO E MIGRAÇÃO
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS filiais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            cnpj TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS colaboradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matricula TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            cpf TEXT,
            rg TEXT,
            funcao TEXT,
            cnpj_empresa TEXT,
            filial_id INTEGER,
            data_nascimento DATE,
            data_contratacao DATE,
            data_retorno_folga DATE,
            intervalo_folga_dias INTEGER,
            proxima_folga DATE,
            he_50 REAL DEFAULT 0,
            he_100 REAL DEFAULT 0,
            saldo_cartao_alimentacao REAL DEFAULT 0,
            status_aso TEXT,
            doc_pessoais TEXT,
            doc_preadmissionais TEXT,
            doc_admissionais TEXT,
            tipo_usuario_va TEXT DEFAULT 'Já Usuário',
            motivo_retorno TEXT DEFAULT 'Folga',
            status_solicitacao_va TEXT DEFAULT 'Normal / Atualizado',
            status_colaborador TEXT DEFAULT 'Ativo',
            data_demissao DATE,
            FOREIGN KEY (filial_id) REFERENCES filiais (id)
        )
    ''')
    
    try:
        c.execute("ALTER TABLE colaboradores ADD COLUMN status_colaborador TEXT DEFAULT 'Ativo'")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE colaboradores ADD COLUMN data_demissao DATE")
    except Exception:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS historico_colaboradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_matricula TEXT,
            tipo_alteracao TEXT,
            valor_antigo TEXT,
            valor_novo TEXT,
            data_registro DATETIME,
            FOREIGN KEY (colaborador_matricula) REFERENCES colaboradores (matricula)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS historico_pedidos_va (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_ano TEXT,
            filial_nome TEXT,
            matricula TEXT,
            cnpj_empresa TEXT,
            nome TEXT,
            cpf TEXT,
            saldo REAL,
            tipo_usuario TEXT,
            data_registro DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# FUNÇÕES DE FORMATAÇÃO E MASCARAS (BR)
# ---------------------------------------------------------
def formatar_cpf(valor):
    if not valor or pd.isna(valor):
        return ""
    nums = re.sub(r'\D', '', str(valor))
    if len(nums) == 11:
        return f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"
    return str(valor)

def formatar_cnpj(valor):
    if not valor or pd.isna(valor):
        return ""
    nums = re.sub(r'\D', '', str(valor))
    if len(nums) == 14:
        return f"{nums[:2]}.{nums[2:5]}.{nums[5:8]}/{nums[8:12]}-{nums[12:]}"
    return str(valor)

MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2100, 12, 31)

def registrar_historico(matricula, tipo, antigo, novo):
    if str(antigo).strip() != str(novo).strip():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO historico_colaboradores (colaborador_matricula, tipo_alteracao, valor_antigo, valor_novo, data_registro)
            VALUES (?, ?, ?, ?, ?)
        ''', (matricula, tipo, str(antigo), str(novo), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

def converter_para_date(valor):
    if not valor or pd.isna(valor) or str(valor).strip() in ["", "None", "NaT"]:
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    
    val_str = str(valor).split()[0].strip()
    try:
        if "/" in val_str:
            partes = val_str.split("/")
            if len(partes) == 3:
                return date(int(partes[2]), int(partes[1]), int(partes[0]))
        elif "-" in val_str:
            partes = val_str.split("-")
            if len(partes) == 3:
                return date(int(partes[0]), int(partes[1]), int(partes[2]))
    except Exception:
        pass
    return None

def calcular_proxima_folga(data_retorno, dias):
    dt = converter_para_date(data_retorno)
    if dt and dias:
        try:
            proxima = dt + timedelta(days=int(dias))
            return proxima
        except Exception:
            return None
    return None

def parse_date_para_input(valor_str):
    dt = converter_para_date(valor_str)
    return dt if dt else date.today()

def formatar_data_br(valor):
    dt = converter_para_date(valor)
    if dt:
        return dt.strftime("%d/%m/%Y")
    return str(valor) if valor and not pd.isna(valor) else ""

def get_filiais_dict():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT id, nome FROM filiais ORDER BY nome", conn)
    conn.close()
    return dict(zip(df['nome'], df['id'])), dict(zip(df['id'], df['nome']))

def get_cargos_cadastrados():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT DISTINCT funcao FROM colaboradores WHERE funcao IS NOT NULL AND funcao != '' ORDER BY funcao", conn)
    conn.close()
    return df['funcao'].tolist()

filiais_nome_para_id, filiais_id_para_nome = get_filiais_dict()

# ---------------------------------------------------------
# MENU PRINCIPAL (DISPONÍVEL NO TOPO DA TELA)
# ---------------------------------------------------------
lista_modulos = [
    "📊 Dashboard / Consulta",
    "➕ Novo Colaborador / Admissão",
    "✏️ Editar Cadastro do Colaborador",
    "🏢 Cadastro de Filiais",
    "🔄 Transferência entre Filiais",
    "💳 Pedido Saldo Alimentação",
    "📥 Importar Excel por Filial",
    "📤 Exportar Dados",
    "📜 Histórico de Alterações"
]

st.markdown("### 🏢 Sistema de Gestão ADM")
menu = st.selectbox("📌 **SELECIONE O MÓDULO DESEJADO ABAIXO:**", lista_modulos, key="menu_principal_topo")
st.markdown("---")

# ---------------------------------------------------------
# BARRA LATERAL (EXIBIÇÃO DA LOGO OFICIAL ENGESP)
# ----------------info: Tentativa por arquivo local ou fallback HTML/Base64---
st.sidebar.markdown("## 🏢 ENGESP")
st.sidebar.write("Engenharia São Patrício - Gestão ADM")
st.sidebar.markdown("---")

try:
    # Tenta carregar o arquivo de imagem fornecido na pasta local
    st.sidebar.image("image_ec1b03.png", use_column_width=True)
except Exception:
    # Se por acaso o arquivo não for encontrado na pasta do servidor, exibe via HTML com a tag oficial
    st.sidebar.markdown(
        """
        <div style="text-align: center; margin-bottom: 15px;">
            <img src="app/static/image_ec1b03.png" style="max-width: 100%; border-radius: 8px;">
        </div>
        """,
        unsafe_allow_html=True
    )

st.sidebar.markdown("---")

# ---------------------------------------------------------
# MÓDULO 1: DASHBOARD (PAINEL DE GESTÃO)
# ---------------------------------------------------------
if menu == "📊 Dashboard / Consulta":
    st.title("📊 Painel de Gestão")
    
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT c.id, c.matricula, c.nome, c.funcao as "Cargo / Função", c.cpf, c.rg, c.cnpj_empresa,
               f.nome as filial, c.data_nascimento, c.data_contratacao,
               c.data_retorno_folga, c.intervalo_folga_dias, c.proxima_folga, c.motivo_retorno as "Tipo Retorno",
               c.he_50, c.he_100, c.saldo_cartao_alimentacao, c.tipo_usuario_va as "Tipo de Usuário",
               c.status_solicitacao_va as "Status Cartão", c.status_aso, c.doc_pessoais, c.doc_preadmissionais, c.doc_admissionais,
               c.status_colaborador as "Status", c.data_demissao as "Data Demissão"
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()

    if not df.empty:
        opcoes_filiais_painel = ["Todas as Filiais"] + sorted(df['filial'].dropna().unique().tolist())
        filial_escolhida_painel = st.selectbox("🏢 Selecione a Filial para Visualização:", opcoes_filiais_painel)
        
        if filial_escolhida_painel != "Todas as Filiais":
            df = df[df['filial'] == filial_escolhida_painel]
    else:
        filial_escolhida_painel = "Todas as Filiais"

    st.markdown("---")
    st.metric("Total Colaboradores", len(df))
    st.markdown("---")

    if df.empty:
        st.info("Nenhum colaborador cadastrado para esta seleção.")
    else:
        colunas_data = ['data_nascimento', 'data_contratacao', 'data_retorno_folga', 'proxima_folga', 'Data Demissão']
        for col in colunas_data:
            if col in df.columns:
                df[col] = df[col].apply(formatar_data_br)

        if 'cpf' in df.columns:
            df['cpf'] = df['cpf'].apply(formatar_cpf)
        if 'cnpj_empresa' in df.columns:
            df['cnpj_empresa'] = df['cnpj_empresa'].apply(formatar_cnpj)

        col1, col2, col3 = st.columns(3)
        with col1:
            filtro_status_aso = st.multiselect("Filtrar por Status ASO:", options=df['status_aso'].dropna().unique())
        with col2:
            filtro_cargo = st.multiselect("Filtrar por Cargo / Função:", options=df['Cargo / Função'].dropna().unique())
        with col3:
            filtro_status_colab = st.multiselect("Filtrar por Status (Ativo/Demitido):", options=df['Status'].dropna().unique(), default=["Ativo"])

        df_filtered = df.copy()
        if filtro_status_aso:
            df_filtered = df_filtered[df_filtered['status_aso'].isin(filtro_status_aso)]
        if filtro_cargo:
            df_filtered = df_filtered[df_filtered['Cargo / Função'].isin(filtro_cargo)]
        if filtro_status_colab:
            df_filtered = df_filtered[df_filtered['Status'].isin(filtro_status_colab)]

        st.subheader(f"Registros Exibidos ({len(df_filtered)})")
        st.dataframe(df_filtered, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 2: NOVO COLABORADOR / ADMISSÃO
# ---------------------------------------------------------
elif menu == "➕ Novo Colaborador / Admissão":
    st.title("➕ Admissão de Novo Colaborador")
    
    if not filiais_nome_para_id:
        st.warning("⚠️ Cadastre pelo menos uma filial antes de adicionar colaboradores.")
    else:
        st.subheader("1. Informações Pessoais, Cargo / Função e Empresa")
        c_fil, c1, c2 = st.columns(3)
        filial_nome = c_fil.selectbox("Filial *", options=list(filiais_nome_para_id.keys()))
        matricula = c1.text_input("Matrícula *")
        nome = c2.text_input("Nome Completo *")

        c3, c4, c5 = st.columns(3)
        cargos_existentes = get_cargos_cadastrados()
        cargo_sel = c3.selectbox("Selecionar Cargo / Função Existente:", ["-- Novo Cargo / Função --"] + cargos_existentes)
        
        if cargo_sel == "-- Novo Cargo / Função --":
            cargo = c3.text_input("Digite o Novo Cargo / Função *")
        else:
            cargo = cargo_sel

        cpf = c4.text_input("CPF (somente números ou formatado)")
        rg = c5.text_input("RG")

        c6, c7 = st.columns(2)
        cnpj_empresa = c6.text_input("CNPJ da Empresa (somente números ou formatado)", value="37.608.361/0001-25")
        data_nascimento = c7.date_input("Data de Nascimento", min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

        status_colab_novo = st.selectbox("Status do Colaborador", ["Ativo", "Demitido"], index=0)
        data_demissao_novo = None
        if status_colab_novo == "Demitido":
            data_demissao_novo = st.date_input("Data da Demissão", min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

        st.subheader("2. Dados Contratuais e Afastamento / Retorno")
        d1, d2, d3, d4 = st.columns(4)
        data_contratacao = d1.date_input("Data de Contratação", min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")
        motivo_retorno = d2.selectbox("Motivo do Retorno", ["Folga", "Férias", "Recesso"])
        data_retorno_folga = d3.date_input("Data Retorno (Folga/Férias/Recesso)", min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")
        intervalo_folga = d4.selectbox("Cálculo Próxima Previsão (Dias)", [30, 60, 90])

        proxima_folga_calc = calcular_proxima_folga(data_retorno_folga, intervalo_folga)
        st.success(f"💡 **Previsão Exata da Próxima Previsão ({intervalo_folga} dias a partir de {formatar_data_br(data_retorno_folga)}):** {formatar_data_br(proxima_folga_calc)}")

        st.subheader("3. Saldos e Benefícios")
        s1, s2, s3, s4, s5 = st.columns(5)
        he_50 = s1.number_input("Horas Extras 50% (Horas)", min_value=0.0, step=0.5)
        he_100 = s2.number_input("Horas Extras 100% (Horas)", min_value=0.0, step=0.5)
        saldo_va = s3.number_input("Saldo Cartão Alimentação Inicial (R$)", min_value=0.0, step=10.0)
        status_sol_va = s4.selectbox("Status Cartão Alimentação", ["Normal / Atualizado", "Solicitar Saldo"])
        tipo_usuario_va = s5.selectbox("Tipo de Usuário (Alimentação)", ["Já Usuário", "Novo Usuário"], index=0)

        if st.button("💾 Finalizar Cadastro"):
            if not matricula or not nome:
                st.error("Preencha os campos obrigatórios (Matrícula e Nome).")
            else:
                cpf_formatado = formatar_cpf(cpf)
                cnpj_formatado = formatar_cnpj(cnpj_empresa)
                dt_dem_val = str(data_demissao_novo) if status_colab_novo == "Demitido" and data_demissao_novo else None
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO colaboradores (
                            matricula, nome, cpf, rg, funcao, cnpj_empresa, filial_id,
                            data_nascimento, data_contratacao, data_retorno_folga,
                            intervalo_folga_dias, proxima_folga, motivo_retorno, he_50, he_100,
                            saldo_cartao_alimentacao, status_solicitacao_va, tipo_usuario_va, status_aso, doc_pessoais,
                            doc_preadmissionais, doc_admissionais, status_colaborador, data_demissao
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        matricula, nome, cpf_formatado, rg, cargo, cnpj_formatado,
                        filiais_nome_para_id[filial_nome], str(data_nascimento),
                        str(data_contratacao), str(data_retorno_folga), intervalo_folga,
                        str(proxima_folga_calc), motivo_retorno, he_50, he_100, saldo_va, status_sol_va, tipo_usuario_va,
                        'Pendente', 'Pendente', 'Pendente', 'Pendente', status_colab_novo, dt_dem_val
                    ))
                    conn.commit()
                    conn.close()
                    
                    registrar_historico(matricula, "Admissão Inicial", "-", f"Admitido na Filial {filial_nome} - Cargo/Função: {cargo}")
                    st.success(f"Colaborador {nome} cadastrado com sucesso!")
                except sqlite3.IntegrityError:
                    st.error("Erro: Matrícula já cadastrada no sistema.")

# ---------------------------------------------------------
# MÓDULO 3: EDITAR CADASTRO COMPLETO (COM FILTRO POR MATRÍCULA)
# ---------------------------------------------------------
elif menu == "✏️ Editar Cadastro do Colaborador":
    st.title("✏️ Editar Cadastro Completo do Colaborador")
    
    conn = sqlite3.connect(DB_FILE)
    df_colab = pd.read_sql_query('''
        SELECT c.matricula, c.nome, c.funcao as cargo, f.nome as filial
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        ORDER BY c.nome
    ''', conn)
    conn.close()

    if df_colab.empty:
        st.info("Nenhum colaborador cadastrado.")
    else:
        st.subheader("🔍 Filtre para localizar o colaborador facilmente")
        f1, f2, f3 = st.columns(3)
        filtro_mat_edit = f3.text_input("Filtrar por Matrícula (Parcial ou Completa):")
        filtro_filial_edit = f1.multiselect("Filtrar por Filial:", options=df_colab['filial'].dropna().unique())
        filtro_cargo_edit = f2.multiselect("Filtrar por Cargo / Função:", options=df_colab['cargo'].dropna().unique())

        df_edit_filtered = df_colab.copy()
        if filtro_mat_edit:
            df_edit_filtered = df_edit_filtered[df_edit_filtered['matricula'].str.contains(filtro_mat_edit, case=False, na=False)]
        if filtro_filial_edit:
            df_edit_filtered = df_edit_filtered[df_edit_filtered['filial'].isin(filtro_filial_edit)]
        if filtro_cargo_edit:
            df_edit_filtered = df_edit_filtered[df_edit_filtered['cargo'].isin(filtro_cargo_edit)]

        if df_edit_filtered.empty:
            st.warning("Nenhum colaborador encontrado com os filtros informados.")
        else:
            opcoes_colab = df_edit_filtered['matricula'] + " - " + df_edit_filtered['nome'] + " (Cargo/Função: " + df_edit_filtered['cargo'].fillna('Sem Registro') + ")"
            colab_selecionado = st.selectbox("Selecione o Colaborador para Editar:", opcoes_colab)
            
            if colab_selecionado:
                matricula_sel = colab_selecionado.split(" - ")[0]
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT * FROM colaboradores WHERE matricula = ?", (matricula_sel,))
                dados = c.fetchone()
                conn.close()

                if dados:
                    tab_edit, tab_delete = st.tabs(["✏️ Alterar Todas as Informações", "🗑️ Excluir Registros"])
                    
                    with tab_edit:
                        st.subheader("1. Identificação, Cargo / Função e Dados Pessoais")
                        u1, u2, u3 = st.columns(3)
                        mat_e = u1.text_input("Matrícula *", value=dados[1])
                        nome_e = u2.text_input("Nome Completo *", value=dados[2])
                        cargo_e = u3.text_input("Cargo / Função *", value=dados[5] or "")

                        u4, u5, u6 = st.columns(3)
                        cpf_e = u4.text_input("CPF (com pontuação BR)", value=formatar_cpf(dados[3]))
                        rg_e = u5.text_input("RG", value=dados[4] or "")
                        
                        cnpj_val_atual = formatar_cnpj(dados[6]) if dados[6] else "37.608.361/0001-25"
                        cnpj_e = u6.text_input("CNPJ Empresa (com pontuação BR)", value=cnpj_val_atual)

                        u7, u8 = st.columns(2)
                        filial_atual_nome = filiais_id_para_nome.get(dados[7], list(filiais_nome_para_id.keys())[0] if filiais_nome_para_id else "")
                        filial_idx = list(filiais_nome_para_id.keys()).index(filial_atual_nome) if filial_atual_nome in filiais_nome_para_id else 0
                        filial_e = u7.selectbox("Filial", options=list(filiais_nome_para_id.keys()), index=filial_idx)
                        
                        dt_nasc_val = parse_date_para_input(dados[8])
                        dt_nasc_e = u8.date_input("Data de Nascimento", value=dt_nasc_val, min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

                        # CAMPOS DE STATUS E DEMISSÃO
                        col_st1, col_st2 = st.columns(2)
                        status_atual_colab = dados[23] if len(dados) > 23 and dados[23] in ["Ativo", "Demitido"] else "Ativo"
                        status_idx = ["Ativo", "Demitido"].index(status_atual_colab)
                        status_colab_e = col_st1.selectbox("Status do Colaborador", ["Ativo", "Demitido"], index=status_idx)
                        
                        data_demissao_e = None
                        if status_colab_e == "Demitido":
                            dt_dem_val = parse_date_para_input(dados[24]) if len(dados) > 24 and dados[24] else date.today()
                            data_demissao_e = col_st2.date_input("Data da Demissão", value=dt_dem_val, min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

                        st.subheader("2. Dados Contratuais e Retorno de Folga / Férias / Recesso")
                        d1, d2, d3, d4 = st.columns(4)
                        dt_contr_val = parse_date_para_input(dados[9])
                        dt_ret_val = parse_date_para_input(dados[10])
                        
                        data_contratacao_e = d1.date_input("Data de Contratação", value=dt_contr_val, min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")
                        
                        motivo_atual = dados[21] if len(dados) > 21 and dados[21] in ["Folga", "Férias", "Recesso"] else "Folga"
                        motivo_idx = ["Folga", "Férias", "Recesso"].index(motivo_atual)
                        motivo_retorno_e = d2.selectbox("Motivo do Retorno", ["Folga", "Férias", "Recesso"], index=motivo_idx)

                        data_retorno_folga_e = d3.date_input("Data Retorno de Folga/Férias/Recesso", value=dt_ret_val, min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")
                        
                        inter_val = int(dados[11]) if dados[11] in [30, 60, 90] else 30
                        inter_idx = [30, 60, 90].index(inter_val)
                        intervalo_folga_e = d4.selectbox("Cálculo Próxima Previsão (Dias)", [30, 60, 90], index=inter_idx)

                        proxima_folga_calc_e = calcular_proxima_folga(data_retorno_folga_e, intervalo_folga_e)
                        st.success(f"💡 **Previsão Exata Recalculada ({intervalo_folga_e} dias a partir de {formatar_data_br(data_retorno_folga_e)}):** {formatar_data_br(proxima_folga_calc_e)}")

                        st.subheader("3. Horas Extras e Cartão Alimentação")
                        s1, s2, s3, s4, s5 = st.columns(5)
                        he_50_e = s1.number_input("Horas Extras 50%", value=float(dados[13] or 0.0), step=0.5)
                        he_100_e = s2.number_input("Horas Extras 100%", value=float(dados[14] or 0.0), step=0.5)
                        saldo_va_e = s3.number_input("Saldo Cartão Alimentação Padrão (R$)", value=float(dados[15] or 0.0), step=10.0)
                        
                        status_sol_atual = dados[22] if len(dados) > 22 and dados[22] in ["Normal / Atualizado", "Solicitar Saldo"] else "Normal / Atualizado"
                        status_sol_idx = ["Normal / Atualizado", "Solicitar Saldo"].index(status_sol_atual)
                        status_sol_va_e = s4.selectbox("Status Cartão Alimentação", ["Normal / Atualizado", "Solicitar Saldo"], index=status_sol_idx)

                        tipo_va_opts = ["Já Usuário", "Novo Usuário"]
                        tipo_va_atual = dados[20] if len(dados) > 20 and dados[20] in tipo_va_opts else "Já Usuário"
                        tipo_va_idx = tipo_va_opts.index(tipo_va_atual)
                        tipo_usuario_va_e = s5.selectbox("Tipo de Usuário (Alimentação)", tipo_va_opts, index=tipo_va_idx)

                        if st.button("💾 Salvar Todas as Alterações"):
                            cpf_salvar = formatar_cpf(cpf_e)
                            cnpj_salvar = formatar_cnpj(cnpj_e)
                            dt_dem_salvar = str(data_demissao_e) if status_colab_e == "Demitido" and data_demissao_e else None

                            registrar_historico(matricula_sel, "Alteração de Cargo / Função", dados[5], cargo_e)
                            registrar_historico(matricula_sel, "Alteração de Filial", filial_atual_nome, filial_e)
                            registrar_historico(matricula_sel, "Alteração de Status", status_atual_colab, status_colab_e)
                            registrar_historico(matricula_sel, "Status Cartão Alimentação", status_sol_atual, status_sol_va_e)

                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                UPDATE colaboradores
                                SET matricula = ?, nome = ?, cpf = ?, rg = ?, funcao = ?, cnpj_empresa = ?,
                                    filial_id = ?, data_nascimento = ?, data_contratacao = ?, data_retorno_folga = ?,
                                    intervalo_folga_dias = ?, proxima_folga = ?, motivo_retorno = ?, he_50 = ?, he_100 = ?,
                                    saldo_cartao_alimentacao = ?, status_solicitacao_va = ?, tipo_usuario_va = ?, 
                                    status_colaborador = ?, data_demissao = ?
                                WHERE matricula = ?
                            ''', (
                                mat_e, nome_e, cpf_salvar, rg_e, cargo_e, cnpj_salvar,
                                filiais_nome_para_id[filial_e], str(dt_nasc_e), str(data_contratacao_e),
                                str(data_retorno_folga_e), intervalo_folga_e, str(proxima_folga_calc_e),
                                motivo_retorno_e, he_50_e, he_100_e, saldo_va_e, status_sol_va_e,
                                tipo_usuario_va_e, status_colab_e, dt_dem_salvar, matricula_sel
                            ))
                            conn.commit()
                            conn.close()
                            st.success("Cadastro atualizado com sucesso!")
                            st.rerun()

                    with tab_delete:
                        st.warning(f"⚠️ Você está prestes a excluir **{dados[2]}** (Matrícula {dados[1]}).")
                        confirma = st.checkbox("Confirmo que desejo excluir definitivamente.")
                        if st.button("🗑️ Confirmar Exclusão", type="primary"):
                            if confirma:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("DELETE FROM colaboradores WHERE matricula = ?", (matricula_sel,))
                                conn.commit()
                                conn.close()
                                st.success("Colaborador excluído!")
                                st.rerun()

# ---------------------------------------------------------
# MÓDULO 4: CADASTRO DE FILIAIS
# ---------------------------------------------------------
elif menu == "🏢 Cadastro de Filiais":
    st.title("🏢 Gestão e Cadastro de Filiais")
    
    tab_nova, tab_gerenciar = st.tabs(["➕ Cadastrar Nova Filial", "✏️ Editar / Excluir Filial"])
    
    with tab_nova:
        st.subheader("Adicionar Nova Filial")
        nome_filial = st.text_input("Nome da Filial / Unidade *")
        cnpj_filial = st.text_input("CNPJ da Filial (Opcional)", value="37.608.361/0001-25")
        
        if st.button("Cadastrar Filial"):
            if not nome_filial:
                st.error("Informe o nome da filial.")
            else:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT INTO filiais (nome, cnpj) VALUES (?, ?)", (nome_filial, formatar_cnpj(cnpj_filial)))
                    conn.commit()
                    conn.close()
                    st.success(f"Filial '{nome_filial}' cadastrada com sucesso!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Esta filial já está cadastrada.")

    with tab_gerenciar:
        st.subheader("Gerenciar Filiais Existentes")
        conn = sqlite3.connect(DB_FILE)
        df_filiais = pd.read_sql_query("SELECT id, nome, cnpj FROM filiais ORDER BY nome", conn)
        conn.close()
        
        if df_filiais.empty:
            st.info("Nenhuma filial cadastrada.")
        else:
            opcoes_filiais_gestao = df_filiais['nome'].tolist()
            filial_selecionada_edit = st.selectbox("Selecione a Filial para Editar/Excluir:", options=opcoes_filiais_gestao)
            
            if filial_selecionada_edit:
                filial_row = df_filiais[df_filiais['nome'] == filial_selecionada_edit].iloc[0]
                filial_id_sel = filial_row['id']
                
                novo_nome_filial = st.text_input("Nome da Filial", value=filial_row['nome'])
                novo_cnpj_filial = st.text_input("CNPJ da Filial", value=formatar_cnpj(filial_row['cnpj']) if filial_row['cnpj'] else "37.608.361/0001-25")
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("💾 Salvar Alterações da Filial"):
                        try:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE filiais SET nome = ?, cnpj = ? WHERE id = ?", (novo_nome_filial, formatar_cnpj(novo_cnpj_filial), filial_id_sel))
                            conn.commit()
                            conn.close()
                            st.success("Filial atualizada com sucesso!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Já existe outra filial com este nome.")
                with col_b2:
                    confirma_del_filial = st.checkbox("Confirmo exclusão desta filial")
                    if st.button("🗑️ Excluir Filial", type="primary"):
                        if confirma_del_filial:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("DELETE FROM filiais WHERE id = ?", (filial_id_sel,))
                            conn.commit()
                            conn.close()
                            st.success("Filial excluída com sucesso!")
                            st.rerun()

# ---------------------------------------------------------
# MÓDULO 5: TRANSFERÊNCIA ENTRE FILIAIS
# ---------------------------------------------------------
elif menu == "🔄 Transferência entre Filiais":
    st.title("🔄 Transferência de Colaborador entre Filiais")
    
    conn = sqlite3.connect(DB_FILE)
    df_colab = pd.read_sql_query('''
        SELECT c.matricula, c.nome, f.nome as filial
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        ORDER BY c.nome
    ''', conn)
    conn.close()

    if df_colab.empty:
        st.info("Nenhum colaborador cadastrado para transferência.")
    elif not filiais_nome_para_id or len(filiais_nome_para_id) < 2:
        st.warning("⚠️ É necessário ter pelo menos duas filiais cadastradas para realizar transferências.")
    else:
        opcoes_c = df_colab['matricula'] + " - " + df_colab['nome'] + " (Atual: " + df_colab['filial'].fillna('Nenhuma') + ")"
        colab_sel = st.selectbox("Selecione o Colaborador:", opcoes_c)
        
        if colab_sel:
            matricula_transf = colab_sel.split(" - ")[0]
            filial_atual_str = colab_sel.split("(Atual: ")[1].replace(")", "")
            
            nova_filial_destino = st.selectbox("Selecione a Filial de Destino:", options=list(filiais_nome_para_id.keys()))
            
            if st.button("Confirmar Transferência"):
                if filial_atual_str == nova_filial_destino:
                    st.warning("O colaborador já pertence a esta filial.")
                else:
                    novo_id = filiais_nome_para_id[nova_filial_destino]
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE colaboradores SET filial_id = ? WHERE matricula = ?", (novo_id, matricula_transf))
                    conn.commit()
                    conn.close()
                    
                    registrar_historico(matricula_transf, "Transferência de Filial", filial_atual_str, nova_filial_destino)
                    st.success(f"Colaborador transferido com sucesso para a filial {nova_filial_destino}!")
                    st.rerun()

# ---------------------------------------------------------
# MÓDULO 6: PEDIDO SALDO ALIMENTAÇÃO
# ---------------------------------------------------------
elif menu == "💳 Pedido Saldo Alimentação":
    st.title("💳 Pedido e Gestão de Saldo do Cartão Alimentação")
    st.write("Defina o mês de referência, selecione a filial e edite diretamente os campos **Saldo (R$)** e **Tipo de Usuário** na tabela abaixo.")

    tab_lanc, tab_hist = st.tabs(["📋 Lançamento e Atualização por Filial", "📜 Histórico de Pedidos e Exportação"])

    with tab_lanc:
        conn = sqlite3.connect(DB_FILE)
        df_va_base = pd.read_sql_query('''
            SELECT c.matricula, c.nome, c.cpf, c.cnpj_empresa, f.nome as filial, 
                   c.saldo_cartao_alimentacao, c.tipo_usuario_va
            FROM colaboradores c
            LEFT JOIN filiais f ON c.filial_id = f.id
            WHERE c.status_colaborador = 'Ativo'
            ORDER BY c.nome
        ''', conn)
        conn.close()

        if df_va_base.empty:
            st.info("Nenhum colaborador ativo cadastrado.")
        else:
            st.subheader("1. Seleção de Competência (Mês / Ano)")
            col_m1, col_m2 = st.columns(2)
            meses_disp = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            mes_atual_idx = datetime.now().month - 1
            mes_sel = col_m1.selectbox("Mês de Referência:", meses_disp, index=mes_atual_idx)
            
            anos_disp = [str(y) for y in range(datetime.now().year - 1, datetime.now().year + 3)]
            ano_sel = col_m2.selectbox("Ano de Referência:", anos_disp, index=1)
            competencia_str = f"{mes_sel} / {ano_sel}"

            st.markdown("---")
            st.subheader("2. Seleção de Filial e Edição de Colaboradores")
            
            opcoes_filial_va = sorted(df_va_base['filial'].dropna().unique().tolist())
            filial_va_escolhida = st.selectbox("Selecione a Filial:", opcoes_filial_va)

            df_filial_edit = df_va_base[df_va_base['filial'] == filial_va_escolhida].copy()

            if df_filial_edit.empty:
                st.warning("Nenhum colaborador ativo encontrado nesta filial.")
            else:
                st.write(f"Altere abaixo os valores de **Saldo (R$)** e o **Tipo de Usuário** para os colaboradores de **{filial_va_escolhida}**:")
                
                df_filial_edit['Saldo (R$)'] = df_filial_edit['saldo_cartao_alimentacao'].astype(float)
                df_filial_edit['Tipo de Usuário'] = df_filial_edit['tipo_usuario_va'].fillna('Já Usuário')
                
                tabela_para_edicao = df_filial_edit[['matricula', 'cnpj_empresa', 'nome', 'cpf', 'Saldo (R$)', 'Tipo de Usuário']].copy()
                tabela_para_edicao.columns = ['Matrícula', 'CNPJ', 'Nome do Colaborador', 'CPF', 'Saldo (R$)', 'Tipo de Usuário']
                
                tabela_editada = st.data_editor(
                    tabela_para_edicao,
                    column_config={
                        "Matrícula": st.column_config.TextColumn("Matrícula", disabled=True),
                        "CNPJ": st.column_config.TextColumn("CNPJ", disabled=True),
                        "Nome do Colaborador": st.column_config.TextColumn("Nome do Colaborador", disabled=True),
                        "CPF": st.column_config.TextColumn("CPF", disabled=True),
                        "Saldo (R$)": st.column_config.NumberColumn("Saldo (R$)", min_value=0.0, step=0.5, format="R$ %.2f"),
                        "Tipo de Usuário": st.column_config.SelectboxColumn("Tipo de Usuário", options=["Já Usuário", "Novo Usuário"], required=True)
                    },
                    hide_index=True,
                    use_container_width=True,
                    key=f"editor_va_{filial_va_escolhida}"
                )

                if st.button("💾 Salvar e Registrar Pedido para esta Filial"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    
                    c.execute("DELETE FROM historico_pedidos_va WHERE mes_ano = ? AND filial_nome = ?", (competencia_str, filial_va_escolhida))
                    
                    for idx, row in tabela_editada.iterrows():
                        mat_original = row['Matrícula']
                        novo_saldo_val = float(row['Saldo (R$)'])
                        novo_tipo_val = row['Tipo de Usuário']
                        cnpj_val = row['CNPJ']
                        nome_val = row['Nome do Colaborador']
                        cpf_val = row['CPF']
                        
                        c.execute('''
                            UPDATE colaboradores 
                            SET saldo_cartao_alimentacao = ?, tipo_usuario_va = ?
                            WHERE matricula = ?
                        ''', (novo_saldo_val, novo_tipo_val, mat_original))
                        
                        c.execute('''
                            INSERT INTO historico_pedidos_va (mes_ano, filial_nome, matricula, cnpj_empresa, nome, cpf, saldo, tipo_usuario, data_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (competencia_str, filial_va_escolhida, mat_original, cnpj_val, nome_val, cpf_val, novo_saldo_val, novo_tipo_val, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        
                    conn.commit()
                    conn.close()
                    st.success(f"Alterações e pedido da filial {filial_va_escolhida} salvos com sucesso!")
                    st.rerun()

    with tab_hist:
        st.subheader("📜 Histórico de Pedidos de Saldo Alimentação")
        
        conn = sqlite3.connect(DB_FILE)
        df_hist_va = pd.read_sql_query('''
            SELECT id, mes_ano as "Mês/Ano", filial_nome as "Filial", cnpj_empresa as "CNPJ", 
                   nome as "Nome do Colaborador", cpf as "CPF", saldo as "Saldo", tipo_usuario as "Tipo de Usuário", data_registro as "Data Registro"
            FROM historico_pedidos_va
            ORDER BY data_registro DESC
        ''', conn)
        conn.close()

        if df_hist_va.empty:
            st.info("Nenhum pedido registrado no histórico até o momento.")
        else:
            meses_disponiveis_hist = sorted(df_hist_va['Mês/Ano'].dropna().unique().tolist())
            mes_export_sel = st.selectbox("Selecione o Mês/Ano para Exportação/Gerenciamento:", meses_disponiveis_hist)
            
            df_hist_filtrado = df_hist_va[df_hist_va['Mês/Ano'] == mes_export_sel]
            
            st.write(f"Exibindo registros para o período: **{mes_export_sel}** ({len(df_hist_filtrado)} registros)")
            
            tabela_exibicao_hist = df_hist_filtrado[['CNPJ', 'Nome do Colaborador', 'CPF', 'Saldo', 'Tipo de Usuário', 'Filial']].copy()
            st.dataframe(tabela_exibicao_hist, use_container_width=True)

            col_exp_1, col_exp_2 = st.columns(2)
            
            with col_exp_1:
                output_va = io.BytesIO()
                with pd.ExcelWriter(output_va, engine='openpyxl') as writer:
                    tabela_exibicao_hist.to_excel(writer, index=False, sheet_name='Pedido VA')
                excel_va_data = output_va.getvalue()

                st.download_button(
                    label=f"📥 Baixar Relatório do Mês ({mes_export_sel}) em Excel",
                    data=excel_va_data,
                    file_name=f"pedido_va_{mes_export_sel.replace('/', '_').strip()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col_exp_2:
                if st.button(f"🗑️ Excluir Histórico do Mês ({mes_export_sel})", type="primary"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("DELETE FROM historico_pedidos_va WHERE mes_ano = ?", (mes_export_sel,))
                    conn.commit()
                    conn.close()
                    st.success(f"Histórico do período {mes_export_sel} excluído com sucesso!")
                    st.rerun()

# ---------------------------------------------------------
# MÓDULO 7: IMPORTAR EXCEL POR FILIAL
# ---------------------------------------------------------
elif menu == "📥 Importar Excel por Filial":
    st.title("📥 Importar Colaboradores via Excel por Filial")
    st.write("Faça o upload de uma planilha Excel (`.xlsx`) contendo os dados dos colaboradores para uma filial específica.")
    
    if not filiais_nome_para_id:
        st.warning("⚠️ Cadastre pelo menos uma filial antes de importar planilhas.")
    else:
        filial_import_nome = st.selectbox("Selecione a Filial de Destino da Importação:", options=list(filiais_nome_para_id.keys()))
        
        uploaded_file = st.file_uploader("Selecione o arquivo Excel", type=["xlsx", "xls"])
        
        if uploaded_file is not None:
            try:
                df_import = pd.read_excel(uploaded_file)
                st.write("Prévia dos dados encontrados no arquivo:")
                st.dataframe(df_import.head(), use_container_width=True)
                
                if st.button("Processar e Importar Dados"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    filial_id_val = filiais_nome_para_id[filial_import_nome]
                    
                    importados = 0
                    erros = 0
                    
                    for _, row in df_import.iterrows():
                        try:
                            mat = str(row.get('matricula', row.get('Matrícula', '')))
                            nom = str(row.get('nome', row.get('Nome', '')))
                            if not mat or mat == 'nan' or not nom or nom == 'nan':
                                continue
                                
                            c.execute('''
                                INSERT OR IGNORE INTO colaboradores (
                                    matricula, nome, funcao, filial_id, status_aso, cnpj_empresa, status_colaborador
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                mat, nom, 
                                str(row.get('funcao', row.get('Cargo', 'Não Informado'))),
                                filial_id_val, 'Pendente', '37.608.361/0001-25', 'Ativo'
                            ))
                            if c.rowcount > 0:
                                importados += 1
                            else:
                                erros += 1
                        except Exception:
                            erros += 1
                            
                    conn.commit()
                    conn.close()
                    st.success(f"Importação concluída! {importados} registros inseridos com sucesso ({erros} ignorados/duplicados).")
            except Exception as e:
                st.error(f"Erro ao ler o arquivo Excel: {e}")

# ---------------------------------------------------------
# MÓDULO 8: EXPORTAR DADOS
# ---------------------------------------------------------
elif menu == "📤 Exportar Dados":
    st.title("📤 Exportar Dados do Sistema")
    st.write("Baixe as informações completas dos colaboradores e do painel para formato Excel.")
    
    conn = sqlite3.connect(DB_FILE)
    df_export = pd.read_sql_query('''
        SELECT c.matricula as "Matrícula", c.nome as "Nome", c.funcao as "Cargo / Função", 
               c.cpf as "CPF", c.rg as "RG", c.cnpj_empresa as "CNPJ Empresa",
               f.nome as "Filial", c.data_nascimento as "Data Nascimento", 
               c.data_contratacao as "Data Contratação", c.data_retorno_folga as "Data Retorno",
               c.intervalo_folga_dias as "Intervalo Dias", c.proxima_folga as "Próxima Previsão",
               c.he_50 as "HE 50%", c.he_100 as "HE 100%", c.saldo_cartao_alimentacao as "Saldo VA",
               c.status_aso as "Status ASO", c.status_solicitacao_va as "Status Cartão",
               c.status_colaborador as "Status", c.data_demissao as "Data Demissão"
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
    ''', conn)
    conn.close()

    if df_export.empty:
        st.info("Não há dados cadastrados para exportação.")
    else:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Colaboradores')
        processed_data = output.getvalue()

        st.download_button(
            label="📥 Baixar Planilha Geral de Colaboradores (Excel)",
            data=processed_data,
            file_name=f"relatorio_rh_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ---------------------------------------------------------
# MÓDULO 9: HISTÓRICO DE ALTERAÇÕES
# ---------------------------------------------------------
elif menu == "📜 Histórico de Alterações":
    st.title("📜 Histórico Geral de Alterações")
    st.write("Acompanhe todas as mudanças de cargo/função, transferências de filial e alterações de status efetuadas no sistema.")

    conn = sqlite3.connect(DB_FILE)
    df_hist = pd.read_sql_query('''
        SELECT h.data_registro as "Data / Hora", c.nome as "Colaborador", h.colaborador_matricula as "Matrícula",
               h.tipo_alteracao as "Tipo de Alteração", h.valor_antigo as "De (Antigo)", h.valor_novo as "Para (Novo)"
        FROM historico_colaboradores h
        LEFT JOIN colaboradores c ON h.colaborador_matricula = c.matricula
        ORDER BY h.data_registro DESC
    ''', conn)
    conn.close()

    if df_hist.empty:
        st.info("Nenhum histórico registrado até o momento.")
    else:
        filtro_mat = st.multiselect("Filtrar por Colaborador:", options=df_hist['Colaborador'].dropna().unique())
        df_h_filtered = df_hist.copy()
        if filtro_mat:
            df_h_filtered = df_h_filtered[df_h_filtered['Colaborador'].isin(filtro_mat)]
        
        st.dataframe(df_h_filtered, use_container_width=True)
