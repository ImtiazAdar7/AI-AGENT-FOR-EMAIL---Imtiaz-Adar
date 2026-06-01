"""
Project: AI Email Agent - Streamlit Cloud Edition
Author: Imtiaz Adar
Contact: imtiazadarofficial@gmail.com
"""

import streamlit as st
import os
import pickle
import base64
import time
import re
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict
from pathlib import Path
import pandas as pd
import plotly.express as px
import imaplib
import email
from email.header import decode_header

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.generativeai as genai
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="AI Email Agent",
    page_icon="globe.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stButton > button {
        width: 100%;
        background-color: #ff4b4b;
        color: white;
    }
    .email-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class EmailAgent:
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
    
    AVAILABLE_MODELS = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
    
    def __init__(self, gemini_api_key: str):
        self.processed_emails = set()
        self.model = None
        self.model_name = None
        self.gmail_user = None
        self.gmail_app_password = None
        self.service = None
        self.use_gmail = False
        self.use_app_password = False
        
        genai.configure(api_key=gemini_api_key)
        self._initialize_model()
        
    def _initialize_model(self):
        for model_name in self.AVAILABLE_MODELS:
            try:
                self.model = genai.GenerativeModel(model_name)
                self.model.generate_content("Test")
                self.model_name = model_name
                return
            except:
                continue
        raise Exception("No working Gemini model found")
    
    def authenticate_with_app_password(self, email: str, app_password: str):
        """Authenticate using App Password - Works on Streamlit Cloud!"""
        try:
            clean_password = app_password.replace(" ", "")
            
            # Test connection
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(email, clean_password)
            server.quit()
            
            self.gmail_user = email
            self.gmail_app_password = clean_password
            self.use_app_password = True
            self.use_gmail = True
            
            return True, "✅ Gmail connected with App Password!"
        except Exception as e:
            return False, f"Connection failed: {str(e)[:100]}"
    
    def authenticate_gmail(self, credentials_file: str = 'credentials.json'):
        """Original OAuth method - also works"""
        creds = None
        token_file = 'token.pickle'
        
        if Path(token_file).exists():
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(credentials_file).exists():
                    return False, "credentials.json not found"
                
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('gmail', 'v1', credentials=creds)
        self.use_gmail = True
        return True, "✅ Gmail authenticated!"
    
    def send_email(self, to: str, subject: str, body: str):
        if self.use_app_password:
            try:
                msg = MIMEMultipart()
                msg['From'] = self.gmail_user
                msg['To'] = to
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain'))
                
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.gmail_user, self.gmail_app_password)
                server.send_message(msg)
                server.quit()
                return True, "Email sent!"
            except Exception as e:
                return False, str(e)
        
        elif self.service:
            try:
                message = self._create_message(to, subject, body)
                self.service.users().messages().send(userId='me', body={'raw': message}).execute()
                return True, "Email sent!"
            except Exception as e:
                return False, str(e)
        
        return False, "Gmail not connected"
    
    def _create_message(self, to, subject, body):
        message_text = f"To: {to}\nSubject: {subject}\n\n{body}"
        return base64.urlsafe_b64encode(message_text.encode()).decode()
    
    def get_unread_emails(self, max_results=10):
        if not self.use_gmail:
            # Return demo emails
            return [
                {'from': 'demo@example.com', 'subject': 'Welcome to AI Email Agent', 
                 'body': 'This is a demo email. Connect Gmail to see real emails!',
                 'message_id': '1', 'date': datetime.now().strftime('%Y-%m-%d')}
            ]
        
        if self.use_app_password:
            try:
                imap = imaplib.IMAP4_SSL('imap.gmail.com', 993)
                imap.login(self.gmail_user, self.gmail_app_password)
                imap.select('INBOX')
                status, messages = imap.search(None, 'UNSEEN')
                if status != 'OK':
                    return []
                
                emails = []
                for num in messages[0].split()[:max_results]:
                    _, msg_data = imap.fetch(num, '(RFC822)')
                    for response in msg_data:
                        if isinstance(response, tuple):
                            msg = email.message_from_bytes(response[1])
                            subject, enc = decode_header(msg['Subject'])[0]
                            subject = subject.decode(enc or 'utf-8') if isinstance(subject, bytes) else subject
                            
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            
                            emails.append({
                                'from': msg['From'],
                                'subject': subject,
                                'body': body[:1000],
                                'message_id': num.decode(),
                                'date': msg['Date']
                            })
                imap.close()
                imap.logout()
                return emails
            except:
                return []
        
        return []
    
    def mark_as_read(self, message_id):
        if self.use_app_password:
            try:
                imap = imaplib.IMAP4_SSL('imap.gmail.com', 993)
                imap.login(self.gmail_user, self.gmail_app_password)
                imap.select('INBOX')
                imap.store(message_id, '+FLAGS', '\\Seen')
                imap.close()
                imap.logout()
            except:
                pass
    
    def generate_ai_reply(self, email_data):
        prompt = f"""
You are a professional email assistant. Generate a polite reply.

Email:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:500]}

Requirements: Acknowledge message, answer questions, be concise (2-4 sentences).
Reply:"""
        try:
            return self.model.generate_content(prompt).text.strip()
        except:
            return "Thank you for your email. We'll respond shortly."

def main():
    from PIL import Image
    
    try:
        icon = Image.open("globe.png")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(icon, width=60)
        with col2:
            st.title("AI Email Agent")
    except:
        st.title("🤖 AI Email Agent")
    
    st.markdown("*Automate your email operations with Gemini AI*")
    st.markdown("Built with ❤️ by **Imtiaz Adar**")
    
    with st.sidebar:
        st.header("⚙️ Setup")
        
        gemini_key = st.text_input("Gemini API Key", type="password")
        if gemini_key:
            os.environ['GEMINI_API_KEY'] = gemini_key
        
        st.divider()
        st.subheader("Gmail Connection")
        
        auth_method = st.radio("Choose method:", ["App Password (Recommended)", "OAuth (credentials.json)"])
        
        gmail_email = None
        gmail_password = None
        credentials_file = None
        
        if auth_method == "App Password (Recommended)":
            st.info("Get App Password: Google Account → Security → App Passwords")
            gmail_email = st.text_input("Gmail Address")
            gmail_password = st.text_input("App Password", type="password")
        else:
            uploaded_file = st.file_uploader("Upload credentials.json", type=['json'])
            if uploaded_file:
                with open('credentials.json', 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                credentials_file = 'credentials.json'
        
        st.divider()
        max_emails = st.slider("Max emails", 1, 20, 5)
        
        if st.button("Initialize Agent", type="primary"):
            if not gemini_key:
                st.error("Enter Gemini API Key")
            else:
                with st.spinner("Initializing..."):
                    try:
                        st.session_state.agent = EmailAgent(gemini_key)
                        st.success(f"✅ AI Ready! Model: {st.session_state.agent.model_name}")
                        
                        if auth_method == "App Password (Recommended)" and gmail_email and gmail_password:
                            success, msg = st.session_state.agent.authenticate_with_app_password(gmail_email, gmail_password)
                            if success:
                                st.success(msg)
                                st.session_state.gmail_connected = True
                            else:
                                st.warning(msg)
                        elif credentials_file:
                            success, msg = st.session_state.agent.authenticate_gmail(credentials_file)
                            if success:
                                st.success(msg)
                                st.session_state.gmail_connected = True
                            else:
                                st.warning(msg)
                        else:
                            st.info("💡 Gmail not configured - Using AI-only mode")
                        
                        st.session_state.initialized = True
                    except Exception as e:
                        st.error(f"Error: {e}")
    
    if not hasattr(st.session_state, 'initialized'):
        st.info("👈 Enter Gemini API Key and click Initialize Agent")
        return
    
    tab1, tab2, tab3, tab4 = st.tabs(["📧 Inbox", "✍️ Compose", "🤖 AI Playground", "📊 Analytics"])
    
    with tab1:
        st.header("Email Inbox")
        
        if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
            if st.button("Fetch Unread Emails"):
                with st.spinner("Fetching..."):
                    st.session_state.emails = st.session_state.agent.get_unread_emails(max_emails)
                    st.rerun()
        else:
            st.info("Connect Gmail to see real emails. Demo mode active.")
        
        if hasattr(st.session_state, 'emails'):
            for idx, email in enumerate(st.session_state.emails):
                with st.expander(f"📧 {email['subject'][:50]} - from {email['from'][:30]}"):
                    st.write(f"**From:** {email['from']}")
                    st.write(f"**Date:** {email.get('date', 'Unknown')}")
                    st.write(f"**Body:**\n{email['body'][:500]}")
                    
                    if st.button(f"🤖 Generate Reply", key=f"reply_{idx}"):
                        reply = st.session_state.agent.generate_ai_reply(email)
                        st.session_state[f"reply_text_{idx}"] = reply
                        st.success("Reply generated!")
                    
                    if st.session_state.get(f"reply_text_{idx}"):
                        st.text_area("AI Generated Reply:", st.session_state[f"reply_text_{idx}"], height=150, key=f"reply_area_{idx}")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"✏️ Edit", key=f"edit_{idx}"):
                                st.session_state[f"editing_{idx}"] = True
                        with col2:
                            if st.button(f"📤 Send", key=f"send_{idx}"):
                                if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                                    success, msg = st.session_state.agent.send_email(
                                        email['from'], f"Re: {email['subject']}", st.session_state[f"reply_text_{idx}"]
                                    )
                                    if success:
                                        st.success(msg)
                                        st.session_state.agent.mark_as_read(email['message_id'])
                                    else:
                                        st.error(msg)
                                else:
                                    st.info("Demo: Email would be sent here")
    
    with tab2:
        st.header("Compose New Email")
        col1, col2 = st.columns(2)
        
        with col1:
            recipient = st.text_input("To:")
            subject = st.text_input("Subject:")
            if st.button("✨ AI Compose"):
                if subject:
                    prompt = f"Write a professional email with subject '{subject}'. Keep it concise."
                    response = st.session_state.agent.model.generate_content(prompt)
                    st.session_state.composed_body = response.text
                    st.success("Email generated!")
        
        with col2:
            body = st.text_area("Body:", value=st.session_state.get('composed_body', ''), height=200)
        
        if st.button("Send Email", type="primary"):
            if recipient and subject and body:
                if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                    success, msg = st.session_state.agent.send_email(recipient, subject, body)
                    if success:
                        st.success(msg)
                        st.balloons()
                    else:
                        st.error(msg)
                else:
                    st.info("📧 Demo: Email would be sent here")
                    st.code(f"To: {recipient}\nSubject: {subject}\n\n{body}")
    
    with tab3:
        st.header("AI Playground")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Test Reply")
            test_email = st.text_area("Paste email:", height=150)
            if st.button("Generate Reply"):
                if test_email:
                    test_data = {'from': 'test@example.com', 'subject': 'Test', 'body': test_email}
                    reply = st.session_state.agent.generate_ai_reply(test_data)
                    st.success(reply)
        
        with col2:
            st.subheader("Analyze Email")
            analyze = st.text_area("Paste for analysis:", height=150)
            if st.button("Analyze"):
                if analyze:
                    prompt = f"Analyze sentiment (positive/negative/neutral) and urgency (high/medium/low): {analyze[:300]}"
                    result = st.session_state.agent.model.generate_content(prompt)
                    st.info(result.text)
        
        st.subheader("Generate Cold Email")
        topic = st.text_input("Topic:")
        tone = st.selectbox("Tone", ["Professional", "Friendly", "Formal"])
        if st.button("Generate"):
            prompt = f"Write a {tone.lower()} email about: {topic}. Keep it concise."
            response = st.session_state.agent.model.generate_content(prompt)
            st.code(response.text)
            st.download_button("Download", response.text, "email.txt")
    
    with tab4:
        st.header("Analytics")
        if hasattr(st.session_state, 'emails') and st.session_state.emails:
            df = pd.DataFrame(st.session_state.emails)
            st.metric("Total Emails", len(df))
            st.metric("Unique Senders", df['from'].nunique())
            st.dataframe(df[['from', 'subject']])
        else:
            st.info("Fetch emails to see analytics")

if __name__ == "__main__":
    main()
