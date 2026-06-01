"""
Project: AI Email Agent
Author: Imtiaz Adar
Contact: imtiazadarofficial@gmail.com
"""

import streamlit as st
import os
import base64
import time
import re
import json
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime
from typing import List, Dict
import pandas as pd
import plotly.express as px

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
    
    def __init__(self, gemini_api_key: str):
        self.processed_emails = set()
        self.model = None
        self.model_name = None
        self.gmail_user = None
        self.gmail_password = None
        self.is_gmail_connected = False
        
        try:
            genai.configure(api_key=gemini_api_key)
            self._initialize_model()
        except Exception as e:
            st.error(f"Gemini configuration failed: {e}")
            raise
    
    def _initialize_model(self):
        """Initialize Gemini model"""
        try:
            working_models = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-1.0-pro']
            
            for model_name in working_models:
                try:
                    self.model = genai.GenerativeModel(model_name)
                    response = self.model.generate_content("Test")
                    if response and hasattr(response, 'text') and response.text:
                        self.model_name = model_name
                        return
                except:
                    continue
                    
            raise Exception("No working Gemini model found")
            
        except Exception as e:
            st.error(f"Model initialization failed: {e}")
            raise
    
    def connect_gmail(self, email: str, app_password: str):
        """Connect to Gmail using App Password"""
        try:
            clean_password = app_password.replace(" ", "")
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(email, clean_password)
            server.quit()
            
            self.gmail_user = email
            self.gmail_password = clean_password
            self.is_gmail_connected = True
            
            return True, "✅ Gmail connected successfully!"
        except Exception as e:
            return False, f"❌ Connection failed: {str(e)[:100]}"
    
    def send_email(self, to: str, subject: str, body: str):
        """Send email using SMTP"""
        if not self.is_gmail_connected:
            return False, "Gmail not connected"
        
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
            server.login(self.gmail_user, self.gmail_password)
            server.send_message(msg)
            server.quit()
            
            return True, "Email sent successfully!"
        except Exception as e:
            return False, f"Failed to send: {str(e)}"
    
    def get_all_emails(self, max_results: int = 20) -> List[Dict]:
        """Fetch ALL emails (not just unread) - latest first"""
        if not self.is_gmail_connected:
            return []
        
        try:
            imap = imaplib.IMAP4_SSL('imap.gmail.com', 993)
            imap.login(self.gmail_user, self.gmail_password)
            imap.select('INBOX')
            
            status, messages = imap.search(None, 'ALL')
            
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()[::-1][:max_results]
            
            emails = []
            
            for email_id in email_ids:
                status, msg_data = imap.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject, encoding = decode_header(msg['Subject'])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else 'utf-8')
                        
                        from_addr = msg['From']
                        date_str = msg['Date']
                        
                        try:
                            from email.utils import parsedate_to_datetime
                            date_obj = parsedate_to_datetime(date_str)
                        except:
                            date_obj = datetime.now()
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                        
                        is_read = 'UNSEEN' not in str(msg)
                        
                        emails.append({
                            'from': from_addr,
                            'subject': subject if subject else "No Subject",
                            'body': body[:3000],
                            'message_id': email_id.decode(),
                            'thread_id': email_id.decode(),
                            'date': date_str,
                            'date_obj': date_obj,
                            'is_read': is_read
                        })
            
            imap.close()
            imap.logout()
            
            emails.sort(key=lambda x: x['date_obj'], reverse=True)
            
            return emails
            
        except Exception as e:
            st.error(f"Error fetching emails: {e}")
            return []
    
    def get_unread_emails(self, max_results: int = 20) -> List[Dict]:
        """Fetch only unread emails - latest first"""
        if not self.is_gmail_connected:
            return []
        
        try:
            imap = imaplib.IMAP4_SSL('imap.gmail.com', 993)
            imap.login(self.gmail_user, self.gmail_password)
            imap.select('INBOX')
            
            status, messages = imap.search(None, 'UNSEEN')
            
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()[::-1][:max_results]
            
            emails = []
            
            for email_id in email_ids:
                status, msg_data = imap.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject, encoding = decode_header(msg['Subject'])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else 'utf-8')
                        
                        from_addr = msg['From']
                        date_str = msg['Date']
                        
                        try:
                            from email.utils import parsedate_to_datetime
                            date_obj = parsedate_to_datetime(date_str)
                        except:
                            date_obj = datetime.now()
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                        
                        emails.append({
                            'from': from_addr,
                            'subject': subject if subject else "No Subject",
                            'body': body[:3000],
                            'message_id': email_id.decode(),
                            'thread_id': email_id.decode(),
                            'date': date_str,
                            'date_obj': date_obj,
                            'is_read': False
                        })
            
            imap.close()
            imap.logout()
            
            emails.sort(key=lambda x: x['date_obj'], reverse=True)
            
            return emails
            
        except Exception as e:
            st.error(f"Error fetching emails: {e}")
            return []
    
    def mark_as_read(self, message_id: str):
        """Mark email as read"""
        if not self.is_gmail_connected:
            return
        
        try:
            imap = imaplib.IMAP4_SSL('imap.gmail.com', 993)
            imap.login(self.gmail_user, self.gmail_password)
            imap.select('INBOX')
            imap.store(message_id, '+FLAGS', '\\Seen')
            imap.close()
            imap.logout()
        except:
            pass
    
    def generate_ai_reply(self, email_data: Dict) -> str:
        """Generate AI reply using Gemini"""
        if not self.model:
            return "AI model not initialized."
        
        prompt = f"""
You are a professional email assistant. Generate a polite, helpful reply.

Original Email:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:800]}

Requirements:
1. Acknowledge the message
2. Answer any questions
3. Be concise (2-4 sentences)
4. Professional and friendly

Reply:
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            return f"Thank you for your email. We'll get back to you soon."

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
    
    # Sidebar
    with st.sidebar:
        st.header("🔐 Gmail Login")
        st.info("""
        **How to get App Password:**
        1. Enable 2-Step Verification
        2. Go to Security → App Passwords  
        3. Copy the 16-character password
        """)
        
        gmail_email = st.text_input("Gmail Address", placeholder="youremail@gmail.com")
        gmail_password = st.text_input("App Password", type="password", placeholder="16 character password")
        
        st.divider()
        st.header("🤖 Gemini AI Setup")
        gemini_key = st.text_input(
            "Gemini API Key",
            type="password",
            help="Get from https://makersuite.google.com/app/apikey"
        )
        
        st.divider()
        max_emails = st.slider("Max emails to fetch", 5, 50, 20)
        
        if st.button("🚀 Initialize & Connect", type="primary"):
            if not gemini_key:
                st.error("❌ Please enter Gemini API Key")
            elif not gmail_email or not gmail_password:
                st.error("❌ Please enter Gmail credentials")
            else:
                with st.spinner("Initializing AI and connecting to Gmail..."):
                    try:
                        st.session_state.agent = EmailAgent(gemini_key)
                        st.success(f"✅ AI Ready! Model: {st.session_state.agent.model_name}")
                        
                        success, msg = st.session_state.agent.connect_gmail(gmail_email, gmail_password)
                        if success:
                            st.success(msg)
                            st.session_state.gmail_connected = True
                        else:
                            st.error(msg)
                            st.session_state.gmail_connected = False
                        
                        st.session_state.initialized = True
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        if hasattr(st.session_state, 'initialized'):
            st.divider()
            st.header("📊 Status")
            if hasattr(st.session_state, 'gmail_connected') and st.session_state.gmail_connected:
                st.success("✅ Gmail Connected")
            else:
                st.warning("⚠️ Gmail Not Connected")
            if hasattr(st.session_state, 'agent') and st.session_state.agent.model_name:
                st.info(f"🤖 Model: {st.session_state.agent.model_name}")
    
    # Check if initialized
    if not hasattr(st.session_state, 'initialized'):
        st.info("👈 Enter your credentials and click 'Initialize & Connect'")
        
        with st.expander("📚 Quick Start Guide", expanded=True):
            st.markdown("""
            ### Step 1: Get Gemini API Key (FREE)
            1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
            2. Sign in with Google account
            3. Click "Create API Key"
            4. Copy the key
            
            ### Step 2: Get Gmail App Password
            1. Enable 2-Step Verification
            2. Go to Security → App Passwords
            3. Copy the 16-character password
            
            ### Step 3: Connect
            1. Enter both credentials
            2. Click "Initialize & Connect"
            3. Start using AI features!
            """)
        return
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📧 Inbox", "✍️ Compose", "🤖 AI Playground", "📊 Analytics"])
    
    with tab1:
        st.header("Email Inbox")
        
        if not hasattr(st.session_state, 'gmail_connected') or not st.session_state.gmail_connected:
            st.warning("⚠️ Gmail not connected. Please check your credentials in sidebar.")
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                filter_option = st.radio("Select view:", ["📬 All Inbox", "🆕 Unread Only"], 
                                        index=0, horizontal=True)
            
            with col2:
                if st.button("🔄 Refresh Inbox", use_container_width=True):
                    with st.spinner("Fetching emails..."):
                        if filter_option == "📬 All Inbox":
                            st.session_state.emails = st.session_state.agent.get_all_emails(max_emails)
                        else:
                            st.session_state.emails = st.session_state.agent.get_unread_emails(max_emails)
                        st.rerun()
            
            if not hasattr(st.session_state, 'emails'):
                with st.spinner("Loading your inbox..."):
                    if filter_option == "📬 All Inbox":
                        st.session_state.emails = st.session_state.agent.get_all_emails(max_emails)
                    else:
                        st.session_state.emails = st.session_state.agent.get_unread_emails(max_emails)
            
            if hasattr(st.session_state, 'emails') and st.session_state.emails:
                unread_count = sum(1 for e in st.session_state.emails if not e.get('is_read', True))
                st.success(f"📬 Showing {len(st.session_state.emails)} emails ({unread_count} unread)")
                
                for idx, email in enumerate(st.session_state.emails):
                    status_icon = "🆕" if not email.get('is_read', True) else "📧"
                    
                    with st.expander(f"{status_icon} {email['subject'][:80]} - {email['from'][:50]}"):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown(f"**From:** {email['from']}")
                            st.markdown(f"**Date:** {email.get('date', 'Unknown')}")
                        with col2:
                            if not email.get('is_read', True):
                                st.caption("🔴 Unread")
                            else:
                                st.caption("✅ Read")
                        
                        st.divider()
                        st.markdown(f"**Message:**\n{email['body'][:1000]}")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            if st.button(f"🤖 AI Reply", key=f"reply_{idx}"):
                                with st.spinner("Generating AI response..."):
                                    reply = st.session_state.agent.generate_ai_reply(email)
                                    st.session_state[f"reply_text_{idx}"] = reply
                                    st.success("✅ Reply generated!")
                        
                        if st.session_state.get(f"reply_text_{idx}"):
                            st.text_area("AI Generated Reply:", st.session_state[f"reply_text_{idx}"], 
                                        height=150, key=f"reply_area_{idx}")
                            
                            with col2:
                                if st.button(f"📤 Send Reply", key=f"send_{idx}"):
                                    success, msg = st.session_state.agent.send_email(
                                        email['from'], 
                                        f"Re: {email['subject']}", 
                                        st.session_state[f"reply_text_{idx}"]
                                    )
                                    if success:
                                        st.success(msg)
                                        st.balloons()
                                        if not email.get('is_read', True):
                                            st.session_state.agent.mark_as_read(email['message_id'])
                                        st.rerun()
                                    else:
                                        st.error(msg)
                            
                            with col3:
                                if not email.get('is_read', True):
                                    if st.button(f"✓ Mark Read", key=f"read_{idx}"):
                                        st.session_state.agent.mark_as_read(email['message_id'])
                                        st.success("Marked as read")
                                        st.rerun()
            else:
                st.info("📭 No emails found. Try refreshing.")
    
    with tab2:
        st.header("✍️ Compose New Email")
        
        col1, col2 = st.columns(2)
        
        with col1:
            recipient = st.text_input("To:", placeholder="recipient@example.com")
            subject = st.text_input("Subject:", placeholder="Email subject")
            
            if st.button("✨ AI Compose Email", use_container_width=True):
                if subject:
                    with st.spinner("Generating email..."):
                        prompt = f"Write a professional email with subject '{subject}'. Keep it concise (3-4 sentences)."
                        response = st.session_state.agent.model.generate_content(prompt)
                        st.session_state.composed_body = response.text
                        st.success("Email generated!")
                else:
                    st.warning("Please enter a subject first")
        
        with col2:
            body = st.text_area("Message Body:", 
                               value=st.session_state.get('composed_body', ''),
                               height=300,
                               placeholder="Write your email here or use AI to generate")
        
        if st.button("📤 Send Email", type="primary", use_container_width=True):
            if recipient and subject and body:
                success, msg = st.session_state.agent.send_email(recipient, subject, body)
                if success:
                    st.success(msg)
                    st.balloons()
                    st.session_state.composed_body = ""
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Please fill all fields")
    
    with tab3:
        st.header("🤖 AI Playground")
        st.markdown("*Test AI capabilities before connecting Gmail*")
        
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
        
        # Email Analysis - Beautiful version
        st.subheader("📊 Email Analysis")
        st.markdown("*AI analyzes sentiment, urgency, and provides recommendations*")
        
        email_to_analyze = st.text_area(
            "Paste email for AI analysis",
            height=150,
            key="email_analysis_input",
            placeholder="Example: Hi team, I'm extremely frustrated! The system has been down for 2 hours and we're losing customers. Please fix this urgently!"
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
                        
                        st.markdown("### 📊 Analysis Results")
                        
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
                            response_icon = "✅ Yes" if requires_response else "❌ No"
                            st.metric("Needs Reply", response_icon)
                        
                        st.subheader("🏷️ Key Topics")
                        topics = parsed_data.get('key_topics', [])
                        if topics:
                            for topic in topics:
                                st.markdown(f"- {topic}")
                        else:
                            st.info("No specific topics identified")
                        
                        st.subheader("💡 Suggested Action")
                        suggested_action = parsed_data.get('suggested_action', 'Review the email and respond appropriately')
                        st.info(suggested_action)
                        
                        with st.expander("🔧 View Raw Analysis Data"):
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
            if len(df) > 0:
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
                    st.metric("Total Emails", len(df))
                    st.metric("Unique Senders", df['from'].nunique())
                    unread = len([e for e in st.session_state.emails if not e.get('is_read', True)])
                    st.metric("Unread Emails", unread)
                    if 'subject' in df.columns:
                        st.metric("Avg Subject Length", int(df['subject'].str.len().mean()))
                
                st.subheader("Recent Emails")
                display_df = df[['from', 'subject', 'date']].head(10)
                st.dataframe(display_df, use_container_width=True)
            else:
                st.info("No email data available")
        else:
            st.info("Click 'Refresh Inbox' in the Inbox tab to see analytics")

if __name__ == "__main__":
    main()
