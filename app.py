from datetime import date, datetime, timedelta
import io
import json
import re
from PIL import Image
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
# BANCO DE DADOS - INICIALIZAÇÃO E MIGRAÇÃO ROBUSTA
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
            tipo_alteracao TEXT,
            valor_antigo TEXT,
            valor_novo TEXT,
            data_registro DATETIME,
            FOREIGN KEY (colaborador_matricula) REFERENCES colaboradores (matricula)
        )
    """)

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
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# FUNÇÕES DE FORMATAÇÃO E TRATAMENTO RIGOROSO DE DATAS
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
        c.execute(
            """
            INSERT INTO historico_colaboradores (colaborador_matricula, tipo_alteracao, valor_antigo, valor_novo, data_registro)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                matricula,
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
    """Converte valores digitados com vírgula, ponto ou dois-pontos em horas decimais (float)."""
    if valor is None or pd.isna(valor):
        return 0.0
    val_str = str(valor).strip()
    if not val_str or val_str in ["0", "0.0", "None", "nan"]:
        return 0.0

    # Se contém dois-pontos (ex: 01:30 -> 1 hora e 30 min = 1.5)
    if ":" in val_str:
        try:
            partes = val_str.split(":")
            horas = float(partes[0])
            minutos = float(partes[1]) if len(partes) > 1 else 0.0
            return horas + (minutos / 60.0)
        except Exception:
            return 0.0

    # Substitui vírgula por ponto para conversão float padrão
    val_str = val_str.replace(",", ".")
    try:
        return float(val_str)
    except Exception:
        return 0.0


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
    "🏢 Filiais",
    "🔄 Transferência entre Filiais",
    "👥 Colaboradores",
    "➕ Novo Colaborador / Admissão",
    "✏️ Editar Cadastro do Colaborador",
    "💳 Pedido Saldo Alimentação",
    "⏱️ Folha de Ponto",
    "📤 Exportar Dados",
    "📜 Histórico de Alterações",
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
logo_file = str_lit.sidebar.file_uploader(
    "Enviar Logo da Empresa", type=["png", "jpg", "jpeg"]
)
if logo_file is not None:
    image = Image.open(logo_file)
    str_lit.sidebar.image(image, use_container_width=True)
str_lit.sidebar.markdown("---")

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
    str_lit.title("🏢 Cadastro de Novas Filiais")
    with str_lit.form("form_nova_filial"):
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
                    str_lit.success(f"Filial '{nome_f}' cadastrada com sucesso!")
                    str_lit.rerun()
                except sqlite3.IntegrityError:
                    str_lit.error("Erro: Filial já cadastrada.")

    str_lit.markdown("---")
    str_lit.subheader("Filiais Cadastradas")
    conn = sqlite3.connect(DB_FILE)
    try:
        df_f_cad = pd.read_sql_query("SELECT id, nome, cnpj FROM filiais", conn)
    except Exception:
        df_f_cad = pd.DataFrame()
    conn.close()
    if not df_f_cad.empty:
        df_f_cad["cnpj"] = df_f_cad["cnpj"].apply(formatar_cnpj)
        str_lit.dataframe(df_f_cad, use_container_width=True)
    else:
        str_lit.info("Nenhuma filial cadastrada.")

# ---------------------------------------------------------
# MÓDULO 3: IMPORTAR COLABORADORES POR FILIAL
# ---------------------------------------------------------
elif menu == "📥 Importar Colaboradores por Filial":
    str_lit.title("📥 Importação de Colaboradores em Lote")
    if not filiais_nome_para_id:
        str_lit.warning("Cadastre uma filial primeiro.")
    else:
        filial_imp = str_lit.selectbox(
            "Selecione a Filial de Destino da Importação:",
            options=list(filiais_nome_para_id.keys()),
        )
        arquivo_upload = str_lit.file_uploader(
            "Envie a planilha (Excel .xlsx, .xls, .xlsm ou CSV):",
            type=["xlsx", "xls", "xlsm", "csv"],
        )

        if arquivo_upload is not None:
            try:
                nome_arq = arquivo_upload.name.lower()
                if nome_arq.endswith(".csv"):
                    df_imp = pd.read_csv(arquivo_upload)
                else:
                    df_imp = pd.read_excel(arquivo_upload, engine="openpyxl")

                str_lit.write("Pré-visualização dos dados importados:")
                str_lit.dataframe(df_imp.head(), use_container_width=True)

                if str_lit.button("🚀 Processar e Importar para o Banco de Dados"):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    importados = 0
                    for _, r in df_imp.iterrows():
                        mat = str(
                            r.get("Matrícula", r.get("matricula", ""))
                        ).strip()
                        nome = str(r.get("Nome", r.get("nome", ""))).strip()
                        if mat and nome:
                            try:
                                c.execute(
                                    """
                                    INSERT INTO colaboradores (matricula, nome, cpf, rg, funcao, cnpj_empresa, filial_id, status_colaborador, tipo_contratacao)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Ativo', 'CLT')
                                """,
                                    (
                                        mat,
                                        nome,
                                        str(r.get("CPF", "")),
                                        str(r.get("RG", "")),
                                        str(r.get("Cargo", r.get("funcao", ""))),
                                        CNPJ_PADRAO,
                                        filiais_nome_para_id[filial_imp],
                                    ),
                                )
                                importados += 1
                            except Exception:
                                pass
                    conn.commit()
                    conn.close()
                    str_lit.success(
                        f"Importação concluída! {importados} registros salvos na filial {filial_imp}."
                    )
            except Exception as e:
                str_lit.error(f"Erro ao ler o arquivo: {e}")

# ---------------------------------------------------------
# MÓDULO 4: FILIAIS
# ---------------------------------------------------------
elif menu == "🏢 Filiais":
    str_lit.title("🏢 Gestão e Filtragem por Filial")
    conn = sqlite3.connect(DB_FILE)
    try:
        df_filiais_list = pd.read_sql_query(
            "SELECT id, nome, cnpj FROM filiais ORDER BY nome", conn
        )
    except Exception:
        df_filiais_list = pd.DataFrame()
    conn.close()

    if df_filiais_list.empty:
        str_lit.warning("⚠️ Nenhuma filial cadastrada no sistema.")
    else:
        nomes_filiais = df_filiais_list["nome"].tolist()
        filial_selecionada_detalhe = str_lit.selectbox(
            "🏢 **Selecione a Filial para Consulta:**", nomes_filiais
        )
        filial_row = df_filiais_list[
            df_filiais_list["nome"] == filial_selecionada_detalhe
        ].iloc[0]
        filial_id_atual = filial_row["id"]
        cnpj_filial_atual = (
            formatar_cnpj(filial_row["cnpj"])
            if filial_row["cnpj"]
            else CNPJ_PADRAO
        )

        str_lit.markdown(
            f"### 📍 Unidade: {filial_selecionada_detalhe} (CNPJ: {cnpj_filial_atual})"
        )

        conn = sqlite3.connect(DB_FILE)
        try:
            df_colab_filial = pd.read_sql_query(
                """
                SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                       c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
                       c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
                       c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão", 
                       c.status_colaborador as "Status", c.observacoes as "Observações"
                FROM colaboradores c
                WHERE c.filial_id = ?
                ORDER BY c.nome
            """,
                conn,
                params=(filial_id_atual,),
            )
        except Exception:
            df_colab_filial = pd.DataFrame()
        conn.close()

        if not df_colab_filial.empty:
            df_colab_filial["CPF"] = df_colab_filial["CPF"].apply(formatar_cpf)
            df_colab_filial["Data Admissão"] = df_colab_filial[
                "Data Admissão"
            ].apply(formatar_data_br)
            df_colab_filial["Data Movimentação"] = df_colab_filial[
                "Data Movimentação"
            ].apply(formatar_data_br)

        col_m1, col_m2, col_m3 = str_lit.columns(3)
        col_m1.metric("Total de Colaboradores", len(df_colab_filial))
        ativos_filial = (
            len(df_colab_filial[df_colab_filial["Status"] == "Ativo"])
            if not df_colab_filial.empty
            else 0
        )
        col_m2.metric("Ativos", ativos_filial)
        demitidos_filial = (
            len(df_colab_filial[df_colab_filial["Status"] == "Demitido"])
            if not df_colab_filial.empty
            else 0
        )
        col_m3.metric("Demitidos", demitidos_filial)

        str_lit.markdown("---")
        str_lit.subheader(
            f"📋 Relação de Colaboradores - {filial_selecionada_detalhe}"
        )
        if df_colab_filial.empty:
            str_lit.info("Nenhum colaborador vinculado a esta filial.")
        else:
            str_lit.dataframe(df_colab_filial, use_container_width=True)
            output_filial = io.BytesIO()
            with pd.ExcelWriter(output_filial, engine="openpyxl") as writer:
                df_colab_filial.to_excel(
                    writer,
                    index=False,
                    sheet_name=filial_selecionada_detalhe[:30],
                )
            str_lit.download_button(
                label=f"📥 Baixar Relatório da Filial ({filial_selecionada_detalhe}) em Excel",
                data=output_filial.getvalue(),
                file_name=f"relatorio_filial_{filial_selecionada_detalhe.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

# ---------------------------------------------------------
# MÓDULO 5: TRANSFERÊNCIA ENTRE FILIAIS
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
                
                if str_lit.button("🔄 Efetivar Transferência em Lote", type="primary"):
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
                            f"Sucesso! {len(matriculas_selecionadas)} colaborador(es) transferido(s) para a filial {filial_destino}!"
                        )
                        str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 6: COLABORADORES
# ---------------------------------------------------------
elif menu == "👥 Colaboradores":
    str_lit.title("👥 Consulta de Colaboradores por Filial")
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
            "🏢 Selecione a Filial para filtrar os colaboradores:", lista_nomes_f
        )

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
                    WHERE c.filial_id = ?
                    ORDER BY c.nome
                """
                df_c_res = pd.read_sql_query(query_c, conn, params=(f_id_sel,))
        except Exception:
            df_c_res = pd.DataFrame()
        conn.close()

        if not df_c_res.empty:
            df_c_res["CPF"] = df_c_res["CPF"].apply(formatar_cpf)
            df_c_res["Data Admissão"] = df_c_res["Data Admissão"].apply(
                formatar_data_br
            )
            df_c_res["Data Movimentação"] = df_c_res[
                "Data Movimentação"
            ].apply(formatar_data_br)

        str_lit.metric("Colaboradores Listados", len(df_c_res))
        str_lit.markdown("---")

        if df_c_res.empty:
            str_lit.info("Nenhum colaborador encontrado para esta seleção.")
        else:
            df_c_res.insert(0, "Selecionar", False)

            str_lit.write(
                "Marque a caixa 'Selecionar' nos registros que deseja remover da lista (ex: demitidos):"
            )
            df_editavel = str_lit.data_editor(
                df_c_res,
                column_config={
                    "Selecionar": str_lit.column_config.CheckboxColumn(
                        "Selecionar", required=True
                    )
                },
                hide_index=True,
                use_container_width=True,
            )

            matriculas_para_excluir = df_editavel[
                df_editavel["Selecionar"] == True
            ]["Matrícula"].tolist()

            if matriculas_para_excluir:
                str_lit.warning(
                    f"⚠️ Você selecionou {len(matriculas_para_excluir)} colaborador(es) para exclusão."
                )
                if str_lit.button(
                    "🗑️ Deletar Colaboradores Selecionados", type="primary"
                ):
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    for mat_exc in matriculas_para_excluir:
                        c.execute(
                            "DELETE FROM colaboradores WHERE matricula = ?",
                            (mat_exc,),
                        )
                    conn.commit()
                    conn.close()
                    str_lit.success(
                        "Colaboradores selecionados excluídos com sucesso!"
                    )
                    str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 7: NOVO COLABORADOR / ADMISSÃO
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

        if str_lit.button("💾 Finalizar Cadastro / Movimentação"):
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
                        f"Empregado {empregado} cadastrado/movimentado com sucesso!"
                    )
                except sqlite3.IntegrityError:
                    str_lit.error(
                        "Erro: Matrícula já cadastrada no sistema."
                    )

# ---------------------------------------------------------
# MÓDULO 8: EDITAR CADASTRO DO COLABORADOR
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
                            "💾 Salvar Alterações"
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
                                "Cadastro atualizado com sucesso!"
                            )
                            str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 9: PEDIDO SALDO ALIMENTAÇÃO
# ---------------------------------------------------------
elif menu == "💳 Pedido Saldo Alimentação":
    str_lit.title("💳 Pedido de Saldo Alimentação (VA)")

    aba_pedido, aba_historico_pedidos = str_lit.tabs(
        ["Novo Pedido / Exportação", "📜 Histórico de Pedidos Realizados"]
    )

    with aba_pedido:
        conn = sqlite3.connect(DB_FILE)
        try:
            df_va = pd.read_sql_query(
                """
                SELECT c.cnpj_empresa as "CNPJ", c.nome as "Nome Completo", c.cpf as "CPF",
                       f.nome as "Obra", c.premiacao as "Premiação", 
                       c.mobilidade as "Mobilidade", c.alimentacao as "Alimentação",
                       c.tipo_usuario_va as "Tags"
                FROM colaboradores c
                LEFT JOIN filiais f ON c.filial_id = f.id
                WHERE c.status_colaborador = 'Ativo'
                ORDER BY c.nome
            """,
                conn,
            )
        except Exception:
            df_va = pd.DataFrame()
        conn.close()

        if df_va.empty:
            str_lit.info("Nenhum colaborador ativo encontrado.")
        else:
            c_mes, c_ano = str_lit.columns(2)
            meses_disponiveis = [
                "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            mes_atual_idx = datetime.now().month - 1
            mes_sel = c_mes.selectbox(
                "Mês de Referência:",
                options=meses_disponiveis,
                index=mes_atual_idx,
            )
            ano_atual = datetime.now().year
            anos_disponiveis = [str(ano) for ano in range(ano_atual - 2, ano_atual + 4)]
            ano_sel = c_ano.selectbox(
                "Ano de Referência:",
                options=anos_disponiveis,
                index=anos_disponiveis.index(str(ano_atual)),
            )

            mes_ano_ref = f"{mes_sel} de {ano_sel}"

            opcoes_f_va = ["Todas as Filiais"] + sorted(
                df_va["Obra"].dropna().unique().tolist()
            )
            f_va_sel = str_lit.selectbox(
                "Filtrar Obra para Pedido VA:", options=opcoes_f_va
            )

            df_va_filtered = df_va.copy()
            if f_va_sel != "Todas as Filiais":
                df_va_filtered = df_va_filtered[df_va_filtered["Obra"] == f_va_sel]

            str_lit.write(
                f"**Período Selecionado:** {mes_ano_ref} | **Obra:** {f_va_sel}"
            )
            str_lit.write(
                "Ajuste os valores e tags abaixo se necessário (Ordem: CNPJ, Nome Completo, CPF, Obra, Premiação, Mobilidade, Alimentação, Tags):"
            )

            df_va_edit = str_lit.data_editor(
                df_va_filtered, hide_index=True, use_container_width=True
            )

            if str_lit.button("📥 Gerar e Salvar Pedido VA no Histórico"):
                output_va = io.BytesIO()

                df_export = df_va_edit.copy()
                for col_val in ["Premiação", "Mobilidade", "Alimentação"]:
                    if col_val in df_export.columns:
                        df_export[col_val] = pd.to_numeric(
                            df_export[col_val], errors="coerce"
                        ).fillna(0.0)

                with pd.ExcelWriter(output_va, engine="openpyxl") as writer:
                    df_export.to_excel(
                        writer, index=False, sheet_name="Pedido_VA"
                    )

                    workbook = writer.book
                    worksheet = writer.sheets["Pedido_VA"]
                    for col_idx in [5, 6, 7]:
                        for row_idx in range(2, len(df_export) + 2):
                            cell = worksheet.cell(row=row_idx, column=col_idx)
                            cell.number_format = "#,##0.00"

                dados_json_pedido = df_export.to_json(orient="records")
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                
                c.execute("""
                    CREATE TABLE IF NOT EXISTS historico_pedidos_va (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mes_ano TEXT,
                        obra TEXT,
                        data_geracao DATETIME,
                        dados_json TEXT
                    )
                """)
                
                c.execute(
                    """
                    INSERT INTO historico_pedidos_va (mes_ano, obra, data_geracao, dados_json)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        mes_ano_ref,
                        f_va_sel,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        dados_json_pedido,
                    ),
                )
                conn.commit()
                conn.close()

                str_lit.success(
                    f"Pedido referente a {mes_ano_ref} gerado e salvo com sucesso no histórico!"
                )

                str_lit.download_button(
                    label="📥 Baixar Planilha de Pedido VA em Excel",
                    data=output_va.getvalue(),
                    file_name=f"pedido_va_{mes_sel}_{ano_sel}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    with aba_historico_pedidos:
        str_lit.subheader("📜 Histórico de Pedidos de Saldo Alimentação Registrados")
        conn = sqlite3.connect(DB_FILE)
        try:
            df_hist_va = pd.read_sql_query(
                """
                SELECT id, mes_ano as "Mês/Ano", obra as "Obra/Filial", data_geracao as "Data de Geração", dados_json
                FROM historico_pedidos_va
                ORDER BY id DESC
            """,
                conn,
            )
        except Exception:
            df_hist_va = pd.DataFrame()
        conn.close()

        if df_hist_va.empty:
            str_lit.info("Nenhum pedido de VA registrado até o momento.")
        else:
            for _, row_hist in df_hist_va.iterrows():
                with str_lit.expander(
                    f"📅 Pedido: {row_hist['Mês/Ano']} | Obra: {row_hist['Obra/Filial']} (Gerado em: {row_hist['Data de Geração']})"
                ):
                    try:
                        df_salvo = pd.read_json(row_hist["dados_json"])
                        str_lit.dataframe(df_salvo, use_container_width=True)

                        output_hist_item = io.BytesIO()
                        with pd.ExcelWriter(
                            output_hist_item, engine="openpyxl"
                        ) as writer:
                            df_salvo.to_excel(
                                writer, index=False, sheet_name="Pedido_VA"
                            )
                            worksheet = writer.sheets["Pedido_VA"]
                            for col_idx in [5, 6, 7]:
                                for row_idx in range(2, len(df_salvo) + 2):
                                    cell = worksheet.cell(
                                        row=row_idx, column=col_idx
                                    )
                                    cell.number_format = "#,##0.00"

                        str_lit.download_button(
                            label=f"📥 Baixar Novamente (ID {row_hist['id']})",
                            data=output_hist_item.getvalue(),
                            file_name=f"pedido_va_{row_hist['Mês/Ano'].replace(' ', '_')}_{row_hist['Obra/Filial'].replace(' ', '_')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_hist_{row_hist['id']}",
                        )
                    except Exception as e:
                        str_lit.error(f"Erro ao carregar dados salvos: {e}")

# ---------------------------------------------------------
# MÓDULO 10: FOLHA DE PONTO (Inteligente por Mês e Dias da Semana)
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
        colab_ponto = str_lit.selectbox(
            "Selecione o Colaborador:",
            options=df_ponto["Matrícula"]
            + " - "
            + df_ponto["Empregado"]
            + " ("
            + df_ponto["Filial"].fillna("Nenhuma")
            + ")",
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

        # Descobre quantidade de dias do mês selecionado
        if mes_num == 12:
            proximo_mes = datetime(ano_escolhido + 1, 1, 1)
        else:
            proximo_mes = datetime(ano_escolhido, mes_num + 1, 1)
        ultimo_dia = (proximo_mes - timedelta(days=1)).day

        dias_semana_pt = {
            0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"
        }

        # Carrega dados salvos anteriormente se existirem
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

        # Monta estrutura dos dias do mês
        lista_linhas_dias = []
        for dia in range(1, ultimo_dia + 1):
            data_atual = datetime(ano_escolhido, mes_num, dia)
            dia_semana_num = data_atual.weekday()
            nome_dia_sem = dias_semana_pt[dia_semana_num]
            coluna_nome = f"Dia {dia:02d} ({nome_dia_sem})"
            
            valor_salvo = dados_anteriores.get(coluna_nome, "0")
            lista_linhas_dias.append({
                "Dia": coluna_nome,
                "Tipo Dia": "Domingo" if dia_semana_num == 6 else "Útil/Sábado",
                "Horas": str(valor_salvo)
            })

        df_dias_tabela = pd.DataFrame(lista_linhas_dias)

        str_lit.markdown(f"### 📋 Lançamento Diário de Horas Extras - {mes_ano_str}")
        str_lit.write("Preencha a quantidade de horas em cada dia. Você pode usar vírgula, ponto ou dois-pontos (ex: `1,5` ou `01:30`).")

        df_edit_ponto = str_lit.data_editor(
            df_dias_tabela,
            column_config={
                "Dia": str_lit.column_config.TextColumn("Dia do Mês", disabled=True),
                "Tipo Dia": str_lit.column_config.TextColumn("Tipo", disabled=True),
                "Horas": str_lit.column_config.TextColumn("Qtd Horas Feitas", required=True)
            },
            hide_index=True,
            use_container_width=True
        )

        # Cálculo automático de Seg-Sáb (50%) e Domingos (100%)
        total_he_50_calc = 0.0
        total_he_100_calc = 0.0
        dicionario_salvar = {}

        for _, row in df_edit_ponto.iterrows():
            dia_str = row["Dia"]
            qtd_convertida = converter_hora_flexivel(row["Horas"])
            dicionario_salvar[dia_str] = row["Horas"]

            if "Dom" in dia_str:
                total_he_100_calc += qtd_convertida
            else:
                total_he_50_calc += qtd_convertida

        str_lit.markdown("---")
        c_res1, c_res2 = str_lit.columns(2)
        c_res1.metric("Total Horas Extras 50% (Seg a Sáb)", f"{total_he_50_calc:.2f} h")
        c_res2.metric("Total Horas Extras 100% (Domingos)", f"{total_he_100_calc:.2f} h")
        str_lit.markdown("---")

        if str_lit.button("💾 Salvar Folha de Ponto Completa", type="primary"):
            json_dados = json.dumps(dicionario_salvar)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Remove registro anterior do mesmo mês/colaborador para atualizar
            c.execute("DELETE FROM folha_ponto WHERE matricula = ? AND mes_ano = ?", (matricula_atual, mes_ano_str))
            
            c.execute(
                """
                INSERT INTO folha_ponto (matricula, mes_ano, total_50, total_100, dados_json)
                VALUES (?, ?, ?, ?, ?)
            """,
                (matricula_atual, mes_ano_str, total_he_50_calc, total_he_100_calc, json_dados),
            )
            conn.commit()
            conn.close()
            str_lit.success(f"Folha de ponto de {mes_ano_str} salva com sucesso!")

# ---------------------------------------------------------
# MÓDULO 11: EXPORTAR DADOS
# ---------------------------------------------------------
elif menu == "📤 Exportar Dados":
    str_lit.title("📤 Central de Exportação de Dados")

    conn = sqlite3.connect(DB_FILE)
    try:
        df_exp_base = pd.read_sql_query(
            """
            SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.funcao as "Cargo", 
                   c.tipo_movimentacao as "Tipo", c.subtipo_movimentacao as "Subtipo", 
                   c.data_movimentacao as "Data Movimentação", c.tipo_contratacao as "Contratação",
                   f.nome as "Filial", c.cpf as "CPF", c.rg as "RG", c.data_contratacao as "Data Admissão", 
                   c.status_colaborador as "Status", c.observacoes as "Observações"
            FROM colaboradores c
            LEFT JOIN filiais f ON c.filial_id = f.id
            ORDER BY c.nome
        """,
            conn,
        )
    except Exception:
        df_exp_base = pd.DataFrame()
    conn.close()

    if df_exp_base.empty:
        str_lit.info("Nenhum dado disponível para exportação.")
    else:
        lista_exp_filial = ["Todas as Filiais"] + sorted(
            df_exp_base["Filial"].dropna().unique().tolist()
        )
        filial_escolhida_export = str_lit.selectbox(
            "🏢 Selecione a Filial para Exportação:", lista_exp_filial
        )

        df_para_exportar = df_exp_base.copy()
        if filial_escolhida_export != "Todas as Filiais":
            df_para_exportar = df_para_exportar[
                df_para_exportar["Filial"] == filial_escolhida_export
            ]

        str_lit.write(
            f"Registros selecionados para exportação: {len(df_para_exportar)}"
        )

        output_geral = io.BytesIO()
        with pd.ExcelWriter(output_geral, engine="openpyxl") as writer:
            df_para_exportar.to_excel(
                writer, index=False, sheet_name="Dados_ENGESP"
            )

        str_lit.download_button(
            label="📥 Baixar Dados Filtrados em Excel (.xlsx)",
            data=output_geral.getvalue(),
            file_name=f"exportacao_dados_{filial_escolhida_export.replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ---------------------------------------------------------
# MÓDULO 12: HISTÓRICO DE ALTERAÇÕES
# ---------------------------------------------------------
elif menu == "📜 Histórico de Alterações":
    str_lit.title("📜 Histórico de Alterações e Movimentações")
    conn = sqlite3.connect(DB_FILE)
    try:
        df_hist = pd.read_sql_query(
            """
            SELECT colaborador_matricula as "Matrícula", tipo_alteracao as "Tipo", 
                   valor_antigo as "Valor Antigo", valor_novo as "Valor Novo", data_registro as "Data Registro"
            FROM historico_colaboradores
            ORDER BY id DESC
        """,
            conn,
        )
    except Exception:
        df_hist = pd.DataFrame()
    conn.close()

    if df_hist.empty:
        str_lit.info("Nenhum histórico registrado até o momento.")
    else:
        str_lit.dataframe(df_hist, use_container_width=True)
