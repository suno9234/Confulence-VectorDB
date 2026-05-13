"""
llm.py — LLM 클라이언트 초기화

.env의 LLM_PROVIDER / LLM_MODEL을 읽어 LangChain chat model 객체를 반환한다.
지원 provider: openai, anthropic
"""

import os
from dotenv import load_dotenv
load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")       # 사용할 LLM 서비스 (openai | anthropic)
LLM_MODEL    = os.getenv("LLM_MODEL",    "gpt-4o-mini")  # 모델명 (예: gpt-4o, claude-sonnet-4-5)


def get_llm():
    """LLM_PROVIDER에 맞는 LangChain chat model 인스턴스를 반환. streaming=True로 고정."""
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=LLM_MODEL, temperature=0, streaming=True)

    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=LLM_MODEL, temperature=0, streaming=True)

    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {LLM_PROVIDER}  (openai | anthropic)")
