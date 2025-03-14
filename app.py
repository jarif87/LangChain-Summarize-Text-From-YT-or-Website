import os
import validators
import streamlit as st
from dotenv import load_dotenv
from langchain.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain.chains.summarize import load_summarize_chain
from langchain.schema import Document
import yt_dlp
import requests
from bs4 import BeautifulSoup
import re
import json

try:
    with open('youtube.json', 'r') as f:
        cookies = json.load(f)
    
    cookie_content = """# Netscape HTTP Cookie File
# https://curl.haxx.se/docs/http-cookies.html
# This file is generated by yt-dlp! Edit at your own risk.

"""
    for cookie in cookies:
        domain = cookie.get('domain', '')
        if not domain.startswith('.'):  # Ensure domain starts with a dot
            domain = '.' + domain
        path = cookie.get('path', '/')
        secure = "TRUE" if cookie.get('secure', False) else "FALSE"
        expires = str(int(cookie.get('expirationDate', 2147483647)))
        name = cookie.get('name', '')
        value = cookie.get('value', '')
        
        if domain and name and value:
            cookie_line = f"{domain}\tTRUE\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"
            cookie_content += cookie_line
    
    with open('youtube_cookies.txt', 'w', encoding='utf-8') as f:
        f.write(cookie_content)
except Exception as e:
    print(f"Error processing cookies: {e}")
    
# Load environment variables
load_dotenv()

# Streamlit App
st.set_page_config(page_title="LangChain: Summarize Text From YT or Website", page_icon="🦜")
st.title("🦜 LangChain: Summarize Text From YT or Website")
st.subheader("Summarize URL")

# Get API Key & URL input
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    st.error("GROQ API Key not found. Please check your environment variables.")

generic_url = st.text_input("Enter YouTube or Website URL", label_visibility="collapsed")

# LangChain Model with Groq API
llm = ChatGroq(model="gemma2-9b-it", groq_api_key=groq_api_key)

# Prompt Template
prompt_template = """
Provide a clear and concise summary in 300 words of the following content:

{text}

Focus on the main points and key insights. Write in a professional tone.
"""
prompt = PromptTemplate(template=prompt_template, input_variables=["text"])

def get_youtube_content(url):
    """Get content from YouTube video"""
    try:
        # First try youtube-transcript-api
        from youtube_transcript_api import YouTubeTranscriptApi
        from urllib.parse import urlparse, parse_qs

        # Extract video ID from URL
        if 'youtube.com' in url:
            video_id = parse_qs(urlparse(url).query)['v'][0]
        elif 'youtu.be' in url:
            video_id = urlparse(url).path[1:]
        else:
            raise ValueError("Not a valid YouTube URL")

        try:
            # Try getting transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            transcript_text = ' '.join([entry['text'] for entry in transcript_list])
        except:
            # Fallback to yt-dlp for description if transcript fails
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    video_info = ydl.extract_info(url, download=False)
                    transcript_text = video_info.get('description', 'No description available')
                except:
                    transcript_text = "Could not extract video content."

        # Get video info
        response = requests.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json")
        if response.status_code == 200:
            video_info = response.json()
            title = video_info.get('title', '')
            uploader = video_info.get('author_name', '')
        else:
            title = "Unknown Title"
            uploader = "Unknown Uploader"

        content = f"""
Video Title: {title}
Uploader: {uploader}

Content:
{transcript_text}
"""
        return [Document(page_content=content)]

    except Exception as e:
        st.error(f"Error getting YouTube content: {str(e)}")
        return None

def get_website_content(url):
    """Get content from website using requests and BeautifulSoup"""
    try:
        # Send request with headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Get title
        title = soup.title.string if soup.title else "No title found"
        
        # Get main content (adjust selectors based on the website structure)
        main_content = ""
        
        # Try to find article content first
        article = soup.find('article')
        if article:
            main_content = article.get_text()
        else:
            # If no article tag, try common content containers
            content_tags = ['main', 'div.content', 'div.post-content', 'div.article-content']
            for tag in content_tags:
                element = soup.select_one(tag)
                if element:
                    main_content = element.get_text()
                    break
            
            # If still no content, get all paragraph text
            if not main_content:
                paragraphs = soup.find_all('p')
                main_content = '\n'.join(p.get_text() for p in paragraphs)
        
        # Clean up the text
        # Remove extra whitespace and newlines
        main_content = re.sub(r'\s+', ' ', main_content).strip()
        # Remove any remaining HTML tags
        main_content = re.sub(r'<[^>]+>', '', main_content)
        
        content = f"""
Title: {title}
URL: {url}

Content:
{main_content}
"""
        return [Document(page_content=content)]
        
    except Exception as e:
        st.error(f"Error fetching or processing {url}, exception:\n{str(e)}")
        return None

if st.button("Summarize the Content from YT or Website"):
    # Validate Input
    if not groq_api_key or not generic_url.strip():
        st.error("Please provide a valid API key and URL.")
    elif not validators.url(generic_url):
        st.error("Please enter a valid URL (YouTube or a website).")
    else:
        try:
            with st.spinner("Fetching content and summarizing..."):
                # Load data from YouTube or Website
                if "youtube.com" in generic_url or "youtu.be" in generic_url:
                    docs = get_youtube_content(generic_url)
                else:
                    docs = get_website_content(generic_url)
                
                if docs is None:
                    st.stop()

                # Create the summary chain and run it
                chain = load_summarize_chain(llm, chain_type="stuff", prompt=prompt)
                output_summary = chain.run(docs)

                # Display the results
                st.success("Summary Generated Successfully!")
                
                tab1, tab2 = st.tabs(["Summary", "Raw Content"])
                
                with tab1:
                    st.write(output_summary)
                    
                with tab2:
                    if docs:
                        st.text_area("Original Content", docs[0].page_content, height=300)

        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.exception(e)