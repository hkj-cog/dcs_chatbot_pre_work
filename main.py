import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from libs.config import Settings
from libs.redis_manager import redis_manager
from receiver.apis import router as save_router
from responders.api import router as ws_router
from worker.api import process_redis_message, router as pubsub_router
from fastapi.middleware.cors import CORSMiddleware

settings = Settings()


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await redis_manager.init_pool()
#
#     # Pass the function 'process_redis_message' as the callback
#     sub_task = asyncio.create_task(
#         redis_manager.start_subscriber("user_*", process_redis_message)
#     )
#
#     yield
#
#     sub_task.cancel()
#     await redis_manager.close_pool()


# app = FastAPI(lifespan=lifespan)
app = FastAPI()

raw_origins = settings.allowed_origins

origins = [o.strip() for o in raw_origins.split(",") if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)
app.include_router(save_router, prefix="/conversation")
app.include_router(pubsub_router, prefix="/webhook")
app.include_router(ws_router, prefix="/ws")
