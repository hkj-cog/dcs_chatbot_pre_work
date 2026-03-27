import asyncio
from fastapi import FastAPI
from receiver.apis import router as save_router
from responders.api import router as ws_router
from worker.api import router as pubsub_router

app = FastAPI()

app.include_router(save_router, prefix="/v1")
app.include_router(pubsub_router, prefix="/v1")
app.include_router(ws_router)
