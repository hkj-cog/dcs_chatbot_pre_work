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
