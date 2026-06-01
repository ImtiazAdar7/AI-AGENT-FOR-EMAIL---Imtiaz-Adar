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
import random

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
    
    AVAILABLE_MODELS = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.5-flash']
    
    def __init__(self, gemini_api_key: str):
        self.processed_emails = set()
        self.model = None
        self.model_name = None
        self.gmail_user = None
        self.gmail_app_password = None
        self.service = None
        self.use_gmail = False
        self.use_app_password = False
        self.last_api_call = 0
        
        genai.configure(api_key=gemini_api_key)
        self._initialize_model()
    
    def _call_with_retry(self, func, *args, max_retries=3, **kwargs):
        """Call Gemini API with retry logic for rate limits"""
        for attempt in range(max_retries):
            try:
                # Add delay between calls (rate limiting)
                current_time = time.time()
                if current_time - self.last_api_call < 2:  # 2 second delay
                    time.sleep(2 - (current_time - self.last_api_call))
                
                result = func(*args, **kwargs)
                self.last_api_call = time.time()
                return result
            except Exception as e:
                if "ResourceExhausted" in str(e) or "429" in str(e):
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    st.warning(f"Rate limit hit. Waiting {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        st.error("API is busy. Please try again in a few moments.")
                        return "Service temporarily busy. Please try again."
                else:
                    raise e
        return None
        
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
        try:
            clean_password = app_password.replace(" ", "")
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
            return True, "✅ Gmail connected!"
        except Exception as e:
            return False, f"Connection failed: {str(e)[:100]}"
    
    def authenticate_gmail(self, credentials_file: str = 'credentials.json'):
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
    
    def get_all_emails(self, max_results=10):
        """Fetch ALL emails (not just unread)"""
        if not self.use_gmail:
            return self._get_demo_emails()
        
        if self.use_app_password:
            try:
                imap = imaplib.IMAP4_SSL('imap.gmail.com', 993)
                imap.login(self.gmail_user, self.gmail_app_password)
                imap.select('INBOX')
                status, messages = imap.search(None, 'ALL')  # Changed from UNSEEN to ALL
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
                                'date': msg['Date'],
                                'is_read': 'UNSEEN' not in str(msg)
                            })
                imap.close()
                imap.logout()
                return emails
            except Exception as e:
                st.error(f"Error: {e}")
                return self._get_demo_emails()
        return self._get_demo_emails()
    
    def get_unread_emails(self, max_results=10):
        """Fetch only unread emails"""
        if not self.use_gmail:
            return self._get_demo_emails()
        
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
                return self._get_demo_emails()
        return self._get_demo_emails()
    
    def _get_demo_emails(self):
        return [
            {'from': 'recruiter@techcompany.com', 'subject': 'Interview Opportunity', 
             'body': 'We were impressed with your portfolio...', 'message_id': '1', 
             'date': 'Jan 15, 2024', 'is_read': False},
            {'from': 'client@startup.io', 'subject': 'Question about services', 
             'body': 'Can you tell me more about your AI solutions?', 'message_id': '2', 
             'date': 'Jan 14, 2024', 'is_read': False},
            {'from': 'newsletter@example.com', 'subject': 'Weekly Update', 
             'body': 'Here are the latest updates...', 'message_id': '3', 
             'date': 'Jan 13, 2024', 'is_read': True},
        ]
    
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
You are a professional email assistant. Generate a polite, helpful reply.

Email:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:500]}

Requirements:
1. Acknowledge the message
2. Answer any questions
3. Be concise (2-4 sentences)
4. Professional and friendly

Reply:"""
        
        def call_api():
            return self.model.generate_content(prompt).text.strip()
        
        result = self._call_with_retry(call_api)
        if result:
            return result
        return "Thank you for your email. We'll get back to you shortly."

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
        
        if auth_method == "App Password (Recommended)":
            st.info("Get App Password: Google Account → Security → App Passwords")
            gmail_email = st.text_input("Gmail Address")
            gmail_password = st.text_input("App Password", type="password")
        else:
            uploaded_file = st.file_uploader("Upload credentials.json", type=['json'])
            if uploaded_file:
                with open('credentials.json', 'wb') as f:
                    f.write(uploaded_file.getbuffer())
        
        st.divider()
        max_emails = st.slider("Max emails to fetch", 1, 30, 10)
        
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
                        elif auth_method == "OAuth (credentials.json)" and Path('credentials.json').exists():
                            success, msg = st.session_state.agent.authenticate_gmail('credentials.json')
                            if success:
                                st.success(msg)
                                st.session_state.gmail_connected = True
                            else:
                                st.warning(msg)
                        else:
                            st.info("💡 Gmail not configured - Using AI-only mode with demo emails")
                        
                        st.session_state.initialized = True
                    except Exception as e:
                        st.error(f"Error: {e}")
    
    if not hasattr(st.session_state, 'initialized'):
        st.info("👈 Enter Gemini API Key and click Initialize Agent")
        with st.expander("Quick Start Guide"):
            st.markdown("""
            1. Get Gemini API Key from [Google AI Studio](https://makersuite.google.com/app/apikey)
            2. (Optional) Get Gmail App Password from Google Account → Security → App Passwords
            3. Click Initialize Agent
            4. Start using AI features!
            """)
        return
    
    tab1, tab2, tab3, tab4 = st.tabs(["📧 Inbox", "✍️ Compose", "🤖 AI Playground", "📊 Analytics"])
    
    with tab1:
        st.header("Email Inbox")
        
        if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📬 Fetch Unread Only", use_container_width=True):
                    with st.spinner("Fetching unread emails..."):
                        st.session_state.emails = st.session_state.agent.get_unread_emails(max_emails)
                        st.session_state.email_type = "unread"
                        st.rerun()
            with col2:
                if st.button("📥 Fetch All Inbox", use_container_width=True):
                    with st.spinner("Fetching all emails..."):
                        st.session_state.emails = st.session_state.agent.get_all_emails(max_emails)
                        st.session_state.email_type = "all"
                        st.rerun()
        else:
            st.info("🔌 Connect Gmail to see real emails. Showing demo emails below.")
            if st.button("Load Demo Emails"):
                st.session_state.emails = st.session_state.agent._get_demo_emails()
                st.rerun()
        
        if hasattr(st.session_state, 'emails') and st.session_state.emails:
            email_type = st.session_state.get('email_type', 'all')
            st.success(f"📬 Found {len(st.session_state.emails)} email(s) ({email_type})")
            
            for idx, email in enumerate(st.session_state.emails):
                with st.expander(f"📧 {email['subject'][:60]} - {email['from'][:40]}"):
                    st.markdown(f"**From:** {email['from']}")
                    st.markdown(f"**Date:** {email.get('date', 'Unknown')}")
                    if email.get('is_read') is not None:
                        st.markdown(f"**Status:** {'✅ Read' if email['is_read'] else '🆕 Unread'}")
                    st.divider()
                    st.markdown(f"**Body:**\n{email['body'][:800]}")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button(f"🤖 AI Reply", key=f"reply_{idx}"):
                            with st.spinner("Generating AI response..."):
                                reply = st.session_state.agent.generate_ai_reply(email)
                                st.session_state[f"reply_text_{idx}"] = reply
                                st.success("Reply generated!")
                    
                    if st.session_state.get(f"reply_text_{idx}"):
                        st.text_area("AI Generated Reply:", st.session_state[f"reply_text_{idx}"], 
                                    height=150, key=f"reply_area_{idx}")
                        
                        with col2:
                            if st.button(f"📤 Send Reply", key=f"send_{idx}"):
                                if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                                    success, msg = st.session_state.agent.send_email(
                                        email['from'], f"Re: {email['subject']}", 
                                        st.session_state[f"reply_text_{idx}"]
                                    )
                                    if success:
                                        st.success(msg)
                                        st.balloons()
                                    else:
                                        st.error(msg)
                                else:
                                    st.info("📧 Demo: Email would be sent here")
                                    st.code(st.session_state[f"reply_text_{idx}"])
                        
                        with col3:
                            if st.button(f"✓ Mark Read", key=f"read_{idx}"):
                                if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                                    st.session_state.agent.mark_as_read(email['message_id'])
                                st.success("Marked as read")
        else:
            st.info("Click a button above to load emails")
    
    with tab2:
        st.header("Compose New Email")
        col1, col2 = st.columns(2)
        
        with col1:
            recipient = st.text_input("To:", placeholder="recipient@example.com")
            subject = st.text_input("Subject:", placeholder="Email subject")
            
            if st.button("✨ AI Compose", use_container_width=True):
                if subject:
                    with st.spinner("Generating..."):
                        prompt = f"Write a professional email with subject '{subject}'. Keep it concise (3-4 sentences)."
                        response = st.session_state.agent.model.generate_content(prompt)
                        st.session_state.composed_body = response.text
                        st.success("Email generated!")
        
        with col2:
            body = st.text_area("Body:", value=st.session_state.get('composed_body', ''), height=250)
        
        if st.button("📤 Send Email", type="primary", use_container_width=True):
            if recipient and subject and body:
                if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                    success, msg = st.session_state.agent.send_email(recipient, subject, body)
                    if success:
                        st.success(msg)
                        st.balloons()
                        st.session_state.composed_body = ""
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.info("📧 Demo: Email would be sent here")
                    st.code(f"To: {recipient}\nSubject: {subject}\n\n{body}")
            else:
                st.warning("Please fill all fields")
    
    with tab3:
        st.header("AI Playground")
        st.caption("All features work without Gmail connection")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📝 Test Reply")
            test_email = st.text_area("Paste an email:", height=150)
            if st.button("Generate Reply"):
                if test_email:
                    with st.spinner("AI thinking..."):
                        test_data = {'from': 'test@example.com', 'subject': 'Test', 'body': test_email}
                        reply = st.session_state.agent.generate_ai_reply(test_data)
                        st.success(reply)
        
        with col2:
            st.subheader("🎯 Sentiment Analysis")
            analyze_text = st.text_area("Paste email for analysis:", height=150)
            if st.button("Analyze"):
                if analyze_text:
                    with st.spinner("Analyzing..."):
                        prompt = f"Analyze this email. Return JSON: sentiment (positive/negative/neutral), urgency (high/medium/low), requires_response (true/false). Email: {analyze_text[:300]}"
                        result = st.session_state.agent._call_with_retry(
                            lambda: st.session_state.agent.model.generate_content(prompt).text.strip()
                        )
                        if result:
                            st.info(result)
        
        st.divider()
        st.subheader("✍️ Cold Email Generator")
        topic = st.text_input("Topic:", placeholder="Product launch, Meeting request, Follow up")
        tone = st.selectbox("Tone", ["Professional", "Friendly", "Formal", "Casual"])
        
        if st.button("Generate Email", use_container_width=True):
            if topic:
                with st.spinner("Crafting email..."):
                    prompt = f"Write a {tone.lower()} email about: {topic}. Keep it concise (4-5 sentences)."
                    response = st.session_state.agent.model.generate_content(prompt)
                    st.markdown("### Generated Email:")
                    st.code(response.text)
                    st.download_button("📥 Download", response.text, "email.txt")
            else:
                st.warning("Enter a topic")
    
    with tab4:
        st.header("Analytics Dashboard")
        
        if hasattr(st.session_state, 'emails') and st.session_state.emails:
            df = pd.DataFrame(st.session_state.emails)
            st.metric("Total Emails", len(df))
            st.metric("Unique Senders", df['from'].nunique())
            if 'subject' in df.columns:
                st.metric("Avg Subject Length", int(df['subject'].str.len().mean()))
            st.dataframe(df[['from', 'subject', 'date']], use_container_width=True)
        else:
            st.info("Load emails from Inbox tab to see analytics")

if __name__ == "__main__":
    main()
