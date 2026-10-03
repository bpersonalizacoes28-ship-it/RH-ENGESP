from datetime import date, datetime, timedelta
import io
import json
import random
import re
import streamlit as str_lit
import pandas as pd
import hashlib
from sqlalchemy import create_engine, text

str_lit.set_page_config(
    page_title="Sistema de Gestão ADM - ENGESP",
    layout="wide",
    initial_sidebar_state="expanded",
)
# Configuração do Administrador Inicial
ADMIN_EMAIL = "admin@engesp.com"
ADMIN_SENHA_PADRAO = "admin123"

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

CNPJ_PADRAO = "37.608.361/0001-25"
ADMIN_EMAIL = "admin@engesp.com"
ADMIN_SENHA_PADRAO = "admin123"

# ---------------------------------------------------------
# CONEXÃO SEGURA COM O SUPABASE
# ---------------------------------------------------------
ddef get_engine():
    try:
        db_url = str_lit.secrets["connections"]["postgresql"]["url"]
    except Exception:
        try:
            db_url = str_lit.secrets["DATABASE_URL"]
        except Exception:
            db_url = ""
    
    if not db_url:
        str_lit.error("⚠️ O Streamlit não encontrou o link do banco nos Secrets! Verifique as configurações.")
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    if db_url.startswith("postgresql://") and not db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        
    return create_engine(db_url)

def executar_query(query, params=None):
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params or {})
    return df

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()
    
# ---------------------------------------------------------
# BANCO DE DADOS - INICIALIZAÇÃO NA NUVEM
# ---------------------------------------------------------
def init_db():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                email TEXT PRIMARY KEY,
                senha TEXT NOT NULL,
                criado_por TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS logs_auditoria (
                id SERIAL PRIMARY KEY,
                usuario TEXT,
                acao TEXT,
                detalhes TEXT,
                data_hora TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS filiais (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL UNIQUE,
                cnpj TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS colaboradores (
                id SERIAL PRIMARY KEY,
                matricula TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                cpf TEXT,
                rg TEXT,
                funcao TEXT,
                cnpj_empresa TEXT,
                filial_id INTEGER,
                data_contratacao DATE,
                tipo_contratacao TEXT DEFAULT 'CLT',
                status_colaborador TEXT DEFAULT 'Ativo',
                data_demissao DATE,
                tipo_movimentacao TEXT DEFAULT 'Entrada',
                subtipo_movimentacao TEXT DEFAULT 'Admissão',
                data_movimentacao DATE,
                observacoes TEXT,
                he_50 REAL DEFAULT 0,
                he_100 REAL DEFAULT 0,
                periculosidade TEXT DEFAULT 'Não',
                ajuda_custo REAL DEFAULT 0,
                premiacao REAL DEFAULT 0,
                mobilidade REAL DEFAULT 0,
                alimentacao REAL DEFAULT 0,
                tipo_usuario_va TEXT DEFAULT 'Já Usuário',
                FOREIGN KEY (filial_id) REFERENCES filiais (id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS historico_pedidos_va (
                id SERIAL PRIMARY KEY,
                mes_ano TEXT,
                obra TEXT,
                data_geracao TIMESTAMP,
                dados_json TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS folha_ponto (
                id SERIAL PRIMARY KEY,
                matricula TEXT,
                mes_ano TEXT,
                total_50 REAL DEFAULT 0,
                total_100 REAL DEFAULT 0,
                dados_json TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS importacoes_arquivos (
                filial_id INTEGER PRIMARY KEY,
                nome_arquivo TEXT,
                data_importacao TIMESTAMP,
                arquivo_blob BYTEA
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS folga_campo_recesso (
                filial_id INTEGER PRIMARY KEY,
                nome_arquivo TEXT,
                data_importacao TIMESTAMP,
                dados_json TEXT
            )
        """))

    df_adm = executar_query("SELECT email FROM usuarios WHERE email = :email", {"email": ADMIN_EMAIL})
    if df_adm.empty:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO usuarios (email, senha, criado_por) VALUES (:email, :senha, :criado)"
            ), {"email": ADMIN_EMAIL, "senha": hash_senha(ADMIN_SENHA_PADRAO), "criado": "Sistema"})

init_db()

# ---------------------------------------------------------
# TELA INICIAL DO APP
# ---------------------------------------------------------
str_lit.title("Sistema RH - ENGESP")
str_lit.success("Banco de dados conectado e inicializado com sucesso! Faça login para continuar.")

# ---------------------------------------------------------
# FUNÇÕES DE SEGURANÇA E AUDITORIA
# ---------------------------------------------------------
def registrar_auditoria(acao, detalhes=""):
    usuario = str_lit.session_state.get("usuario_logado", "Sistema")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO logs_auditoria (usuario, acao, detalhes, data_hora) VALUES (:u, :a, :d, :dh)"
        ), {"u": usuario, "a": acao, "d": detalhes, "dh": datetime.now().strftime("%d/%m/%Y %H:%M:%S")})

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
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(val_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return str(date.today())

def formatar_data_br(valor):
    if not valor or pd.isna(valor) or str(valor).strip() in ["", "None", "nan", "NaT"]:
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
        date(ano, 1, 1), date(ano, 4, 21), date(ano, 5, 1), date(ano, 9, 7),
        date(ano, 10, 12), date(ano, 11, 2), date(ano, 11, 15), date(ano, 11, 20), date(ano, 12, 25),
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
    try:
        df = executar_query("SELECT id, nome FROM filiais ORDER BY nome")
    except Exception:
        df = pd.DataFrame(columns=["id", "nome"])
    if df.empty:
        return {}, {}
    return dict(zip(df["nome"], df["id"])), dict(zip(df["id"], df["nome"]))

def calcular_ultima_folga_colaborador(f_id, matricula):
    try:
        df_f = executar_query("SELECT dados_json FROM folga_campo_recesso WHERE filial_id = :fid", {"fid": int(f_id)})
    except Exception:
        df_f = pd.DataFrame()
    if df_f.empty or not df_f.iloc[0]["dados_json"]:
        return "Nenhuma"
    try:
        registros = json.loads(df_f.iloc[0]["dados_json"])
        for reg in registros:
            if str(reg.get("MATRÍCULA", "")) == str(matricula):
                colunas_datas = ["1° FOLGA", "CHEGOU DA 1° FOLGA", "2° FOLGA", "CHEGOU DA 2° FOLGA", "3° FOLGA"]
                ultima_valida = ""
                for col in colunas_datas:
                    val = str(reg.get(col, "")).strip()
                    if val and val not in ["None", "nan", "-"]:
                        ultima_valida = val
                return ultima_valida if ultima_valida else "Nenhuma"
    except Exception:
        pass
    return "Nenhuma"

# =========================================================
# CONTROLE DE SESSÃO E TELA DE AUTENTICAÇÃO
# =========================================================
if "autenticado" not in str_lit.session_state:
    str_lit.session_state.autenticado = False
if "usuario_logado" not in str_lit.session_state:
    str_lit.session_state.usuario_logado = None

if not str_lit.session_state.autenticado:
    str_lit.title("🔐 Portal ENGESP - Acesso ao Sistema ADM")
    aba_login, aba_cadastro, aba_recuperar = str_lit.tabs(["🔑 Entrar", "📝 Novo Cadastro", "🔄 Esqueci a Senha"])

    with aba_login:
        str_lit.subheader("Acesse com seu E-mail Corporativo e Senha")
        with str_lit.form("form_login"):
            email_l = str_lit.text_input("E-mail Corporativo (@engesp.com):")
            senha_l = str_lit.text_input("Senha:", type="password")
            btn_entrar = str_lit.form_submit_button("Entrar no Sistema", type="primary")

            if btn_entrar:
                if not email_l.endswith("@engesp.com"):
                    str_lit.error("⚠️ O e-mail deve terminar com `@engesp.com`.")
                else:
                    df_u = executar_query("SELECT senha FROM usuarios WHERE email = :email", {"email": email_l})
                    if not df_u.empty and df_u.iloc[0]["senha"] == hash_senha(senha_l):
                        str_lit.session_state.autenticado = True
                        str_lit.session_state.usuario_logado = email_l
                        registrar_auditoria("Login", f"Usuário {email_l} acessou o sistema.")
                        str_lit.success("Login realizado com sucesso! Carregando...")
                        str_lit.rerun()
                    else:
                        str_lit.error("⚠️ E-mail ou senha incorretos.")

    with aba_cadastro:
        str_lit.subheader("Cadastrar Novo Usuário Corporativo")
        with str_lit.form("form_cadastro"):
            email_c = str_lit.text_input("Novo E-mail Corporativo (@engesp.com):")
            senha_c = str_lit.text_input("Crie uma Senha:", type="password")
            senha_c2 = str_lit.text_input("Confirme a Senha:", type="password")
            btn_cadastrar = str_lit.form_submit_button("Cadastrar Nova Conta")

            if btn_cadastrar:
                if not email_c.endswith("@engesp.com"):
                    str_lit.error("⚠️ O e-mail deve terminar com `@engesp.com`.")
                elif senha_c != senha_c2:
                    str_lit.error("⚠️ As senhas não coincidem.")
                elif len(senha_c) < 4:
                    str_lit.error("⚠️ A senha deve conter pelo menos 4 caracteres.")
                else:
                    df_existe = executar_query("SELECT email FROM usuarios WHERE email = :email", {"email": email_c})
                    if not df_existe.empty:
                        str_lit.error("⚠️ Este e-mail já possui cadastro no sistema.")
                    else:
                        engine = get_engine()
                        with engine.begin() as conn:
                            conn.execute(text(
                                "INSERT INTO usuarios (email, senha, criado_por) VALUES (:e, :s, :c)"
                            ), {"e": email_c, "s": hash_senha(senha_c), "c": "Auto-cadastro"})
                        registrar_auditoria("Novo Usuário", f"Cadastrou a conta {email_c}")
                        str_lit.success("Conta cadastrada com sucesso! Vá para a aba 'Entrar' para acessar.")

    with aba_recuperar:
        str_lit.subheader("Redefinir / Esqueci minha Senha")
        with str_lit.form("form_recuperar"):
            email_r = str_lit.text_input("Seu E-mail Corporativo Cadastrado (@engesp.com):")
            nova_senha_r = str_lit.text_input("Nova Senha:", type="password")
            nova_senha_r2 = str_lit.text_input("Confirme a Nova Senha:", type="password")
            btn_redefinir = str_lit.form_submit_button("Atualizar Senha")

            if btn_redefinir:
                if not email_r.endswith("@engesp.com"):
                    str_lit.error("⚠️ E-mail inválido.")
                elif nova_senha_r != nova_senha_r2:
                    str_lit.error("⚠️ As senhas informadas não coincidem.")
                else:
                    df_existe = executar_query("SELECT email FROM usuarios WHERE email = :email", {"email": email_r})
                    if df_existe.empty:
                        str_lit.error("⚠️ E-mail não encontrado no banco de dados.")
                    else:
                        engine = get_engine()
                        with engine.begin() as conn:
                            conn.execute(text(
                                "UPDATE usuarios SET senha = :s WHERE email = :e"
                            ), {"s": hash_senha(nova_senha_r), "e": email_r})
                        registrar_auditoria("Redefinição de Senha", f"Senha alterada para {email_r}")
                        str_lit.success("Senha alterada com sucesso! Acesse pela aba 'Entrar'.")

else:
    filiais_nome_para_id, filiais_id_para_nome = get_filiais_dict()

    str_lit.sidebar.write(f"👤 Logado como: **{str_lit.session_state.usuario_logado}**")
    if str_lit.sidebar.button("🚪 Sair / Logout"):
        registrar_auditoria("Logout", "Usuário encerrou a sessão.")
        str_lit.session_state.autenticado = False
        str_lit.session_state.usuario_logado = None
        str_lit.rerun()

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
        "🏖️ Folga de Campo / Recesso",
    ]

    if str_lit.session_state.usuario_logado.lower() == ADMIN_EMAIL.lower():
        lista_modulos.append("🛡️️ Auditoria de Sistema")

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
    str_lit.sidebar.info("💾 **Status:** Dados salvos permanentemente na nuvem em tempo real.")

    # ---------------------------------------------------------
    # MÓDULO 1: DASHBOARD / CONSULTA
    # ---------------------------------------------------------
    if menu == "📊 Dashboard / Consulta":
        str_lit.title("📊 Painel de Gestão")
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
            df = executar_query(query)
        except Exception:
            df = pd.DataFrame()

        if not df.empty:
            opcoes_filiais_painel = ["Todas as Filiais"] + sorted(df["filial"].dropna().unique().tolist())
            filial_escolhida_painel = str_lit.selectbox("🏢 Selecione a Filial para Visualização:", opcoes_filiais_painel)
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
            str_lit.subheader(f"Registros Exibidos ({len(df)})")
            str_lit.dataframe(df, use_container_width=True)

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
                        engine = get_engine()
                        with engine.begin() as conn:
                            conn.execute(text(
                                "INSERT INTO filiais (nome, cnpj) VALUES (:n, :c)"
                            ), {"n": nome_f, "c": formatar_cnpj(cnpj_f)})
                        registrar_auditoria("Cadastro de Filial", f"Cadastrou a filial {nome_f}")
                        str_lit.success(f"Filial '{nome_f}' cadastrada com sucesso!")
                        str_lit.rerun()
                    except Exception:
                        str_lit.error("Erro: Filial já cadastrada.")

        str_lit.markdown("---")
        str_lit.subheader("Filiais Cadastradas e Gerenciamento")
        try:
            df_f_cad = executar_query("SELECT id, nome, cnpj FROM filiais ORDER BY nome")
        except Exception:
            df_f_cad = pd.DataFrame()

        if df_f_cad.empty:
            str_lit.info("Nenhuma filial cadastrada.")
        else:
            df_f_cad["cnpj"] = df_f_cad["cnpj"].apply(formatar_cnpj)
            str_lit.dataframe(df_f_cad, use_container_width=True)
            str_lit.markdown("---")
            str_lit.subheader("🗑️ Excluir Filial Cadastrada")
            str_lit.warning("⚠️ **Atenção:** Ao excluir uma filial, todos os colaboradores e dados vinculados a ela serão removidos.")

            filiais_dict_del, _ = get_filiais_dict()
            if filiais_dict_del:
                filial_para_deletar = str_lit.selectbox("Selecione a Filial que deseja excluir:", options=list(filiais_dict_del.keys()), key="select_del_filial")
                if str_lit.button("🗑️ Deletar Filial Selecionada", type="secondary"):
                    if filial_para_deletar:
                        f_id_del = filiais_dict_del[filial_para_deletar]
                        engine = get_engine()
                        with engine.begin() as conn:
                            conn.execute(text("DELETE FROM colaboradores WHERE filial_id = :fid"), {"fid": int(f_id_del)})
                            conn.execute(text("DELETE FROM importacoes_arquivos WHERE filial_id = :fid"), {"fid": int(f_id_del)})
                            conn.execute(text("DELETE FROM folga_campo_recesso WHERE filial_id = :fid"), {"fid": int(f_id_del)})
                            conn.execute(text("DELETE FROM filiais WHERE id = :fid"), {"fid": int(f_id_del)})
                        registrar_auditoria("Exclusão de Filial", f"Removeu a filial {filial_para_deletar}")
                        str_lit.success(f"Filial '{filial_para_deletar}' excluída com sucesso!")
                        str_lit.rerun()

    # ---------------------------------------------------------
    # MÓDULO 3: IMPORTAR COLABORADORES POR FILIAL
    # ---------------------------------------------------------
    elif menu == "📥 Importar Colaboradores por Filial":
        str_lit.title("📥 Importação de Colaboradores")
        str_lit.info(
            "💡 **Ordem obrigatória dos campos na planilha importada:**\n"
            "1. `MATRÍCULA` | 2. `TIPO` | 3. `SUBTIPO` | 4. `DATA MOVIMENTAÇÃO` | 5. `CARGO` | "
            "6. `DATA ADMISSÃO` | 7. `CPF` | 8. `RG` | 9. `OBSERVAÇÕES` | 10. `TIPO DE CONTRATAÇÃO` (CLT ou PJ)"
        )
        f_map_atual, _ = get_filiais_dict()
        if not f_map_atual:
            str_lit.warning("⚠️ Cadastre uma filial primeiro.")
        else:
            filial_imp = str_lit.selectbox("Selecione a Filial de Destino:", options=list(f_map_atual.keys()))
            filial_id_atual = f_map_atual[filial_imp]

            try:
                df_arq_salvo = executar_query("SELECT nome_arquivo, data_importacao FROM importacoes_arquivos WHERE filial_id = :fid", {"fid": int(filial_id_atual)})
            except Exception:
                df_arq_salvo = pd.DataFrame()

            if not df_arq_salvo.empty:
                row_arq = df_arq_salvo.iloc[0]
                str_lit.success(f"📂 **Planilha de colaboradores arquivada:** `{row_arq['nome_arquivo']}` (Importada em: {row_arq['data_importacao']})")
                if str_lit.button("🗑️ Apagar Lista e Colaboradores Desta Filial", type="secondary"):
                    engine = get_engine()
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM colaboradores WHERE filial_id = :fid"), {"fid": int(filial_id_atual)})
                        conn.execute(text("DELETE FROM importacoes_arquivos WHERE filial_id = :fid"), {"fid": int(filial_id_atual)})
                    registrar_auditoria("Limpeza de Filial", f"Apagou colaboradores da filial {filial_imp}")
                    str_lit.success("Colaboradores apagados com sucesso!")
                    str_lit.rerun()
                str_lit.markdown("---")

            arquivo_upload = str_lit.file_uploader("Envie a planilha (Excel .xlsx, .xls, .xlsm ou CSV):", type=["xlsx", "xls", "xlsm", "csv"])
            if arquivo_upload is not None:
                try:
                    nome_arq = arquivo_upload.name
                    bytes_arquivo = arquivo_upload.getvalue()
                    if nome_arq.lower().endswith(".csv"):
                        df_imp = pd.read_csv(io.BytesIO(bytes_arquivo))
                    else:
                        df_imp = pd.read_excel(io.BytesIO(bytes_arquivo), engine="openpyxl")

                    colunas_map_normalizado = {str(c).strip().upper(): c for c in df_imp.columns}
                    str_lit.write(f"Pré-visualização ({len(df_imp)} registros):")
                    str_lit.dataframe(df_imp.head(), use_container_width=True)

                    if str_lit.button("🚀 Processar e Salvar Dados"):
                        inseridos = 0
                        atualizados = 0
                        f_dict_rec, _ = get_filiais_dict()
                        f_id_dest = f_dict_rec.get(filial_imp)

                        engine = get_engine()
                        with engine.begin() as conn:
                            for _, r in df_imp.iterrows():
                                mat = str(r.get(colunas_map_normalizado.get("MATRÍCULA", "matricula"), r.get("MATRICULA", ""))).strip()
                                if not mat or mat.lower() == "nan":
                                    continue
                                tipo_v = str(r.get(colunas_map_normalizado.get("TIPO", "tipo"), "Entrada")).strip()
                                subtipo_v = str(r.get(colunas_map_normalizado.get("SUBTIPO", "subtipo"), "Admissão")).strip()
                                dt_mov_v = parse_data_rigorosa(r.get(colunas_map_normalizado.get("DATA MOVIMENTAÇÃO", "data movimentacao"), date.today()))
                                cargo_v = str(r.get(colunas_map_normalizado.get("CARGO", "cargo"), "")).strip()
                                dt_adm_v = parse_data_rigorosa(r.get(colunas_map_normalizado.get("DATA ADMISSÃO", "data admissao"), date.today()))
                                cpf_v = formatar_cpf(r.get(colunas_map_normalizado.get("CPF", "cpf"), ""))
                                rg_v = str(r.get(colunas_map_normalizado.get("RG", "rg"), "")).strip()
                                obs_v = str(r.get(colunas_map_normalizado.get("OBSERVAÇÕES", "observacoes"), "")).strip()
                                tipo_contr_v = str(r.get(colunas_map_normalizado.get("TIPO DE CONTRATAÇÃO", "tipo de contratacao"), "CLT")).strip()
                                if tipo_contr_v not in ["CLT", "PJ"]:
                                    tipo_contr_v = "CLT"

                                nome_col_chave = colunas_map_normalizado.get("NOME", colunas_map_normalizado.get("EMPREGADO", colunas_map_normalizado.get("FUNCIONÁRIO", None)))
                                nome_v = str(r.get(nome_col_chave, f"Colaborador {mat}")).strip() if nome_col_chave else f"Colaborador {mat}"

                                res_verif = conn.execute(text("SELECT id, status_colaborador FROM colaboradores WHERE matricula = :m"), {"m": mat}).fetchone()
                                if res_verif:
                                    st_atual = res_verif[1] if res_verif[1] else 'Ativo'
                                    conn.execute(text("""
                                        UPDATE colaboradores 
                                        SET nome = :n, tipo_movimentacao = :tm, subtipo_movimentacao = :stm, data_movimentacao = :dm, 
                                            funcao = :f, data_contratacao = :da, cpf = :cpf, rg = :rg, observacoes = :obs, 
                                            tipo_contratacao = :tc, filial_id = :fid, status_colaborador = :st
                                        WHERE matricula = :m
                                    """), {
                                        "n": nome_v, "tm": tipo_v, "stm": subtipo_v, "dm": dt_mov_v, "f": cargo_v,
                                        "da": dt_adm_v, "cpf": cpf_v, "rg": rg_v, "obs": obs_v, "tc": tipo_contr_v,
                                        "fid": int(f_id_dest), "st": st_atual, "m": mat
                                    })
                                    atualizados += 1
                                else:
                                    conn.execute(text("""
                                        INSERT INTO colaboradores (
                                            matricula, nome, tipo_movimentacao, subtipo_movimentacao, data_movimentacao, 
                                            funcao, data_contratacao, cpf, rg, observacoes, tipo_contratacao, 
                                            filial_id, status_colaborador, cnpj_empresa
                                        ) VALUES (:m, :n, :tm, :stm, :dm, :f, :da, :cpf, :rg, :obs, :tc, :fid, 'Ativo', :cnpj)
                                    """), {
                                        "m": mat, "n": nome_v, "tm": tipo_v, "stm": subtipo_v, "dm": dt_mov_v, "f": cargo_v,
                                        "da": dt_adm_v, "cpf": cpf_v, "rg": rg_v, "obs": obs_v, "tc": tipo_contr_v,
                                        "fid": int(f_id_dest), "cnpj": CNPJ_PADRAO
                                    })
                                    inseridos += 1

                            conn.execute(text("""
                                INSERT INTO importacoes_arquivos (filial_id, nome_arquivo, data_importacao, arquivo_blob)
                                VALUES (:fid, :na, :di, :ab)
                                ON CONFLICT (filial_id) DO UPDATE 
                                SET nome_arquivo = EXCLUDED.nome_arquivo, data_importacao = EXCLUDED.data_importacao, arquivo_blob = EXCLUDED.arquivo_blob
                            """), {"fid": int(f_id_dest), "na": nome_arq, "di": datetime.now(), "ab": bytes_arquivo})

                        registrar_auditoria("Importação Colaboradores", f"Filial {filial_imp}: {inseridos} novos, {atualizados} atualizados.")
                        str_lit.success(f"Importação realizada com sucesso! Novos: {inseridos} | Atualizados: {atualizados}")
                        str_lit.rerun()
                except Exception as e:
                    str_lit.error(f"Erro ao processar arquivo: {e}")

    # ---------------------------------------------------------
    # MÓDULO 4: TRANSFERÊNCIA ENTRE FILIAIS
    # ---------------------------------------------------------
    elif menu == "🔄 Transferência entre Filiais":
        str_lit.title("🔄 Transferência de Colaboradores entre Filiais")
        try:
            df_transf = executar_query("""
                SELECT c.matricula, c.nome, c.funcao as cargo, c.filial_id, f.nome as filial_nome
                FROM colaboradores c
                LEFT JOIN filiais f ON c.filial_id = f.id
                WHERE c.status_colaborador = 'Ativo'
                ORDER BY c.nome
            """)
        except Exception:
            df_transf = pd.DataFrame()

        if df_transf.empty or not filiais_nome_para_id:
            str_lit.info("⚠️ Nenhum colaborador ativo disponível ou filiais insuficientes.")
        else:
            lista_origens = sorted(df_transf["filial_nome"].dropna().unique().tolist())
            filial_origem_sel = str_lit.selectbox("🏢 1. Selecione a Filial de Origem:", options=lista_origens)
            df_origem_colab = df_transf[df_transf["filial_nome"] == filial_origem_sel].copy()
            df_origem_colab.insert(0, "Selecionar", False)
            df_tabela_exibicao = df_origem_colab[["Selecionar", "matricula", "nome", "cargo"]].rename(columns={"matricula": "Matrícula", "nome": "Nome do Colaborador", "cargo": "Cargo"})
            
            df_selecionados_editor = str_lit.data_editor(df_tabela_exibicao, column_config={"Selecionar": str_lit.column_config.CheckboxColumn("Selecionar", required=True)}, hide_index=True, use_container_width=True)
            matriculas_selecionadas = df_selecionados_editor[df_selecionados_editor["Selecionar"] == True]["Matrícula"].tolist()

            str_lit.markdown("---")
            lista_dest = [f for f in list(filiais_nome_para_id.keys()) if f != filial_origem_sel]
            if lista_dest:
                filial_destino = str_lit.selectbox("🏢 2. Selecione a Filial de Destino:", options=lista_dest)
                data_transf = str_lit.date_input("Data da Transferência", value=date.today(), format="DD/MM/YYYY")
                if str_lit.button("🔄 Efetivar e Salvar Transferência", type="primary"):
                    if not matriculas_selecionadas:
                        str_lit.error("Selecione pelo menos um colaborador.")
                    else:
                        nova_filial_id = filiais_nome_para_id[filial_destino]
                        engine = get_engine()
                        with engine.begin() as conn:
                            for mat_t in matriculas_selecionadas:
                                conn.execute(text("""
                                    UPDATE colaboradores
                                    SET filial_id = :fid, tipo_movimentacao = 'Entrada', subtipo_movimentacao = 'Transferência', data_movimentacao = :dm
                                    WHERE matricula = :m
                                """), {"fid": int(nova_filial_id), "dm": str(data_transf), "m": mat_t})
                        registrar_auditoria("Transferencia em Lote", f"{len(matriculas_selecionadas)} transferidos para {filial_destino}")
                        str_lit.success("Transferência realizada com sucesso!")
                        str_lit.rerun()

    # ---------------------------------------------------------
    # MÓDULO 5: COLABORADORES
    # ---------------------------------------------------------
    elif menu == "👥 Colaboradores":
        str_lit.title("👥 Resumo Consolidado de Colaboradores")
        aba_ativos, aba_demitidos = str_lit.tabs(["🟢 Colaboradores Ativos", "🔴 Colaboradores Demitidos"])

        with aba_ativos:
            try:
                df_filiais_colab = executar_query("SELECT id, nome FROM filiais ORDER BY nome")
            except Exception:
                df_filiais_colab = pd.DataFrame()

            if df_filiais_colab.empty:
                str_lit.warning("⚠️ Nenhuma filial cadastrada.")
            else:
                lista_nomes_f = ["Todas as Filiais"] + df_filiais_colab["nome"].tolist()
                filial_escolhida_colab_mod = str_lit.selectbox("🏢 Selecione a Filial (Ativos):", lista_nomes_f, key="sel_filial_ativos")
                try:
                    if filial_escolhida_colab_mod == "Todas as Filiais":
                        df_res = executar_query("""
                            SELECT c.matricula as "MATRÍCULA", c.nome as "NOME COMPLETO", f.nome as "FILIAL",
                                   c.tipo_movimentacao as "TIPO", c.subtipo_movimentacao as "SUBTIPO",
                                   c.data_movimentacao as "DATA MOVIMENTAÇÃO", c.funcao as "CARGO",
                                   c.data_contratacao as "DATA ADMISSÃO", c.cpf as "CPF", c.rg as "RG",
                                   c.observacoes as "OBSERVAÇÕES", c.tipo_contratacao as "TIPO DE CONTRATAÇÃO",
                                   c.he_50 as "HE 50%", c.he_100 as "HE 100%", c.periculosidade as "PERICULOSIDADE",
                                   c.ajuda_custo as "AJUDA DE CUSTO (R$)", c.filial_id
                            FROM colaboradores c
                            LEFT JOIN filiais f ON c.filial_id = f.id
                            WHERE c.status_colaborador = 'Ativo'
                            ORDER BY c.nome
                        """)
                    else:
                        f_id_sel = filiais_nome_para_id[filial_escolhida_colab_mod]
                        df_res = executar_query("""
                            SELECT c.matricula as "MATRÍCULA", c.nome as "NOME COMPLETO", f.nome as "FILIAL",
                                   c.tipo_movimentacao as "TIPO", c.subtipo_movimentacao as "SUBTIPO",
                                   c.data_movimentacao as "DATA MOVIMENTAÇÃO", c.funcao as "CARGO",
                                   c.data_contratacao as "DATA ADMISSÃO", c.cpf as "CPF", c.rg as "RG",
                                   c.observacoes as "OBSERVAÇÕES", c.tipo_contratacao as "TIPO DE CONTRATAÇÃO",
                                   c.he_50 as "HE 50%", c.he_100 as "HE 100%", c.periculosidade as "PERICULOSIDADE",
                                   c.ajuda_custo as "AJUDA DE CUSTO (R$)", c.filial_id
                            FROM colaboradores c
                            LEFT JOIN filiais f ON c.filial_id = f.id
                            WHERE c.filial_id = :fid AND c.status_colaborador = 'Ativo'
                            ORDER BY c.nome
                        """, {"fid": int(f_id_sel)})
                except Exception:
                    df_res = pd.DataFrame()

                if df_res.empty:
                    str_lit.info("ℹ️ Nenhum colaborador ativo.")
                else:
                    for col_d in ["DATA MOVIMENTAÇÃO", "DATA ADMISSÃO"]:
                        if col_d in df_res.columns:
                            df_res[col_d] = df_res[col_d].apply(formatar_data_br)
                    if "CPF" in df_res.columns:
                        df_res["CPF"] = df_res["CPF"].apply(formatar_cpf)

                    proximas_folgas = [calcular_ultima_folga_colaborador(r["filial_id"], r["MATRÍCULA"]) for _, r in df_res.iterrows()]
                    df_res.insert(3, "PRÓXIMA FOLGA DE CAMPO", proximas_folgas)
                    df_res.insert(0, "Demitir?", False)
                    df_para_editar = df_res.drop(columns=["filial_id"]).copy()

                    df_editado_colab = str_lit.data_editor(df_para_editar, column_config={
                        "Demitir?": str_lit.column_config.CheckboxColumn("Demitir?", required=True),
                        "MATRÍCULA": str_lit.column_config.TextColumn("MATRÍCULA", disabled=True),
                        "FILIAL": str_lit.column_config.TextColumn("FILIAL", disabled=True),
                        "PRÓXIMA FOLGA DE CAMPO": str_lit.column_config.TextColumn("PRÓXIMA FOLGA DE CAMPO", disabled=True),
                        "TIPO DE CONTRATAÇÃO": str_lit.column_config.SelectboxColumn("TIPO DE CONTRATAÇÃO", options=["CLT", "PJ"], required=True),
                        "PERICULOSIDADE": str_lit.column_config.SelectboxColumn("PERICULOSIDADE", options=["Sim", "Não"], required=True),
                        "AJUDA DE CUSTO (R$)": str_lit.column_config.NumberColumn("AJUDA DE CUSTO (R$)", format="R$ %.2f"),
                        "HE 50%": str_lit.column_config.NumberColumn("HE 50%", disabled=True),
                        "HE 100%": str_lit.column_config.NumberColumn("HE 100%", disabled=True),
                    }, hide_index=True, use_container_width=True)

                    c_b_salvar, c_b_demitir = str_lit.columns(2)
                    with c_b_salvar:
                        if str_lit.button("💾 Salvar Alterações dos Ativos", type="primary"):
                            engine = get_engine()
                            with engine.begin() as conn:
                                for _, row in df_editado_colab.iterrows():
                                    conn.execute(text("""
                                        UPDATE colaboradores 
                                        SET nome = :n, tipo_movimentacao = :tm, subtipo_movimentacao = :stm, data_movimentacao = :dm,
                                            funcao = :f, data_contratacao = :da, cpf = :cpf, rg = :rg, observacoes = :obs,
                                            tipo_contratacao = :tc, periculosidade = :p, ajuda_custo = :ac
                                        WHERE matricula = :m
                                    """), {
                                        "n": row["NOME COMPLETO"], "tm": row["TIPO"], "stm": row["SUBTIPO"], "dm": parse_data_rigorosa(row["DATA MOVIMENTAÇÃO"]),
                                        "f": row["CARGO"], "da": parse_data_rigorosa(row["DATA ADMISSÃO"]), "cpf": formatar_cpf(row["CPF"]), "rg": row["RG"],
                                        "obs": row["OBSERVAÇÕES"], "tc": row["TIPO DE CONTRATAÇÃO"], "p": row["PERICULOSIDADE"], "ac": row["AJUDA DE CUSTO (R$)"], "m": row["MATRÍCULA"]
                                    })
                            registrar_auditoria("Edição Resumo", "Atualizou dados consolidados.")
                            str_lit.success("Salvo com sucesso!")
                            str_lit.rerun()

                    with c_b_demitir:
                        if str_lit.button("🔴 Enviar Selecionados para Demitidos", type="secondary"):
                            mats_dem = df_editado_colab[df_editado_colab["Demitir?"] == True]["MATRÍCULA"].tolist()
                            if mats_dem:
                                engine = get_engine()
                                with engine.begin() as conn:
                                    for mat_d in mats_dem:
                                        conn.execute(text("UPDATE colaboradores SET status_colaborador = 'Demitido', data_demissao = :dt WHERE matricula = :m"), {"dt": str(date.today()), "m": mat_d})
                                registrar_auditoria("Demissão", f"Moveu {len(mats_dem)} para demitidos.")
                                str_lit.success("Colaboradores movidos para demitidos!")
                                str_lit.rerun()

        with aba_demitidos:
            str_lit.subheader("🔴 Colaboradores Demitidos")
            try:
                df_dem = executar_query("""
                    SELECT c.matricula as "MATRÍCULA", c.nome as "NOME COMPLETO", f.nome as "FILIAL",
                           c.funcao as "CARGO", c.data_contratacao as "DATA ADMISSÃO", c.data_demissao as "DATA DEMISSÃO", 
                           c.cpf as "CPF", c.observacoes as "OBSERVAÇÕES", c.tipo_contratacao as "CONTRATAÇÃO"
                    FROM colaboradores c
                    LEFT JOIN filiais f ON c.filial_id = f.id
                    WHERE c.status_colaborador = 'Demitido'
                    ORDER BY c.nome
                """)
            except Exception:
                df_dem = pd.DataFrame()

            if df_dem.empty:
                str_lit.info("ℹ️ Nenhum colaborador demitido.")
            else:
                for col_d in ["DATA ADMISSÃO", "DATA DEMISSÃO"]:
                    if col_d in df_dem.columns:
                        df_dem[col_d] = df_dem[col_d].apply(formatar_data_br)
                if "CPF" in df_dem.columns:
                    df_dem["CPF"] = df_dem["CPF"].apply(formatar_cpf)

                df_editado_dem = str_lit.data_editor(df_dem, column_config={
                    "MATRÍCULA": str_lit.column_config.TextColumn("MATRÍCULA", disabled=True),
                    "NOME COMPLETO": str_lit.column_config.TextColumn("NOME COMPLETO", disabled=True),
                    "FILIAL": str_lit.column_config.TextColumn("FILIAL", disabled=True),
                    "CARGO": str_lit.column_config.TextColumn("CARGO", disabled=True),
                    "DATA ADMISSÃO": str_lit.column_config.TextColumn("DATA ADMISSÃO", disabled=True),
                    "DATA DEMISSÃO": str_lit.column_config.TextColumn("DATA DEMISSÃO (DD/MM/AAAA)", required=True),
                }, hide_index=True, use_container_width=True)

                if str_lit.button("💾 Salvar Alterações dos Demitidos", type="primary"):
                    engine = get_engine()
                    with engine.begin() as conn:
                        for _, row in df_editado_dem.iterrows():
                            conn.execute(text("UPDATE colaboradores SET data_demissao = :dt WHERE matricula = :m"), {"dt": parse_data_rigorosa(row["DATA DEMISSÃO"]), "m": row["MATRÍCULA"]})
                    str_lit.success("Datas de demissão salvas!")
                    str_lit.rerun()

    # ---------------------------------------------------------
    # MÓDULO 6: NOVO COLABORADOR / ADMISSÃO
    # ---------------------------------------------------------
    elif menu == "➕ Novo Colaborador / Admissão":
        str_lit.title("➕ Admissão / Movimentação de Empregado")
        if not filiais_nome_para_id:
            str_lit.warning("⚠️ Cadastre pelo menos uma filial.")
        else:
            c_fil, c1, c2 = str_lit.columns(3)
            filial_nome = c_fil.selectbox("Filial *", options=list(filiais_nome_para_id.keys()))
            empregado = c1.text_input("Empregado (Nome Completo) *")
            matricula = c2.text_input("Matrícula *")

            c_t1, c_t2, c_t3 = str_lit.columns(3)
            tipo_mov = c_t1.selectbox("Tipo *", options=["Entrada", "Saída"])
            subtipo_mov = c_t2.text_input("Subtipo *", value="Admissão")
            data_mov = c_t3.date_input("Data da Movimentação *", format="DD/MM/YYYY")

            c3, c4, c5 = str_lit.columns(3)
            cargo = c3.text_input("Cargo *")
            data_admissao = c4.date_input("Data de Admissão *", format="DD/MM/YYYY")
            tipo_contratacao = c5.selectbox("Tipo de Contratação *", options=["CLT", "PJ"])

            c6, c7 = str_lit.columns(2)
            cpf = c6.text_input("CPF")
            rg = c7.text_input("RG")

            c8, c9 = str_lit.columns(2)
            periculosidade_in = c8.selectbox("Periculosidade", options=["Não", "Sim"])
            ajuda_custo_in = c9.number_input("Ajuda de Custo (R$)", min_value=0.0, value=0.0, format="%.2f")
            observacoes = str_lit.text_area("Observações")

            if str_lit.button("💾 Salvar Cadastro Permanentemente"):
                if not matricula or not empregado:
                    str_lit.error("Preencha Empregado e Matrícula.")
                else:
                    try:
                        engine = get_engine()
                        with engine.begin() as conn:
                            conn.execute(text("""
                                INSERT INTO colaboradores (
                                    matricula, nome, tipo_movimentacao, subtipo_movimentacao, data_movimentacao,
                                    funcao, data_contratacao, cpf, rg, observacoes, tipo_contratacao,
                                    periculosidade, ajuda_custo, filial_id, status_colaborador, cnpj_empresa
                                ) VALUES (:m, :n, :tm, :stm, :dm, :f, :da, :cpf, :rg, :obs, :tc, :p, :ac, :fid, 'Ativo', :cnpj)
                            """), {
                                "m": matricula, "n": empregado, "tm": tipo_mov, "stm": subtipo_mov, "dm": str(data_mov),
                                "f": cargo, "da": str(data_admissao), "cpf": formatar_cpf(cpf), "rg": rg, "obs": observacoes,
                                "tc": tipo_contratacao, "p": periculosidade_in, "ac": ajuda_custo_in, "fid": int(filiais_nome_para_id[filial_nome]), "cnpj": CNPJ_PADRAO
                            })
                        registrar_auditoria("Novo Colaborador", f"Cadastrou {empregado}")
                        str_lit.success("Colaborador cadastrado com sucesso!")
                    except Exception:
                        str_lit.error("Erro: Matrícula já cadastrada.")

    # ---------------------------------------------------------
    # MÓDULO 7: EDITAR CADASTRO DO COLABORADOR
    # ---------------------------------------------------------
    elif menu == "✏️ Editar Cadastro do Colaborador":
        str_lit.title("✏️ Editar Cadastro Individual do Colaborador")
        try:
            df_colab_geral = executar_query("SELECT c.matricula, c.nome, c.funcao as cargo, f.nome as filial FROM colaboradores c LEFT JOIN filiais f ON c.filial_id = f.id ORDER BY c.nome")
        except Exception:
            df_colab_geral = pd.DataFrame()

        if df_colab_geral.empty:
            str_lit.info("⚠️ Nenhum colaborador cadastrado.")
        else:
            lista_filiais_ed = ["Todas as Filiais"] + sorted(df_colab_geral["filial"].dropna().unique().tolist())
            filial_filtro_ed = str_lit.selectbox("🏢 Filtrar por Filial:", options=lista_filiais_ed, key="filtro_edicao_filial")
            if filial_filtro_ed != "Todas as Filiais":
                df_colab_geral = df_colab_geral[df_colab_geral["filial"] == filial_filtro_ed]

            if not df_colab_geral.empty:
                opcoes_colab = df_colab_geral["matricula"] + " - " + df_colab_geral["nome"] + " (" + df_colab_geral["filial"].fillna("Sem Filial") + ")"
                colab_sel = str_lit.selectbox("Selecione o Colaborador:", options=opcoes_colab)
                if colab_sel:
                    mat_sel = colab_sel.split(" - ")[0]
                    df_det = executar_query("SELECT * FROM colaboradores WHERE matricula = :m", {"m": mat_sel})
                    if not df_det.empty:
                        row_d = df_det.iloc[0]
                        with str_lit.form("form_edicao_individual"):
                            n_nome = str_lit.text_input("Nome Completo", value=str(row_d["nome"] or ""))
                            n_cargo = str_lit.text_input("Cargo", value=str(row_d["funcao"] or ""))
                            n_cpf = str_lit.text_input("CPF", value=formatar_cpf(row_d["cpf"]))
                            n_rg = str_lit.text_input("RG", value=str(row_d["rg"] or ""))
                            n_peric = str_lit.selectbox("Periculosidade", options=["Não", "Sim"], index=0 if str(row_d["periculosidade"]) == "Não" else 1)
                            n_ajuda = str_lit.number_input("Ajuda de Custo (R$)", value=float(row_d["ajuda_custo"] or 0.0), format="%.2f")
                            n_status = str_lit.selectbox("Status", options=["Ativo", "Demitido"], index=0 if str(row_d["status_colaborador"]) == "Ativo" else 1)
                            n_obs = str_lit.text_area("Observações", value=str(row_d["observacoes"] or ""))

                            if str_lit.form_submit_button("💾 Salvar Alterações"):
                                engine = get_engine()
                                with engine.begin() as conn:
                                    conn.execute(text("""
                                        UPDATE colaboradores 
                                        SET nome = :n, funcao = :f, cpf = :cpf, rg = :rg, periculosidade = :p, ajuda_custo = :ac, status_colaborador = :st, observacoes = :obs
                                        WHERE matricula = :m
                                    """), {"n": n_nome, "f": n_cargo, "cpf": formatar_cpf(n_cpf), "rg": n_rg, "p": n_peric, "ac": n_ajuda, "st": n_status, "obs": n_obs, "m": mat_sel})
                                registrar_auditoria("Edição Individual", f"Atualizou {mat_sel}")
                                str_lit.success("Atualizado com sucesso!")
                                str_lit.rerun()

    # ---------------------------------------------------------
    # MÓDULO 8: PEDIDO SALDO ALIMENTAÇÃO
    # ---------------------------------------------------------
    elif menu == "💳 Pedido Saldo Alimentação":
        str_lit.title("💳 Gestão e Histórico de Saldo Alimentação / VA")
        aba_saldos, aba_historico_pedidos = str_lit.tabs(["📝 Gestão de Saldos Atuais", "📜 Histórico de Pedidos"])

        with aba_saldos:
            f_map, _ = get_filiais_dict()
            if not f_map:
                str_lit.warning("⚠️ Cadastre filiais primeiro.")
            else:
                c_fil_va, c_mes_va, c_ano_va = str_lit.columns(3)
                filial_va = c_fil_va.selectbox("Selecione a Filial:", options=list(f_map.keys()), key="sel_filial_va")
                f_id = f_map[filial_va]

                meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
                mes_va = c_mes_va.selectbox("Mês:", options=meses_lista, index=datetime.now().month - 1)
                ano_va = c_ano_va.number_input("Ano:", min_value=2020, max_value=2100, value=datetime.now().year)
                mes_ano_str = f"{mes_va} de {ano_va}"

                try:
                    df_va_raw = executar_query("SELECT cnpj_empresa, nome, cpf, premiacao, mobilidade, alimentacao, tipo_usuario_va, matricula FROM colaboradores WHERE filial_id = :fid AND status_colaborador = 'Ativo' ORDER BY nome", {"fid": int(f_id)})
                except Exception:
                    df_va_raw = pd.DataFrame()

                if df_va_raw.empty:
                    str_lit.info("ℹ️ Nenhum colaborador ativo.")
                else:
                    lista_linhas_estruturadas = []
                    for _, row in df_va_raw.iterrows():
                        lista_linhas_estruturadas.append({
                            "Exportar?": True,
                            "CNPJ": formatar_cnpj(row["cnpj_empresa"]),
                            "NOME COMPLETO": row["nome"],
                            "CPF": formatar_cpf(row["cpf"]),
                            "OBRA": filial_va,
                            "PREMIACAO": float(row["premiacao"] or 0.0),
                            "MOBILIDADE": float(row["mobilidade"] or 0.0),
                            "ALIMENTACAO": float(row["alimentacao"] or 0.0),
                            "TAGS": row["tipo_usuario_va"] if row["tipo_usuario_va"] in ["Já Usuário", "Novo"] else "Já Usuário",
                            "_matricula": row["matricula"]
                        })

                    df_va_final = pd.DataFrame(lista_linhas_estruturadas)
                    df_va_editado = str_lit.data_editor(df_va_final.drop(columns=["_matricula"]), column_config={
                        "Exportar?": str_lit.column_config.CheckboxColumn("Exportar?", required=True),
                        "CNPJ": str_lit.column_config.TextColumn("CNPJ", disabled=True),
                        "NOME COMPLETO": str_lit.column_config.TextColumn("NOME COMPLETO", disabled=True),
                        "CPF": str_lit.column_config.TextColumn("CPF", disabled=True),
                        "OBRA": str_lit.column_config.TextColumn("OBRA", disabled=True),
                        "PREMIACAO": str_lit.column_config.NumberColumn("PREMIACAO (R$)", format="R$ %.2f"),
                        "MOBILIDADE": str_lit.column_config.NumberColumn("MOBILIDADE (R$)", format="R$ %.2f"),
                        "ALIMENTACAO": str_lit.column_config.NumberColumn("ALIMENTACAO (R$)", format="R$ %.2f"),
                        "TAGS": str_lit.column_config.SelectboxColumn("TAGS", options=["Já Usuário", "Novo"], required=True)
                    }, hide_index=True, use_container_width=True)

                    c_btn1, c_btn2 = str_lit.columns(2)
                    with c_btn1:
                        if str_lit.button("💾 Salvar Alterações e Registrar Pedido", type="primary"):
                            engine = get_engine()
                            with engine.begin() as conn:
                                for idx, row in df_va_editado.iterrows():
                                    mat_real = df_va_final.iloc[idx]["_matricula"]
                                    conn.execute(text("""
                                        UPDATE colaboradores 
                                        SET premiacao = :pr, mobilidade = :mb, alimentacao = :al, tipo_usuario_va = :tu
                                        WHERE matricula = :m
                                    """), {"pr": row["PREMIACAO"], "mb": row["MOBILIDADE"], "al": row["ALIMENTACAO"], "tu": row["TAGS"], "m": mat_real})
                                
                                dados_json_ped = df_va_editado.to_json(orient="records", force_ascii=False)
                                conn.execute(text("""
                                    INSERT INTO historico_pedidos_va (mes_ano, obra, data_geracao, dados_json)
                                    VALUES (:ma, :ob, :dg, :dj)
                                """), {"ma": mes_ano_str, "ob": filial_va, "dg": datetime.now(), "dj": dados_json_ped})
                            registrar_auditoria("Pedido VA", f"Registrou pedido de VA da filial {filial_va}")
                            str_lit.success("Salvo com sucesso!")
                            str_lit.rerun()

                    with c_btn2:
                        df_para_excel = df_va_editado[df_va_editado["Exportar?"] == True].copy()
                        if "Exportar?" in df_para_excel.columns:
                            df_para_excel = df_para_excel.drop(columns=["Exportar?"])
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_para_excel.to_excel(writer, index=False, sheet_name='Pedido VA')
                        str_lit.download_button(
                            label="📥 Exportar Excel (.xlsx)",
                            data=output.getvalue(),
                            file_name=f"Pedido_VA_{filial_va}_{mes_va}_{ano_va}.xlsx".replace(" ", "_"),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

        with aba_historico_pedidos:
            str_lit.subheader("📜 Histórico de Pedidos")
            try:
                df_hist = executar_query("SELECT id, mes_ano, obra, data_geracao FROM historico_pedidos_va ORDER BY data_geracao DESC")
            except Exception:
                df_hist = pd.DataFrame()
            if df_hist.empty:
                str_lit.info("ℹ️ Nenhum histórico.")
            else:
                str_lit.dataframe(df_hist, use_container_width=True)

    # ---------------------------------------------------------
    # MÓDULO 9: FOLHA DE PONTO
    # ---------------------------------------------------------
    elif menu == "⏱️ Folha de Ponto":
        str_lit.title("⏱️ Controle de Folha de Ponto e Horas Extras")
        try:
            df_ponto = executar_query("SELECT c.matricula as \"Matrícula\", c.nome as \"Empregado\", f.nome as \"Filial\" FROM colaboradores c LEFT JOIN filiais f ON c.filial_id = f.id WHERE c.status_colaborador = 'Ativo' ORDER BY c.nome")
        except Exception:
            df_ponto = pd.DataFrame()

        if df_ponto.empty:
            str_lit.info("⚠️ Nenhum colaborador ativo.")
        else:
            lista_filiais_ponto = sorted(df_ponto["Filial"].dropna().unique().tolist())
            filial_escolhida_ponto = str_lit.selectbox("🏢 1. Selecione a Filial / Obra:", options=lista_filiais_ponto)
            df_ponto_filtrado = df_ponto[df_ponto["Filial"] == filial_escolhida_ponto]

            if not df_ponto_filtrado.empty:
                colab_ponto = str_lit.selectbox("👥 2. Selecione o Colaborador:", options=df_ponto_filtrado["Matrícula"] + " - " + df_ponto_filtrado["Empregado"])
                matricula_atual = colab_ponto.split(" - ")[0]

                c_mes_p, c_ano_p = str_lit.columns(2)
                meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
                mes_escolhido = c_mes_p.selectbox("Mês:", options=meses_lista, index=datetime.now().month - 1)
                ano_escolhido = c_ano_p.number_input("Ano:", min_value=2020, max_value=2100, value=datetime.now().year)
                mes_num = meses_lista.index(mes_escolhido) + 1
                mes_ano_str = f"{mes_escolhido} de {ano_escolhido}"

                proximo_mes = datetime(ano_escolhido + 1, 1, 1) if mes_num == 12 else datetime(ano_escolhido, mes_num + 1, 1)
                ultimo_dia = (proximo_mes - timedelta(days=1)).day
                nomes_dias_semana = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
                feriados_do_ano = obter_feriados_nacionais(int(ano_escolhido))

                df_salvo_ponto = executar_query("SELECT dados_json FROM folha_ponto WHERE matricula = :m AND mes_ano = :ma", {"m": matricula_atual, "ma": mes_ano_str})
                dados_anteriores = json.loads(df_salvo_ponto.iloc[0]["dados_json"]) if not df_salvo_ponto.empty and df_salvo_ponto.iloc[0]["dados_json"] else {}

                lista_linhas_dias = []
                for dia in range(1, ultimo_dia + 1):
                    dt_d = date(int(ano_escolhido), mes_num, dia)
                    dia_sem = nomes_dias_semana[dt_d.weekday()]
                    eh_fer = dt_d in feriados_do_ano
                    tipo_d = f"Feriado ({dia_sem})" if eh_fer else dia_sem
                    col_n = f"Dia {dia:02d} ({dt_d.strftime('%d/%m')})"
                    lista_linhas_dias.append({"Dia": col_n, "Tipo": tipo_d, "Horas": str(dados_anteriores.get(col_n, "0"))})

                df_edit_ponto = str_lit.data_editor(pd.DataFrame(lista_linhas_dias), hide_index=True, use_container_width=True)
                total_50 = 0.0
                total_100 = 0.0
                dicionario_salvar = {}

                for _, row in df_edit_ponto.iterrows():
                    qtd = converter_hora_flexivel(row["Horas"])
                    dicionario_salvar[row["Dia"]] = row["Horas"]
                    if "Domingo" in row["Tipo"] or "Feriado" in row["Tipo"]:
                        total_100 += qtd
                    else:
                        total_50 += qtd

                str_lit.metric("Total HE 50%", f"{total_50:.2f} h")
                str_lit.metric("Total HE 100%", f"{total_100:.2f} h")

                if str_lit.button("💾 Salvar Folha de Ponto", type="primary"):
                    engine = get_engine()
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM folha_ponto WHERE matricula = :m AND mes_ano = :ma"), {"m": matricula_atual, "ma": mes_ano_str})
                        conn.execute(text("INSERT INTO folha_ponto (matricula, mes_ano, total_50, total_100, dados_json) VALUES (:m, :ma, :t50, :t100, :dj)"), {
                            "m": matricula_atual, "ma": mes_ano_str, "t50": total_50, "t100": total_100, "dj": json.dumps(dicionario_salvar)
                        })
                        conn.execute(text("UPDATE colaboradores SET he_50 = :t50, he_100 = :t100 WHERE matricula = :m"), {"t50": total_50, "t100": total_100, "m": matricula_atual})
                    registrar_auditoria("Folha de Ponto", f"Ponto salvo para {matricula_atual}")
                    str_lit.success("Salvo com sucesso!")

    # ---------------------------------------------------------
    # MÓDULO 10: FOLGA DE CAMPO / RECESSO
    # ---------------------------------------------------------
    elif menu == "🏖️ Folga de Campo / Recesso":
        str_lit.title("🏖️ Controle de Folga de Campo / Recesso")
        f_map_folga, _ = get_filiais_dict()
        if not f_map_folga:
            str_lit.warning("⚠️ Cadastre uma filial primeiro.")
        else:
            filial_folga_sel = str_lit.selectbox("🏢 Selecione a Filial / Obra:", options=list(f_map_folga.keys()), key="sel_filial_folga")
            f_id_folga = f_map_folga[filial_folga_sel]

            try:
                df_f_db = executar_query("SELECT dados_json FROM folga_campo_recesso WHERE filial_id = :fid", {"fid": int(f_id_folga)})
            except Exception:
                df_f_db = pd.DataFrame()

            df_trabalho = pd.DataFrame()
            if not df_f_db.empty and df_f_db.iloc[0]["dados_json"]:
                try:
                    df_trabalho = pd.read_json(io.StringIO(df_f_db.iloc[0]["dados_json"]))
                except Exception:
                    pass

            if df_trabalho.empty:
                try:
                    df_colabs_filial = executar_query("SELECT matricula, nome FROM colaboradores WHERE filial_id = :fid AND status_colaborador = 'Ativo'", {"fid": int(f_id_folga)})
                except Exception:
                    df_colabs_filial = pd.DataFrame()

                linhas_iniciais = []
                for _, rc in df_colabs_filial.iterrows():
                    linhas_iniciais.append({
                        "MATRÍCULA": str(rc["matricula"]), "NOME COMPLETO": rc["nome"], "OBRA": filial_folga_sel,
                        "1° FOLGA": "", "CHEGOU DA 1° FOLGA": "", "2° FOLGA": "", "CHEGOU DA 2° FOLGA": "", "3° FOLGA": ""
                    })
                df_trabalho = pd.DataFrame(linhas_iniciais)

            if df_trabalho.empty:
                str_lit.info("ℹ️ Nenhum colaborador ativo nesta filial.")
            else:
                c_op1, c_op2 = str_lit.columns(2)
                dias_intervalo_1 = c_op1.selectbox("Intervalo 1ª para 2ª (dias):", options=[29, 59, 89], index=1)
                dias_intervalo_2 = c_op2.selectbox("Intervalo 2ª para 3ª (dias):", options=[29, 59, 89], index=2)

                if str_lit.button("⚡ Aplicar Fórmulas Automáticas"):
                    for idx, row in df_trabalho.iterrows():
                        f1_str = str(row.get("1° FOLGA", "")).strip()
                        if f1_str and f1_str not in ["None", "nan", "-"]:
                            try:
                                dt1 = datetime.strptime(parse_data_rigorosa(f1_str), "%Y-%m-%d").date()
                                df_trabalho.loc[idx, "2° FOLGA"] = (dt1 + timedelta(days=dias_intervalo_1)).strftime("%d/%m/%Y")
                            except Exception:
                                pass
                        f2_str = str(row.get("2° FOLGA", "")).strip()
                        if f2_str and f2_str not in ["None", "nan", "-"]:
                            try:
                                dt2 = datetime.strptime(parse_data_rigorosa(f2_str), "%Y-%m-%d").date()
                                df_trabalho.loc[idx, "3° FOLGA"] = (dt2 + timedelta(days=dias_intervalo_2)).strftime("%d/%m/%Y")
                            except Exception:
                                pass
                    str_lit.success("Fórmulas aplicadas!")

                df_edit_folga = str_lit.data_editor(df_trabalho, column_config={
                    "MATRÍCULA": str_lit.column_config.TextColumn("MATRÍCULA", disabled=True),
                    "NOME COMPLETO": str_lit.column_config.TextColumn("NOME COMPLETO", disabled=True),
                    "OBRA": str_lit.column_config.TextColumn("OBRA", disabled=True),
                    "1° FOLGA": str_lit.column_config.TextColumn("1° FOLGA (DD/MM/AAAA)"),
                    "CHEGOU DA 1° FOLGA": str_lit.column_config.TextColumn("CHEGOU DA 1° FOLGA (DD/MM/AAAA)"),
                    "2° FOLGA": str_lit.column_config.TextColumn("2° FOLGA (DD/MM/AAAA)"),
                    "CHEGOU DA 2° FOLGA": str_lit.column_config.TextColumn("CHEGOU DA 2° FOLGA (DD/MM/AAAA)"),
                    "3° FOLGA": str_lit.column_config.TextColumn("3° FOLGA (DD/MM/AAAA)"),
                }, hide_index=True, use_container_width=True)

                c_b1, c_b2, c_b3 = str_lit.columns(3)
                with c_b1:
                    if str_lit.button("💾 Salvar Folgas", type="primary"):
                        json_str_folga = df_edit_folga.to_json(orient="records", force_ascii=False)
                        engine = get_engine()
                        with engine.begin() as conn:
                            conn.execute(text("""
                                INSERT INTO folga_campo_recesso (filial_id, nome_arquivo, data_importacao, dados_json)
                                VALUES (:fid, :na, :di, :dj)
                                ON CONFLICT (filial_id) DO UPDATE 
                                SET nome_arquivo = EXCLUDED.nome_arquivo, data_importacao = EXCLUDED.data_importacao, dados_json = EXCLUDED.dados_json
                            """), {"fid": int(f_id_folga), "na": f"Controle_Folga_{filial_folga_sel}.xlsx", "di": datetime.now(), "dj": json_str_folga})
                        registrar_auditoria("Folga de Campo Salva", f"Atualizou folgas da filial {filial_folga_sel}")
                        str_lit.success("Salvo com sucesso!")
                        str_lit.rerun()

                with c_b2:
                    output_f = io.BytesIO()
                    with pd.ExcelWriter(output_f, engine='openpyxl') as writer:
                        df_edit_folga.to_excel(writer, index=False, sheet_name='Folga de Campo')
                    str_lit.download_button(label="📥 Exportar Excel", data=output_f.getvalue(), file_name=f"Folga_Campo_{filial_folga_sel}.xlsx".replace(" ", "_"), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                with c_b3:
                    if str_lit.button("🗑️ Apagar Registros", type="secondary"):
                        engine = get_engine()
                        with engine.begin() as conn:
                            conn.execute(text("DELETE FROM folga_campo_recesso WHERE filial_id = :fid"), {"fid": int(f_id_folga)})
                        registrar_auditoria("Limpeza Folga", f"Removeu folgas da filial {filial_folga_sel}")
                        str_lit.success("Apagado com sucesso!")
                        str_lit.rerun()

    # ---------------------------------------------------------
    # MÓDULO 11: AUDITORIA DE SISTEMA
    # ---------------------------------------------------------
    elif menu == "🛡️ Auditoria de Sistema":
        if str_lit.session_state.usuario_logado.lower() != ADMIN_EMAIL.lower():
            str_lit.error("⚠️ Acesso não autorizado.")
        else:
            str_lit.title("🛡️ Auditoria e Logs de Atividades")
            try:
                df_logs = executar_query("SELECT id as 'ID', usuario as 'Usuário', acao as 'Ação', detalhes as 'Detalhes', data_hora as 'Data/Hora' FROM logs_auditoria ORDER BY id DESC")
            except Exception:
                df_logs = pd.DataFrame()
            if df_logs.empty:
                str_lit.info("ℹ️ Nenhum log.")
            else:
                str_lit.metric("Total de Ações", len(df_logs))
                str_lit.dataframe(df_logs, use_container_width=True)
