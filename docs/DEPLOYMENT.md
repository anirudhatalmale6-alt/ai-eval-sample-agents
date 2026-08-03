---
title: "Deploying & Connecting Agents"
subtitle: "AI Evaluation Platform — sample agents and real cloud agents"
---

# 1. Overview

There are two kinds of agent you'll test with the platform:

- **Sample agents** (this repo) — mock, text-based agents you run locally. They
  let you exercise every platform feature (functional, red-team, load,
  governance) with **no cloud accounts and no API keys**. Use them for demos and
  for smoke-testing the platform itself.
- **Real agents** — your actual production agents on Dialogflow CX, Azure AI
  Foundry, Bedrock, Rasa, and so on. You point the platform's connector at them.

Both connect the **same way**: a connector sends the prompt to an endpoint and
reads the reply out of the JSON response. The only difference is which connector
you pick and what config it needs. This document covers deploying the sample
agents (Part 2–3) and standing up + connecting each real agent type (Part 4).

Repo: <https://github.com/anirudhatalmale6-alt/ai-eval-sample-agents>

---

# 2. Deploy the sample agents (this repo)

## 2.1 Prerequisites

- **Docker** + Docker Compose (recommended), **or** Python 3.11+.
- The AI Evaluation Platform running (locally or on a server) and reachable from
  your browser.

## 2.2 Run with Docker (recommended)

```bash
git clone https://github.com/anirudhatalmale6-alt/ai-eval-sample-agents
cd ai-eval-sample-agents
docker compose up --build
```

The service listens on port **8080**.

## 2.3 Run with Python (no Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## 2.4 Health check

```bash
curl http://localhost:8080/health
```

You should get `{"status":"ok",...}` and a list of every agent endpoint.

## 2.5 The 15 sample agents

| # | Agent | Endpoint | Register as | Extraction |
| - | ----- | -------- | ----------- | ---------- |
| 1 | Chatbot | `POST /chat` | `http` | `response` |
| 2 | Voice / IVA | `POST /voice/turn` | `http` | `response` |
| 3 | OpenAI-compatible | `POST /v1/chat/completions` | `openai_compatible` | built-in |
| 4 | Azure AI Foundry | `POST /openai/deployments/{d}/chat/completions` | `azure_ai_foundry` | built-in |
| 5 | Dialogflow CX | `POST /dialogflow/detectIntent` | `http` | `queryResult.responseMessages[0].text.text[0]` |
| 6 | Genesys Cloud CX | `POST /genesys/inbound` | `http` | `textBody` |
| 7 | Copilot Studio | `POST /v3/directline/...` | `copilot_studio` | built-in |
| 8 | Rasa | `POST /webhooks/rest/webhook` | `rasa` | built-in |
| 9 | IBM watsonx | `POST /watsonx/message` | `watsonx_assistant` | built-in |
| 10 | RAG (knowledge-base) | `POST /rag/chat` | `http` | `response` |
| 11 | Tool-using | `POST /tools/chat` | `http` | `response` |
| 12 | Banking (PII) | `POST /banking/chat` | `http` | `response` |
| 13 | Healthcare triage | `POST /healthcare/chat` | `http` | `response` |
| 14 | Multi-turn concierge | `POST /concierge/chat` | `http` | `response` |
| 15 | Flaky / high-latency | `POST /flaky/chat` | `http` | `response` |

## 2.6 Networking: reaching the mock from the platform

The endpoint the platform uses depends on where the platform runs:

| Platform runs… | Use this host in the connector |
| -------------- | ------------------------------ |
| In Docker (same machine) | `http://host.docker.internal:8080` |
| Outside Docker on the same machine | `http://localhost:8080` |
| On another machine / VM | `http://<the-mock-host-LAN-IP>:8080` |

On **Linux**, `host.docker.internal` only resolves if the platform's compose file
maps it:

```yaml
services:
  api:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

If it doesn't, use the host's LAN IP instead.

## 2.7 Tuning the agents

Set via environment (see `docker-compose.yml`):

```
AGENT_BASE_LATENCY_MS=40   # base per-request delay (all agents)
AGENT_JITTER_MS=60         # random extra, for a realistic p50/p95/p99 spread
FLAKY_ERROR_RATE=0.15      # fraction of /flaky/chat requests that return 503
FLAKY_SPIKE_RATE=0.10      # fraction that get a big latency spike
FLAKY_SPIKE_MS=1200        # size of that spike
```

## 2.8 Running the mock on a server (optional)

The mock is stateless, so you can run the same container on any VM
(`docker compose up -d`) and point the platform at `http://<vm-ip>:8080`.

> **Security note:** the sample agents have **no authentication** and deliberately
> contain unsafe/leaky responses for testing. Keep them on an internal network or
> behind a firewall — never expose them to the public internet.

---

# 3. Register the sample agents in the platform

## 3.1 One shot (recommended)

Open **Platform as Code**, paste [`manifests/sample-agents.yaml`](../manifests/sample-agents.yaml),
click **Apply**. That registers all 15 agents, a guardrail policy, and a
functional + red-team suite for each — ready to run.

Or via API:

```bash
curl -sf -X POST http://localhost:8000/api/v1/iac/apply \
  -H 'Content-Type: application/json' \
  --data-binary @<(jq -Rs '{manifest: .}' manifests/sample-agents.yaml)
```

> If the platform runs outside Docker, first replace `host.docker.internal` with
> `localhost` in the manifest.

## 3.2 One agent at a time (UI)

**Agents → New**, pick the connector, paste the matching config from
[`connectors/connectors.json`](../connectors/connectors.json).

---

# 4. Deploy & connect REAL agents

Each section below is: **what you need**, **how to stand it up**, and the exact
**connector config** to paste into the platform (**Agents → New → pick the
connector**).

## 4.1 Text-based / generic HTTP agent — connector `http`

The most general case: any agent that accepts a POST and returns JSON.

- **What you need:** a reachable HTTPS endpoint and the JSON path to the reply.
- **Connector config:**

```json
{
  "endpoint_url": "https://your-agent.example.com/chat",
  "body_template": { "prompt": "{{prompt}}" },
  "response_extraction": "reply.text",
  "headers": { "Authorization": "Bearer <token>" },
  "timeout_seconds": 30
}
```

- `body_template` is your agent's request shape; `{{prompt}}` is substituted with
  the test input. `response_extraction` is a JMESPath into the response (e.g.
  `reply.text`, `data.messages[0].content`, `output`).

## 4.2 Google Dialogflow CX — connector `dialogflow_cx`

- **What you need:** a Dialogflow CX agent, and either a short-lived access token
  or a service-account key.

**Stand up the agent:**
1. In the **Google Cloud Console**, enable the **Dialogflow API** on your project.
2. Open **Dialogflow CX** → **Create agent**. Pick a **location** (e.g. `global`
   or `us-central1`) and name it. Build a Start Flow / intents, or import a
   prebuilt agent (e.g. the sample "Order and Account Management" agent).
3. Note three values:
   - **project_id** — your GCP project id.
   - **location** — the agent's region (as above).
   - **agent_id** — the UUID in the agent's console URL
     (`.../agents/<agent_id>/...`).

**Authenticate (pick one):**
- **Quick (short-lived, ~1 hour):** run `gcloud auth print-access-token` and use
  the value as `access_token`.
- **Durable:** create a service account with the **Dialogflow API Client** role,
  download its JSON key, and paste the whole JSON as `service_account_info`.

- **Connector config (access token):**

```json
{
  "project_id": "my-gcp-project",
  "location": "us-central1",
  "agent_id": "0000-1111-2222-3333",
  "language_code": "en",
  "access_token": "ya29.a0Af..."
}
```

- **Connector config (service account):**

```json
{
  "project_id": "my-gcp-project",
  "location": "us-central1",
  "agent_id": "0000-1111-2222-3333",
  "language_code": "en",
  "service_account_info": { "type": "service_account", "project_id": "...", "private_key": "...", "client_email": "..." }
}
```

The platform calls the Dialogflow CX `detectIntent` REST endpoint directly and
reads `queryResult.responseMessages[].text.text[]`.

> **No GCP agent yet?** You can demo the Dialogflow flow with **no cloud account**
> using this repo's `/dialogflow/detectIntent` mock — it returns the authentic
> `detectIntent` shape. Register it via the `http` connector (row 5 in §2.5). If
> you want the **native** `dialogflow_cx` connector to point at the mock too
> (fully offline), I can add a base-host override to that adapter — just ask.

## 4.3 OpenAI-compatible (OpenAI, vLLM, Ollama, Together, Groq) — `openai_compatible`

- **What you need:** a `/chat/completions` endpoint, an API key, a model name.

```json
{
  "endpoint_url": "https://api.openai.com/v1/chat/completions",
  "api_key": "sk-...",
  "model": "gpt-4o-mini"
}
```

For a self-hosted model (vLLM/Ollama), point `endpoint_url` at your server, e.g.
`http://localhost:11434/v1/chat/completions` for Ollama.

## 4.4 Google Gemini — connector `google_gemini`

```json
{
  "endpoint_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
  "api_key": "AIza..."
}
```

The key is passed as a `?key=` query parameter automatically.

## 4.5 Azure AI Foundry / Azure OpenAI — connector `azure_ai_foundry`

- **What you need:** an Azure OpenAI resource with a **deployment**.
1. In **Azure AI Foundry / Azure OpenAI Studio**, deploy a model — note the
   **deployment name**.
2. From the resource's **Keys and Endpoint** page, copy the **endpoint** and a
   **key**.

```json
{
  "endpoint": "https://my-resource.openai.azure.com",
  "deployment_name": "gpt-4o-mini",
  "api_key": "<azure-key>",
  "api_version": "2024-02-01"
}
```

## 4.6 AWS Bedrock AgentCore / Bedrock model — `bedrock_agentcore` / `direct_bedrock_model`

- **What you need:** AWS credentials with Bedrock access, and either a hosted
  agent (AgentCore) or a foundation model id.
- Set AWS creds on the **platform** environment: `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (or an attached IAM role).

**Hosted agent (AgentCore):**

```json
{ "runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:1234:runtime/my-agent", "region": "us-east-1" }
```

(You can also use `gateway_id` + `target_id`.)

**Foundation model directly** (connector `direct_bedrock_model`):

```json
{ "model_id": "amazon.nova-micro-v1:0", "region": "us-east-1" }
```

## 4.7 Microsoft Copilot Studio — connector `copilot_studio`

1. Publish your Copilot Studio bot.
2. **Settings → Channels → Direct Line** → copy a **secret**.

```json
{
  "secret": "<direct-line-secret>",
  "user_id": "eval-harness",
  "poll_timeout": 20
}
```

(Leave `endpoint` unset to use the default Direct Line host.)

## 4.8 Rasa — connector `rasa`

Run your Rasa assistant with the REST channel enabled (`credentials.yml` →
`rest:`), then:

```json
{ "endpoint_url": "https://your-rasa-host/webhooks/rest/webhook" }
```

## 4.9 IBM watsonx Assistant — connector `watsonx_assistant`

From your watsonx Assistant instance, copy the message API URL and an API key:

```json
{
  "endpoint_url": "https://api.us-south.assistant.watson.cloud.ibm.com/instances/<id>/v2/assistants/<assistant-id>/message",
  "api_key": "<key>"
}
```

## 4.10 Genesys Cloud CX — connector `genesys_cloud`

- **What you need:** an OAuth **client id/secret** (client-credentials grant) and
  an **open-messaging deployment id**.

```json
{
  "region": "mypurecloud.com",
  "client_id": "<client-id>",
  "client_secret": "<client-secret>",
  "deployment_id": "<deployment-id>",
  "language": "en-US"
}
```

## 4.11 Twilio Voice — connector `twilio_phone`

- **What you need:** a Twilio account SID + auth token, a Twilio **from** number,
  and the agent's phone number to call.

```json
{
  "account_sid": "AC...",
  "auth_token": "<token>",
  "from_number": "+1500...",
  "to_number": "+1444...",
  "mode": "voice"
}
```

(SID/token can also be set on the platform as `TWILIO_ACCOUNT_SID` /
`TWILIO_AUTH_TOKEN`.)

## 4.12 LangChain / LangServe — connector `langchain_http`

```json
{ "endpoint_url": "https://your-langserve-host/invoke" }
```

---

# 5. Verify a connection

After creating an agent (sample or real):

1. On the agent, click **Health check** — it should go green.
2. Create (or reuse) a small **functional** suite and hit **Run**.
3. Open **Results** and confirm the replies came back and were scored.

If health fails, it's almost always the endpoint/host (see §2.6) or auth.

---

# 6. Troubleshooting

| Symptom | Likely cause / fix |
| ------- | ------------------ |
| Health check red on a sample agent | Wrong host — use `host.docker.internal` (platform in Docker) or `localhost` (§2.6). |
| `Connection refused` | Mock not running (`docker compose up`) or port 8080 blocked. |
| Reply is empty / whole-JSON | Wrong `response_extraction` path — check the JSON with `curl` and fix the JMESPath. |
| Dialogflow 401/403 | Access token expired (regenerate) or service account missing the Dialogflow API Client role. |
| Azure 404 | Wrong `deployment_name` or `api_version`. |
| Bedrock `AccessDenied` | AWS creds/region not set on the platform, or the role lacks Bedrock permissions. |
