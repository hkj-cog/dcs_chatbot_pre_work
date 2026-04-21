# DCS Chatbot API

A FastAPI-based chatbot API service integrating Google ADK Agents and Gemini models, designed for interactive chat applications.

## Features

- **RESTful API & WebSocket support** via FastAPI
- **Conversational AI** using Google Gemini-2.5-flash through an extendable agent architecture
- **Stateful chat sessions** with Redis and in-memory services
- **Pluggable architecture** (see `agent/`, `receivers/`, and `responders/` modules)
- **Custom tools/examples** for time queries and more

## Directory Structure

- `main.py` &mdash; FastAPI app entrypoint and router includes
- `agent/` &mdash; Implements root LLM agent and runner (Google ADK integration)
- `receiver/` &mdash; Handles POST/GET REST APIs for chat and session management
- `responders/` &mdash; Handles WebSocket/real-time communication
- `worker/` &mdash; Pub/sub endpoints for push subscriptions
- `libs/` &mdash; Support libraries (logger, etc)
- `curls.http` &mdash; Example HTTP requests for testing

## Quickstart

Install dependencies:

```bash
pip install -r requirements.txt
```

Run with Uvicorn:

```bash
uvicorn main:app --reload
```

## Example Use

Check `curls.http` for sample API requests (e.g., /v1/chat, /ws).

## Requirements

- Python 3.13
- FastAPI, Redis
- Google ADK agent (see agent/)

---

Project scaffolded for streamlined development and deployment on GCP/Cloud Run or similar platforms.



   columns Index = Index(['name', 'span_kind', 'parent_id', 'start_time', 'end_time',
                           'status_code', 'status_message', 'events', 'context.span_id',
                           'context.trace_id', 'attributes.llm.token_count.prompt',
                           'attributes.gcp', 'attributes.llm.tools',
                           'attributes.llm.invocation_parameters',
                           'attributes.llm.token_count.total', 'attributes.output.value',
                           'attributes.llm.output_messages', 'attributes.gen_ai',
                           'attributes.openinference.span.kind', 'attributes.input.mime_type',
                           'attributes.input.value', 'attributes.session.id',
                           'attributes.llm.model_name', 'attributes.user.id',
                           'attributes.output.mime_type', 'attributes.llm.token_count.completion',
                           'attributes.llm.provider', 'attributes.llm.input_messages',
                           'attributes.tool.description', 'attributes.tool.parameters',
                           'attributes.tool.name',
                           'attributes.llm.token_count.completion_details.reasoning',
                           'attributes.agent.name', 'attributes.eval'],
                          dtype='str')




2026-04-16 16:12:05 [INFO] dcs_chatbot: Preparing to publish message to Pub/Sub: {'sen
der': 'system', 'content': 'The current time in Sydney is 10:30 AM.'} with session_id=
f69cff3a-1902-4c7a-ad72-fd9ba8bc7546, topic=projects/cog01hygeb83z4tne1xxrhezf82e2/top
ics/adk_chat_messages
INFO:dcs_chatbot:Preparing to publish message to Pub/Sub: {'sender': 'system', 'conten
t': 'The current time in Sydney is 10:30 AM.'} with session_id=f69cff3a-1902-4c7a-ad72
-fd9ba8bc7546, topic=projects/cog01hygeb83z4tne1xxrhezf82e2/topics/adk_chat_messages
2026-04-16 16:12:05 [INFO] dcs_chatbot: Starting evaluation of last session





{
  "textPayload": "[Before Agent Callback] Modified Text: --- SYSTEM CONTEXT\nCurrent date is 2026-04-20\nLocation is Sydney\n---\ncognizant ceo\n---",
  "insertId": "1o17j1f1jq8lu",
  "resource": {
    "type": "generic_node",
    "labels": {
      "location": "global",
      "project_id": "cog01hygeb83z4tne1xxrhezf82e2",
      "namespace": "",
      "node_id": ""
    }
  },
  "timestamp": "2026-04-20T04:10:41.937504Z",
  "severity": "INFO",
  "labels": {
    "code.line.number": "178",
    "code.file.path": "/Users/2279450/codes/python/dcs/dcs-chatbot-api/models/vertex.py",
    "code.function.name": "callback"
  },
  "logName": "projects/cog01hygeb83z4tne1xxrhezf82e2/logs/otel_python_inprocess_log_name_temp",
  "receiveTimestamp": "2026-04-20T04:10:45.575707736Z"
}
