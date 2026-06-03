from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_pagination import add_pagination

from app.api.v1.common.chat.router import base_chat_router
from app.api.v1.router import api_router
from app.websocket import quiz_session_ws_router, notification_ws_router
from app.websocket.chat.chat_websocket import chat_ws_router
from app.websocket.pdf_job_ws import job_ws_router
from app.websocket.student_session_ws import quiz_sessions

app = FastAPI(title="Test Platform API")

app.mount("/media", StaticFiles(directory="media"), name="media")
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
add_pagination(app)
app.include_router(api_router, prefix="/api")
app.include_router(quiz_session_ws_router)
app.include_router(notification_ws_router)

app.include_router(chat_ws_router)
app.include_router(job_ws_router)
app.include_router(quiz_sessions)
app.include_router(base_chat_router)


@app.get("/")
async def root():
    return {"status": "API running"}
