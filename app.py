"""
Project: AI Email Agent
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
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Any, Optional
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
    .success-message {
        padding: 1rem;
        background-color: #d4edda;
        color: #155724;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

class EmailAgent:
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
    
    AVAILABLE_MODELS = [
        'gemini-2.5-flash',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-1.0-pro',
    ]
    
    def __init__(self, gemini_api_key: str):
        self.processed_emails = set()
        self.conversation_history = {}
        self.model = None
        self.model_name = None
        self.gmail_user = None
        self.gmail_app_password = None
        self.service = None
        self.use_app_password = False
        
        genai.configure(api_key=gemini_api_key)
        self._initialize_model()
        
    def _initialize_model(self):
        try:
            available_models = []
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    available_models.append(model.name)
            
            for model_name in self.AVAILABLE_MODELS:
                try:
                    self.model = genai.GenerativeModel(model_name)
                    test_response = self.model.generate_content("Test")
                    self.model_name = model_name
                    return
                except Exception as e:
                    continue
            
            for model in available_models:
                try:
                    model_id = model.split('/')[-1]
                    self.model = genai.GenerativeModel(model_id)
                    self.model_name = model_id
                    return
                except:
                    continue
                    
            raise Exception("No working Gemini model found")
            
        except Exception as e:
            st.error(f"Model initialization failed: {e}")
            raise

    def authenticate_with_app_password(self, email: str, app_password: str):
        """Authenticate using App Password with timeout"""
        try:
            clean_password = app_password.replace(" ", "")
            
            # Set socket timeout to prevent hanging
            socket.setdefaulttimeout(10)
            
            # Try port 587 with STARTTLS
            try:
                server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(email, clean_password)
                server.quit()
                smtp_worked = True
            except Exception as e:
                smtp_worked = False
                st.warning(f"SMTP connection failed (this is normal on Render): {str(e)[:100]}")
            
            # Don't let Gmail failure stop the app
            if not smtp_worked:
                # Still mark as "connected" for demo purposes
                self.gmail_user = email
                self.gmail_app_password = clean_password
                self.use_app_password = False  # Mark as not fully connected
                return True, "✅ AI Agent ready! (Gmail sending may be limited on Render)"
            
            self.gmail_user = email
            self.gmail_app_password = clean_password
            self.use_app_password = True
            
            return True, "✅ Gmail connected successfully!"
        except Exception as e:
            # Don't fail the whole app if Gmail doesn't connect
            return True, f"⚠️ AI Agent ready, but Gmail connection failed: {str(e)[:100]}"

def main():
    from PIL import Image
    icon = Image.open("globe.png")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.image(icon, width=60)

    with col2:
        st.title("AI Email Agent")
    st.markdown("*Automate your email related operations with Gemini*")
    st.markdown("""
<div style='color: #666;'>
    Built with ❤️ by <strong style='color: #ff4b4b;'>Imtiaz Adar</strong>
</div>
""", unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("Configuration")
        
        gemini_key = st.text_input(
            "Gemini API Key (FREE)",
            type="password",
            value=os.getenv('GEMINI_API_KEY', ''),
            help="Get from https://makersuite.google.com/app/apikey"
        )
        
        if gemini_key:
            os.environ['GEMINI_API_KEY'] = gemini_key
        
        st.markdown("---")
        st.subheader("Gmail Authentication (Optional)")
        
        st.info("""
        **📧 For Gmail integration (optional):**
        - Enable 2-Step Verification on your Google Account
        - Go to Security → App Passwords
        - Generate password for 'Mail' and 'Other'
        """)
        
        gmail_email = st.text_input("Gmail Address (Optional)", placeholder="youremail@gmail.com")
        gmail_app_password = st.text_input("App Password (Optional)", type="password", placeholder="16-character password")
        
        st.markdown("---")
        st.subheader("Settings")
        max_emails = st.slider("Max emails to process", 1, 20, 5)
        
        if st.button("Initialize Agent", type="primary"):
            if not gemini_key:
                st.error("Please enter Gemini API Key")
            else:
                with st.spinner("Initializing AI Agent..."):
                    try:
                        # First, just initialize the AI model (fast)
                        st.session_state.agent = EmailAgent(gemini_key)
                        st.success(f"✅ AI Agent initialized with {st.session_state.agent.model_name}")
                        
                        # Then try Gmail connection separately (with timeout)
                        if gmail_email and gmail_app_password:
                            st.info("🔌 Attempting Gmail connection (this may take a few seconds)...")
                            success, message = st.session_state.agent.authenticate_with_app_password(
                                gmail_email, 
                                gmail_app_password
                            )
                            if "✅" in message:
                                st.success(message)
                                st.session_state.gmail_connected = True
                            else:
                                st.warning(message)
                                st.session_state.gmail_connected = False
                        else:
                            st.info("💡 Gmail not configured. Using AI-only mode.")
                            st.session_state.gmail_connected = False
                        
                        st.session_state.initialized = True
                        
                    except Exception as e:
                        st.error(f"Initialization failed: {e}")
                        st.session_state.initialized = True  # Still mark as initialized so UI shows
        
        if hasattr(st.session_state, 'initialized') and st.session_state.initialized:
            st.markdown("---")
            st.header("Stats")
            if hasattr(st.session_state, 'agent'):
                st.metric("Processed Emails", len(st.session_state.agent.processed_emails))
                st.metric("Model", st.session_state.agent.model_name)
            if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                st.success("✅ Gmail Connected")
            else:
                st.info("⚡ AI Mode Only - Gmail features limited")
    
    if not hasattr(st.session_state, 'initialized') or not st.session_state.initialized:
        st.info("👈 Please enter your Gemini API Key and click 'Initialize Agent'")
        
        with st.expander("Quick Start Guide (FREE)", expanded=True):
            st.markdown("""
            ### Step 1: Get Free Gemini API Key
            1. Visit https://makersuite.google.com/app/apikey
            2. Sign in with your Google account
            3. Click Create API Key
            4. Copy the key

            ### Step 2: Use AI Features (No Gmail Required!)
            - Generate AI replies to any email
            - Analyze email sentiment
            - Create professional emails
            - Try the AI Playground!

            ### Step 3: Optional Gmail Integration
            - Enable 2-Step Verification on Google Account
            - Generate App Password
            - Enter credentials above
            """)
        return
    
    tab1, tab2, tab3, tab4 = st.tabs(["📧 Inbox", "✍️ Compose", "🤖 AI Playground", "📊 Analytics"])
    
    with tab1:
        st.header("Email Inbox")
        
        if not hasattr(st.session_state, 'gmail_connected') or not st.session_state.gmail_connected:
            st.info("""
            ### 📧 Gmail Inbox Preview
            
            To see your real inbox:
            1. Configure Gmail credentials in sidebar
            2. Re-initialize the agent
            3. Click 'Fetch Unread Emails'
            
            **Current Mode:** AI-Only (all playground features work!)
            """)
            
            # Show demo emails
            st.subheader("📬 Demo: How Inbox Would Look")
            demo_emails = [
                {"from": "recruiter@company.com", "subject": "Interview Opportunity", "date": "2024-01-15"},
                {"from": "client@business.com", "subject": "Project Update Request", "date": "2024-01-14"},
                {"from": "team@startup.io", "subject": "Weekly Sync Meeting", "date": "2024-01-13"},
            ]
            for email in demo_emails:
                st.markdown(f"""
                <div class="email-card">
                    <strong>📨 From:</strong> {email['from']}<br>
                    <strong>📌 Subject:</strong> {email['subject']}<br>
                    <strong>📅 Date:</strong> {email['date']}
                </div>
                """, unsafe_allow_html=True)
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("Fetch Unread Emails", use_container_width=True):
                    with st.spinner("Fetching emails..."):
                        st.session_state.emails = st.session_state.agent.get_unread_emails(max_emails)
                        st.rerun()
            
            if hasattr(st.session_state, 'emails') and st.session_state.emails:
                st.success(f"📬 Found {len(st.session_state.emails)} unread email(s)")
                
                for idx, email in enumerate(st.session_state.emails):
                    with st.container():
                        st.markdown(f"""
                        <div class="email-card">
                            <strong>📨 From:</strong> {email['from']}<br>
                            <strong>📌 Subject:</strong> {email['subject']}<br>
                            <strong>📅 Date:</strong> {email.get('date', 'Unknown')}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        with st.expander("📝 View Email Body"):
                            st.text(email['body'][:500] + "..." if len(email['body']) > 500 else email['body'])
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            if st.button(f"🤖 Generate AI Reply", key=f"gen_{idx}"):
                                with st.spinner("Generating AI response..."):
                                    reply = st.session_state.agent.generate_ai_reply(email)
                                    st.session_state[f"reply_{idx}"] = reply
                                    st.success("✅ Reply generated!")
                        
                        with col2:
                            if st.button(f"📤 Send Reply", key=f"send_{idx}"):
                                if f"reply_{idx}" in st.session_state:
                                    success, result = st.session_state.agent.send_email(
                                        to=email['from'],
                                        subject=f"Re: {email['subject']}",
                                        body=st.session_state[f"reply_{idx}"],
                                        thread_id=email['thread_id']
                                    )
                                    if success:
                                        st.success(f"✅ Reply sent to {email['from']}")
                                        st.session_state.agent.mark_as_read(email['message_id'])
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to send: {result}")
                                else:
                                    st.warning("Generate reply first")
                        
                        with col3:
                            if st.button(f"✓ Mark as Read", key=f"read_{idx}"):
                                st.session_state.agent.mark_as_read(email['message_id'])
                                st.success("Marked as read")
                                st.rerun()
                        
                        if f"reply_{idx}" in st.session_state:
                            st.markdown("### 🤖 AI Generated Reply:")
                            st.info(st.session_state[f"reply_{idx}"])
                        
                        st.markdown("---")
            else:
                st.info("Click 'Fetch Unread Emails' to check your inbox")
    
    with tab2:
        st.header("✍️ Compose New Email")
        
        col1, col2 = st.columns(2)
        
        with col1:
            recipient = st.text_input("To:", placeholder="recipient@example.com")
            subject = st.text_input("Subject:", placeholder="Email subject")
            
            if st.button("✨ AI-Assisted Writing", use_container_width=True):
                if subject:
                    with st.spinner("Generating email content..."):
                        prompt = f"Write a professional email with subject '{subject}'. Keep it concise (3-4 sentences)."
                        response = st.session_state.agent.model.generate_content(prompt)
                        st.session_state.ai_body = response.text
                        st.success("✅ Email generated! Review and edit below.")
                else:
                    st.warning("Please enter a subject first")
        
        with col2:
            body = st.text_area("Message Body:", 
                               value=st.session_state.get('ai_body', ''),
                               height=300,
                               placeholder="Write your email here or use AI to generate")
        
        if st.button("📤 Send Email", type="primary", use_container_width=True):
            if recipient and subject and body:
                if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                    success, result = st.session_state.agent.send_email(recipient, subject, body)
                    if success:
                        st.success(f"✅ Email sent successfully to {recipient}")
                        st.balloons()
                        st.session_state.ai_body = ""
                        st.rerun()
                    else:
                        st.error(f"Failed to send: {result}")
                else:
                    st.info("💡 Gmail not connected - Email preview only")
                    st.code(f"To: {recipient}\nSubject: {subject}\n\n{body}")
            else:
                st.warning("Please fill all fields")
    
    with tab3:
        st.header("🤖 AI Playground")
        st.markdown("*All AI features work without Gmail!*")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Test Email Reply")
            test_email = st.text_area(
                "Paste an email to test AI reply",
                height=200,
                placeholder="Subject: Question about services\n\nHi, I'm interested in your AI services."
            )
            
            if st.button("🤖 Generate Test Reply", use_container_width=True):
                if test_email:
                    with st.spinner("AI is thinking..."):
                        test_data = {
                            'from': 'test@example.com',
                            'subject': test_email.split('\n')[0] if '\n' in test_email else 'Test',
                            'body': test_email
                        }
                        reply = st.session_state.agent.generate_ai_reply(test_data)
                        st.markdown("### 🤖 AI Generated Reply:")
                        st.success(reply)
                else:
                    st.warning("Please enter a test email")
        
        with col2:
            st.subheader("Generate Cold Email")
            topic = st.text_input("What's the email about?", placeholder="Product launch, Meeting request")
            tone = st.selectbox("Tone", ["Professional", "Friendly", "Formal", "Casual"])
            
            if st.button("✨ Generate Email", use_container_width=True):
                if topic:
                    with st.spinner("Crafting email..."):
                        prompt = f"Write a {tone.lower()} email about: {topic}. Keep it concise (3-4 sentences)."
                        response = st.session_state.agent.model.generate_content(prompt)
                        st.markdown("### 📧 Generated Email:")
                        st.code(response.text)
                        st.download_button(
                            label="📥 Download Email",
                            data=response.text,
                            file_name="generated_email.txt",
                            mime="text/plain"
                        )
                else:
                    st.warning("Please enter a topic")
        
        st.subheader("📊 Email Analysis")
        
        email_to_analyze = st.text_area(
            "Paste email for AI analysis",
            height=150,
            key="email_analysis_input",
            placeholder="Example: Hi team, I'm extremely frustrated! The system has been down for 2 hours."
        )
        
        if st.button("🔍 Analyze Email", use_container_width=True, key="analyze_btn"):
            if email_to_analyze:
                with st.spinner("Analyzing email with AI..."):
                    prompt = f"""
Analyze this email and return ONLY valid JSON (no markdown, no backticks, no extra text).

Email: {email_to_analyze[:500]}

Return EXACTLY this format:
{{"sentiment":"positive/negative/neutral","urgency":"high/medium/low","requires_response":true/false,"key_topics":["topic1","topic2"],"suggested_action":"brief action suggestion"}}

ONLY return the JSON, nothing else.
"""
                    try:
                        response = st.session_state.agent.model.generate_content(prompt)
                        raw_response = response.text.strip()
                        
                        clean_response = raw_response
                        clean_response = re.sub(r'```json\s*', '', clean_response)
                        clean_response = re.sub(r'```\s*', '', clean_response)
                        clean_response = clean_response.strip()
                        
                        parsed_data = json.loads(clean_response)
                        
                        st.markdown("### Analysis Results")
                        
                        col_a, col_b, col_c = st.columns(3)
                        
                        with col_a:
                            sentiment = parsed_data.get('sentiment', 'neutral')
                            sentiment_icon = {'positive': '😊', 'negative': '😠', 'neutral': '😐'}.get(sentiment, '🤔')
                            st.metric("Sentiment", f"{sentiment_icon} {sentiment.title()}")
                        
                        with col_b:
                            urgency = parsed_data.get('urgency', 'medium')
                            urgency_icon = {'high': '🚨', 'medium': '⚠️', 'low': '✅'}.get(urgency, '📧')
                            st.metric("Urgency", f"{urgency_icon} {urgency.title()}")
                        
                        with col_c:
                            requires_response = parsed_data.get('requires_response', True)
                            response_icon = "Yes" if requires_response else "No"
                            st.metric("Needs Reply", response_icon)
                        
                        st.subheader("Key Topics")
                        topics = parsed_data.get('key_topics', [])
                        if topics:
                            for topic in topics:
                                st.markdown(f"- {topic}")
                        else:
                            st.info("No specific topics identified")
                        
                        st.subheader("Suggested Action")
                        suggested_action = parsed_data.get('suggested_action', 'Review the email')
                        st.info(suggested_action)
                        
                        with st.expander("View Raw Analysis Data"):
                            st.json(parsed_data)
                        
                    except json.JSONDecodeError as e:
                        st.error(f"JSON Parse Error: {e}")
                        st.text("Raw AI response:")
                        st.code(raw_response)
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
            else:
                st.warning("Please paste an email to analyze")
    
    with tab4:
        st.header("📊 Analytics Dashboard")
        
        if hasattr(st.session_state, 'emails') and st.session_state.emails:
            df = pd.DataFrame(st.session_state.emails)
            df['domain'] = df['from'].apply(lambda x: x.split('@')[-1] if '@' in x else 'unknown')
            domain_counts = df['domain'].value_counts().head(10)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Top Sender Domains")
                fig = px.bar(x=domain_counts.values, y=domain_counts.index, orientation='h')
                fig.update_layout(height=400, xaxis_title="Number of Emails")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Email Statistics")
                st.metric("Total Unread", len(df))
                st.metric("Unique Senders", df['from'].nunique())
                st.metric("Avg Subject Length", int(df['subject'].str.len().mean()) if len(df) > 0 else 0)
            
            st.subheader("Recent Emails")
            st.dataframe(df[['from', 'subject', 'date']], use_container_width=True)
        else:
            st.info("Connect Gmail and fetch emails to see analytics")

if __name__ == "__main__":
    main()
