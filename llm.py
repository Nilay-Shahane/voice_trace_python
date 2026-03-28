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
    model="gpt-4o-mini",   # BEST choice for your use case
    temperature=0
)

print("LLM INITIALIZATION")
print('LLM INITIALIZATION')