import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
from PIL import Image
import re
import random
import smtplib
from email.mime.text import MIMEText

# Configuração inicial da página
st.set_page_config(page_title="Sistema de Gestão RH", layout="wide", initial_sidebar_state="expanded")

DB_FILE = "gestao_empresa.db"

# ---------------------------------------------------------
# SISTEMA DE AUTENTICAÇÃO POR E-MAIL (LOGIN)
# ---------------------------------------------------------
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "codigo_enviado" not in st.session_state:
    st.session_state.codigo_enviado = ""
if "email_usuario" not in st.session_state:
    st.session_state.email_usuario = ""

# Função que permite qualquer e-mail válido
def verificar_email_autorizado(email):
    if "@" in email and "." in email:
        return True
    return False

if not st.session_state.autenticado:
    st.title("🔐 Acesso Restrito - Gestão RH")
    st.write("Digite seu e-mail para receber o código de acesso de 6 dígitos.")
    
    email_input = st.text_input("E-mail do Administrativo:")
    
    if st.button("Enviar Código de Acesso"):
        if verificar_email_autorizado(email_input):
            codigo_gerado = str(random.randint(100000, 999999))
            st.session_state.codigo_enviado = codigo_gerado
            st.session_state.email_usuario = email_input
            
            # TENTATIVA DE ENVIO DE E-MAIL (SMTP)
            try:
                remetente = "seu_email@gmail.com"
                senha = "sua_senha_de_app_do_gmail"
                
                mensagem = MIMEText(f"Seu código de acesso ao Sistema de Gestão RH é: {codigo_gerado}")
                mensagem['Subject'] = "Código de Acesso - Gestão RH"
                mensagem['From'] = remetente
                mensagem['To'] = email_input
                
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(remetente, senha)
                    server.sendmail(remetente, email_input, mensagem.as_string())
                
                st.success(f"Código enviado com sucesso para {email_input}!")
            except Exception as e:
                # Caso ocorra falha no envio por SMTP, o código aparece direto na tela para teste
                st.info(f"[Modo de Teste / Configuração] Seu código de acesso é: {codigo_gerado}")
        else:
            st.error("Por favor, digite um e-mail válido.")
            
    if st.session_state.codigo_enviado:
        codigo_digitado = st.text_input("Digite o Código de 6 Dígitos:", type="password")
        if st.button("Validar e Entrar"):
            if codigo_digitado == st.session_state.codigo_enviado:
                st.session_state.autenticado = True
                st.success("Acesso liberado!")
                st.rerun()
            else:
                st.error("Código incorreto. Tente novamente.")
                
    st.stop() # Interrompe a execução do restante do app até que o usuário faça o login

# =========================================================
# A PARTIR DAQUI FICA O RESTANTE DO SEU PROGRAMA PRINCIPAL
# =========================================================
st.sidebar.title("Menu do Sistema")
st.sidebar.write(f"Logado como: **{st.session_state.email_usuario}**")

if st.sidebar.button("Sair / Trocar de Conta"):
    st.session_state.autenticado = False
    st.session_state.codigo_enviado = ""
    st.session_state.email_usuario = ""
    st.rerun()

# Exemplo de conteúdo do seu sistema principal
st.title("Painel Principal - Gestão de Filiais")
st.write("Bem-vindo ao sistema! Aqui fica o restante das suas telas e funcionalidades.")
