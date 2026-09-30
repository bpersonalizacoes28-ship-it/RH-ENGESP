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
        str_lit.warning("⚠️ **Atenção:** Ao excluir uma filial, todos os colaboradores e arquivos importados vinculados a ela também serão removidos do sistema.")

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
                
                str_lit.success(f"Filial '{filial_para_deletar}' e seus dados associados foram excluídos com sucesso!")
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
                    c.execute("DELETE FROM colaboradores WHERE filial_id = ?", (filial_id_atual,))
                    c.execute("DELETE FROM importacoes_arquivos WHERE filial_id = ?", (filial_id_atual,))
                    conn.commit()
                    conn.close()
                    str_lit.success(f"Todos os colaboradores e a planilha arquivada da filial '{filial_imp}' foram apagados com sucesso!")
                    str_lit.rerun()

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
                               c.tipo_contratacao as "Contratação", f.nome as "Filial", c.cpf as "CPF", 
                               c.rg as "RG", c.data_contratacao as "Data Admissão", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.status_colaborador = 'Ativo'
                        ORDER BY c.nome
                    """
                    df_c_ativos = pd.read_sql_query(query_c, conn)
                else:
                    f_id_sel = filiais_nome_para_id.get(filial_escolhida_colab_mod)
                    query_c = """
                        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                               c.tipo_contratacao as "Contratação", f.nome as "Filial", c.cpf as "CPF", 
                               c.rg as "RG", c.data_contratacao as "Data Admissão", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.status_colaborador = 'Ativo' AND c.filial_id = ?
                        ORDER BY c.nome
                    """
                    df_c_ativos = pd.read_sql_query(query_c, conn, params=(f_id_sel,))
            except Exception:
                df_c_ativos = pd.DataFrame()
            conn.close()

            if df_c_ativos.empty:
                str_lit.info("Nenhum colaborador ativo encontrado.")
            else:
                if "Data Admissão" in df_c_ativos.columns:
                    df_c_ativos["Data Admissão"] = df_c_ativos["Data Admissão"].apply(formatar_data_br)
                if "CPF" in df_c_ativos.columns:
                    df_c_ativos["CPF"] = df_c_ativos["CPF"].apply(formatar_cpf)
                str_lit.dataframe(df_c_ativos, use_container_width=True)

        with aba_demitidos:
            conn = sqlite3.connect(DB_FILE)
            try:
                if filial_escolhida_colab_mod == "Todas as Filiais":
                    query_d = """
                        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                               c.tipo_contratacao as "Contratação", f.nome as "Filial", c.cpf as "CPF", 
                               c.data_contratacao as "Data Admissão", c.data_demissao as "Data Demissão", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.status_colaborador = 'Demitido'
                        ORDER BY c.nome
                    """
                    df_c_demitidos = pd.read_sql_query(query_d, conn)
                else:
                    f_id_sel = filiais_nome_para_id.get(filial_escolhida_colab_mod)
                    query_d = """
                        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                               c.tipo_contratacao as "Contratação", f.nome as "Filial", c.cpf as "CPF", 
                               c.data_contratacao as "Data Admissão", c.data_demissao as "Data Demissão", c.observacoes as "Observações"
                        FROM colaboradores c
                        LEFT JOIN filiais f ON c.filial_id = f.id
                        WHERE c.status_colaborador = 'Demitido' AND c.filial_id = ?
                        ORDER BY c.nome
                    """
                    df_c_demitidos = pd.read_sql_query(query_d, conn, params=(f_id_sel,))
            except Exception:
                df_c_demitidos = pd.DataFrame()
            conn.close()

            if df_c_demitidos.empty:
                str_lit.info("Nenhum colaborador demitido encontrado.")
            else:
                for col in ["Data Admissão", "Data Demissão"]:
                    if col in df_c_demitidos.columns:
                        df_c_demitidos[col] = df_c_demitidos[col].apply(formatar_data_br)
                if "CPF" in df_c_demitidos.columns:
                    df_c_demitidos["CPF"] = df_c_demitidos["CPF"].apply(formatar_cpf)
                str_lit.dataframe(df_c_demitidos, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 6: NOVO COLABORADOR / ADMISSÃO
# ---------------------------------------------------------
elif menu == "➕ Novo Colaborador / Admissão":
    str_lit.title("➕ Cadastrar Novo Colaborador / Admissão Individual")
    
    f_map_novo, _ = get_filiais_dict()
    if not f_map_novo:
        str_lit.warning("⚠️ Cadastre uma filial antes de admitir colaboradores.")
    else:
        with str_lit.form("form_novo_colaborador"):
            c1, c2 = str_lit.columns(2)
            with c1:
                mat_novo = str_lit.text_input("Matrícula *")
                nome_novo = str_lit.text_input("Nome Completo *")
                cpf_novo = str_lit.text_input("CPF")
                rg_novo = str_lit.text_input("RG")
                cargo_novo = str_lit.text_input("Cargo / Função")
                tipo_contrato = str_lit.selectbox("Tipo de Contratação", options=["CLT", "PJ", "Temporário", "Estágio"])
            with c2:
                filial_novo_escolhida = str_lit.selectbox("Filial de Alocação *", options=list(f_map_novo.keys()))
                data_adm = str_lit.date_input("Data de Admissão", value=date.today(), format="DD/MM/YYYY")
                data_nasc = str_lit.date_input("Data de Nascimento", value=date(1990, 1, 1), format="DD/MM/YYYY")
                obs_novo = str_lit.text_area("Observações")

            btn_salvar_novo = str_lit.form_submit_button("💾 Salvar Novo Colaborador Permanentemente")

            if btn_salvar_novo:
                if not mat_novo or not nome_novo:
                    str_lit.error("Os campos 'Matrícula' e 'Nome Completo' são obrigatórios.")
                else:
                    try:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        
                        f_id_dest = f_map_novo[filial_novo_escolhida]
                        c.execute(
                            """
                                INSERT INTO colaboradores (
                                    matricula, nome, cpf, rg, funcao, filial_id, cnpj_empresa,
                                    data_contratacao, data_nascimento, tipo_contratacao,
                                    status_colaborador, tipo_movimentacao, subtipo_movimentacao,
                                    data_movimentacao, observacoes
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Ativo', 'Entrada', 'Admissão', ?, ?)
                            """,
                            (
                                mat_novo.strip(),
                                nome_novo.strip(),
                                formatar_cpf(cpf_novo),
                                rg_novo.strip(),
                                cargo_novo.strip(),
                                f_id_dest,
                                CNPJ_PADRAO,
                                str(data_adm),
                                str(data_nasc),
                                tipo_contrato,
                                str(date.today()),
                                obs_novo.strip(),
                            ),
                        )
                        conn.commit()
                        conn.close()
                        str_lit.success(f"Colaborador '{nome_novo}' cadastrado com sucesso!")
                        str_lit.rerun()
                    except sqlite3.IntegrityError:
                        str_lit.error("Erro: Já existe um colaborador cadastrado com esta matrícula.")

# ---------------------------------------------------------
# MÓDULO 7: EDITAR CADASTRO DO COLABORADOR
# ---------------------------------------------------------
elif menu == "✏️ Editar Cadastro do Colaborador":
    str_lit.title("✏️ Editar ou Demitir Colaborador Cadastrado")
    
    conn = sqlite3.connect(DB_FILE)
    try:
        df_edit_list = pd.read_sql_query("SELECT matricula, nome FROM colaboradores ORDER BY nome", conn)
    except Exception:
        df_edit_list = pd.DataFrame()
    conn.close()

    if df_edit_list.empty:
        str_lit.info("Nenhum colaborador encontrado para edição.")
    else:
        opcoes_colab_edit = [f"{row['matricula']} - {row['nome']}" for _, row in df_edit_list.iterrows()]
        colab_escolhido_str = str_lit.selectbox("Selecione o Colaborador:", options=opcoes_colab_edit)
        
        if colab_escolhido_str:
            mat_selecionada = colab_escolhido_str.split(" - ")[0]
            
            conn = sqlite3.connect(DB_FILE)
            try:
                df_colab_dados = pd.read_sql_query("SELECT * FROM colaboradores WHERE matricula = ?", conn, params=(mat_selecionada,))
            except Exception:
                df_colab_dados = pd.DataFrame()
            conn.close()

            if not df_colab_dados.empty:
                r_colab = df_colab_dados.iloc[0]
                
                with str_lit.form("form_edicao_colab"):
                    str_lit.subheader(f"Editando: {r_colab['nome']} (Matrícula: {r_colab['matricula']})")
                    
                    e1, e2 = str_lit.columns(2)
                    with e1:
                        novo_nome = str_lit.text_input("Nome Completo", value=str(r_colab["nome"]))
                        novo_cpf = str_lit.text_input("CPF", value=str(r_colab["cpf"] if r_colab["cpf"] else ""))
                        novo_rg = str_lit.text_input("RG", value=str(r_colab["rg"] if r_colab["rg"] else ""))
                        nova_funcao = str_lit.text_input("Cargo / Função", value=str(r_colab["funcao"] if r_colab["funcao"] else ""))
                    with e2:
                        status_atual_colab = r_colab["status_colaborador"] if r_colab["status_colaborador"] else "Ativo"
                        novo_status = str_lit.selectbox("Status do Colaborador", options=["Ativo", "Demitido"], index=0 if status_atual_colab == "Ativo" else 1)
                        
                        data_dem_val = parse_data_rigorosa(r_colab["data_demissao"]) if r_colab["data_demissao"] else str(date.today())
                        nova_data_demissao = str_lit.date_input("Data de Demissão (se aplicable)", value=datetime.strptime(data_dem_val, "%Y-%m-%d").date(), format="DD/MM/YYYY")
                        
                        nova_obs = str_lit.text_area("Observações", value=str(r_colab["observacoes"] if r_colab["observacoes"] else ""))

                    btn_salvar_edicao = str_lit.form_submit_button("💾 Salvar Alterações Permanentemente")

                    if btn_salvar_edicao:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute(
                            """
                                UPDATE colaboradores
                                SET nome = ?, cpf = ?, rg = ?, funcao = ?, status_colaborador = ?, 
                                    data_demissao = ?, observacoes = ?
                                WHERE matricula = ?
                            """,
                            (
                                novo_nome.strip(),
                                formatar_cpf(novo_cpf),
                                novo_rg.strip(),
                                nova_funcao.strip(),
                                novo_status,
                                str(nova_data_demissao) if novo_status == "Demitido" else None,
                                nova_obs.strip(),
                                mat_selecionada,
                            ),
                        )
                        conn.commit()
                        conn.close()
                        str_lit.success("Dados atualizados e salvos com sucesso!")
                        str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 8: PEDIDO SALDO ALIMENTAÇÃO
# ---------------------------------------------------------
elif menu == "💳 Pedido Saldo Alimentação":
    str_lit.title("💳 Gestão e Pedido de Saldo de Vale Alimentação")
    
    f_map_va, _ = get_filiais_dict()
    if not f_map_va:
        str_lit.warning("⚠️ Nenhuma filial cadastrada.")
    else:
        filial_va_sel = str_lit.selectbox("Selecione a Filial para o Pedido de VA:", options=list(f_map_va.keys()), key="va_filial")
        f_id_va = f_map_va[filial_va_sel]

        conn = sqlite3.connect(DB_FILE)
        try:
            df_va = pd.read_sql_query(
                """
                    SELECT matricula, nome, funcao, tipo_usuario_va, saldo_cartao_alimentacao, status_solicitacao_va
                    FROM colaboradores
                    WHERE filial_id = ? AND status_colaborador = 'Ativo'
                    ORDER BY nome
                """,
                conn, params=(f_id_va,)
            )
        except Exception:
            df_va = pd.DataFrame()
        conn.close()

        if df_va.empty:
            str_lit.info("Nenhum colaborador ativo encontrado nesta filial.")
        else:
            str_lit.write(f"Colaboradores ativos encontrados: {len(df_va)}")
            
            df_va_editor = str_lit.data_editor(
                df_va,
                column_config={
                    "matricula": "Matrícula",
                    "nome": "Nome",
                    "funcao": "Cargo",
                    "tipo_usuario_va": str_lit.column_config.SelectboxColumn("Tipo Usuário", options=["Já Usuário", "Novo Usuário"], required=True),
                    "saldo_cartao_alimentacao": str_lit.column_config.NumberColumn("Valor Pedido (R$)", format="R$ %.2f", min_value=0.0, step=10.0),
                    "status_solicitacao_va": str_lit.column_config.SelectboxColumn("Status Solicitação", options=["Normal / Atualizado", "Pendente", "Bloqueado"], required=True),
                },
                hide_index=True,
                use_container_width=True,
            )

            if str_lit.button("💾 Salvar Alterações de VA Permanentemente"):
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                for _, row in df_va_editor.iterrows():
                    c.execute(
                        """
                            UPDATE colaboradores
                            SET tipo_usuario_va = ?, saldo_cartao_alimentacao = ?, status_solicitacao_va = ?
                            WHERE matricula = ?
                        """,
                        (row["tipo_usuario_va"], row["saldo_cartao_alimentacao"], row["status_solicitacao_va"], row["matricula"])
                    )
                conn.commit()
                conn.close()
                str_lit.success("Dados do Saldo Alimentação salvos permanentemente!")
                str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 9: FOLHA DE PONTO
# ---------------------------------------------------------
elif menu == "⏱️ Folha de Ponto":
    str_lit.title("⏱️ Gestão e Apuração de Folha de Ponto")
    
    f_map_ponto, _ = get_filiais_dict()
    if not f_map_ponto:
        str_lit.warning("⚠️ Nenhuma filial cadastrada.")
    else:
        filial_ponto_sel = str_lit.selectbox("Selecione a Filial para Apuração de Ponto:", options=list(f_map_ponto.keys()), key="ponto_filial")
        f_id_ponto = f_map_ponto[filial_ponto_sel]

        conn = sqlite3.connect(DB_FILE)
        try:
            df_ponto = pd.read_sql_query(
                """
                    SELECT matricula, nome, he_50, he_100
                    FROM colaboradores
                    WHERE filial_id = ? AND status_colaborador = 'Ativo'
                    ORDER BY nome
                """,
                conn, params=(f_id_ponto,)
            )
        except Exception:
            df_ponto = pd.DataFrame()
        conn.close()

        if df_ponto.empty:
            str_lit.info("Nenhum colaborador ativo encontrado nesta filial.")
        else:
            str_lit.write(f"Colaboradores ativos encontrados: {len(df_ponto)}")
            
            df_ponto_editor = str_lit.data_editor(
                df_ponto,
                column_config={
                    "matricula": "Matrícula",
                    "nome": "Nome",
                    "he_50": str_lit.column_config.NumberColumn("Horas Extras 50% (h)", min_value=0.0, step=0.5, format="%.2f"),
                    "he_100": str_lit.column_config.NumberColumn("Horas Extras 100% (h)", min_value=0.0, step=0.5, format="%.2f"),
                },
                hide_index=True,
                use_container_width=True,
            )

            if str_lit.button("💾 Salvar Apuração de Ponto Permanentemente"):
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                for _, row in df_ponto_editor.iterrows():
                    c.execute(
                        """
                            UPDATE colaboradores
                            SET he_50 = ?, he_100 = ?
                            WHERE matricula = ?
                        """,
                        (row["he_50"], row["he_100"], row["matricula"])
                    )
                conn.commit()
                conn.close()
                str_lit.success("Apuração de folha de ponto salva permanentemente com sucesso!")
                str_lit.rerun()
