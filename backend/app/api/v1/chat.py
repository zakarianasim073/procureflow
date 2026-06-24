"""Chat API routes"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.core.security import get_optional_user
from app.core.gpt_client import BOQChatClient
from app.core.ollama_client import OllamaClient

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    language: Optional[str] = "en"
    engine: Optional[str] = "auto"


class ChatResponse(BaseModel):
    success: bool
    content: str
    tokens_used: int = 0
    engine: str = "rule-based"


chat_client = BOQChatClient()
ollama_client = OllamaClient()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(get_optional_user)):
    """Chat with AI assistant"""
    try:
        if req.engine in ("auto", "ollama"):
            if await ollama_client.is_available():
                r = await ollama_client.chat(req.messages, req.language)
                if r["success"]:
                    return ChatResponse(**r)
        
        r = await chat_client.chat(
            user_id=user["id"],
            messages=req.messages,
            language=req.language
        )
        return ChatResponse(
            success=r["success"],
            content=r["content"],
            tokens_used=r.get("tokens_used", 0),
            engine=r.get("engine", "rule-based")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@router.get("/models")
async def list_models(user: dict = Depends(get_optional_user)):
    """List available AI models"""
    ollama_available = await ollama_client.is_available()
    ollama_models = []
    if ollama_available:
        ollama_models = await ollama_client.list_models()
    
    return {
        "success": True,
        "models": {
            "ollama": {
                "available": ollama_available,
                "models": ollama_models,
            },
            "openai": {
                "available": bool(chat_client.use_openai),
            },
            "anthropic": {
                "available": bool(chat_client.use_anthropic),
            }
        }
    }
