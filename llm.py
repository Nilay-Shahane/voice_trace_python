import os
from dotenv import load_dotenv
load_dotenv()

# from langchain_groq import ChatGroq

# from langchain_openai import ChatOpenAI

# llm = ChatGroq(
#     model="llama-3.1-8b-instant",  # fast + cheap
#     temperature=0
# )
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0,
    top_p=1.0,
    max_tokens=512,
    timeout=30,
    max_retries=2
)

print("LLM INITIALIZATION")