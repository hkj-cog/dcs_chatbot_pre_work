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




   attributes mappingproxy = mappingproxy({'openinference.span.kind': 'AGENT', 'agent.name': 'root_agent', 'user.id': 'your_user_id_here', 'gen_ai.operation.name': 'invoke_agent', 'gen_ai.agent.description': 'Tells the current time in a specified city.', 'gen_ai.agent.name': 'root_agent', 'gen_ai.conversation.id': 'dbad6237-1555-4175-99a3-79f1de5bde9d', 'session.id': 'dbad6237-1555-4175-99a3-79f1de5bde9d', 'session.created_on': '1970-01-01T00:00:00', 'output.value': '{"model_version":"gemini-2.5-flash","content":{"parts":[{"text":"Gurugram, also known as Gurgaon, is a city located in the northern Indian state of Haryana. It is situated near the Delhi–Haryana border, approximately 30 kilometers (19 mi) southwest of the national capital New Delhi. Gurugram is considered one of the major satellite cities of Delhi and is part of the National Capital Region of India. It is also about 268 kilometers (167 mi) south of Chandigarh, the state capital of Haryana."}],"role":"model"},"grounding_metadata":{"grounding_chunks":[{"web":{"domain":"wikipedia.org","title":"wikipedia.org","uri":"https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEOQYbheJYr-n9hrZc1CPLJsyEs3myn3omNJ776rnnekzRpSvk6twok3whglnD52QY2xbz_niDTIfAKOad9NHVTw9VNNtVpZfFonIGCD0j_1Bryxjr1gEGRmMyWSXg_Sso="}},{"web":{"domain":"google.com","title":"google.com","uri":"https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGbkvfnZLGgDUH9VuiszverHvjk3bciokJu_gsT8Q7WXChqDN3A0_RLXpouj6MQ9eWUBwdeCqKxjUekOON6T7AIIUO8Fq8xsQNvnhSz10zPJTAv4wM54lbHnc7bEfQ6fpU_3b-oPQ-O2d0oDTvk0fzfw-FUtR-eX8iVtw=="}}],"grounding_supports":[{"grounding_chunk_indices":[0,1],"segment":{"start_index":221,"end_index":339,"text":"Gurugram is considered one of the major satellite cities of Delhi and is part of the National Capital Region of India."}},{"grounding_chunk_indices":[0,1],"segment":{"start_index":340,"end_index":431,"text":"It is also about 268 kilometers (167 mi) south of Chandigarh, the state capital of Haryana."}}],"retrieval_metadata":{},"search_entry_point":{"rendered_content":"<style>\\n.container {\\n  align-items: center;\\n  border-radius: 8px;\\n  display: flex;\\n  font-family: Google Sans, Roboto, sans-serif;\\n  font-size: 14px;\\n  line-height: 20px;\\n  padding: 8px 12px;\\n}\\n.chip {\\n  display: inline-block;\\n  border: solid 1px;\\n  border-radius: 16px;\\n  min-width: 14px;\\n  padding: 5px 16px;\\n  text-align: center;\\n  user-select: none;\\n  margin: 0 8px;\\n  -webkit-tap-highlight-color: transparent;\\n}\\n.carousel {\\n  overflow: auto;\\n  scrollbar-width: none;\\n  white-space: nowrap;\\n  margin-right: -12px;\\n}\\n.headline {\\n  display: flex;\\n  margin-right: 4px;\\n}\\n.gradient-container {\\n  position: relative;\\n}\\n.gradient {\\n  position: absolute;\\n  transform: translate(3px, -9px);\\n  height: 36px;\\n  width: 9px;\\n}\\n@media (prefers-color-scheme: light) {\\n  .container {\\n    background-color: #fafafa;\\n    box-shadow: 0 0 0 1px #0000000f;\\n  }\\n  .headline-label {\\n    color: #1f1f1f;\\n  }\\n  .chip {\\n    background-color: #ffffff;\\n    border-color: #d2d2d2;\\n    color: #5e5e5e;\\n    text-decoration: none;\\n  }\\n  .chip:hover {\\n    background-color: #f2f2f2;\\n  }\\n  .chip:focus {\\n    background-color: #f2f2f2;\\n  }\\n  .chip:active {\\n    background-color: #d8d8d8;\\n    border-color: #b6b6b6;\\n  }\\n  .logo-dark {\\n    display: none;\\n  }\\n  .gradient {\\n    background: linear-gradient(90deg, #fafafa 15%, #fafafa00 100%);\\n  }\\n}\\n@media (prefers-color-scheme: dark) {\\n  .container {\\n    background-color: #1f1f1f;\\n    box-shadow: 0 0 0 1px #ffffff26;\\n  }\\n  .headline-label {\\n    color: #fff;\\n  }\\n  .chip {\\n    background-color: #2c2c2c;\\n    border-color: #3c4043;\\n    color: #fff;\\n    text-decoration: none;\\n  }\\n  .chip:hover {\\n    background-color: #353536;\\n  }\\n  .chip:focus {\\n    background-color: #353536;\\n  }\\n  .chip:active {\\n    background-color: #464849;\\n    border-color: #53575b;\\n  }\\n  .logo-light {\\n    display: none;\\n  }\\n  .gradient {\\n    background: linear-gradient(90deg, #1f1f1f 15%, #1f1f1f00 100%);\\n  }\\n}\\n</style>\\n<div class=\\"container\\">\\n  <div class=\\"headline\\">\\n    <svg class=\\"logo-light\\" width=\\"18\\" height=\\"18\\" viewBox=\\"9 9 35 35\\" fill=\\"none\\" xmlns=\\"http://www.w3.org/2000/svg\\">\\n      <path fill-rule=\\"evenodd\\" clip-rule=\\"evenodd\\" d=\\"M42.8622 27.0064C42.8622 25.7839 42.7525 24.6084 42.5487 23.4799H26.3109V30.1568H35.5897C35.1821 32.3041 33.9596 34.1222 32.1258 35.3448V39.6864H37.7213C40.9814 36.677 42.8622 32.2571 42.8622 27.0064V27.0064Z\\" fill=\\"#4285F4\\"/>\\n      <path fill-rule=\\"evenodd\\" clip-rule=\\"evenodd\\" d=\\"M26.3109 43.8555C30.9659 43.8555 34.8687 42.3195 37.7213 39.6863L32.1258 35.3447C30.5898 36.3792 28.6306 37.0061 26.3109 37.0061C21.8282 37.0061 18.0195 33.9811 16.6559 29.906H10.9194V34.3573C13.7563 39.9841 19.5712 43.8555 26.3109 43.8555V43.8555Z\\" fill=\\"#34A853\\"/>\\n      <path fill-rule=\\"evenodd\\" clip-rule=\\"evenodd\\" d=\\"M16.6559 29.8904C16.3111 28.8559 16.1074 27.7588 16.1074 26.6146C16.1074 25.4704 16.3111 24.3733 16.6559 23.3388V18.8875H10.9194C9.74388 21.2072 9.06992 23.8247 9.06992 26.6146C9.06992 29.4045 9.74388 32.022 10.9194 34.3417L15.3864 30.8621L16.6559 29.8904V29.8904Z\\" fill=\\"#FBBC05\\"/>\\n      <path fill-rule=\\"evenodd\\" clip-rule=\\"evenodd\\" d=\\"M26.3109 16.2386C28.85 16.2386 31.107 17.1164 32.9095 18.8091L37.8466 13.8719C34.853 11.082 30.9659 9.3736 26.3109 9.3736C19.5712 9.3736 13.7563 13.245 10.9194 18.8875L16.6559 23.3388C18.0195 19.2636 21.8282 16.2386 26.3109 16.2386V16.2386Z\\" fill=\\"#EA4335\\"/>\\n    </svg>\\n    <svg class=\\"logo-dark\\" width=\\"18\\" height=\\"18\\" viewBox=\\"0 0 48 48\\" xmlns=\\"http://www.w3.org/2000/svg\\">\\n      <circle cx=\\"24\\" cy=\\"23\\" fill=\\"#FFF\\" r=\\"22\\"/>\\n      <path d=\\"M33.76 34.26c2.75-2.56 4.49-6.37 4.49-11.26 0-.89-.08-1.84-.29-3H24.01v5.99h8.03c-.4 2.02-1.5 3.56-3.07 4.56v.75l3.91 2.97h.88z\\" fill=\\"#4285F4\\"/>\\n      <path d=\\"M15.58 25.77A8.845 8.845 0 0 0 24 31.86c1.92 0 3.62-.46 4.97-1.31l4.79 3.71C31.14 36.7 27.65 38 24 38c-5.93 0-11.01-3.4-13.45-8.36l.17-1.01 4.06-2.85h.8z\\" fill=\\"#34A853\\"/>\\n      <path d=\\"M15.59 20.21a8.864 8.864 0 0 0 0 5.58l-5.03 3.86c-.98-2-1.53-4.25-1.53-6.64 0-2.39.55-4.64 1.53-6.64l1-.22 3.81 2.98.22 1.08z\\" fill=\\"#FBBC05\\"/>\\n      <path d=\\"M24 14.14c2.11 0 4.02.75 5.52 1.98l4.36-4.36C31.22 9.43 27.81 8 24 8c-5.93 0-11.01 3.4-13.45 8.36l5.03 3.85A8.86 8.86 0 0 1 24 14.14z\\" fill=\\"#EA4335\\"/>\\n    </svg>\\n    <div class=\\"gradient-container\\"><div class=\\"gradient\\"></div></div>\\n  </div>\\n  <div class=\\"carousel\\">\\n    <a class=\\"chip\\" href=\\"https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEEFWp1SIJX9XCI0j_wgfmwWhZ0xsDz-mORw9Lg-4qwcDVyWpcG8FQXd79Mrw7ajXNApvDcdTKLF9YvQXP8XR7qsgMF9NoBNj-GFh1qvZgusuJUDHAi_HmqwMF4OKDZNj27IppzBkmofp4H3P9N7_xP6LZcTwmGcaWF7eVS6YCIKdPs1Q_brYDtepj9qt6XUILSIwfR\\">where is Gurugram</a>\\n    <a class=\\"chip\\" href=\\"https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH1wlNN4gviohWbEEf98LWcom7rDzEDOKVXR-lzM6-OJeUvhaqv-9hWH7y8wrKLAeUZK6gbcJV8kpFyUHoIB0sH_T9z9TqxZbLlMcBZm4wZd4jOgZKmmOclf8TzBZFEgoA3CwM_teg4pcO1Cd8h9Ds91b-BemMaaJUOSWT74DSEQwgCXOAoN6rFb5LGMxp2YWbzbhjM\\">Gurugram location</a>\\n  </div>\\n</div>\\n"},"web_search_queries":["Gurugram location","where is Gurugram"]},"finish_reason":"STOP","usage_metadata":{"candidates_token_count":98,"candidates_tokens_details":[{"modality":"TEXT","token_count":98}],"prompt_token_count":329,"prompt_tokens_details":[{"modality":"TEXT","token_count":329}],"thoughts_token_count":112,"tool_use_prompt_token_count":49,"tool_use_prompt_tokens_details":[{"modality":"TEXT","token_count":49}],"total_token_count":588,"traffic_type":"ON_DEMAND"},"invocation_id":"e-2a2edf5a-a616-4e67-972f-ff8ccb7a1dcf","author":"root_agent","actions":{"state_delta":{},"artifact_delta":{},"requested_auth_configs":{},"requested_tool_confirmations":{}},"id":"d7ddc6d7-fca0-4761-9e9a-06e9b05d5aff","timestamp":1777604783.165774}', 'output.mime_type': 'application/json'})
    special variables

