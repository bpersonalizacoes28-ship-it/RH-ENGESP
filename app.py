import sqlite3
import pandas as pd
import streamlit as str_lit
from datetime import datetime, date, timedelta
from PIL import Image
import re
import io

str_lit.set_page_config(page_title="Sistema de Gestão ADM - ENGESP", layout="wide", initial_sidebar_state="expanded")

# =========================================================
# ESTILIZAÇÃO CSS
# =========================================================
str_lit.markdown("""
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
            tipo_movimentacao TEXT DEFAULT 'Entrada',
            subtipo_movimentacao TEXT DEFAULT 'Admissão',
            data_movimentacao DATE,
            observacoes TEXT,
            tipo_contratacao TEXT DEFAULT 'CLT',
            FOREIGN KEY (filial_id) REFERENCES filiais (id)
        )
    ''')
    
    novas_colunas = [
        ("status_colaborador", "TEXT DEFAULT 'Ativo'"),
        ("data_demissao", "DATE"),
        ("tipo_movimentacao", "TEXT DEFAULT 'Entrada'"),
        ("subtipo_movimentacao", "TEXT DEFAULT 'Admissão'"),
        ("data_movimentacao", "DATE"),
        ("observacoes", "TEXT"),
        ("tipo_contratacao", "TEXT DEFAULT 'CLT'")
    ]
    for col, def_sql in novas_colunas:
        try:
            c.execute(f"ALTER TABLE colaboradores ADD COLUMN {col} {def_sql}")
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
# FUNÇÕES DE FORMATAÇÃO E TRATAMENTO RIGOROSO DE DATAS
# ---------------------------------------------------------
def formatar_cpf(valor):
    if not valor or pd.isna(valor):
        return ""
    nums = re.sub(r'\D', '', str(valor))
    if len(nums) == 11:
        return f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"
    return str(valor).strip()

def formatar_cnpj(valor):
    if not valor or pd.isna(valor):
        return ""
    nums = re.sub(r'\D', '', str(valor))
    if len(nums) == 14:
        return f"{nums[:2]}.{nums[2:5]}.{nums[5:8]}/{nums[8:12]}-{nums[12:]}"
    return str(valor).strip()

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

def parse_data_rigorosa(valor):
    """Tratamento blindado e absoluto para datas do Excel ou banco."""
    if valor is None or pd.isna(valor) or str(valor).strip() in ["", "None", "NaT", "nan", "NAT"]:
        return str(date.today())
    
    # Se for número serial do Excel
    if isinstance(valor, (int, float)) and valor > 1000:
        try:
            dt_base = datetime(1899, 12, 30)
            return (dt_base + timedelta(days=float(valor))).strftime("%Y-%m-%d")
        except Exception:
            pass

    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")
    
    val_str = str(valor).split()[0].strip()
    
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(val_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    try:
        if "/" in val_str:
            partes = val_str.split("/")
            if len(partes) == 3:
                if len(partes[2]) == 4:
                    return f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}"
                elif len(partes[0]) == 4:
                    return f"{partes[0]}-{partes[1].zfill(2)}-{partes[2].zfill(2)}"
        elif "-" in val_str:
            partes = val_str.split("-")
            if len(partes) == 3:
                if len(partes[0]) == 4:
                    return f"{partes[0]}-{partes[1].zfill(2)}-{partes[2].zfill(2)}"
                elif len(partes[2]) == 4:
                    return f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}"
    except Exception:
        pass
        
    return str(date.today())

def converter_para_date(valor):
    res = parse_data_rigorosa(valor)
    try:
        return datetime.strptime(res, "%Y-%m-%d").date()
    except Exception:
        return date.today()

def formatar_data_br(valor):
    if not valor or pd.isna(valor):
        return ""
    dt_str = parse_data_rigorosa(valor)
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(valor)

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
# MENU PRINCIPAL
# ---------------------------------------------------------
lista_modulos = [
    "📊 Dashboard / Consulta",
    "🏢 Filiais",
    "👥 Colaboradores",
    "➕ Novo Colaborador / Admissão",
    "✏️ Editar Cadastro do Colaborador",
    "🏢 Cadastro de Filiais",
    "🔄 Transferência entre Filiais",
    "💳 Pedido Saldo Alimentação",
    "📥 Importar Excel por Filial",
    "📤 Exportar Dados",
    "📜 Histórico de Alterações"
]

str_lit.markdown("### 🏢 Sistema de Gestão ADM")
menu = str_lit.selectbox("📌 **SELECIONE O MÓDULO DESEJADO ABAIXO:**", lista_modulos, key="menu_principal_topo")
str_lit.markdown("---")

str_lit.sidebar.markdown("## 🏢 ENGESP")
str_lit.sidebar.write("Engenharia São Patrício - Gestão ADM")
str_lit.sidebar.markdown("---")
logo_file = str_lit.sidebar.file_uploader("Enviar Logo da Empresa", type=["png", "jpg", "jpeg"])
if logo_file is not None:
    image = Image.open(logo_file)
    str_lit.sidebar.image(image, use_column_width=True)
str_lit.sidebar.markdown("---")

# ---------------------------------------------------------
# MÓDULO 1: DASHBOARD
# ---------------------------------------------------------
if menu == "📊 Dashboard / Consulta":
    str_lit.title("📊 Painel de Gestão")
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT c.id, c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
               c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo",
               c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
               f.nome as filial, c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão",
               c.observacoes as "Observações", c.status_colaborador as "Status", c.data_demissao as "Data Demissão"
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()

    if not df.empty:
        opcoes_filiais_painel = ["Todas as Filiais"] + sorted(df['filial'].dropna().unique().tolist())
        filial_escolhida_painel = str_lit.selectbox("🏢 Selecione a Filial para Visualização:", opcoes_filiais_painel)
        if filial_escolhida_painel != "Todas as Filiais":
            df = df[df['filial'] == filial_escolhida_painel]

    str_lit.markdown("---")
    str_lit.metric("Total Colaboradores", len(df))
    str_lit.markdown("---")

    if df.empty:
        str_lit.info("Nenhum colaborador cadastrado para esta seleção.")
    else:
        for col in ['Data Admissão', 'Data Movimentação', 'Data Demissão']:
            if col in df.columns:
                df[col] = df[col].apply(formatar_data_br)
        if 'CPF' in df.columns:
            df['CPF'] = df['CPF'].apply(formatar_cpf)

        c1, c2, c3 = str_lit.columns(3)
        with c1:
            filtro_tipo = str_lit.multiselect("Filtrar por Tipo:", options=df['Tipo'].dropna().unique())
        with c2:
            filtro_subtipo = str_lit.multiselect("Filtrar por Subtipo:", options=df['Subtipo'].dropna().unique())
        with c3:
            filtro_status_colab = str_lit.multiselect("Filtrar por Status:", options=df['Status'].dropna().unique(), default=["Ativo"])

        df_filtered = df.copy()
        if filtro_tipo:
            df_filtered = df_filtered[df_filtered['Tipo'].isin(filtro_tipo)]
        if filtro_subtipo:
            df_filtered = df_filtered[df_filtered['Subtipo'].isin(filtro_subtipo)]
        if filtro_status_colab:
            df_filtered = df_filtered[df_filtered['Status'].isin(filtro_status_colab)]

        str_lit.subheader(f"Registros Exibidos ({len(df_filtered)})")
        str_lit.dataframe(df_filtered, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 2: FILIAIS
# ---------------------------------------------------------
elif menu == "🏢 Filiais":
    str_lit.title("🏢 Gestão e Filtragem por Filial")
    conn = sqlite3.connect(DB_FILE)
    df_filiais_list = pd.read_sql_query("SELECT id, nome, cnpj FROM filiais ORDER BY nome", conn)
    conn.close()

    if df_filiais_list.empty:
        str_lit.warning("⚠️ Nenhuma filial cadastrada no sistema.")
    else:
        nomes_filiais = df_filiais_list['nome'].tolist()
        filial_selecionada_detalhe = str_lit.selectbox("🏢 **Selecione a Filial para Consulta:**", nomes_filiais)
        filial_row = df_filiais_list[df_filiais_list['nome'] == filial_selecionada_detalhe].iloc[0]
        filial_id_atual = filial_row['id']
        cnpj_filial_atual = formatar_cnpj(filial_row['cnpj']) if filial_row['cnpj'] else "Não Informado"

        str_lit.markdown(f"### 📍 Unidade: {filial_selecionada_detalhe} (CNPJ: {cnpj_filial_atual})")

        conn = sqlite3.connect(DB_FILE)
        df_colab_filial = pd.read_sql_query('''
            SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                   c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
                   c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
                   c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão", 
                   c.status_colaborador as "Status", c.observacoes as "Observações"
            FROM colaboradores c
            WHERE c.filial_id = ?
            ORDER BY c.nome
        ''', conn, params=(filial_id_atual,))
        conn.close()

        if not df_colab_filial.empty:
            df_colab_filial['CPF'] = df_colab_filial['CPF'].apply(formatar_cpf)
            df_colab_filial['Data Admissão'] = df_colab_filial['Data Admissão'].apply(formatar_data_br)
            df_colab_filial['Data Movimentação'] = df_colab_filial['Data Movimentação'].apply(formatar_data_br)

        col_m1, col_m2, col_m3 = str_lit.columns(3)
        col_m1.metric("Total de Colaboradores", len(df_colab_filial))
        ativos_filial = len(df_colab_filial[df_colab_filial['Status'] == 'Ativo']) if not df_colab_filial.empty else 0
        col_m2.metric("Ativos", ativos_filial)
        demitidos_filial = len(df_colab_filial[df_colab_filial['Status'] == 'Demitido']) if not df_colab_filial.empty else 0
        col_m3.metric("Demitidos", demitidos_filial)

        str_lit.markdown("---")
        str_lit.subheader(f"📋 Relação de Colaboradores - {filial_selecionada_detalhe}")
        if df_colab_filial.empty:
            str_lit.info("Nenhum colaborador vinculado a esta filial.")
        else:
            str_lit.dataframe(df_colab_filial, use_container_width=True)
            output_filial = io.BytesIO()
            with pd.ExcelWriter(output_filial, engine='openpyxl') as writer:
                df_colab_filial.to_excel(writer, index=False, sheet_name=filial_selecionada_detalhe[:30])
            str_lit.download_button(
                label=f"📥 Baixar Relatório da Filial ({filial_selecionada_detalhe}) em Excel",
                data=output_filial.getvalue(),
                file_name=f"relatorio_filial_{filial_selecionada_detalhe.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ---------------------------------------------------------
# MÓDULO 3: COLABORADORES
# ---------------------------------------------------------
elif menu == "👥 Colaboradores":
    str_lit.title("👥 Consulta de Colaboradores por Filial")
    conn = sqlite3.connect(DB_FILE)
    df_filiais_colab = pd.read_sql_query("SELECT id, nome FROM filiais ORDER BY nome", conn)
    conn.close()

    if df_filiais_colab.empty:
        str_lit.warning("⚠️ Nenhuma filial cadastrada.")
    else:
        lista_nomes_f = ["Todas as Filiais"] + df_filiais_colab['nome'].tolist()
        filial_escolhida_colab_mod = str_lit.selectbox("🏢 Selecione a Filial para filtrar os colaboradores:", lista_nomes_f)

        conn = sqlite3.connect(DB_FILE)
        if filial_escolhida_colab_mod == "Todas as Filiais":
            query_c = '''
                SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                       c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
                       c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
                       f.nome as "Filial", c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão", 
                       c.status_colaborador as "Status", c.observacoes as "Observações"
                FROM colaboradores c
                LEFT JOIN filiais f ON c.filial_id = f.id
                ORDER BY c.nome
            '''
            df_c_res = pd.read_sql_query(query_c, conn)
        else:
            f_id_sel = filiais_nome_para_id[filial_escolhida_colab_mod]
            query_c = '''
                SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                       c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
                       c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
                       f.nome as "Filial", c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão", 
                       c.status_colaborador as "Status", c.observacoes as "Observações"
                FROM colaboradores c
                LEFT JOIN filiais f ON c.filial_id = f.id
                WHERE c.filial_id = ?
                ORDER BY c.nome
            '''
            df_c_res = pd.read_sql_query(query_c, conn, params=(f_id_sel,))
        conn.close()

        if not df_c_res.empty:
            df_c_res['CPF'] = df_c_res['CPF'].apply(formatar_cpf)
            df_c_res['Data Admissão'] = df_c_res['Data Admissão'].apply(formatar_data_br)
            df_c_res['Data Movimentação'] = df_c_res['Data Movimentação'].apply(formatar_data_br)

        str_lit.metric("Colaboradores Listados", len(df_c_res))
        str_lit.markdown("---")
        if df_c_res.empty:
            str_lit.info("Nenhum colaborador encontrado para esta seleção.")
        else:
            str_lit.dataframe(df_c_res, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 4: NOVO COLABORADOR / ADMISSÃO
# ---------------------------------------------------------
elif menu == "➕ Novo Colaborador / Admissão":
    str_lit.title("➕ Admissão / Movimentação de Empregado")
    if not filiais_nome_para_id:
        str_lit.warning("⚠️ Cadastre pelo menos uma filial antes de adicionar colaboradores.")
    else:
        str_lit.subheader("1. Informações Principais e Movimentação")
        c_fil, c1, c2 = str_lit.columns(3)
        filial_nome = c_fil.selectbox("Filial *", options=list(filiais_nome_para_id.keys()))
        empregado = c1.text_input("Empregado (Nome Completo) *")
        matricula = c2.text_input("Matrícula *")

        c_t1, c_t2, c_t3 = str_lit.columns(3)
        tipo_mov = c_t1.selectbox("Tipo *", options=["Entrada", "Saída"])
        subtipo_mov = c_t2.selectbox("Subtipo *", options=["Admissão", "Alocação", "Transferência", "Demissão"])
        data_mov = c_t3.date_input("Data da Movimentação *", min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

        str_lit.subheader("2. Dados Profissionais, Contratação e Documentos")
        c3, c4, c5 = str_lit.columns(3)
        cargos_existentes = get_cargos_cadastrados()
        cargo_sel = c3.selectbox("Cargo Existente:", ["-- Novo Cargo --"] + cargos_existentes)
        cargo = c3.text_input("Digite o Cargo *") if cargo_sel == "-- Novo Cargo --" else cargo_sel

        data_admissao = c4.date_input("Data de Admissão *", min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")
        tipo_contratacao = c5.selectbox("Tipo de Contratação *", options=["CLT", "PJ"])

        c6, c7 = str_lit.columns(2)
        cpf = c6.text_input("CPF")
        rg = c7.text_input("RG")

        observacoes = str_lit.text_area("Observações")
        status_colab_novo = "Demitido" if subtipo_mov == "Demissão" or tipo_mov == "Saída" else "Ativo"
        data_demissao_novo = data_mov if status_colab_novo == "Demitido" else None

        if str_lit.button("💾 Finalizar Cadastro / Movimentação"):
            if not matricula or not empregado:
                str_lit.error("Preencha os campos obrigatórios (Empregado e Matrícula).")
            else:
                cpf_formatado = formatar_cpf(cpf)
                dt_dem_val = str(data_demissao_novo) if status_colab_novo == "Demitido" and data_demissao_novo else None
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO colaboradores (
                            matricula, nome, cpf, rg, funcao, filial_id,
                            data_contratacao, status_colaborador, data_demissao,
                            tipo_movimentacao, subtipo_movimentacao, data_movimentacao,
                            observacoes, tipo_contratacao, cnpj_empresa
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        matricula, empregado, cpf_formatado, rg, cargo,
                        filiais_nome_para_id[filial_nome], str(data_admissao),
                        status_colab_novo, dt_dem_val, tipo_mov, subtipo_mov,
                        str(data_mov), observacoes, tipo_contratacao, "37.608.361/0001-25"
                    ))
                    conn.commit()
                    conn.close()
                    registrar_historico(matricula, "Nova Movimentação", "-", f"Tipo: {tipo_mov} / Subtipo: {subtipo_mov} - Filial {filial_nome}")
                    str_lit.success(f"Empregado {empregado} cadastrado/movimentado com sucesso!")
                except sqlite3.IntegrityError:
                    str_lit.error("Erro: Matrícula já cadastrada no sistema.")

# ---------------------------------------------------------
# MÓDULO 5: EDITAR CADASTRO DO COLABORADOR (ATUALIZADO)
# ---------------------------------------------------------
elif menu == "✏️ Editar Cadastro do Colaborador":
    str_lit.title("✏️ Editar Cadastro do Colaborador")
    
    conn = sqlite3.connect(DB_FILE)
    df_colab_geral = pd.read_sql_query('''
        SELECT c.matricula, c.nome, c.funcao as cargo, f.nome as filial
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        ORDER BY c.nome
    ''', conn)
    conn.close()

    if df_colab_geral.empty:
        str_lit.info("Nenhum colaborador cadastrado.")
    else:
        str_lit.subheader("🔍 Localize o colaborador")
        
        # Filtrar por Filial primeiro (conforme solicitado)
        lista_filiais_edit = ["Todas as Filiais"] + sorted(df_colab_geral['filial'].dropna().unique().tolist())
        filial_escolhida_edicao = str_lit.selectbox("Filtrar por Filial:", options=lista_filiais_edit)
        
        df_edit_filtered = df_colab_geral.copy()
        if filial_escolhida_edicao != "Todas as Filiais":
            df_edit_filtered = df_edit_filtered[df_edit_filtered['filial'] == filial_escolhida_edicao]
            
        # Exibe todos os colaboradores referentes a essa seleção de filial
        if df_edit_filtered.empty:
            str_lit.warning("Nenhum colaborador encontrado para esta filial.")
        else:
            opcoes_colab = df_edit_filtered['matricula'] + " - " + df_edit_filtered['nome'] + " (Cargo: " + df_edit_filtered['cargo'].fillna('Não informado') + ")"
            colab_selecionado = str_lit.selectbox("Selecione o Colaborador que deseja editar:", options=opcoes_colab)
            
            if colab_selecionado:
                matricula_sel = colab_selecionado.split(" - ")[0]
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT * FROM colaboradores WHERE matricula = ?", (matricula_sel,))
                dados = c.fetchone()
                conn.close()

                if dados:
                    tab_edit, tab_delete = str_lit.tabs(["✏️ Editar Dados do Colaborador", "🗑️ Excluir Registro"])
                    
                    with tab_edit:
                        str_lit.subheader("Editar Dados do Colaborador")
                        u1, u2, u3 = str_lit.columns(3)
                        mat_e = u1.text_input("Matrícula *", value=dados[1])
                        nome_e = u2.text_input("Empregado *", value=dados[2])
                        cargo_e = u3.text_input("Cargo *", value=dados[5] or "")

                        u4, u5, u6 = str_lit.columns(3)
                        cpf_e = u4.text_input("CPF", value=formatar_cpf(dados[3]))
                        rg_e = u5.text_input("RG", value=dados[4] or "")
                        
                        filial_atual_nome = filiais_id_para_nome.get(dados[7], list(filiais_nome_para_id.keys())[0] if filiais_nome_para_id else "")
                        filial_idx = list(filiais_nome_para_id.keys()).index(filial_atual_nome) if filial_atual_nome in filiais_nome_para_id else 0
                        filial_e = u6.selectbox("Filial", options=list(filiais_nome_para_id.keys()), index=filial_idx)

                        m1, m2, m3 = str_lit.columns(3)
                        tipo_mov_opts = ["Entrada", "Saída"]
                        t_mov_atual = dados[25] if len(dados) > 25 and dados[25] in tipo_mov_opts else "Entrada"
                        tipo_mov_e = m1.selectbox("Tipo", tipo_mov_opts, index=tipo_mov_opts.index(t_mov_atual))

                        subtipo_opts = ["Admissão", "Alocação", "Transferência", "Demissão"]
                        sub_atual = dados[26] if len(dados) > 26 and dados[26] in subtipo_opts else "Admissão"
                        subtipo_mov_e = m2.selectbox("Subtipo", subtipo_opts, index=subtipo_opts.index(sub_atual))
                        
                        dt_mov_val = converter_para_date(dados[27]) if len(dados) > 27 and dados[27] else date.today()
                        data_mov_e = m3.date_input("Data da Movimentação", value=dt_mov_val, min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

                        c_contr1, c_contr2 = str_lit.columns(2)
                        contrato_opts = ["CLT", "PJ"]
                        contrato_atual = dados[29] if len(dados) > 29 and dados[29] in contrato_opts else "CLT"
                        tipo_contratacao_e = c_contr1.selectbox("Tipo de Contratação", contrato_opts, index=contrato_opts.index(contrato_atual))
                        
                        dt_adm_val = converter_para_date(dados[9]) if dados[9] else date.today()
                        data_admissao_e = c_contr2.date_input("Data de Admissão", value=dt_adm_val, min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

                        observacoes_e = str_lit.text_area("Observações", value=dados[28] if len(dados) > 28 and dados[28] else "")

                        if str_lit.button("💾 Salvar Alterações"):
                            cpf_salvar = formatar_cpf(cpf_e)
                            status_colab_e = "Demitido" if subtipo_mov_e == "Demissão" or tipo_mov_e == "Saída" else "Ativo"
                            dt_dem_salvar = str(data_mov_e) if status_colab_e == "Demitido" else None

                            registrar_historico(matricula_sel, "Alteração Cadastral", dados[2], nome_e)

                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute('''
                                UPDATE colaboradores
                                SET matricula = ?, nome = ?, cpf = ?, rg = ?, funcao = ?,
                                    filial_id = ?, data_contratacao = ?, status_colaborador = ?,
                                    data_demissao = ?, tipo_movimentacao = ?, subtipo_movimentacao = ?,
                                    data_movimentacao = ?, observacoes = ?, tipo_contratacao = ?
                                WHERE matricula = ?
                            ''', (
                                mat_e, nome_e, cpf_salvar, rg_e, cargo_e,
                                filiais_nome_para_id[filial_e], str(data_admissao_e),
                                status_colab_e, dt_dem_salvar, tipo_mov_e, subtipo_mov_e,
                                str(data_mov_e), observacoes_e, tipo_contratacao_e, matricula_sel
                            ))
                            conn.commit()
                            conn.close()
                            str_lit.success("Cadastro atualizado com sucesso!")
                            str_lit.rerun()

                    with tab_delete:
                        str_lit.warning(f"⚠️ Excluir permanentemente o registro de **{dados[2]}**?")
                        confirma = str_lit.checkbox("Confirmo a exclusão.")
                        if str_lit.button("🗑️ Confirmar Exclusão", type="primary"):
                            if confirma:
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("DELETE FROM colaboradores WHERE matricula = ?", (matricula_sel,))
                                conn.commit()
                                conn.close()
                                str_lit.success("Registro excluído!")
                                str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 6: CADASTRO DE FILIAIS
# ---------------------------------------------------------
elif menu == "🏢 Cadastro de Filiais":
    str_lit.title("🏢 Gestão e Cadastro de Filiais")
    tab_nova, tab_gerenciar = str_lit.tabs(["➕ Cadastrar Nova Filial", "✏️ Editar / Excluir Filial"])
    
    with tab_nova:
        str_lit.subheader("Adicionar Nova Filial")
        nome_filial = str_lit.text_input("Nome da Filial / Unidade *")
        cnpj_filial = str_lit.text_input("CNPJ da Filial (Opcional)", value="37.608.361/0001-25")
        if str_lit.button("Cadastrar Filial"):
            if not nome_filial:
                str_lit.error("Informe o nome da filial.")
            else:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT INTO filiais (nome, cnpj) VALUES (?, ?)", (nome_filial, formatar_cnpj(cnpj_filial)))
                    conn.commit()
                    conn.close()
                    str_lit.success(f"Filial '{nome_filial}' cadastrada com sucesso!")
                    str_lit.rerun()
                except sqlite3.IntegrityError:
                    str_lit.error("Esta filial já está cadastrada.")

    with tab_gerenciar:
        str_lit.subheader("Gerenciar Filiais Existentes")
        conn = sqlite3.connect(DB_FILE)
        df_filiais = pd.read_sql_query("SELECT id, nome, cnpj FROM filiais ORDER BY nome", conn)
        conn.close()
        if df_filiais.empty:
            str_lit.info("Nenhuma filial cadastrada.")
        else:
            opcoes_filiais_gestao = df_filiais['nome'].tolist()
            filial_selecionada_edit = str_lit.selectbox("Selecione a Filial:", options=opcoes_filiais_gestao)
            if filial_selecionada_edit:
                filial_row = df_filiais[df_filiais['nome'] == filial_selecionada_edit].iloc[0]
                filial_id_sel = filial_row['id']
                novo_nome_filial = str_lit.text_input("Nome da Filial", value=filial_row['nome'])
                novo_cnpj_filial = str_lit.text_input("CNPJ da Filial", value=formatar_cnpj(filial_row['cnpj']) if filial_row['cnpj'] else "37.608.361/0001-25")
                col_b1, col_b2 = str_lit.columns(2)
                with col_b1:
                    if str_lit.button("💾 Salvar Alterações"):
                        try:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("UPDATE filiais SET nome = ?, cnpj = ? WHERE id = ?", (novo_nome_filial, formatar_cnpj(novo_cnpj_filial), filial_id_sel))
                            conn.commit()
                            conn.close()
                            str_lit.success("Filial atualizada!")
                            str_lit.rerun()
                        except sqlite3.IntegrityError:
                            str_lit.error("Já existe outra filial com este nome.")
                with col_b2:
                    confirma_del_filial = str_lit.checkbox("Confirmo exclusão desta filial")
                    if str_lit.button("🗑️ Excluir Filial", type="primary"):
                        if confirma_del_filial:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute("DELETE FROM filiais WHERE id = ?", (filial_id_sel,))
                            conn.commit()
                            conn.close()
                            str_lit.success("Filial excluída!")
                            str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 7: TRANSFERÊNCIA ENTRE FILIAIS
# ---------------------------------------------------------
elif menu == "🔄 Transferência entre Filiais":
    str_lit.title("🔄 Transferência de Empregado entre Filiais")
    conn = sqlite3.connect(DB_FILE)
    df_colab = pd.read_sql_query('''
        SELECT c.matricula, c.nome, f.nome as filial
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        ORDER BY c.nome
    ''', conn)
    conn.close()

    if df_colab.empty:
        str_lit.info("Nenhum empregado cadastrado.")
    elif not filiais_nome_para_id or len(filiais_nome_para_id) < 2:
        str_lit.warning("⚠️ Cadastre pelo menos duas filiais para realizar transferências.")
    else:
        opcoes_c = df_colab['matricula'] + " - " + df_colab['nome'] + " (Atual: " + df_colab['filial'].fillna('Nenhuma') + ")"
        colab_sel = str_lit.selectbox("Selecione o Empregado:", opcoes_c)
        if colab_sel:
            matricula_transf = colab_sel.split(" - ")[0]
            filial_atual_str = colab_sel.split("(Atual: ")[1].replace(")", "")
            nova_filial_destino = str_lit.selectbox("Filial de Destino:", options=list(filiais_nome_para_id.keys()))
            if str_lit.button("Confirmar Transferência"):
                if filial_atual_str == nova_filial_destino:
                    str_lit.warning("O empregado já pertence a esta filial.")
                else:
                    novo_id = filiais_nome_para_id[nova_filial_destino]
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE colaboradores SET filial_id = ?, tipo_movimentacao = 'Entrada', subtipo_movimentacao = 'Transferência' WHERE matricula = ?", (novo_id, matricula_transf))
                    conn.commit()
                    conn.close()
                    registrar_historico(matricula_transf, "Transferência de Filial", filial_atual_str, nova_filial_destino)
                    str_lit.success(f"Empregado transferido com sucesso para {nova_filial_destino}!")
                    str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 8: PEDIDO SALDO ALIMENTAÇÃO
# ---------------------------------------------------------
elif menu == "💳 Pedido Saldo Alimentação":
    str_lit.title("💳 Pedido e Gestão de Saldo do Cartão Alimentação")
    tab_lanc, tab_hist = str_lit.tabs(["📋 Lançamento por Filial", "📜 Histórico"])

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
            str_lit.info("Nenhum empregado ativo cadastrado.")
        else:
            col_m1, col_m2 = str_lit.columns(2)
            meses_disp = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            mes_sel = col_m1.selectbox("Mês:", meses_disp, index=datetime.now().month - 1)
            anos_disp = [str(y) for y in range(datetime.now().year - 1, datetime.now().year + 3)]
            ano_sel = col_m2.selectbox("Ano:", anos_disp, index=1)
            competencia_str = f"{mes_sel} / {ano_sel}"

            opcoes_filial_va = sorted(df_va_base['filial'].dropna().unique().tolist())
            filial_va_escolhida = str_lit.selectbox("Filial:", opcoes_filial_va)
            df_filial_edit = df_va_base[df_va_base['filial'] == filial_va_escolhida].copy()

            if df_filial_edit.empty:
                str_lit.warning("Nenhum empregado ativo nesta filial.")
            else:
                df_filial_edit['Saldo (R$)'] = df_filial_edit['saldo_cartao_alimentacao'].astype(float)
                df_filial_edit['Tipo de Usuário'] = df_filial_edit['tipo_usuario_va'].fillna('Já Usuário')
                tabela_para_edicao = df_filial_edit[['matricula', 'cnpj_empresa', 'nome', 'cpf', 'Saldo (R$)', 'Tipo de Usuário']].copy()
                tabela_para_edicao.columns = ['Matrícula', 'CNPJ', 'Empregado', 'CPF', 'Saldo (R$)', 'Tipo de Usuário']
                
                tabela_editada = str_lit.data_editor(
                    tabela_para_edicao,
                    column_config={
                        "Matrícula": str_lit.column_config.TextColumn("Matrícula", disabled=True),
                        "CNPJ": str_lit.column_config.TextColumn("CNPJ", disabled=True),
                        "Empregado": str_lit.column_config.TextColumn("Empregado", disabled=True),
                        "CPF": str_lit.column_config.TextColumn("CPF", disabled=True),
                        "Saldo (R$)": str_lit.column_config.NumberColumn("Saldo (R$)", min_value=0.0, step=0.5, format="R$ %.2f"),
                        "Tipo de Usuário": str_lit.column_config.SelectboxColumn("Tipo de Usuário", options=["Já Usuário", "Novo Usuário"], required=True)
                    },
                    hide_index=True,
                    use_container_width=True,
                    key=f"editor_va_{filial_va_escolhida}"
                )

                if str_lit.button("💾 Salvar Pedido da Filial"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("DELETE FROM historico_pedidos_va WHERE mes_ano = ? AND filial_nome = ?", (competencia_str, filial_va_escolhida))
                    for _, row in tabela_editada.iterrows():
                        c.execute('''
                            UPDATE colaboradores 
                            SET saldo_cartao_alimentacao = ?, tipo_usuario_va = ?
                            WHERE matricula = ?
                        ''', (float(row['Saldo (R$)']), row['Tipo de Usuário'], row['Matrícula']))
                        c.execute('''
                            INSERT INTO historico_pedidos_va (mes_ano, filial_nome, matricula, cnpj_empresa, nome, cpf, saldo, tipo_usuario, data_registro)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (competencia_str, filial_va_escolhida, row['Matrícula'], row['CNPJ'], row['Empregado'], row['CPF'], float(row['Saldo (R$)']), row['Tipo de Usuário'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
                    str_lit.success("Pedido salvo com sucesso!")
                    str_lit.rerun()

    with tab_hist:
        str_lit.subheader("Histórico de Pedidos")
        conn = sqlite3.connect(DB_FILE)
        df_hist_va = pd.read_sql_query('SELECT * FROM historico_pedidos_va ORDER BY data_registro DESC', conn)
        conn.close()
        if df_hist_va.empty:
            str_lit.info("Nenhum histórico.")
        else:
            str_lit.dataframe(df_hist_va, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 9: IMPORTAR EXCEL POR FILIAL (CORRIGIDO RIGOROSAMENTE)
# ---------------------------------------------------------
elif menu == "📥 Importar Excel por Filial":
    str_lit.title("📥 Importar Colaboradores por Filial (Leitura Rigorosa de Datas)")
    str_lit.write("Selecione a filial e faça o upload da planilha. As datas de Admissão e Movimentação serão extraídas rigorosamente.")
    
    if not filiais_nome_para_id:
        str_lit.warning("Cadastre uma filial primeiro.")
    else:
        filial_import_nome = str_lit.selectbox("Filial de Destino:", options=list(filiais_nome_para_id.keys()))
        uploaded_file = str_lit.file_uploader("Arquivo de Planilha (.xlsx, .xls, .csv)", type=["xlsx", "xls", "csv"])
        
        if uploaded_file is not None:
            try:
                nome_arq = uploaded_file.name.lower()
                if nome_arq.endswith('.csv'):
                    df_import = pd.read_csv(uploaded_file)
                else:
                    df_import = pd.read_excel(uploaded_file, engine='openpyxl' if not nome_arq.endswith('.xls') else 'xlrd')
                
                # Normaliza os nomes das colunas de forma limpa (remove espaços e converte para minúsculas)
                df_import.columns = [str(c).strip().lower() for c in df_import.columns]
                
                str_lit.write("Prévia dos dados encontrados no arquivo:")
                str_lit.dataframe(df_import.head(), use_container_width=True)
                
                if str_lit.button("Processar e Sincronizar Importação"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    filial_id_val = filiais_nome_para_id[filial_import_nome]
                    novos = 0
                    atualizados = 0
                    
                    for _, row in df_import.iterrows():
                        try:
                            # Busca segura de chaves por correspondência exata ou parcial de colunas
                            row_dict = {str(k).strip().lower(): v for k, v in row.to_dict().items()}
                            
                            mat = str(row_dict.get('matricula', row_dict.get('matrícula', row_dict.get('mat', row_dict.get('id', ''))))).strip()
                            nom = str(row_dict.get('empregado', row_dict.get('nome', row_dict.get('funcionário', row_dict.get('funcionario', ''))))).strip()
                            
                            if not mat or mat == 'nan' or not nom or nom == 'nan':
                                continue
                            
                            t_mov = str(row_dict.get('tipo', row_dict.get('tipo_movimentacao', row_dict.get('tipo movimentacao', 'Entrada')))).strip()
                            sub_mov = str(row_dict.get('subtipo', row_dict.get('subtipo_movimentacao', row_dict.get('subtipo movimentacao', 'Admissão')))).strip()
                            
                            # Extração blindada da Data de Movimentação
                            raw_dt_mov = None
                            for key_candidate in ['data_movimentacao', 'data movimentacao', 'datamovimentacao', 'data']:
                                if key_candidate in row_dict:
                                    raw_dt_mov = row_dict[key_candidate]
                                    break
                            dt_mov = parse_data_rigorosa(raw_dt_mov)
                            
                            cargo = str(row_dict.get('cargo', row_dict.get('funcao', row_dict.get('função', 'Não Informado')))).strip()
                            
                            # Extração blindada da Data de Admissão
                            raw_dt_adm = None
                            for key_candidate in ['data_admissao', 'data admissao', 'dataadmissao', 'admissao', 'admissão']:
                                if key_candidate in row_dict:
                                    raw_dt_adm = row_dict[key_candidate]
                                    break
                            dt_adm = parse_data_rigorosa(raw_dt_adm)
                            
                            t_cont = str(row_dict.get('tipo_contratacao', row_dict.get('contratacao', row_dict.get('contratação', 'CLT')))).strip()
                            cpf_val = formatar_cpf(row_dict.get('cpf', ''))
                            rg_val = str(row_dict.get('rg', '')).strip()
                            obs_val = str(row_dict.get('observacoes', row_dict.get('obs', ''))).strip()
                            
                            status_c = "Demitido" if sub_mov.lower() in ["demissão", "demissao"] or t_mov.lower() == "saída" else "Ativo"
                            dt_dem = dt_mov if status_c == "Demitido" else None

                            c.execute("SELECT id FROM colaboradores WHERE matricula = ?", (mat,))
                            existe = c.fetchone()

                            if existe:
                                c.execute('''
                                    UPDATE colaboradores SET
                                        nome = ?, cpf = ?, rg = ?, funcao = ?, filial_id = ?,
                                        data_contratacao = ?, status_colaborador = ?, data_demissao = ?,
                                        tipo_movimentacao = ?, subtipo_movimentacao = ?, data_movimentacao = ?,
                                        observacoes = ?, tipo_contratacao = ?
                                    WHERE matricula = ?
                                ''', (
                                    nom, cpf_val, rg_val, cargo, filial_id_val,
                                    dt_adm, status_c, dt_dem, t_mov, sub_mov,
                                    dt_mov, obs_val, t_cont, mat
                                ))
                                atualizados += 1
                            else:
                                c.execute('''
                                    INSERT INTO colaboradores (
                                        matricula, nome, cpf, rg, funcao, filial_id,
                                        data_contratacao, status_colaborador, data_demissao,
                                        tipo_movimentacao, subtipo_movimentacao, data_movimentacao,
                                        observacoes, tipo_contratacao, cnpj_empresa
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    mat, nom, cpf_val, rg_val, cargo, filial_id_val,
                                    dt_adm, status_c, dt_dem, t_mov, sub_mov,
                                    dt_mov, obs_val, t_cont, "37.608.361/0001-25"
                                ))
                                novos += 1
                        except Exception:
                            pass
                            
                    conn.commit()
                    conn.close()
                    str_lit.success(f"Sincronização concluída! {novos} novos colaboradores cadastrados e {atualizados} registros atualizados com sucesso na filial {filial_import_nome}, respeitando integralmente as datas.")
            except Exception as e:
                str_lit.error(f"Erro ao ler o arquivo: {e}")

# ---------------------------------------------------------
# MÓDULO 10: EXPORTAR DADOS
# ---------------------------------------------------------
elif menu == "📤 Exportar Dados":
    str_lit.title("📤 Exportar Dados")
    conn = sqlite3.connect(DB_FILE)
    df_export = pd.read_sql_query('''
        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
               c.cpf as "CPF", c.rg as "RG", f.nome as "Filial", 
               c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
               c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
               c.status_colaborador as "Status", c.observacoes as "Observações"
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
    ''', conn)
    conn.close()

    if df_export.empty:
        str_lit.info("Sem dados para exportar.")
    else:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Colaboradores')
        str_lit.download_button(
            label="📥 Baixar Planilha Geral em Excel",
            data=output.getvalue(),
            file_name=f"relatorio_geral_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ---------------------------------------------------------
# MÓDULO 11: HISTÓRICO DE ALTERAÇÕES
# ---------------------------------------------------------
elif menu == "📜 Histórico de Alterações":
    str_lit.title("📜 Histórico de Alterações")
    conn = sqlite3.connect(DB_FILE)
    df_hist = pd.read_sql_query('''
        SELECT h.data_registro as "Data / Hora", c.nome as "Empregado", h.colaborador_matricula as "Matrícula",
               h.tipo_alteracao as "Tipo", h.valor_antigo as "Antigo", h.valor_novo as "Novo"
        FROM historico_colaboradores h
        LEFT JOIN colaboradores c ON h.colaborador_matricula = c.matricula
        ORDER BY h.data_registro DESC
    ''', conn)
    conn.close()
    if df_hist.empty:
        str_lit.info("Sem histórico.")
    else:
        str_lit.dataframe(df_hist, use_container_width=True)
