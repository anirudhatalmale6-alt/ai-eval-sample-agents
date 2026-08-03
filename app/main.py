"""Sample agents for the AI Evaluation Platform.

One small FastAPI service that hosts a mock agent for every agent type the
platform supports. Each route wraps the shared AcmeBot brain (see brain.py) in
the *authentic* request/response shape of that vendor, so you can point the
platform's native connector (or the generic HTTP connector) straight at it and
run real functional, red-team and load tests - no cloud accounts required.

Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8080

Every endpoint accepts the vendor's native request body and returns that vendor's
native response body. The connector config you use in the platform (see the
../connectors folder and README) tells the platform how to read each one.
"""
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .brain import respond
from . import behaviors

app = FastAPI(title="AI Eval Sample Agents", version="1.1.0")

# Endpoints exposed, for the health payload and the landing page.
AGENTS = [
    {"type": "chatbot (generic HTTP)", "path": "POST /chat", "connector": "http"},
    {"type": "voice / IVA", "path": "POST /voice/turn", "connector": "http"},
    {"type": "OpenAI-compatible", "path": "POST /v1/chat/completions", "connector": "openai_compatible"},
    {"type": "Azure AI Foundry", "path": "POST /openai/deployments/{deployment}/chat/completions", "connector": "azure_ai_foundry"},
    {"type": "Dialogflow CX", "path": "POST /dialogflow/detectIntent", "connector": "http (Dialogflow shape)"},
    {"type": "Genesys Cloud CX", "path": "POST /genesys/inbound", "connector": "http (Genesys shape)"},
    {"type": "Microsoft Copilot Studio", "path": "POST /v3/directline/...", "connector": "copilot_studio"},
    {"type": "Rasa", "path": "POST /webhooks/rest/webhook", "connector": "rasa"},
    {"type": "IBM watsonx Assistant", "path": "POST /watsonx/message", "connector": "watsonx_assistant"},
    {"type": "RAG (knowledge-base)", "path": "POST /rag/chat", "connector": "http"},
    {"type": "Tool-using / function-calling", "path": "POST /tools/chat", "connector": "http"},
    {"type": "Banking (PII-heavy)", "path": "POST /banking/chat", "connector": "http"},
    {"type": "Healthcare triage (safety)", "path": "POST /healthcare/chat", "connector": "http"},
    {"type": "Multi-turn concierge", "path": "POST /concierge/chat", "connector": "http"},
    {"type": "Flaky / high-latency (load)", "path": "POST /flaky/chat", "connector": "http"},
]


async def _prompt_from(request: Request, *keys: str) -> str:
    """Pull the user text out of an arbitrary JSON body, trying a few common keys."""
    try:
        body = await request.json()
    except Exception:
        return ""
    for k in keys:
        v = body
        for part in k.split("."):
            if isinstance(v, dict):
                v = v.get(part)
            else:
                v = None
                break
        if isinstance(v, str) and v:
            return v
    return ""


# --------------------------------------------------------------------------- #
# Health / landing                                                             #
# --------------------------------------------------------------------------- #
@app.get("/")
@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-eval-sample-agents", "agents": AGENTS}


# --------------------------------------------------------------------------- #
# 1. Generic chatbot  (register as: http)                                      #
#    body   {"prompt": "..."}      extraction: response                        #
# --------------------------------------------------------------------------- #
@app.post("/chat")
async def chat(request: Request):
    prompt = await _prompt_from(request, "prompt", "message", "text", "input")
    r = respond(prompt)
    return {"response": r["text"], "intent": r["intent"], "confidence": r["confidence"]}


# --------------------------------------------------------------------------- #
# 2. Voice / IVA brain  (register as: http)                                    #
#    Tight-latency turn endpoint an IVR/IVA would call after speech-to-text.   #
#    body {"prompt": "..."}        extraction: response                        #
# --------------------------------------------------------------------------- #
@app.post("/voice/turn")
async def voice_turn(request: Request):
    prompt = await _prompt_from(request, "prompt", "utterance", "text", "input")
    r = respond(prompt)
    return {
        "response": r["text"],
        "intent": r["intent"],
        "confidence": r["confidence"],
        "fallback": r["intent"] == "fallback",
        "barge_in": True,
    }


# --------------------------------------------------------------------------- #
# 3/4. OpenAI-compatible + Azure AI Foundry  (chat-completions shape)          #
#      extraction: choices[0].message.content                                  #
# --------------------------------------------------------------------------- #
def _chat_completion_body(prompt: str, model: str) -> dict:
    r = respond(prompt)
    in_tokens = max(1, len(prompt.split()))
    out_tokens = max(1, len(r["text"].split()))
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": r["text"]},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": in_tokens,
            "completion_tokens": out_tokens,
            "total_tokens": in_tokens + out_tokens,
        },
    }


async def _openai_prompt(request: Request) -> tuple[str, str]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    model = body.get("model", "acmebot-1")
    prompt = ""
    for m in reversed(body.get("messages", []) or []):
        if m.get("role") == "user" and m.get("content"):
            prompt = m["content"]
            break
    return prompt, model


@app.post("/v1/chat/completions")
async def openai_chat(request: Request):
    prompt, model = await _openai_prompt(request)
    return _chat_completion_body(prompt, model)


@app.post("/openai/deployments/{deployment}/chat/completions")
async def azure_chat(deployment: str, request: Request):
    prompt, model = await _openai_prompt(request)
    return _chat_completion_body(prompt, deployment or model)


# --------------------------------------------------------------------------- #
# 5. Dialogflow CX  (detectIntent shape) - register as: http                   #
#    extraction: queryResult.responseMessages[0].text.text[0]                  #
#    Also answers the real :detectIntent path in case you add a host override. #
# --------------------------------------------------------------------------- #
def _dialogflow_body(prompt: str) -> dict:
    r = respond(prompt)
    return {
        "responseId": uuid.uuid4().hex,
        "queryResult": {
            "text": prompt,
            "languageCode": "en",
            "responseMessages": [{"text": {"text": [r["text"]]}}],
            "intent": {"displayName": r["intent"]},
            "intentDetectionConfidence": r["confidence"],
        },
    }


@app.post("/dialogflow/detectIntent")
async def dialogflow(request: Request):
    prompt = await _prompt_from(request, "queryInput.text.text", "prompt", "text")
    return _dialogflow_body(prompt)


# --------------------------------------------------------------------------- #
# 6. Genesys Cloud CX  (inbound-message shape) - register as: http             #
#    extraction: textBody                                                       #
# --------------------------------------------------------------------------- #
@app.post("/genesys/inbound")
async def genesys(request: Request):
    prompt = await _prompt_from(request, "text", "prompt", "message")
    r = respond(prompt)
    return {
        "id": uuid.uuid4().hex,
        "direction": "Outbound",
        "textBody": r["text"],
        "type": "Text",
        "channel": {"platform": "Open", "type": "Private"},
    }


# --------------------------------------------------------------------------- #
# 7. Microsoft Copilot Studio  (Direct Line 3.0) - register as: copilot_studio #
#    Stateful: start conversation -> post activity -> poll activities feed.     #
# --------------------------------------------------------------------------- #
_CONVERSATIONS: dict[str, list] = {}


@app.post("/v3/directline/conversations")
async def dl_start():
    cid = "dl_" + uuid.uuid4().hex[:12]
    _CONVERSATIONS[cid] = []
    return {"conversationId": cid, "token": "mock-token", "expires_in": 1800}


@app.post("/v3/directline/conversations/{cid}/activities")
async def dl_post_activity(cid: str, request: Request):
    try:
        activity = await request.json()
    except Exception:
        activity = {}
    prompt = activity.get("text", "")
    r = respond(prompt)
    feed = _CONVERSATIONS.setdefault(cid, [])
    # Bot reply the client will poll for (from an id other than the user's).
    feed.append(
        {
            "type": "message",
            "id": uuid.uuid4().hex,
            "from": {"id": "acmebot"},
            "text": r["text"],
            "conversation": {"id": cid},
        }
    )
    return {"id": uuid.uuid4().hex}


@app.get("/v3/directline/conversations/{cid}/activities")
async def dl_get_activities(cid: str):
    feed = _CONVERSATIONS.get(cid, [])
    return {"activities": feed, "watermark": str(len(feed))}


# --------------------------------------------------------------------------- #
# 8. Rasa  (REST webhook) - register as: rasa                                  #
#    extraction: [0].text                                                       #
# --------------------------------------------------------------------------- #
@app.post("/webhooks/rest/webhook")
async def rasa(request: Request):
    prompt = await _prompt_from(request, "message", "text", "prompt")
    r = respond(prompt)
    sender = "acmebot"
    return JSONResponse([{"recipient_id": sender, "text": r["text"]}])


# --------------------------------------------------------------------------- #
# 9. IBM watsonx Assistant  (message API) - register as: watsonx_assistant     #
#    extraction: output.generic[0].text                                         #
# --------------------------------------------------------------------------- #
@app.post("/watsonx/message")
async def watsonx(request: Request):
    prompt = await _prompt_from(request, "input.text", "text", "prompt")
    r = respond(prompt)
    return {
        "output": {
            "generic": [{"response_type": "text", "text": r["text"]}],
            "intents": [{"intent": r["intent"], "confidence": r["confidence"]}],
            "entities": [],
        }
    }


# --------------------------------------------------------------------------- #
# Demo behaviours (distinct agent TYPES) - all register as the http connector,  #
# extraction: response. Each has a planted weakness a specific metric catches.  #
# --------------------------------------------------------------------------- #
@app.post("/rag/chat")
async def rag(request: Request):
    prompt = await _prompt_from(request, "prompt", "message", "text", "input")
    return behaviors.rag_respond(prompt)


@app.post("/tools/chat")
async def tools(request: Request):
    prompt = await _prompt_from(request, "prompt", "message", "text", "input")
    return behaviors.tool_respond(prompt)


@app.post("/banking/chat")
async def banking(request: Request):
    prompt = await _prompt_from(request, "prompt", "message", "text", "input")
    return behaviors.banking_respond(prompt)


@app.post("/healthcare/chat")
async def healthcare(request: Request):
    prompt = await _prompt_from(request, "prompt", "message", "text", "input")
    return behaviors.healthcare_respond(prompt)


@app.post("/concierge/chat")
async def concierge(request: Request):
    prompt = await _prompt_from(request, "prompt", "message", "text", "input")
    try:
        body = await request.json()
    except Exception:
        body = {}
    cid = (body or {}).get("conversation_id") or (body or {}).get("session_id") or "default"
    return behaviors.concierge_respond(cid, prompt)


@app.post("/flaky/chat")
async def flaky(request: Request):
    prompt = await _prompt_from(request, "prompt", "message", "text", "input")
    if behaviors.flaky_should_error():
        return JSONResponse({"error": "upstream timeout", "code": "503"}, status_code=503)
    return behaviors.flaky_response(prompt)


# --------------------------------------------------------------------------- #
# Dialogflow CX native path (.../sessions/{id}:detectIntent).                   #
# Registered LAST so its greedy path param can't shadow the specific /v3/       #
# Direct Line routes above. Only useful if you add a base-host override to the  #
# native dialogflow_cx connector; the /dialogflow/detectIntent route above is   #
# the one the sample connector config actually uses.                            #
# --------------------------------------------------------------------------- #
@app.post("/v3/{full_path:path}")
async def dialogflow_native(full_path: str, request: Request):
    prompt = await _prompt_from(request, "queryInput.text.text", "prompt", "text")
    return _dialogflow_body(prompt)
