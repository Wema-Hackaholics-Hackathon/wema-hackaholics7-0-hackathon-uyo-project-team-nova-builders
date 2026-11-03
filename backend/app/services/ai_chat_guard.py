"""Guards for FOID AI chat (POST /ledger/chat).

The assistant only talks about the signed-in user's own FOID account. The model is told
that in the system prompt, and these cheap server-side checks back it up:

  precheck(message)    — refuses obvious off-topic / prompt-injection requests before the
                         model is called (no credit is charged for those).
  clean_history(turns) — only "user"/"assistant" turns, capped in count and length, so a
                         client can't smuggle in a fake "system" message.
  mask(text)           — strips emails, phone numbers and long digit runs (NIN, BVN,
                         account numbers) from anything we put into the model's context.
  scrub_reply(text)    — the same masking on the way out, and a refusal if the reply
                         echoes the system prompt.
"""

from __future__ import annotations

import re
from typing import Iterable

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY_TURNS = 12
MAX_HISTORY_CHARS = 1500

SCOPE_HELP = ("I can help with your own FOID account: your income and spending, tax estimate, "
              "connected banks, credential and verification status, and who you share your data with.")

REFUSAL_OFF_TOPIC = "Sorry, that's outside what I can help with. " + SCOPE_HELP
REFUSAL_OTHERS = "I can only discuss your own account, not anyone else's. " + SCOPE_HELP
REFUSAL_INTERNALS = "I can't share how I'm set up. " + SCOPE_HELP

# Marker lines in our system prompt. If any appear in a reply, the model is leaking it.
PROMPT_MARKERS = ("=== ACCOUNT CONTEXT", "=== RULES", "FOID_AI_CONTEXT")

_INJECTION = re.compile(
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,20}"
    r"\b(instructions?|rules|prompts?|messages?)\b"
    r"|\b(system|hidden|initial|developer)\s+(prompt|message|instructions?)\b"
    r"|\b(repeat|print|show|reveal|output|dump)\b.{0,30}\b(your|the|system)\s+(prompt|instructions|rules)\b"
    r"|\b(jailbreak|dan mode|developer mode)\b"
    r"|\bpretend (to be|you are)\b|\bact as (a|an|if)\b|\byou are now\b",
    re.I | re.S,
)
_CODE = re.compile(
    r"\b(write|generate|create|build|give me|make|fix|debug)\b.{0,40}"
    r"\b(code|script|program|function|sql|regex|html|css|javascript|typescript|python|java)\b"
    r"|```",
    re.I | re.S,
)
_OTHER_PEOPLE = re.compile(
    r"\b(someone|somebody|anyone|another (person|user|customer)|other (people|persons?|users?|customers?)"
    r"|my (friend|wife|husband|brother|sister|boss|customer|mum|mom|dad)|this (person|user))('?s)?\b"
    r".{0,40}\b(accounts?|bvn|nin|balance|transactions?|data|credentials?|details|identity|info)\b"
    r"|\b(all|other) (users|customers)\b"
    r"|\b(look ?up|check|find|search)\b.{0,20}\b(a|another|some|any)\s+(person|user|customer|bvn|nin)\b",
    re.I | re.S,
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)(\+?234|0)[789][01]\d{8}(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)(\d[\d ]{8,}\d)(?!\d)")


def precheck(message: str) -> str | None:
    """A refusal to send back without calling the model, or None if the message may go through."""
    m = message.strip()
    if _INJECTION.search(m):
        return REFUSAL_INTERNALS
    if _OTHER_PEOPLE.search(m):
        return REFUSAL_OTHERS
    if _CODE.search(m):
        return REFUSAL_OFF_TOPIC
    return None


def _mask_digits(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return f"••••{digits[-4:]}" if len(digits) >= 9 else match.group(0)


def mask(text: str) -> str:
    """Remove contact details and identity/account numbers (keeps the last 4 digits)."""
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    return _LONG_DIGITS.sub(_mask_digits, text)


def clean_history(turns: Iterable[tuple[str, str]]) -> list[dict[str, str]]:
    out = [{"role": role, "content": mask(content[:MAX_HISTORY_CHARS])}
           for role, content in turns if role in ("user", "assistant") and content.strip()]
    return out[-MAX_HISTORY_TURNS:]


def scrub_reply(reply: str) -> str:
    if any(marker in reply for marker in PROMPT_MARKERS):
        return REFUSAL_INTERNALS
    return mask(reply).strip()
