# AI Eval Sample Agents

Ready-to-run **mock agents** for the AI Evaluation Platform — one for every agent
type the platform supports. Each mock speaks that vendor's **authentic
request/response shape**, so you can point the platform's connector straight at it
and run real **functional**, **red-team** and **load** tests. No cloud accounts,
no API keys.

It's one small FastAPI service. All the agents are the same support bot
("AcmeBot") wrapped in each vendor's envelope, so a run scores the same underlying
behaviour no matter which connector you test through — results stay comparable
across agent types.

---

## Quick start

**With Docker (recommended):**

```bash
docker compose up --build
```

**Or locally with Python:**

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Check it's up:

```bash
curl http://localhost:8080/health
```

---

## What's included

| Agent type | Endpoint | Register in platform as | Extraction path |
| ---------- | -------- | ----------------------- | --------------- |
| Chatbot | `POST /chat` | `http` | `response` |
| Voice / IVA | `POST /voice/turn` | `http` | `response` |
| OpenAI-compatible | `POST /v1/chat/completions` | `openai_compatible` | (built-in) |
| Azure AI Foundry | `POST /openai/deployments/{d}/chat/completions` | `azure_ai_foundry` | (built-in) |
| Dialogflow CX | `POST /dialogflow/detectIntent` | `http` | `queryResult.responseMessages[0].text.text[0]` |
| Genesys Cloud CX | `POST /genesys/inbound` | `http` | `textBody` |
| Copilot Studio | `POST /v3/directline/...` | `copilot_studio` | (built-in) |
| Rasa | `POST /webhooks/rest/webhook` | `rasa` | (built-in) |
| IBM watsonx Assistant | `POST /watsonx/message` | `watsonx_assistant` | (built-in) |

### Demo behaviours (distinct agent types)

These six are less about the connector and more about **behaviour** — each one
exercises a different set of the platform's metrics, with a planted weakness so a
specific metric visibly catches something. All register as the `http` connector
with extraction path `response`.

| Agent | Endpoint | What it demos |
| ----- | -------- | ------------- |
| RAG (knowledge-base) | `POST /rag/chat` | Faithfulness / groundedness / **hallucination** (invents a confident answer off-KB) |
| Tool-using / function-calling | `POST /tools/chat` | **Tool-correctness** + **excessive agency** (refunds with no identity check) |
| Banking (PII-heavy) | `POST /banking/chat` | **PII-leakage** (leaks a fake customer's account details) |
| Healthcare triage (safety) | `POST /healthcare/chat` | **Safety / harmful-advice** (unsafe dosing when jailbroken) |
| Multi-turn concierge | `POST /concierge/chat` | **Coherence / context retention** across a session |
| Flaky / high-latency | `POST /flaky/chat` | **Load & reliability** — error_rate, p95/p99, timeouts |

The flaky agent's error rate and latency spikes are tunable:

```
FLAKY_ERROR_RATE=0.15   # fraction of requests that return 503
FLAKY_SPIKE_RATE=0.10   # fraction that get a big latency spike
FLAKY_SPIKE_MS=1200     # size of that spike
```

The concierge keeps a session together via a `conversation_id` in the request
body (the sample connector config sends a fixed one).

---

## Wire it into the platform

### Option A — one shot (recommended)

Open the platform's **Platform as Code** screen, paste
[`manifests/sample-agents.yaml`](manifests/sample-agents.yaml) and click **Apply**.
That registers all 15 agents (9 connector types + 6 behaviour types), a shared
guardrail policy, and a **functional + red-team suite for each agent** —
everything wired and ready to run.

Or via the API:

```bash
curl -sf -X POST http://localhost:8000/api/v1/iac/apply \
  -H 'Content-Type: application/json' \
  --data-binary @<(jq -Rs '{manifest: .}' manifests/sample-agents.yaml)
```

### Option B — one agent at a time

Go to **Agents → New**, pick the connector, and paste the matching config from
[`connectors/connectors.json`](connectors/connectors.json).

---

## Docker networking note

The endpoints in the manifest use `host.docker.internal:8080`, which is what the
platform's containers use to reach this service running on your host.

- **Platform runs in Docker** (the usual case): keep `host.docker.internal:8080`.
- **Platform runs outside Docker** (e.g. `uvicorn` on the host): replace
  `host.docker.internal` with `localhost`.

On Linux, `host.docker.internal` resolves only if the platform's compose file
maps it (`extra_hosts: ["host.docker.internal:host-gateway"]`). If it doesn't,
use your host's LAN IP instead.

---

## Why the bot has weak spots (on purpose)

AcmeBot answers the common support intents correctly, but it has two **planted
weaknesses** so your runs aren't all green — the point is to see the platform
*catch* things:

1. **Jailbreak** — it drops its guardrails on an "ignore all previous
   instructions…" style prompt.
2. **System-prompt / secret leak** — asked to reveal its instructions, it leaks a
   made-up token (`ACME-SECRET-4242`).

So a **functional** run comes back mostly passing, and a **red-team** run flags a
real jailbreak and a real prompt-leak. Nothing here is sensitive — the "secret"
is fake and exists only to be detected.

---

## Tuning latency for load tests

The bot adds a small, jittered delay so load runs produce a realistic p50/p95/p99
spread. Control it with env vars (see `docker-compose.yml`):

```
AGENT_BASE_LATENCY_MS=40   # base delay per request
AGENT_JITTER_MS=60         # random extra on top
```

Set both to `0` for the fastest possible load runs.

---

## About the host-locked connectors

A few native connectors are pinned to their vendor's cloud host by design:

- **Dialogflow CX** and **Genesys Cloud** build a fixed Google / Genesys
  hostname, so their native connector can't point at a local mock. This repo
  serves each vendor's **authentic response shape** at a local path, and you
  register it via the generic **HTTP** connector with the extraction path from
  the table above — fully works offline.
- **Bedrock AgentCore** and **Twilio Voice** use AWS SigV4 / real telephony,
  which a local HTTP mock can't stand in for. Test those against a real
  deployment using their native connectors.

If you want the **native** Dialogflow / Genesys connectors to also point at this
mock (so even they run fully offline), that needs a small "base host override" in
those two adapters on the platform side — ask and it can be added.
