from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.router import api_router
from app.websocket import quiz_session_ws_router, notification_ws_router
from app.websocket.pdf_job_ws import job_ws_router

app = FastAPI(title="Test Platform API")
app.mount("/media", StaticFiles(directory="media"), name="media")
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # ruxsat berilgan domenlar
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST va h.k.
    allow_headers=["*"],  # headerlarga ruxsat
)
app.include_router(api_router, prefix="/api/v1")
app.include_router(quiz_session_ws_router)
app.include_router(notification_ws_router)
app.include_router(job_ws_router)

@app.get("/")
async def root():
    return {"status": "API running"}
