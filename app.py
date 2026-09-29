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


# ---------------------------------------------------------
# BANCO DE DADOS - INICIALIZAÇÃO E MIGRAÇÃO
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
  
  # Recriar ou garantir estrutura correta da tabela de histórico de VA
  c.execute("""
        CREATE TABLE IF NOT EXISTS historico_pedidos_va (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_ano TEXT,
            filial_nome TEXT,
            matricula TEXT,
            cnpj_empresa TEXT,
            nome TEXT,
            cpf TEXT,
            premiacao REAL,
            mobilidade REAL,
            alimentacao REAL,
            tipo_usuario TEXT,
            data_registro DATETIME
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
    return ""
  nums = re.sub(r"\D", "", str(valor))
  if len(nums) == 14:
    return f"{nums[:2]}.{nums[2:5]}.{nums[5:8]}/{nums[8:12]}-{nums[12:]}"
  return str(valor).strip()


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
  return dict(zip(df["nome"], df["id"])), dict(zip(df["id"], df["nome"]))


def get_cargos_cadastrados():
  conn = sqlite3.connect(DB_FILE)
  df = pd.read_sql_query(
      "SELECT DISTINCT funcao FROM colaboradores WHERE funcao IS NOT NULL AND"
      " funcao != '' ORDER BY funcao",
      conn,
  )
  conn.close()
  return df["funcao"].tolist()


filiais_nome_para_id, filiais_id_para_nome = get_filiais_dict()

# ---------------------------------------------------------
# MENU PRINCIPAL (ORDEM SOLICITADA)
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
  str_lit.sidebar.image(image, use_column_width=True)
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
  df = pd.read_sql_query(query, conn)
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
      df_filtered = df_filtered[df_filtered["Subtipo"].isin(filtro_subtipo)]
    if filtro_status_colab:
      df_filtered = df_filtered[df_filtered["Status"].isin(filtro_status_colab)]

    str_lit.subheader(f"Registros Exibidos ({len(df_filtered)})")
    str_lit.dataframe(df_filtered, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 2: CADASTRO DE FILIAIS
# ---------------------------------------------------------
elif menu == "🏢 Cadastro de Filiais":
  str_lit.title("🏢 Cadastro de Novas Filiais")
  with str_lit.form("form_nova_filial"):
    nome_f = str_lit.text_input("Nome da Filial / Obra *")
    cnpj_f = str_lit.text_input("CNPJ da Filial")
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
  df_f_cad = pd.read_sql_query("SELECT id, nome, cnpj FROM filiais", conn)
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
        "Envie a planilha (Excel ou CSV):", type=["xlsx", "csv"]
    )

    if arquivo_upload is not None:
      try:
        if arquivo_upload.name.endswith(".csv"):
          df_imp = pd.read_csv(arquivo_upload)
        else:
          df_imp = pd.read_excel(arquivo_upload)

        str_lit.write("Pré-visualização dos dados importados:")
        str_lit.dataframe(df_imp.head(), use_container_width=True)

        if str_lit.button("🚀 Processar e Importar para o Banco de Dados"):
          conn = sqlite3.connect(DB_FILE)
          c = conn.cursor()
          importados = 0
          for _, r in df_imp.iterrows():
            mat = str(r.get("Matrícula", r.get("matricula", ""))).strip()
            nome = str(r.get("Nome", r.get("nome", ""))).strip()
            if mat and nome:
              try:
                c.execute(
                    """
                                INSERT INTO colaboradores (matricula, nome, cpf, rg, funcao, filial_id, status_colaborador, tipo_contratacao)
                                VALUES (?, ?, ?, ?, ?, ?, 'Ativo', 'CLT')
                            """,
                    (
                        mat,
                        nome,
                        str(r.get("CPF", "")),
                        str(r.get("RG", "")),
                        str(r.get("Cargo", r.get("funcao", ""))),
                        filiais_nome_para_id[filial_imp],
                    ),
                )
                importados += 1
              except Exception:
                pass
          conn.commit()
          conn.close()
          str_lit.success(
              f"Importação concluída! {importados} registros salvos na filial"
              f" {filial_imp}."
          )
      except Exception as e:
        str_lit.error(f"Erro ao ler o arquivo: {e}")

# ---------------------------------------------------------
# MÓDULO 4: FILIAIS
# ---------------------------------------------------------
elif menu == "🏢 Filiais":
  str_lit.title("🏢 Gestão e Filtragem por Filial")
  conn = sqlite3.connect(DB_FILE)
  df_filiais_list = pd.read_sql_query(
      "SELECT id, nome, cnpj FROM filiais ORDER BY nome", conn
  )
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
        else "Não Informado"
    )

    str_lit.markdown(
        f"### 📍 Unidade: {filial_selecionada_detalhe} (CNPJ:"
        f" {cnpj_filial_atual})"
    )

    conn = sqlite3.connect(DB_FILE)
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
    conn.close()

    if not df_colab_filial.empty:
      df_colab_filial["CPF"] = df_colab_filial["CPF"].apply(formatar_cpf)
      df_colab_filial["Data Admissão"] = df_colab_filial["Data Admissão"].apply(
          formatar_data_br
      )
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
            writer, index=False, sheet_name=filial_selecionada_detalhe[:30]
        )
      str_lit.download_button(
          label=(
              "📥 Baixar Relatório da Filial"
              f" ({filial_selecionada_detalhe}) em Excel"
          ),
          data=output_filial.getvalue(),
          file_name=(
              "relatorio_filial_"
              f"{filial_selecionada_detalhe.replace(' ', '_')}.xlsx"
          ),
          mime=(
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          ),
      )

# ---------------------------------------------------------
# MÓDULO 5: TRANSFERÊNCIA ENTRE FILIAIS
# ---------------------------------------------------------
elif menu == "🔄 Transferência entre Filiais":
  str_lit.title("🔄 Transferência de Colaboradores entre Filiais")
  conn = sqlite3.connect(DB_FILE)
  df_transf = pd.read_sql_query(
      """
        SELECT c.matricula, c.nome, c.filial_id, f.nome as filial_nome
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        WHERE c.status_colaborador = 'Ativo'
        ORDER BY c.nome
    """,
      conn,
  )
  conn.close()

  if df_transf.empty:
    str_lit.info("Nenhum colaborador ativo disponível para transferência.")
  else:
    colab_opts = (
        df_transf["matricula"]
        + " - "
        + df_transf["nome"]
        + " (Filial Atual: "
        + df_transf["filial_nome"].fillna("Nenhuma")
        + ")"
    )
    colab_escolhido = str_lit.selectbox(
        "Selecione o Colaborador:", options=colab_opts
    )

    lista_dest = list(filiais_nome_para_id.keys())
    filial_destino = str_lit.selectbox(
        "Selecione a Filial de Destino:", options=lista_dest
    )
    data_transf = str_lit.date_input(
        "Data da Transferência",
        value=date.today(),
        min_value=MIN_DATE,
        max_value=MAX_DATE,
        format="DD/MM/YYYY",
    )

    if str_lit.button("🔄 Efetivar Transferência"):
      mat_t = colab_escolhido.split(" - ")[0]
      nova_filial_id = filiais_nome_para_id[filial_destino]

      conn = sqlite3.connect(DB_FILE)
      c = conn.cursor()
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

      registrar_historico(
          mat_t, "Transferência de Filial", "-", f"Destino: {filial_destino}"
      )
      str_lit.success(
          f"Colaborador transferido para a filial {filial_destino} com sucesso!"
      )
      str_lit.rerun()

# ---------------------------------------------------------
# MÓDULO 6: COLABORADORES
# ---------------------------------------------------------
elif menu == "👥 Colaboradores":
  str_lit.title("👥 Consulta de Colaboradores por Filial")
  conn = sqlite3.connect(DB_FILE)
  df_filiais_colab = pd.read_sql_query(
      "SELECT id, nome FROM filiais ORDER BY nome", conn
  )
  conn.close()

  if df_filiais_colab.empty:
    str_lit.warning("⚠️ Nenhuma filial cadastrada.")
  else:
    lista_nomes_f = ["Todas as Filiais"] + df_filiais_colab["nome"].tolist()
    filial_escolhida_colab_mod = str_lit.selectbox(
        "🏢 Selecione a Filial para filtrar os colaboradores:", lista_nomes_f
    )

    conn = sqlite3.connect(DB_FILE)
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
    conn.close()

    if not df_c_res.empty:
      df_c_res["CPF"] = df_c_res["CPF"].apply(formatar_cpf)
      df_c_res["Data Admissão"] = df_c_res["Data Admissão"].apply(
          formatar_data_br
      )
      df_c_res["Data Movimentação"] = df_c_res["Data Movimentação"].apply(
          formatar_data_br
      )

    str_lit.metric("Colaboradores Listados", len(df_c_res))
    str_lit.markdown("---")

    if df_c_res.empty:
      str_lit.info("Nenhum colaborador encontrado para esta seleção.")
    else:
      df_c_res.insert(0, "Selecionar", False)

      str_lit.write(
          "Marque a caixa 'Selecionar' nos registros que deseja remover da lista"
          " (ex: demitidos):"
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
            f"⚠️ Você selecionou {len(matriculas_para_excluir)} colaborador(es)"
            " para exclusão."
        )
        if str_lit.button("🗑️ Deletar Colaboradores Selecionados", type="primary"):
          conn = sqlite3.connect(DB_FILE)
          c = conn.cursor()
          for mat_exc in matriculas_para_excluir:
            c.execute("DELETE FROM colaboradores WHERE matricula = ?", (mat_exc,))
          conn.commit()
          conn.close()
          str_lit.success("Colaboradores selecionados excluídos com sucesso!")
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
    tipo_contratacao = c5.selectbox("Tipo de Contratação *", options=["CLT", "PJ"])

    c6, c7 = str_lit.columns(2)
    cpf = c6.text_input("CPF")
    rg = c7.text_input("RG")

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
                  "37.608.361/0001-25",
              ),
          )
          conn.commit()
          conn.close()
          registrar_historico(
              matricula,
              "Nova Movimentação",
              "-",
              f"Tipo: {tipo_mov} / Subtipo: {subtipo_mov} - Filial"
              f" {filial_nome}",
          )
          str_lit.success(
              f"Empregado {empregado} cadastrado/movimentado com sucesso!"
          )
        except sqlite3.IntegrityError:
          str_lit.error("Erro: Matrícula já cadastrada no sistema.")

# ---------------------------------------------------------
# MÓDULO 8: EDITAR CADASTRO DO COLABORADOR
# ---------------------------------------------------------
elif menu == "✏️ Editar Cadastro do Colaborador":
  str_lit.title("✏️ Editar Cadastro do Colaborador")

  conn = sqlite3.connect(DB_FILE)
  df_colab_geral = pd.read_sql_query(
      """
        SELECT c.matricula, c.nome, c.funcao as cargo, f.nome as filial
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        ORDER BY c.nome
    """,
      conn,
  )
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
          "Selecione o Colaborador que deseja editar:", options=opcoes_colab
      )

      if colab_selecionado:
        matricula_sel = colab_selecionado.split(" - ")[0]

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM colaboradores WHERE matricula = ?", (matricula_sel,))
        dados = c.fetchone()
        conn.close()

        if dados:
          tab_edit, tab_delete = str_lit.tabs(
              ["✏️ Editar Dados do Colaborador", "🗑️ Excluir Registro"]
          )

          with tab_edit:
            str_lit.subheader("Editar Dados do Colaborador")
            u1, u2, u3 = str_lit.columns(3)
            mat_e = u1.text_input("Matrícula *", value=dados[1])
            nome_e = u2.text_input("Empregado *", value=dados[2])
            cargo_e = u3.text_input("Cargo *", value=dados[5] or "")

            u4, u5, u6 = str_lit.columns(3)
            cpf_e = u4.text_input("CPF", value=formatar_cpf(dados[3]))
            rg_e = u5.text_input("RG", value=dados[4] or "")

            filial_atual_nome = filiais_id_para_nome.get(
                dados[7],
                (
                    list(filiais_nome_para_id.keys())[0]
                    if filiais_nome_para_id
                    else ""
                ),
            )
            filial_idx = (
                list(filiais_nome_para_id.keys()).index(filial_atual_nome)
                if filial_atual_nome in filiais_nome_para_id
                else 0
            )
            filial_e = u6.selectbox(
                "Filial",
                options=list(filiais_nome_para_id.keys()),
                index=filial_idx,
            )

            m1, m2, m3 = str_lit.columns(3)
            tipo_mov_opts = ["Entrada", "Saída"]
            t_mov_atual = (
                dados[28]
                if len(dados) > 28 and dados[28] in tipo_mov_opts
                else "Entrada"
            )
            tipo_mov_e = m1.selectbox(
                "Tipo", tipo_mov_opts, index=tipo_mov_opts.index(t_mov_atual)
            )

            subtipo_opts = ["Admissão", "Alocação", "Transferência", "Demissão"]
            sub_atual = (
                dados[29]
                if len(dados) > 29 and dados[29] in subtipo_opts
                else "Admissão"
            )
            subtipo_mov_e = m2.selectbox(
                "Subtipo", subtipo_opts, index=subtipo_opts.index(sub_atual)
            )

            dt_mov_val = (
                converter_para_date(dados[30])
                if len(dados) > 30 and dados[30]
                else date.today()
            )
            data_mov_e = m3.date_input(
                "Data da Movimentação",
                value=dt_mov_val,
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                format="DD/MM/YYYY",
            )

            c_contr1, c_contr2 = str_lit.columns(2)
            contrato_opts = ["CLT", "PJ"]
            contrato_atual = (
                dados[32]
                if len(dados) > 32 and dados[32] in contrato_opts
                else "CLT"
            )
            tipo_contratacao_e = c_contr1.selectbox(
                "Tipo de Contratação",
                contrato_opts,
                index=contrato_opts.index(contrato_atual),
            )

            dt_adm_val = (
                converter_para_date(dados[9]) if dados[9] else date.today()
            )
            data_admissao_e = c_contr2.date_input(
                "Data de Admissão",
                value=dt_adm_val,
                min_value=MIN_DATE,
                max_value=MAX_DATE,
                format="DD/MM/YYYY",
            )

            observacoes_e = str_lit.text_area(
                "Observações",
                value=dados[31] if len(dados) > 31 and dados[31] else "",
            )

            if str_lit.button("💾 Salvar Alterações"):
              cpf_salvar = formatar_cpf(cpf_e)
              status_colab_e = (
                  "Demitido"
                  if subtipo_mov_e == "Demissão" or tipo_mov_e == "Saída"
                  else "Ativo"
              )
              dt_dem_salvar = (
                  str(data_mov_e) if status_colab_e == "Demitido" else None
              )

              registrar_historico(
                  matricula_sel, "Alteração Cadastral", dados[2], nome_e
              )

              conn = sqlite3.connect(DB_FILE)
              c = conn.cursor()
              c.execute(
                  """
                                UPDATE colaboradores
                                SET matricula = ?, nome = ?, cpf = ?, rg = ?, funcao = ?,
                                    filial_id = ?, data_contratacao = ?, status_colaborador = ?,
                                    data_demissao = ?, tipo_movimentacao = ?, subtipo_movimentacao = ?,
                                    data_movimentacao = ?, observacoes = ?, tipo_contratacao = ?
                                WHERE matricula = ?
                            """,
                  (
                      mat_e,
                      nome_e,
                      cpf_salvar,
                      rg_e,
                      cargo_e,
                      filiais_nome_para_id[filial_e],
                      str(data_admissao_e),
                      status_colab_e,
                      dt_dem_salvar,
                      tipo_mov_e,
                      subtipo_mov_e,
                      str(data_mov_e),
                      observacoes_e,
                      tipo_contratacao_e,
                      matricula_sel,
                  ),
              )
              conn.commit()
              conn.close()
              str_lit.success("Cadastro atualizado com sucesso!")
              str_lit.rerun()

          with tab_delete:
            str_lit.warning(
                f"⚠️ Excluir permanentemente o registro de **{dados[2]}**?"
            )
            confirma = str_lit.checkbox("Confirmo a exclusão.")
            if str_lit.button("🗑️ Confirmar Exclusão", type="primary"):
              if confirma:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute(
                    "DELETE FROM colaboradores WHERE matricula = ?",
                    (matricula_sel,),
                )
                conn.commit()
                conn.close()
                str_lit.success("Colaborador excluído com sucesso!")
                str_lit.rerun()
              else:
                str_lit.error(
                    "Marque a caixa de confirmação para prosseguir com a"
                    " exclusão."
                )

# ---------------------------------------------------------
# MÓDULO 9: PEDIDO SALDO ALIMENTAÇÃO
# ---------------------------------------------------------
elif menu == "💳 Pedido Saldo Alimentação":
  str_lit.title("💳 Pedido de Saldo / Cartão Alimentação")
  conn = sqlite3.connect(DB_FILE)
  df_va = pd.read_sql_query(
      """
        SELECT c.matricula, c.nome, c.cpf, c.cnpj_empresa, c.premiacao, c.mobilidade, c.alimentacao, c.tipo_usuario_va, f.nome as filial_nome, f.cnpj as filial_cnpj
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        WHERE c.status_colaborador = 'Ativo'
        ORDER BY c.nome
    """,
      conn,
  )
  conn.close()

  if df_va.empty:
    str_lit.info("Nenhum colaborador ativo cadastrado para pedido.")
  else:
    lista_f_va = sorted(df_va["filial_nome"].dropna().unique().tolist())
    filial_va_sel = str_lit.selectbox(
        "🏢 Selecione a Filial / Obra para carregar os dados:", lista_f_va
    )

    if filial_va_sel:
      df_va_filial = df_va[df_va["filial_nome"] == filial_va_sel].copy()
      cnpj_unidade = (
          df_va_filial["filial_cnpj"].iloc[0]
          if not df_va_filial.empty and df_va_filial["filial_cnpj"].iloc[0]
          else "37.608.361/0001-25"
      )

      df_va_filial["cnpj_empresa"] = df_va_filial["cnpj_empresa"].fillna(
          cnpj_unidade
      )
      df_va_filial["CNPJ"] = df_va_filial["cnpj_empresa"].apply(formatar_cnpj)
      df_va_filial["Nome Completo"] = df_va_filial["nome"]
      df_va_filial["CPF"] = df_va_filial["cpf"].apply(formatar_cpf)
      df_va_filial["Obra"] = df_va_filial["filial_nome"]
      df_va_filial["Premiação"] = df_va_filial["premiacao"].fillna(0.0)
      df_va_filial["Mobilidade"] = df_va_filial["mobilidade"].fillna(0.0)
      df_va_filial["Alimentação"] = df_va_filial["alimentacao"].fillna(0.0)
      df_va_filial["Tags"] = df_va_filial["tipo_usuario_va"].fillna(
          "Já Usuário"
      )

      mes_ano_ref = str_lit.text_input(
          "Mês/Ano de Referência (Ex: 09/2026):",
          value=datetime.now().strftime("%m/%Y"),
      )

      str_lit.subheader(f"Relação de Benefícios - Filial: {filial_va_sel}")

      df_editado_va = str_lit.data_editor(
          df_va_filial[
              [
                  "CNPJ",
                  "Nome Completo",
                  "CPF",
                  "Obra",
                  "Premiação",
                  "Mobilidade",
                  "Alimentação",
                  "Tags",
              ]
          ],
          column_config={
              "CNPJ": str_lit.column_config.TextColumn("CNPJ", disabled=True),
              "Nome Completo": str_lit.column_config.TextColumn(
                  "Nome Completo", disabled=True
              ),
              "CPF": str_lit.column_config.TextColumn("CPF", disabled=True),
              "Obra": str_lit.column_config.TextColumn("Obra", disabled=True),
              "Premiação": str_lit.column_config.NumberColumn(
                  "Premiação", format="R$ %.2f", min_value=0.0, step=10.0
              ),
              "Mobilidade": str_lit.column_config.NumberColumn(
                  "Mobilidade", format="R$ %.2f", min_value=0.0, step=10.0
              ),
              "Alimentação": str_lit.column_config.NumberColumn(
                  "Alimentação", format="R$ %.2f", min_value=0.0, step=10.0
              ),
              "Tags": str_lit.column_config.SelectboxColumn(
                  "Tags", options=["Já Usuário", "Novo"], required=True
              ),
          },
          hide_index=True,
          use_container_width=True,
      )

      if str_lit.button("💾 Salvar e Registrar Pedido de Saldo Alimentação"):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for idx, row in df_editado_va.iterrows():
          mat_orig = df_va_filial.iloc[idx]["matricula"]
          c.execute(
              """
                        UPDATE colaboradores
                        SET premiacao = ?, mobilidade = ?, alimentacao = ?, tipo_usuario_va = ?
                        WHERE matricula = ?
                    """,
              (
                  row["Premiação"],
                  row["Mobilidade"],
                  row["Alimentação"],
                  row["Tags"],
                  mat_orig,
              ),
          )
          c.execute(
              """
                        INSERT INTO historico_pedidos_va (mes_ano, filial_nome, matricula, cnpj_empresa, nome, cpf, premiacao, mobilidade, alimentacao, tipo_usuario, data_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
              (
                  mes_ano_ref,
                  row["Obra"],
                  mat_orig,
                  row["CNPJ"],
                  row["Nome Completo"],
                  row["CPF"],
                  row["Premiação"],
                  row["Mobilidade"],
                  row["Alimentação"],
                  row["Tags"],
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              ),
          )
        conn.commit()
        conn.close()
        str_lit.success("Pedido de saldo alimentação registrado com sucesso!")

# ---------------------------------------------------------
# MÓDULO 10: FOLHA DE PONTO
# ---------------------------------------------------------
elif menu == "⏱️ Folha de Ponto":
  str_lit.title("⏱️ Gestão e Apuração de Folha de Ponto (Horas Extras)")
  conn = sqlite3.connect(DB_FILE)
  df_ponto = pd.read_sql_query(
      """
        SELECT c.matricula, c.nome, f.nome as filial_nome
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
        WHERE c.status_colaborador = 'Ativo'
        ORDER BY c.nome
    """,
      conn,
  )
  conn.close()

  if df_ponto.empty:
    str_lit.info("Nenhum colaborador ativo para apuração de ponto.")
  else:
    filial_ponto_sel = str_lit.selectbox(
        "Filtrar por Filial para Ponto:",
        ["Todas as Filiais"] + sorted(df_ponto["filial_nome"].dropna().unique().tolist()),
    )
    if filial_ponto_sel != "Todas as Filiais":
      df_ponto = df_ponto[df_ponto["filial_nome"] == filial_ponto_sel]

    mes_ponto = str_lit.text_input(
        "Mês/Ano de Apuração (Ex: 09/2026):",
        value=datetime.now().strftime("%m/%Y"),
        key="mes_ponto_input",
    )

    colab_ponto_sel = str_lit.selectbox(
        "Selecione o Colaborador para Apuração Detalhada:",
        options=df_ponto["matricula"] + " - " + df_ponto["nome"],
    )

    if colab_ponto_sel:
      mat_p = colab_ponto_sel.split(" - ")[0]
      nome_p = colab_ponto_sel.split(" - ")[1]

      str_lit.markdown(f"### Apuração de Horas - {nome_p} (Matrícula: {mat_p})")
      c_he1, c_he2 = str_lit.columns(2)
      tot_he50 = c_he1.number_input(
          "Total Horas Extras 50% (Horas)", min_value=0.0, step=0.5, value=0.0
      )
      tot_he100 = c_he2.number_input(
          "Total Horas Extras 100% (Horas)", min_value=0.0, step=0.5, value=0.0
      )

      if str_lit.button("💾 Salvar Apuração de Ponto"):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """
                INSERT INTO folha_ponto (matricula, mes_ano, total_50, total_100, dados_json)
                VALUES (?, ?, ?, ?, ?)
            """,
            (
                mat_p,
                mes_ponto,
                tot_he50,
                tot_he100,
                json.dumps({"he_50": tot_he50, "he_100": tot_he100}),
            ),
        )
        conn.commit()
        conn.close()
        str_lit.success("Apuração de ponto salva com sucesso!")

# ---------------------------------------------------------
# MÓDULO 11: EXPORTAR DADOS
# ---------------------------------------------------------
elif menu == "📤 Exportar Dados":
  str_lit.title("📤 Exportação Geral de Dados")
  conn = sqlite3.connect(DB_FILE)
  df_exp = pd.read_sql_query(
      """
        SELECT c.matricula as "Matrícula", c.nome as "Empregado", c.cpf as "CPF", c.rg as "RG",
               c.funcao as "Cargo", f.nome as "Filial", c.tipo_movimentacao as "Tipo Mov.",
               c.subtipo_movimentacao as "Subtipo Mov.", c.data_movimentacao as "Data Mov.",
               c.status_colaborador as "Status", c.tipo_contratacao as "Contratação",
               c.premiacao as "Premiação", c.mobilidade as "Mobilidade", c.alimentacao as "Alimentação", c.observacoes as "Observações"
        FROM colaboradores c
        LEFT JOIN filiais f ON c.filial_id = f.id
    """,
      conn,
  )
  conn.close()

  if df_exp.empty:
    str_lit.info("Nenhum dado disponível para exportação.")
  else:
    output_geral = io.BytesIO()
    with pd.ExcelWriter(output_geral, engine="openpyxl") as writer:
      df_exp.to_excel(writer, index=False, sheet_name="Base Completa")

    str_lit.download_button(
        label="📥 Baixar Base Completa de Colaboradores (Excel)",
        data=output_geral.getvalue(),
        file_name="base_colaboradores_engesp.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    str_lit.dataframe(df_exp, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 12: HISTÓRICO DE ALTERAÇÕES
# ---------------------------------------------------------
elif menu == "📜 Histórico de Alterações":
  str_lit.title("📜 Histórico de Modificações e Auditoria")
  conn = sqlite3.connect(DB_FILE)
  df_hist = pd.read_sql_query(
      """
        SELECT h.data_registro as "Data/Hora", h.colaborador_matricula as "Matrícula",
               c.nome as "Empregado", h.tipo_alteracao as "Tipo de Alteração",
               h.valor_antigo as "Valor Antigo", h.valor_novo as "Valor Novo"
        FROM historico_colaboradores h
        LEFT JOIN colaboradores c ON h.colaborador_matricula = c.matricula
        ORDER BY h.data_registro DESC
    """,
      conn,
  )
  conn.close()

  if df_hist.empty:
    str_lit.info("Nenhum histórico registrado no sistema.")
  else:
    str_lit.dataframe(df_hist, use_container_width=True)
