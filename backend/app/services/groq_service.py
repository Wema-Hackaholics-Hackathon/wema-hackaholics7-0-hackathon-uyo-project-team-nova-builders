"""Groq AI service — receipt OCR + AI chat.

parse_receipt():
  - Accepts file bytes + MIME type
  - Calls Groq's vision model (llava / multimodal)
  - Returns a structured ParsedReceipt dict

chat():
  - Accepts a system prompt + user message
  - Calls Groq's chat completion endpoint
  - Returns the assistant reply text
"""

from __future__ import annotations

import base64
import json
from typing import TypedDict

from groq import AsyncGroq

from ..config import get_settings

_VISION_MODEL = "qwen/qwen3.8-27b"
_CHAT_MODEL = "openai/gpt-oss-120b"


class ParsedReceipt(TypedDict):
    entry_date: str           # YYYY-MM-DD
    description: str
    amount: float
    category: str             # e.g. "Logistics", "Food", "Marketing", etc.
    entry_type: str           # "income" | "expense"
    confidence: float         # 0.0–1.0


_RECEIPT_SYSTEM = """
You are a financial document OCR assistant. Analyse the image and extract:
- entry_date: the transaction date in YYYY-MM-DD format (use today if not found)
- description: a short human-readable description
- amount: the numeric value in NGN (no currency symbol, just the number)
- category: one of: Payroll, Logistics, Software, Marketing, Sales, Food, Utilities, Other
- entry_type: "income" if money was received, "expense" if money was spent
- confidence: your confidence 0.0–1.0

Respond ONLY with valid JSON matching this schema — no markdown, no explanation:
{"entry_date":"...","description":"...","amount":0,"category":"...","entry_type":"expense","confidence":0.9}
""".strip()


async def parse_receipt(file_bytes: bytes, mime_type: str) -> ParsedReceipt:
    """Run vision OCR on a receipt/invoice image and return structured data."""
    b64 = base64.b64encode(file_bytes).decode()
    client = AsyncGroq(api_key=get_settings().GROQ_API_KEY)

    response = await client.chat.completions.create(
        model=_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                    {"type": "text", "text": _RECEIPT_SYSTEM},
                ],
            }
        ],
        max_tokens=256,
        temperature=0.1,
    )

    raw = response.choices[0].message.content or "{}"
    parsed: ParsedReceipt = json.loads(raw)
    return parsed


async def chat(
    user_message: str,
    *,
    system_prompt: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Call Groq chat completions and return the assistant reply.

    Args:
        user_message: The latest message from the user.
        system_prompt: Full system prompt with user context injected by the caller.
        history: List of prior {role, content} dicts for multi-turn context.
    """
    client = AsyncGroq(api_key=get_settings().GROQ_API_KEY)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = await client.chat.completions.create(
        model=_CHAT_MODEL,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=500,
        temperature=0.3,
    )

    return response.choices[0].message.content or ""
