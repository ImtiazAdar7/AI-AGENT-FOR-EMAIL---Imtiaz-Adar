"""
Project: AI Email Agent - Streamlit Cloud Fix
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
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd
import plotly.express as px

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.generativeai as genai
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI Email Agent",
    page_icon="globe.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
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
    
    # ✅ FIXED: Use only models that actually exist
    AVAILABLE_MODELS = [
        'models/gemini-1.5-flash',  # Fast, free tier
        'models/gemini-1.5-pro',    # More capable
        'models/gemini-1.0-pro',    # Legacy fallback
    ]
    
    def __init__(self, gemini_api_key: str):
        self.processed_emails = set()
        self.conversation_history = {}
        self.model = None
        self.model_name = None
        self.service = None
        
        # Configure Gemini
        genai.configure(api_key=gemini_api_key)
        
        # Try to find a working model
        self._initialize_model()
        
    def _initialize_model(self):
        """Initialize the first available Gemini model"""
        try:
            # ✅ FIXED: Better model detection
            st.info("🔍 Checking available Gemini models...")
            
            # Try each model in order
            for model_name in self.AVAILABLE_MODELS:
                try:
                    st.info(f"Attempting to load {model_name}...")
                    self.model = genai.GenerativeModel(model_name)
                    # Test the model with a simple request
                    test_response = self.model.generate_content("Say OK")
                    if test_response and test_response.text:
                        self.model_name = model_name
                        st.success(f"✅ Using model: {model_name}")
                        return
                except Exception as e:
                    st.warning(f"⚠️ {model_name} failed: {str(e)[:50]}")
                    continue
            
            # Fallback: Try to list available models from API
            try:
                st.info("Listing all available models from API...")
                for model in genai.list_models():
                    if 'generateContent' in model.supported_generation_methods:
                        model_id = model.name.replace('models/', '')
                        try:
                            self.model = genai.GenerativeModel(model_id)
                            self.model.generate_content("Test")
                            self.model_name = model_id
                            st.success(f"✅ Using fallback model: {model_id}")
                            return
                        except:
                            continue
            except Exception as e:
                st.error(f"Failed to list models: {e}")
                    
            raise Exception("No working Gemini model found. Please check your API key.")
            
        except Exception as e:
            st.error(f"❌ Model initialization failed: {e}")
            st.info("""
            **Troubleshooting:**
            1. Make sure you have a valid Gemini API key
            2. Get one from: https://makersuite.google.com/app/apikey
            3. Check your internet connection
            4. If on Streamlit Cloud, add GEMINI_API_KEY to secrets
            """)
            raise
    
    def authenticate_gmail(self, credentials_file: str = 'credentials.json'):
        """Authenticate with Gmail API"""
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
                    return False, "credentials.json not found. Please upload in sidebar."
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('gmail', 'v1', credentials=creds)
        return True, "✅ Authenticated successfully!"
    
    def extract_email_content(self, message: Dict) -> Dict:
        """Extract email content"""
        headers = message['payload']['headers']
        
        email_data = {
            'from': '',
            'subject': '',
            'body': '',
            'message_id': message['id'],
            'thread_id': message['threadId'],
            'date': ''
        }
        
        for header in headers:
            if header['name'].lower() == 'from':
                email_data['from'] = header['value']
            elif header['name'].lower() == 'subject':
                email_data['subject'] = header['value']
            elif header['name'].lower() == 'date':
                email_data['date'] = header['value']
        
        # Extract body
        if 'parts' in message['payload']:
            body_data = self._get_body_from_parts(message['payload']['parts'])
            email_data['body'] = self._clean_html(body_data)
        else:
            body_data = message['payload'].get('body', {}).get('data', '')
            if body_data:
                body_text = base64.urlsafe_b64decode(body_data).decode('utf-8')
                email_data['body'] = self._clean_html(body_text)
        
        return email_data
    
    def _get_body_from_parts(self, parts: List, body_text: str = '') -> str:
        """Recursively extract body"""
        for part in parts:
            if part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                data = part['body']['data']
                decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                body_text += decoded
            elif part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                data = part['body']['data']
                decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                body_text += decoded
            elif 'parts' in part:
                body_text = self._get_body_from_parts(part['parts'], body_text)
        return body_text
    
    def _clean_html(self, html_text: str) -> str:
        """Convert HTML to plain text"""
        soup = BeautifulSoup(html_text, 'html.parser')
        return soup.get_text(separator='\n', strip=True)
    
    def generate_ai_reply(self, email_data: Dict) -> str:
        """Generate reply using Gemini"""
        if not self.model:
            return "AI model not initialized. Please check API key."
            
        prompt = f"""
You are a professional email assistant. Generate a polite, helpful reply.

Original Email:
From: {email_data['from']}
Subject: {email_data['subject']}
Body: {email_data['body'][:1000]}

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
            return f"Thank you for your email. We'll get back to you soon.\n\n(Note: AI generation error: {str(e)})"
    
    def send_email(self, to: str, subject: str, body: str, thread_id: str = None):
        """Send email"""
        try:
            message = self._create_message(to, subject, body)
            
            if thread_id:
                result = self.service.users().messages().send(
                    userId='me', 
                    body={'raw': message, 'threadId': thread_id}
                ).execute()
            else:
                result = self.service.users().messages().send(
                    userId='me', 
                    body={'raw': message}
                ).execute()
            
            return True, result['id']
        except HttpError as error:
            return False, str(error)
    
    def _create_message(self, to: str, subject: str, body: str) -> str:
        """Create email message"""
        message_text = f"""To: {to}
Subject: {subject}
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

{body}
"""
        return base64.urlsafe_b64encode(message_text.encode('utf-8')).decode('utf-8')
    
    def get_unread_emails(self, max_results: int = 10) -> List[Dict]:
        """Fetch unread emails"""
        if not self.service:
            return []
            
        try:
            results = self.service.users().messages().list(
                userId='me', 
                labelIds=['INBOX'],
                q='is:unread',
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return []
            
            emails = []
            for msg in messages:
                if msg['id'] in self.processed_emails:
                    continue
                    
                msg_data = self.service.users().messages().get(
                    userId='me', 
                    id=msg['id'],
                    format='full'
                ).execute()
                
                email_content = self.extract_email_content(msg_data)
                emails.append(email_content)
                self.processed_emails.add(msg['id'])
            
            return emails
            
        except HttpError as error:
            st.error(f"Error fetching emails: {error}")
            return []
    
    def mark_as_read(self, message_id: str):
        """Mark email as read"""
        if not self.service:
            return
            
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        except HttpError as error:
            st.error(f"Error marking as read: {error}")

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
        
    st.markdown("*Automate your email related operations with Gemini*")
    st.markdown("""
<div style='color: #666;'>
    Built with ❤️ by <strong style='color: #ff4b4b;'>Imtiaz Adar</strong>
</div>
""", unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Gemini API Key
        gemini_key = st.text_input(
            "Gemini API Key (FREE)",
            type="password",
            value=os.getenv('GEMINI_API_KEY', ''),
            help="Get from https://makersuite.google.com/app/apikey"
        )
        
        # Save API key to session
        if gemini_key:
            os.environ['GEMINI_API_KEY'] = gemini_key
        
        # Credentials file upload
        st.subheader("Gmail Authentication (Optional)")
        st.info("Skip if you just want to test AI features")
        
        uploaded_file = st.file_uploader(
            "Upload credentials.json (from Google Cloud Console)",
            type=['json'],
            help="Required only for Gmail integration"
        )
        
        if uploaded_file:
            with open('credentials.json', 'wb') as f:
                f.write(uploaded_file.getbuffer())
            st.success("✅ credentials.json saved!")
        
        # Settings
        st.subheader("Settings")
        max_emails = st.slider("Max emails to process", 1, 20, 5)
        
        if st.button("🚀 Initialize Agent", type="primary"):
            if not gemini_key:
                st.error("❌ Please enter Gemini API Key")
            else:
                with st.spinner("Initializing AI Agent..."):
                    try:
                        st.session_state.agent = EmailAgent(gemini_key)
                        st.success(f"✅ AI Agent initialized with {st.session_state.agent.model_name}")
                        
                        # Try Gmail auth if credentials exist
                        if Path('credentials.json').exists():
                            success, message = st.session_state.agent.authenticate_gmail()
                            if success:
                                st.success(message)
                                st.session_state.gmail_connected = True
                            else:
                                st.warning(message)
                        else:
                            st.info("💡 Gmail not configured. Using AI-only mode.")
                        
                        st.session_state.initialized = True
                    except Exception as e:
                        st.error(f"Initialization failed: {e}")
        
        # Stats
        if hasattr(st.session_state, 'initialized') and st.session_state.initialized:
            st.markdown("---")
            st.header("📊 Stats")
            if hasattr(st.session_state.agent, 'processed_emails'):
                st.metric("Processed Emails", len(st.session_state.agent.processed_emails))
            st.metric("Model", st.session_state.agent.model_name)
    
    # Main content area
    if not hasattr(st.session_state, 'initialized') or not st.session_state.initialized:
        st.info("👈 Please enter your Gemini API Key and click 'Initialize Agent'")
        
        # Quick start guide
        with st.expander("📚 Quick Start Guide (FREE)", expanded=True):
            st.markdown("""
            ### 🎯 Step 1: Get Free Gemini API Key
            1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
            2. Sign in with your Google account
            3. Click **"Create API Key"**
            4. Copy the key (starts with AIza...)
            
            ### 🚀 Step 2: Enter API Key
            - Paste your API key in the sidebar
            - Click "Initialize Agent"
            
            ### 📧 Step 3: Gmail Integration (Optional)
            1. Go to [Google Cloud Console](https://console.cloud.google.com/)
            2. Create project → Enable Gmail API
            3. Create OAuth 2.0 credentials (Desktop app)
            4. Download `credentials.json`
            5. Upload in sidebar
            
            ### 💡 Note for Streamlit Cloud
            - Add `GEMINI_API_KEY` to Streamlit Cloud secrets
            - Or enter it manually each session
            """)
        return
    
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📧 Inbox", "✍️ Compose", "🤖 AI Playground", "📊 Analytics"])
    
    with tab1:
        st.header("📧 Email Inbox")
        
        if not hasattr(st.session_state, 'gmail_connected') or not st.session_state.gmail_connected:
            st.warning("⚠️ Gmail not connected. Upload credentials.json in sidebar to enable email features.")
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("🔄 Fetch Unread Emails", use_container_width=True):
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
            
            # AI-assisted writing
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
                    st.info("💡 Demo mode: Email not sent (Gmail not configured)")
                    st.code(f"To: {recipient}\nSubject: {subject}\n\n{body}")
            else:
                st.warning("Please fill all fields")
    
    with tab3:
        st.header("🤖 AI Playground - Test Without Gmail")
        st.markdown("*Test AI capabilities before connecting Gmail*")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Test Email Reply")
            test_email = st.text_area(
                "Paste an email to test AI reply",
                height=200,
                placeholder="Subject: Question about services\n\nHi, I'm interested in your AI services. Can you provide pricing information?"
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
            topic = st.text_input("What's the email about?", placeholder="Product launch, Meeting request, Follow up")
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
        
        # Email Analysis
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
                        
                        # Clean the response - remove markdown if present
                        clean_response = raw_response
                        clean_response = re.sub(r'```json\s*', '', clean_response)
                        clean_response = re.sub(r'```\s*', '', clean_response)
                        clean_response = clean_response.strip()
                        
                        # Parse JSON
                        parsed_data = json.loads(clean_response)
                        
                        # Display results
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
            st.info("Fetch emails to see analytics")

if __name__ == "__main__":
    main()
