from datetime import date, datetime, timedelta
import io
import json
import re
import pandas as pd
import sqlite3
import streamlit as str_lit

str_lit.set_page_config(
    page_title="Sistema de Gestão ADM - ENGESP",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# ESTILIZAÇÃO CSS
# =========================================================
str_lit.markdown(
    """
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
""",
    unsafe_allow_html=True,
)

DB_FILE = "gestao_empresa.db"
CNPJ_PADRAO = "37.608.361/0001-25"


# ---------------------------------------------------------
# BANCO DE DADOS - INICIALIZAÇÃO E PERSISTÊNCIA EM TEMPO REAL
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS filiais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            cnpj TEXT
        )
    """)
    c.execute("""
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
            premiacao REAL DEFAULT 0,
            mobilidade REAL DEFAULT 0,
            alimentacao REAL DEFAULT 0,
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
    """)

    novas_colunas = [
        ("status_colaborador", "TEXT DEFAULT 'Ativo'"),
        ("data_demissao", "DATE"),
        ("tipo_movimentacao", "TEXT DEFAULT 'Entrada'"),
        ("subtipo_movimentacao", "TEXT DEFAULT 'Admissão'"),
        ("data_movimentacao", "DATE"),
        ("observacoes", "TEXT"),
        ("tipo_contratacao", "TEXT DEFAULT 'CLT'"),
        ("premiacao", "REAL DEFAULT 0"),
        ("mobilidade", "REAL DEFAULT 0"),
        ("alimentacao", "REAL DEFAULT 0"),
        ("tipo_usuario_va", "TEXT DEFAULT 'Já Usuário'"),
        ("he_50", "REAL DEFAULT 0"),
        ("he_100", "REAL DEFAULT 0"),
    ]
    for col, def_sql in novas_colunas:
        try:
            c.execute(f"ALTER TABLE colaboradores ADD COLUMN {col} {def_sql}")
        except Exception:
            pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS historico_colaboradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_matricula TEXT,
            filial_id INTEGER,
            tipo_alteracao TEXT,
            valor_antigo TEXT,
            valor_novo TEXT,
            data_registro DATETIME,
            FOREIGN KEY (colaborador_matricula) REFERENCES colaboradores (matricula),
            FOREIGN KEY (filial_id) REFERENCES filiais (id)
        )
    """)

    try:
        c.execute("ALTER TABLE historico_colaboradores ADD COLUMN filial_id INTEGER")
    except Exception:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS historico_pedidos_va (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_ano TEXT,
            obra TEXT,
            data_geracao DATETIME,
            dados_json TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS folha_ponto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matricula TEXT,
            mes_ano TEXT,
            total_50 REAL DEFAULT 0,
            total_100 REAL DEFAULT 0,
            dados_json TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS importacoes_arquivos (
            filial_id INTEGER PRIMARY KEY,
            nome_arquivo TEXT,
            data_importacao DATETIME,
            arquivo_blob BLOB,
            FOREIGN KEY (filial_id) REFERENCES filiais (id)
        )
    """)

    conn.commit()
    conn.close()


init_db()

c.execute("""
        CREATE TABLE IF NOT EXISTS log_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            usuario TEXT,
            acao TEXT,
            detalhes TEXT
        )
    """)

# ---------------------------------------------------------
# FUNÇÕES DE FORMATAÇÃO E LEITURA DINÂMICA
# ---------------------------------------------------------
def formatar_cpf(valor):
    if not valor or pd.isna(valor):
        return ""
    nums = re.sub(r"\D", "", str(valor))
    if len(nums) == 11:
        return f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"
    return str(valor).strip()


def formatar_cnpj(valor):
    if not valor or pd.isna(valor):
        return CNPJ_PADRAO
    nums = re.sub(r"\D", "", str(valor))
    if len(nums) == 14:
        return f"{nums[:2]}.{nums[2:5]}.{nums[5:8]}/{nums[8:12]}-{nums[12:]}"
    return str(valor).strip() if str(valor).strip() else CNPJ_PADRAO


MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2100, 12, 31)


def registrar_historico(matricula, tipo, antigo, novo):
    if str(antigo).strip() != str(novo).strip():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute("SELECT filial_id FROM colaboradores WHERE matricula = ?", (matricula,))
        res = c.fetchone()
        filial_id_colab = res[0] if res and res[0] is not None else None

        c.execute(
            """
            INSERT INTO historico_colaboradores (colaborador_matricula, filial_id, tipo_alteracao, valor_antigo, valor_novo, data_registro)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                matricula,
                filial_id_colab,
                tipo,
                str(antigo),
                str(novo),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        conn.close()


def parse_data_rigorosa(valor):
    if (
        valor is None
        or pd.isna(valor)
        or str(valor).strip()
        in ["", "None", "NaT", "nan", "NAT", "0", "0.0"]
    ):
        return str(date.today())

    try:
        val_float = float(valor)
        if val_float > 1000:
            dt_base = datetime(1899, 12, 30)
            return (dt_base + timedelta(days=val_float)).strftime("%Y-%m-%d")
    except Exception:
        pass

    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")

    val_str = str(valor).split()[0].strip()

    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(val_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return str(date.today())


def formatar_data_br(valor):
    if not valor or pd.isna(valor):
        return ""
    dt_str = parse_data_rigorosa(valor)
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(valor)


def converter_hora_flexivel(valor):
    if valor is None or pd.isna(valor):
        return 0.0
    val_str = str(valor).strip()
    if not val_str or val_str in ["0", "0.0", "None", "nan"]:
        return 0.0

    if ":" in val_str:
        try:
            partes = val_str.split(":")
            horas = float(partes[0])
            minutos = float(partes[1]) if len(partes) > 1 else 0.0
            return horas + (minutos / 60.0)
        except Exception:
            return 0.0

    val_str = val_str.replace(",", ".")
    try:
        return float(val_str)
    except Exception:
        return 0.0


def obter_feriados_nacionais(ano):
    feriados = {
        date(ano, 1, 1),   
        date(ano, 4, 21),  
        date(ano, 5, 1),   
        date(ano, 9, 7),   
        date(ano, 10, 12), 
        date(ano, 11, 2),  
        date(ano, 11, 15), 
        date(ano, 11, 20), 
        date(ano, 12, 25), 
    }
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes_pascoa = (h + l - 7 * m + 114) // 31
    dia_pascoa = ((h + l - 7 * m + 114) % 31) + 1
    
    data_pascoa = date(ano, mes_pascoa, dia_pascoa)
    feriados.add(data_pascoa - timedelta(days=2))
    feriados.add(data_pascoa + timedelta(days=60))
    return feriados


def get_filiais_dict():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query("SELECT id, nome FROM filiais ORDER BY nome", conn)
    except Exception:
        df = pd.DataFrame(columns=["id", "nome"])
    conn.close()
    return dict(zip(df["nome"], df["id"])), dict(zip(df["id"], df["nome"]))


def get_cargos_cadastrados():
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query(
            "SELECT DISTINCT funcao FROM colaboradores WHERE funcao IS NOT NULL AND funcao != '' ORDER BY funcao",
            conn,
        )
        cargos = df["funcao"].tolist()
    except Exception:
        cargos = []
    conn.close()
    return cargos


filiais_nome_para_id, filiais_id_para_nome = get_filiais_dict()

def registrar_log(acao, detalhes, usuario="Usuário Padrão"):
    """Registra uma ação no log de auditoria do sistema."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        data_hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO log_auditoria (data_hora, usuario, acao, detalhes) VALUES (?, ?, ?, ?)",
            (data_hora_atual, usuario, acao, detalhes)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao registrar log: {e}")

# ---------------------------------------------------------
# MENU PRINCIPAL
# ---------------------------------------------------------
lista_modulos = [
    "📊 Dashboard / Consulta",
    "🏢 Cadastro de Filiais",
    "📥 Importar Colaboradores por Filial",
    "🔄 Transferência entre Filiais",
    "👥 Colaboradores",
    "➕ Novo Colaborador / Admissão",
    "✏️ Editar Cadastro do Colaborador",
    "💳 Pedido Saldo Alimentação",
    "⏱️ Folha de Ponto",
    "📤 Exportar Dados",
    "📜 Histórico de Alterações",
    "🛡️ Auditoria do Sistema",  # <-- ADICIONADO AQUI
]

str_lit.markdown("### 🏢 Sistema de Gestão ADM")
menu = str_lit.selectbox(
    "📌 **SELECIONE O MÓDULO DESEJADO ABAIXO:**",
    lista_modulos,
    key="menu_principal_topo",
)
str_lit.markdown("---")

str_lit.sidebar.markdown("## 🏢 ENGESP")
str_lit.sidebar.write("Engenharia São Patrício - Gestão ADM")
str_lit.sidebar.markdown("---")
str_lit.sidebar.info("💾 **Status:** Todos os dados e atualizações ficam salvos permanentemente em tempo real no banco de dados local.")

# ---------------------------------------------------------
# MÓDULO 1: DASHBOARD / CONSULTA
# ---------------------------------------------------------
if menu == "📊 Dashboard / Consulta":
    str_lit.title("📊 Painel de Gestão")
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT c.id, c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
               c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo",
               c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
               f.nome as filial, c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão",
               c.observacoes as "Observações", c.status_colaborador as "Status", c.data_demissao as "Data Demissão"
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
    """
    try:
        df = pd.read_sql_query(query, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()

    if not df.empty:
        opcoes_filiais_painel = ["Todas as Filiais"] + sorted(
            df["filial"].dropna().unique().tolist()
        )
        filial_escolhida_painel = str_lit.selectbox(
            "🏢 Selecione a Filial para Visualização:", opcoes_filiais_painel
        )
        if filial_escolhida_painel != "Todas as Filiais":
            df = df[df["filial"] == filial_escolhida_painel]

    str_lit.markdown("---")
    str_lit.metric("Total Colaboradores", len(df))
    str_lit.markdown("---")

    if df.empty:
        str_lit.info("Nenhum colaborador cadastrado para esta seleção.")
    else:
        for col in ["Data Admissão", "Data Movimentação", "Data Demissão"]:
            if col in df.columns:
                df[col] = df[col].apply(formatar_data_br)
        if "CPF" in df.columns:
            df["CPF"] = df["CPF"].apply(formatar_cpf)

        c1, c2, c3 = str_lit.columns(3)
        with c1:
            filtro_tipo = str_lit.multiselect(
                "Filtrar por Tipo:", options=df["Tipo"].dropna().unique()
            )
        with c2:
            filtro_subtipo = str_lit.multiselect(
                "Filtrar por Subtipo:", options=df["Subtipo"].dropna().unique()
            )
        with c3:
            filtro_status_colab = str_lit.multiselect(
                "Filtrar por Status:",
                options=df["Status"].dropna().unique(),
                default=["Ativo"],
            )

        df_filtered = df.copy()
        if filtro_tipo:
            df_filtered = df_filtered[df_filtered["Tipo"].isin(filtro_tipo)]
        if filtro_subtipo:
            df_filtered = df_filtered[
                df_filtered["Subtipo"].isin(filtro_subtipo)
            ]
        if filtro_status_colab:
            df_filtered = df_filtered[
                df_filtered["Status"].isin(filtro_status_colab)
            ]

        str_lit.subheader(f"Registros Exibidos ({len(df_filtered)})")
        str_lit.dataframe(df_filtered, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 2: CADASTRO DE FILIAIS
# ---------------------------------------------------------
elif menu == "🏢 Cadastro de Filiais":
    str_lit.title("🏢 Cadastro e Gestão de Filiais")
    
    with str_lit.form("form_nova_filial"):
        str_lit.subheader("Cadastrar Nova Filial")
        nome_f = str_lit.text_input("Nome da Filial / Obra *")
        cnpj_f = str_lit.text_input("CNPJ da Filial", value=CNPJ_PADRAO)
        btn_cad_fil = str_lit.form_submit_button("Cadastrar Filial")

        if btn_cad_fil:
            if not nome_f:
                str_lit.error("O nome da filial é obrigatório.")
            else:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO filiais (nome, cnpj) VALUES (?, ?)",
                        (nome_f, formatar_cnpj(cnpj_f)),
                    )
                    conn.commit()
                    conn.close()
                    
                    registrar_log("CADASTRO", f"Cadastrou a nova filial: {nome_f}")
                    
                    str_lit.success(f"Filial '{nome_f}' cadastrada e salva com sucesso!")
                    str_lit.rerun()
                except sqlite3.IntegrityError:
                    str_lit.error("Erro: Filial já cadastrada.")

    str_lit.markdown("---")
    str_lit.subheader("Filiais Cadastradas e Gerenciamento")
    
    conn = sqlite3.connect(DB_FILE)
    try:
        df_f_cad = pd.read_sql_query("SELECT id, nome, cnpj FROM filiais ORDER BY nome", conn)
    except Exception:
        df_f_cad = pd.DataFrame()
    conn.close()

    if df_f_cad.empty:
        str_lit.info("Nenhuma filial cadastrada.")
    else:
        df_f_cad["cnpj"] = df_f_cad["cnpj"].apply(formatar_cnpj)
        str_lit.dataframe(df_f_cad, use_container_width=True)

        str_lit.markdown("---")
        str_lit.subheader("🗑️ Excluir Filial Cadastrada")
        str_lit.warning("⚠️ **Atenção:** Ao excluir uma filial, todos os colaboradores e arquivos importados vinculados a ela também serão removidos.")

        filiais_dict_del, _ = get_filiais_dict()
        filial_para_deletar = str_lit.selectbox(
            "Selecione a Filial que deseja excluir:",
            options=list(filiais_dict_del.keys()),
            key="select_del_filial"
        )

        if str_lit.button("🗑️ Deletar Filial Selecionada", type="secondary"):
            if filial_para_deletar:
                f_id_del = filiais_dict_del[filial_para_deletar]
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("DELETE FROM colaboradores WHERE filial_id = ?", (f_id_del,))
                c.execute("DELETE FROM importacoes_arquivos WHERE filial_id = ?", (f_id_del,))
                c.execute("DELETE FROM historico_colaboradores WHERE filial_id = ?", (f_id_del,))
                c.execute("DELETE FROM filiais WHERE id = ?", (f_id_del,))
                conn.commit()
                conn.close()
                
                registrar_log("EXCLUSÃO", f"Excluiu a filial: {filial_para_deletar} e seus registros associados.")
                
                str_lit.success(f"Filial '{filial_para_deletar}' excluída com sucesso!")
                str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 3: IMPORTAR COLABORADORES POR FILIAL
# ---------------------------------------------------------
elif menu == "📥 Importar Colaboradores por Filial":
    str_lit.title("📥 Importação Sincronizada e Arquivamento de Planilhas")
    str_lit.info(
        "💡 **Recurso de Arquivamento:** Além de atualizar os colaboradores em tempo real, o sistema "
        "armazena a última planilha importada para cada filial, permitindo o download dela ou a exclusão da lista a qualquer momento."
    )

    f_map_atual, _ = get_filiais_dict()

    if not f_map_atual:
        str_lit.warning("Cadastre uma filial primeiro.")
    else:
        filial_imp = str_lit.selectbox(
            "Selecione a Filial de Destino da Importação:",
            options=list(f_map_atual.keys()),
        )
        
        filial_id_atual = f_map_atual[filial_imp]

        conn = sqlite3.connect(DB_FILE)
        try:
            df_arq_salvo = pd.read_sql_query(
                "SELECT nome_arquivo, data_importacao, arquivo_blob FROM importacoes_arquivos WHERE filial_id = ?",
                conn, params=(filial_id_atual,)
            )
        except Exception:
            df_arq_salvo = pd.DataFrame()
        conn.close()

        if not df_arq_salvo.empty:
            row_arq = df_arq_salvo.iloc[0]
            str_lit.success(f"📂 **Última planilha arquivada para esta filial:** `{row_arq['nome_arquivo']}` (Importada em: {row_arq['data_importacao']})")
            
            col_dl, col_del = str_lit.columns(2)
            with col_dl:
                str_lit.download_button(
                    label=f"📥 Baixar Planilha Atual Arquivada",
                    data=row_arq["arquivo_blob"],
                    file_name=row_arq["nome_arquivo"],
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_arq_filial_{filial_id_atual}"
                )
            with col_del:
                if str_lit.button("🗑️ Apagar Lista e Colaboradores Desta Filial", type="secondary"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    # Apaga os colaboradores cadastrados nessa filial
                    c.execute("DELETE FROM colaboradores WHERE filial_id = ?", (filial_id_atual,))
                    # Apaga o registro da planilha arquivada
                    c.execute("DELETE FROM importacoes_arquivos WHERE filial_id = ?", (filial_id_atual,))
                    conn.commit()
                    conn.close()
                    str_lit.success(f"Todos os colaboradores e a planilha arquivada da filial '{filial_imp}' foram apagados com sucesso!")
                    str_lit.rerun()

            with col_del:
                if str_lit.button("🗑️ Apagar Lista e Colaboradores Desta Filial", type="secondary"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("DELETE FROM colaboradores WHERE filial_id = ?", (filial_id_atual,))
                    c.execute("DELETE FROM importacoes_arquivos WHERE filial_id = ?", (filial_id_atual,))
                    conn.commit()
                    conn.close()
                    
                    registrar_log("EXCLUSÃO", f"Apagou todos os colaboradores e planilha da filial ID: {filial_id_atual}")
                    
                    str_lit.success(f"Todos os colaboradores da filial '{filial_imp}' foram apagados!")
                    str_lit.rerun()
                    
                    registrar_log("IMPORTAÇÃO", f"Importou planilha '{nome_arq}' para a filial '{filial_imp}': {inseridos} novos, {atualizados} atualizados.")

            str_lit.markdown("---")

        arquivo_upload = str_lit.file_uploader(
            "Envie uma nova planilha para atualizar (Excel .xlsx, .xls, .xlsm ou CSV):",
            type=["xlsx", "xls", "xlsm", "csv"],
        )

        if arquivo_upload is not None:
            try:
                nome_arq = arquivo_upload.name
                bytes_arquivo = arquivo_upload.getvalue()
                
                nome_arq_lower = nome_arq.lower()
                if nome_arq_lower.endswith(".csv"):
                    df_imp = pd.read_csv(io.BytesIO(bytes_arquivo))
                else:
                    df_imp = pd.read_excel(io.BytesIO(bytes_arquivo), engine="openpyxl")

                df_imp.columns = [str(col).strip().lower() for col in df_imp.columns]

                str_lit.write(f"Pré-visualização dos dados importados ({len(df_imp)} registros encontrados):")
                str_lit.dataframe(df_imp.head(), use_container_width=True)

                if str_lit.button("🚀 Processar, Arquivar Planilha e Salvar Permanentemente"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    
                    inseridos = 0
                    atualizados = 0
                    
                    f_dict_recarregado, _ = get_filiais_dict()
                    filial_id_destino = f_dict_recarregado.get(filial_imp)

                    for _, r in df_imp.iterrows():
                        mat = str(r.get("matrícula", r.get("matricula", r.get("mat", "")))).strip()
                        nome = str(r.get("nome", r.get("empregado", r.get("funcionário", "")))).strip()
                        
                        if mat and mat.lower() != "nan" and nome and nome.lower() != "nan":
                            cpf_val = formatar_cpf(r.get("cpf", ""))
                            rg_val = str(r.get("rg", "")).strip()
                            cargo_val = str(r.get("cargo", r.get("funcao", ""))).strip()
                            
                            c.execute("SELECT id FROM colaboradores WHERE matricula = ?", (mat,))
                            existe = c.fetchone()
                            
                            if existe:
                                c.execute(
                                    """
                                    UPDATE colaboradores 
                                    SET nome = ?, cpf = ?, rg = ?, funcao = ?, filial_id = ?, cnpj_empresa = ?, 
                                        status_colaborador = 'Ativo', tipo_movimentacao = 'Entrada', 
                                        subtipo_movimentacao = 'Atualização/Alocação', data_movimentacao = ?
                                    WHERE matricula = ?
                                """,
                                    (nome, cpf_val, rg_val, cargo_val, filial_id_destino, CNPJ_PADRAO, str(date.today()), mat)
                                )
                                atualizados += 1
                            else:
                                c.execute(
                                    """
                                    INSERT INTO colaboradores (
                                        matricula, nome, cpf, rg, funcao, cnpj_empresa, 
                                        filial_id, status_colaborador, tipo_contratacao, 
                                        tipo_movimentacao, subtipo_movimentacao, data_movimentacao
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Ativo', 'CLT', 'Entrada', 'Admissão', ?)
                                """,
                                    (
                                        mat,
                                        nome,
                                        cpf_val,
                                        rg_val,
                                        cargo_val,
                                        CNPJ_PADRAO,
                                        filial_id_destino,
                                        str(date.today()),
                                    ),
                                )
                                inseridos += 1

                    c.execute("""
                        INSERT OR REPLACE INTO importacoes_arquivos (filial_id, nome_arquivo, data_importacao, arquivo_blob)
                        VALUES (?, ?, ?, ?)
                    """, (filial_id_destino, nome_arq, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sqlite3.Binary(bytes_arquivo)))

                    conn.commit()
                    conn.close()
                    
                    str_lit.success(
                        f"Importação realizada e planilha arquivada com sucesso! 🟢 Novos cadastrados: {inseridos} | 🔄 Atualizados/Alocados: {atualizados}."
                    )
                    str_lit.rerun()
            except Exception as e:
                str_lit.error(f"Erro ao processar arquivo: {e}")
                
# ---------------------------------------------------------
# MÓDULO 4: TRANSFERÊNCIA ENTRE FILIAIS
# ---------------------------------------------------------
elif menu == "🔄 Transferência entre Filiais":
    str_lit.title("🔄 Transferência de Colaboradores entre Filiais (Múltiplos)")
    
    conn = sqlite3.connect(DB_FILE)
    try:
        df_transf = pd.read_sql_query(
            """
            SELECT c.matricula, c.nome, c.funcao as cargo, c.filial_id, f.nome as filial_nome
            FROM colaboradores c
            LEFT JOIN filiais f ON c.filial_id = f.id
            WHERE c.status_colaborador = 'Ativo'
            ORDER BY c.nome
        """,
            conn,
        )
    except Exception:
        df_transf = pd.DataFrame()
    conn.close()

    if df_transf.empty or filiais_nome_para_id is None:
        str_lit.info("Nenhum colaborador ativo disponível para transferência ou filiais insuficientes.")
    else:
        lista_origens = sorted(df_transf["filial_nome"].dropna().unique().tolist())
        if not lista_origens:
            str_lit.warning("Nenhuma filial de origem encontrada com colaboradores ativos.")
        else:
            filial_origem_sel = str_lit.selectbox("🏢 1. Selecione a Filial de Origem:", options=lista_origens)
            
            df_origem_colab = df_transf[df_transf["filial_nome"] == filial_origem_sel].copy()
            str_lit.write(f"Colaboradores ativos na filial **{filial_origem_sel}**: {len(df_origem_colab)}")
            
            df_origem_colab.insert(0, "Selecionar", False)
            df_tabela_exibicao = df_origem_colab[["Selecionar", "matricula", "nome", "cargo"]].rename(
                columns={"matricula": "Matrícula", "nome": "Nome do Colaborador", "cargo": "Cargo"}
            )
            
            df_selecionados_editor = str_lit.data_editor(
                df_tabela_exibicao,
                column_config={
                    "Selecionar": str_lit.column_config.CheckboxColumn("Selecionar", required=True)
                },
                hide_index=True,
                use_container_width=True,
            )
            
            matriculas_selecionadas = df_selecionados_editor[
                df_selecionados_editor["Selecionar"] == True
            ]["Matrícula"].tolist()
            
            str_lit.markdown("---")
            lista_dest = [f for f in list(filiais_nome_para_id.keys()) if f != filial_origem_sel]
            
            if not lista_dest:
                str_lit.warning("Cadastre mais filiais para poder realizar transferências entre unidades diferentes.")
            else:
                filial_destino = str_lit.selectbox("🏢 2. Selecione a Filial de Destino:", options=lista_dest)
                data_transf = str_lit.date_input(
                    "Data da Transferência",
                    value=date.today(),
                    min_value=MIN_DATE,
                    max_value=MAX_DATE,
                    format="DD/MM/YYYY",
                )
                
                str_lit.info(f"Total de colaboradores selecionados para transferência: **{len(matriculas_selecionadas)}**")
                
                if str_lit.button("🔄 Efetivar e Salvar Transferência", type="primary"):
                    if not matriculas_selecionadas:
                        str_lit.error("Selecione pelo menos um colaborador na tabela acima marcando a caixa 'Selecionar'.")
                    else:
                        nova_filial_id = filiais_nome_para_id[filial_destino]
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        
                        for mat_t in matriculas_selecionadas:
                            c.execute(
                                """
                                UPDATE colaboradores
                                SET filial_id = ?, tipo_movimentacao = 'Entrada', subtipo_movimentacao = 'Transferência', data_movimentacao = ?
                                WHERE matricula = ?
                            """,
                                (nova_filial_id, str(data_transf), mat_t),
                            )
                        conn.commit()
                        conn.close()
                        
                        for mat_t in matriculas_selecionadas:
                            registrar_historico(
                                mat_t,
                                "Transferência de Filial (Lote)",
                                filial_origem_sel,
                                f"Destino: {filial_destino}",
                            )
                            
                        str_lit.success(
                            f"Sucesso! {len(matriculas_selecionadas)} colaborador(es) transferido(s) e salvos permanentemente!"
                        )
                        str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 5: COLABORADORES
# ---------------------------------------------------------
elif menu == "👥 Colaboradores":
    str_lit.title("👥 Gestão de Colaboradores por Filial (Ativos e Demitidos)")
    
    conn = sqlite3.connect(DB_FILE)
    try:
        df_filiais_colab = pd.read_sql_query(
            "SELECT id, nome FROM filiais ORDER BY nome", conn
        )
    except Exception:
        df_filiais_colab = pd.DataFrame()
    conn.close()

    if df_filiais_colab.empty:
        str_lit.warning("⚠️ Nenhuma filial cadastrada.")
    else:
        lista_nomes_f = ["Todas as Filiais"] + df_filiais_colab["nome"].tolist()
        filial_escolhida_colab_mod = str_lit.selectbox(
            "🏢 Selecione a Filial:", lista_nomes_f
        )

        aba_ativos, aba_demitidos = str_lit.tabs(["🟢 Colaboradores Ativos", "🔴 Colaboradores Demitidos"])

        with aba_ativos:
            conn = sqlite3.connect(DB_FILE)
            try:
                if filial_escolhida_colab_mod == "Todas as Filiais":
                    query_c = """
                        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                               c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
                               c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
                               f.nome as "Filial", c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão", 
                               c.status_colaborador as "Status", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.status_colaborador = 'Ativo'
                        ORDER BY c.nome
                    """
                    df_c_res = pd.read_sql_query(query_c, conn)
                else:
                    f_id_sel = filiais_nome_para_id[filial_escolhida_colab_mod]
                    query_c = """
                        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                               c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
                               c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
                               f.nome as "Filial", c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão", 
                               c.status_colaborador as "Status", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.filial_id = ? AND c.status_colaborador = 'Ativo'
                        ORDER BY c.nome
                    """
                    df_c_res = pd.read_sql_query(query_c, conn, params=(f_id_sel,))
            except Exception:
                df_c_res = pd.DataFrame()
            conn.close()

            if not df_c_res.empty:
                df_c_res["CPF"] = df_c_res["CPF"].apply(formatar_cpf)
                df_c_res["Data Admissão"] = df_c_res["Data Admissão"].apply(formatar_data_br)
                df_c_res["Data Movimentação"] = df_c_res["Data Movimentação"].apply(formatar_data_br)

            str_lit.metric("Total Ativos Listados", len(df_c_res))
            str_lit.markdown("---")

            if df_c_res.empty:
                str_lit.info("Nenhum colaborador ativo encontrado para esta seleção.")
            else:
                df_c_res.insert(0, "Selecionar", False)

                col_sel_todos, _ = str_lit.columns([2, 5])
                selecionar_todos = col_sel_todos.checkbox("✅ Selecionar Todos os Colaboradores Ativos", key="chk_sel_todos_ativos")

                if selecionar_todos:
                    df_c_res["Selecionar"] = True

                str_lit.write("Marque individualmente ou use a opção acima para selecionar todos e efetivar a demissão em lote:")
                df_editavel = str_lit.data_editor(
                    df_c_res,
                    column_config={
                        "Selecionar": str_lit.column_config.CheckboxColumn("Selecionar", required=True)
                    },
                    hide_index=True,
                    use_container_width=True,
                )

                matriculas_para_demitir = df_editavel[
                    df_editavel["Selecionar"] == True
                ]["Matrícula"].tolist()

                if matriculas_para_demitir:
                    str_lit.warning(f"⚠️ Você selecionou **{len(matriculas_para_demitir)}** colaborador(es) para colocar como **Demitido**.")
                    
                    data_demissao_lote = str_lit.date_input(
                        "Data da Demissão:",
                        value=date.today(),
                        min_value=MIN_DATE,
                        max_value=MAX_DATE,
                        format="DD/MM/YYYY",
                        key="dt_demissao_lote_input"
                    )

                    if str_lit.button("🔴 Efetivar Demissão dos Selecionados", type="primary"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        for mat_dem in matriculas_para_demitir:
                            c.execute(
                                """
                                UPDATE colaboradores 
                                SET status_colaborador = 'Demitido', data_demissao = ?, 
                                    tipo_movimentacao = 'Saída', subtipo_movimentacao = 'Demissão', data_movimentacao = ?
                                WHERE matricula = ?
                            """,
                                (str(data_demissao_lote), str(data_demissao_lote), mat_dem),
                            )
                        conn.commit()
                        conn.close()

                        for mat_dem in matriculas_para_demitir:
                            registrar_historico(mat_dem, "Demissão em Lote", "Ativo", "Demitido")

                        str_lit.success(f"{len(matriculas_para_demitir)} colaborador(es) marcado(s) como Demitido(s) e alocado(s) na aba de Demitidos!")
                        str_lit.rerun()

        with aba_demitidos:
            conn = sqlite3.connect(DB_FILE)
            try:
                if filial_escolhida_colab_mod == "Todas as Filiais":
                    query_dem = """
                        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                               f.nome as "Filial", c.cpf as "CPF", c.data_contratacao as "Data Admissão", 
                               c.data_demissao as "Data Demissão", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.status_colaborador = 'Demitido'
                        ORDER BY c.nome
                    """
                    df_dem_res = pd.read_sql_query(query_dem, conn)
                else:
                    f_id_sel = filiais_nome_para_id[filial_escolhida_colab_mod]
                    query_dem = """
                        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                               f.nome as "Filial", c.cpf as "CPF", c.data_contratacao as "Data Admissão", 
                               c.data_demissao as "Data Demissão", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.filial_id = ? AND c.status_colaborador = 'Demitido'
                        ORDER BY c.nome
                    """
                    df_dem_res = pd.read_sql_query(query_dem, conn, params=(f_id_sel,))
            except Exception:
                df_dem_res = pd.DataFrame()
            conn.close()

            if not df_dem_res.empty:
                df_dem_res["CPF"] = df_dem_res["CPF"].apply(formatar_cpf)
                df_dem_res["Data Admissão"] = df_dem_res["Data Admissão"].apply(formatar_data_br)
                df_dem_res["Data Demissão"] = df_dem_res["Data Demissão"].apply(formatar_data_br)

            str_lit.metric("Total Demitidos Registrados", len(df_dem_res))
            str_lit.markdown("---")

            if df_dem_res.empty:
                str_lit.info("Nenhum colaborador demitido encontrado para esta seleção.")
            else:
                str_lit.dataframe(df_dem_res, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 6: NOVO COLABORADOR / ADMISSÃO
# ---------------------------------------------------------
elif menu == "➕ Novo Colaborador / Admissão":
    str_lit.title("➕ Admissão / Movimentação de Empregado")
    if not filiais_nome_para_id:
        str_lit.warning(
            "⚠️ Cadastre pelo menos uma filial antes de adicionar colaboradores."
        )
    else:
        str_lit.subheader("1. Informações Principais e Movimentação")
        c_fil, c1, c2 = str_lit.columns(3)
        filial_nome = c_fil.selectbox(
            "Filial *", options=list(filiais_nome_para_id.keys())
        )
        empregado = c1.text_input("Empregado (Nome Completo) *")
        matricula = c2.text_input("Matrícula *")

        c_t1, c_t2, c_t3 = str_lit.columns(3)
        tipo_mov = c_t1.selectbox("Tipo *", options=["Entrada", "Saída"])
        subtipo_mov = c_t2.selectbox(
            "Subtipo *",
            options=["Admissão", "Alocação", "Transferência", "Demissão"],
        )
        data_mov = c_t3.date_input(
            "Data da Movimentação *",
            min_value=MIN_DATE,
            max_value=MAX_DATE,
            format="DD/MM/YYYY",
        )

        str_lit.subheader("2. Dados Profissionais, Contratação e Documentos")
        c3, c4, c5 = str_lit.columns(3)
        cargos_existentes = get_cargos_cadastrados()
        cargo_sel = c3.selectbox(
            "Cargo Existente:", ["-- Novo Cargo --"] + cargos_existentes
        )
        cargo = (
            c3.text_input("Digite o Cargo *")
            if cargo_sel == "-- Novo Cargo --"
            else cargo_sel
        )

        data_admissao = c4.date_input(
            "Data de Admissão *",
            min_value=MIN_DATE,
            max_value=MAX_DATE,
            format="DD/MM/YYYY",
        )
        tipo_contratacao = c5.selectbox(
            "Tipo de Contratação *", options=["CLT", "PJ"]
        )

        c6, c7 = str_lit.columns(2)
        cpf = c6.text_input("CPF")
        rg = c7.text_input("RG")

        cnpj_empresa_input = str_lit.text_input("CNPJ da Empresa", value=CNPJ_PADRAO)
        observacoes = str_lit.text_area("Observações")
        status_colab_novo = (
            "Demitido"
            if subtipo_mov == "Demissão" or tipo_mov == "Saída"
            else "Ativo"
        )
        data_demissao_novo = (
            data_mov if status_colab_novo == "Demitido" else None
        )

        if str_lit.button("💾 Salvar Cadastro Permanentemente"):
            if not matricula or not empregado:
                str_lit.error(
                    "Preencha os campos obrigatórios (Empregado e Matrícula)."
                )
            else:
                cpf_formatado = formatar_cpf(cpf)
                dt_dem_val = (
                    str(data_demissao_novo)
                    if status_colab_novo == "Demitido" and data_demissao_novo
                    else None
                )
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute(
                        """
                        INSERT INTO colaboradores (
                            matricula, nome, cpf, rg, funcao, filial_id,
                            data_contratacao, status_colaborador, data_demissao,
                            tipo_movimentacao, subtipo_movimentacao, data_movimentacao,
                            observacoes, tipo_contratacao, cnpj_empresa
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            matricula,
                            empregado,
                            cpf_formatado,
                            rg,
                            cargo,
                            filiais_nome_para_id[filial_nome],
                            str(data_admissao),
                            status_colab_novo,
                            dt_dem_val,
                            tipo_mov,
                            subtipo_mov,
                            str(data_mov),
                            observacoes,
                            tipo_contratacao,
                            formatar_cnpj(cnpj_empresa_input),
                        ),
                    )
                    conn.commit()
                    conn.close()
                    registrar_historico(
                        matricula,
                        "Nova Movimentação",
                        "-",
                        f"Tipo: {tipo_mov} / Subtipo: {subtipo_mov} - Filial {filial_nome}",
                    )
                    str_lit.success(
                        f"Empregado {empregado} cadastrado e salvo com sucesso!"
                    )
                except sqlite3.IntegrityError:
                    str_lit.error(
                        "Erro: Matrícula já cadastrada no sistema."
                    )

# ---------------------------------------------------------
# MÓDULO 7: EDITAR CADASTRO DO COLABORADOR
# ---------------------------------------------------------
elif menu == "✏️ Editar Cadastro do Colaborador":
    str_lit.title("✏️ Editar Cadastro do Colaborador")

    conn = sqlite3.connect(DB_FILE)
    try:
        df_colab_geral = pd.read_sql_query(
            """
            SELECT c.matricula, c.nome, c.funcao as cargo, f.nome as filial
            FROM colaboradores c
            LEFT JOIN filiais f ON c.filial_id = f.id
            ORDER BY c.nome
        """,
            conn,
        )
    except Exception:
        df_colab_geral = pd.DataFrame()
    conn.close()

    if df_colab_geral.empty:
        str_lit.info("Nenhum colaborador cadastrado.")
    else:
        str_lit.subheader("🔍 Localize o colaborador")

        lista_filiais_edit = ["Todas as Filiais"] + sorted(
            df_colab_geral["filial"].dropna().unique().tolist()
        )
        filial_escolhida_edicao = str_lit.selectbox(
            "Filtrar por Filial:", options=lista_filiais_edit
        )

        df_edit_filtered = df_colab_geral.copy()
        if filial_escolhida_edicao != "Todas as Filiais":
            df_edit_filtered = df_edit_filtered[
                df_edit_filtered["filial"] == filial_escolhida_edicao
            ]

        if df_edit_filtered.empty:
            str_lit.warning("Nenhum colaborador encontrado para esta filial.")
        else:
            opcoes_colab = (
                df_edit_filtered["matricula"]
                + " - "
                + df_edit_filtered["nome"]
                + " (Cargo: "
                + df_edit_filtered["cargo"].fillna("Não informado")
                + ")"
            )
            colab_selecionado = str_lit.selectbox(
                "Selecione o Colaborador que deseja editar:",
                options=opcoes_colab,
            )

            if colab_selecionado:
                matricula_sel = colab_selecionado.split(" - ")[0]

                conn = sqlite3.connect(DB_FILE)
                try:
                    df_detalhe = pd.read_sql_query(
                        "SELECT * FROM colaboradores WHERE matricula = ?",
                        conn,
                        params=(matricula_sel,),
                    )
                except Exception:
                    df_detalhe = pd.DataFrame()
                conn.close()

                if not df_detalhe.empty:
                    colab_row = df_detalhe.iloc[0]
                    str_lit.markdown("---")
                    str_lit.subheader(
                        f"Editando: {colab_row['nome']} (Mat: {colab_row['matricula']})"
                    )

                    with str_lit.form("form_edicao_colab"):
                        e_nome = str_lit.text_input(
                            "Nome Completo", value=colab_row["nome"]
                        )
                        e_cpf = str_lit.text_input(
                            "CPF", value=str(colab_row["cpf"] or "")
                        )
                        e_rg = str_lit.text_input(
                            "RG", value=str(colab_row["rg"] or "")
                        )
                        e_cargo = str_lit.text_input(
                            "Cargo", value=str(colab_row["funcao"] or "")
                        )
                        e_cnpj = str_lit.text_input(
                            "CNPJ da Empresa", value=str(colab_row["cnpj_empresa"] or CNPJ_PADRAO)
                        )
                        e_status = str_lit.selectbox(
                            "Status",
                            options=["Ativo", "Demitido"],
                            index=(
                                0
                                if colab_row["status_colaborador"] == "Ativo"
                                else 1
                            ),
                        )
                        e_obs = str_lit.text_area(
                            "Observações",
                            value=str(colab_row["observacoes"] or ""),
                        )

                        btn_salvar_edicao = str_lit.form_submit_button(
                            "💾 Salvar Alterações Permanentemente"
                        )

                        if btn_salvar_edicao:
                            conn = sqlite3.connect(DB_FILE)
                            c = conn.cursor()
                            c.execute(
                                """
                                UPDATE colaboradores 
                                SET nome = ?, cpf = ?, rg = ?, funcao = ?, cnpj_empresa = ?, status_colaborador = ?, observacoes = ?
                                WHERE matricula = ?
                            """,
                                (
                                    e_nome,
                                    formatar_cpf(e_cpf),
                                    e_rg,
                                    e_cargo,
                                    formatar_cnpj(e_cnpj),
                                    e_status,
                                    e_obs,
                                    matricula_sel,
                                ),
                            )
                            conn.commit()
                            conn.close()
                            registrar_historico(
                                matricula_sel,
                                "Edição de Cadastro",
                                colab_row["nome"],
                                e_nome,
                            )
                            str_lit.success(
                                "Cadastro atualizado e salvo permanentemente!"
                            )
                            str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 8: PEDIDO SALDO ALIMENTAÇÃO
# ---------------------------------------------------------
elif menu == "💳 Pedido Saldo Alimentação":
    str_lit.title("💳 Gestão, Pedido e Histórico de Saldo Alimentação / VA")
    
    # Criamos abas para separar a gestão de saldos atuais e o histórico de pedidos salvos
    aba_saldos, aba_historico_pedidos = str_lit.tabs(["📝 Gestão de Saldos Atuais", "📜 Histórico de Pedidos Registrados"])

    with aba_saldos:
        f_map, _ = get_filiais_dict()
        if not f_map:
            str_lit.warning("Cadastre filiais primeiro.")
        else:
            filial_va = str_lit.selectbox("Selecione a Filial para o Pedido de VA:", options=list(f_map.keys()), key="sel_filial_va")
            f_id = f_map[filial_va]

            conn = sqlite3.connect(DB_FILE)
            try:
                df_va = pd.read_sql_query(
                    """
                    SELECT matricula as "Matrícula", nome as "Empregado", funcao as "Cargo", 
                           saldo_cartao_alimentacao as "Saldo Atual (R$)", tipo_usuario_va as "Tipo Usuário"
                    FROM colaboradores
                    WHERE filial_id = ? AND status_colaborador = 'Ativo'
                    ORDER BY nome
                """,
                    conn, params=(f_id,)
                )
            except Exception:
                df_va = pd.DataFrame()
            conn.close()

            if df_va.empty:
                str_lit.info("Nenhum colaborador ativo nesta filial.")
            else:
                str_lit.write("Atualize os valores de saldo ou tipo de usuário abaixo e salve:")
                df_va_editado = str_lit.data_editor(df_va, hide_index=True, use_container_width=True)

                if str_lit.button("💾 Salvar Alterações de Saldo VA", key="btn_salvar_saldo_va"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    for _, row in df_va_editado.iterrows():
                        c.execute("""
                            UPDATE colaboradores 
                            SET saldo_cartao_alimentacao = ?, tipo_usuario_va = ?
                            WHERE matricula = ?
                        """, (row["Saldo Atual (R$)"], row["Tipo Usuário"], row["Matrícula"]))
                    conn.commit()
                    conn.close()
                    str_lit.success("Saldos de alimentação salvos com sucesso!")
                    str_lit.rerun()

    with aba_historico_pedidos:
        str_lit.subheader("📜 Histórico de Pedidos de VA / Saldo Alimentação Salvos")
        
        conn = sqlite3.connect(DB_FILE)
        try:
            df_hist_pedidos = pd.read_sql_query(
                "SELECT id, mes_ano, obra, data_geracao FROM historico_pedidos_va ORDER BY data_geracao DESC",
                conn
            )
        except Exception:
            df_hist_pedidos = pd.DataFrame()
        conn.close()

        if df_hist_pedidos.empty:
            str_lit.info("Nenhum histórico de pedido de VA registrado no banco de dados.")
        else:
            str_lit.dataframe(df_hist_pedidos, use_container_width=True)
            
            str_lit.markdown("---")
            str_lit.subheader("🗑️ Excluir Histórico de Pedido")
            
            opcoes_pedidos_del = {
                f"ID: {row['id']} | Mês/Ano: {row['mes_ano']} | Obra: {row['obra']} | Data: {row['data_geracao']}": row['id']
                for _, row in df_hist_pedidos.iterrows()
            }
            
            pedido_escolhido_str = str_lit.selectbox(
                "Selecione o registro de pedido que deseja excluir:",
                options=list(opcoes_pedidos_del.keys()),
                key="select_del_pedido_va"
            )
            
            if str_lit.button("🗑️ Deletar Histórico de Pedido Selecionado", type="secondary"):
                if pedido_escolhido_str:
                    id_pedido_del = opcoes_pedidos_del[pedido_escolhido_str]
                    
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("DELETE FROM historico_pedidos_va WHERE id = ?", (id_pedido_del,))
                    conn.commit()
                    conn.close()
                    
                    registrar_log("EXCLUSÃO", f"Excluiu o histórico de pedido de VA ID: {id_pedido_del}")
                    
                    str_lit.success("Histórico de pedido de VA excluído com sucesso!")
                    str_lit.rerun()
                    
# ---------------------------------------------------------
# MÓDULO 9: FOLHA DE PONTO
# ---------------------------------------------------------
elif menu == "⏱️ Folha de Ponto":
    str_lit.title("⏱️ Controle de Folha de Ponto e Horas Extras")

    conn = sqlite3.connect(DB_FILE)
    try:
        df_ponto = pd.read_sql_query(
            """
            SELECT c.matricula as "Matrícula", c.nome as "Empregado", f.nome as "Filial"
            FROM colaboradores c
            LEFT JOIN filiais f ON c.filial_id = f.id
            WHERE c.status_colaborador = 'Ativo'
            ORDER BY c.nome
        """,
            conn,
        )
    except Exception:
        df_ponto = pd.DataFrame()
    conn.close()

    if df_ponto.empty:
        str_lit.info("Nenhum colaborador ativo cadastrado.")
    else:
        lista_filiais_ponto = sorted(df_ponto["Filial"].dropna().unique().tolist())
        filial_escolhida_ponto = str_lit.selectbox(
            "🏢 1. Selecione a Filial / Obra:", options=lista_filiais_ponto
        )

        df_ponto_filtrado = df_ponto[df_ponto["Filial"] == filial_escolhida_ponto]

        if df_ponto_filtrado.empty:
            str_lit.warning("Nenhum colaborador ativo encontrado nesta filial.")
        else:
            colab_ponto = str_lit.selectbox(
                "👥 2. Selecione o Colaborador:",
                options=df_ponto_filtrado["Matrícula"]
                + " - "
                + df_ponto_filtrado["Empregado"],
            )
            matricula_atual = colab_ponto.split(" - ")[0]

            c_mes_p, c_ano_p = str_lit.columns(2)
            meses_lista = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_escolhido = c_mes_p.selectbox("Mês de Referência:", options=meses_lista, index=datetime.now().month - 1)
            ano_escolhido = c_ano_p.number_input("Ano de Referência:", min_value=2020, max_value=2100, value=datetime.now().year)
            
            mes_num = meses_lista.index(mes_escolhido) + 1
            mes_ano_str = f"{mes_escolhido} de {ano_escolhido}"

            if mes_num == 12:
                proximo_mes = datetime(ano_escolhido + 1, 1, 1)
            else:
                proximo_mes = datetime(ano_escolhido, mes_num + 1, 1)
            ultimo_dia = (proximo_mes - timedelta(days=1)).day

            nomes_dias_semana = {
                0: "Segunda-feira", 1: "Terça-feira", 2: "Quarta-feira",
                3: "Quinta-feira", 4: "Sexta-feira", 5: "Sábado", 6: "Domingo"
            }

            feriados_do_ano = obter_feriados_nacionais(int(ano_escolhido))

            conn = sqlite3.connect(DB_FILE)
            try:
                df_salvo_ponto = pd.read_sql_query(
                    "SELECT dados_json FROM folha_ponto WHERE matricula = ? AND mes_ano = ?",
                    conn, params=(matricula_atual, mes_ano_str)
                )
            except Exception:
                df_salvo_ponto = pd.DataFrame()
            conn.close()

            dados_anteriores = {}
            if not df_salvo_ponto.empty and df_salvo_ponto.iloc[0]["dados_json"]:
                try:
                    dados_anteriores = json.loads(df_salvo_ponto.iloc[0]["dados_json"])
                except Exception:
                    pass

            lista_linhas_dias = []
            for dia in range(1, ultimo_dia + 1):
                data_atual = date(int(ano_escolhido), mes_num, dia)
                dia_semana_num = data_atual.weekday()
                nome_dia_sem = nomes_dias_semana[dia_semana_num]
                
                eh_feriado = data_atual in feriados_do_ano
                tipo_dia_str = f"Feriado ({nome_dia_sem})" if eh_feriado else nome_dia_sem

                coluna_nome = f"Dia {dia:02d} ({data_atual.strftime('%d/%m')})"
                valor_salvo = dados_anteriores.get(coluna_nome, "0")
                
                lista_linhas_dias.append({
                    "Dia": coluna_nome,
                    "Tipo": tipo_dia_str,
                    "Horas": str(valor_salvo)
                })

            df_dias_tabela = pd.DataFrame(lista_linhas_dias)

            str_lit.markdown(f"### 📋 Lançamento Diário de Horas Extras - {mes_ano_str}")
            str_lit.write("Preencha a quantidade de horas em cada dia. Use vírgula, ponto ou dois-pontos (ex: `1,5` ou `01:30`).")
            str_lit.write("ℹ️ **Regra:** Segunda a Sexta-feira (e Sábados) somam em **50%**. Domingos e Feriados Nacionais somam em **100%**.")

            df_edit_ponto = str_lit.data_editor(
                df_dias_tabela,
                column_config={
                    "Dia": str_lit.column_config.TextColumn("Data / Dia", disabled=True),
                    "Tipo": str_lit.column_config.TextColumn("Tipo (Dia da Semana / Feriado)", disabled=True),
                    "Horas": str_lit.column_config.TextColumn("Qtd Horas Feitas", required=True)
                },
                hide_index=True,
                use_container_width=True
            )

            # CÁLCULO DA SOMATÓRIA EM TEMPO REAL ANTES DE SALVAR
            total_he_50_calc = 0.0
            total_he_100_calc = 0.0
            dicionario_salvar = {}

            for _, row in df_edit_ponto.iterrows():
                dia_str = row["Dia"]
                tipo_str = row["Tipo"]
                qtd_convertida = converter_hora_flexivel(row["Horas"])
                dicionario_salvar[dia_str] = row["Horas"]

                if "Domingo" in tipo_str or "Feriado" in tipo_str:
                    total_he_100_calc += qtd_convertida
                else:
                    total_he_50_calc += qtd_convertida

            str_lit.markdown("---")
            str_lit.markdown("#### 📊 Prévia dos Totais Calculados:")
            c_res1, c_res2 = str_lit.columns(2)
            c_res1.metric("Total Horas Extras 50% (Seg a Sex / Sáb)", f"{total_he_50_calc:.2f} h")
            c_res2.metric("Total Horas Extras 100% (Domingos e Feriados)", f"{total_he_100_calc:.2f} h")
            str_lit.markdown("---")

            if str_lit.button("💾 Salvar Folha de Ponto Permanentemente", type="primary"):
                json_dados = json.dumps(dicionario_salvar)
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                
                c.execute("DELETE FROM folha_ponto WHERE matricula = ? AND mes_ano = ?", (matricula_atual, mes_ano_str))
                c.execute(
                    """
                    INSERT INTO folha_ponto (matricula, mes_ano, total_50, total_100, dados_json)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (matricula_atual, mes_ano_str, total_he_50_calc, total_he_100_calc, json_dados),
                )

                c.execute(
                    """
                    UPDATE colaboradores 
                    SET he_50 = ?, he_100 = ?
                    WHERE matricula = ?
                """,
                    (total_he_50_calc, total_he_100_calc, matricula_atual)
                )

                conn.commit()
                conn.close()
                str_lit.success(f"Folha de ponto de {mes_ano_str} e os saldos de HE do colaborador salvos com sucesso no banco de dados!")
                
# ---------------------------------------------------------
# MÓDULO: AUDITORIA DO SISTEMA
# ---------------------------------------------------------
elif menu == "🛡️ Auditoria do Sistema":
    str_lit.title("🛡️ Histórico de Ações e Auditoria")
    str_lit.info("Aqui você acompanha o registro detalhado de quem fez cadastros, exclusões e movimentações no sistema.")

    conn = sqlite3.connect(DB_FILE)
    try:
        df_logs = pd.read_sql_query(
            "SELECT data_hora AS 'Data / Hora', usuario AS 'Usuário', acao AS 'Ação', detalhes AS 'Detalhes' FROM log_auditoria ORDER BY id DESC",
            conn
        )
    except Exception:
        df_logs = pd.DataFrame()
    conn.close()

    if df_logs.empty:
        str_lit.info("Nenhum registro de auditoria encontrado.")
    else:
        str_lit.metric("Total de Ações Registradas", len(df_logs))
        str_lit.markdown("---")
        str_lit.dataframe(df_logs, use_container_width=True)
        
