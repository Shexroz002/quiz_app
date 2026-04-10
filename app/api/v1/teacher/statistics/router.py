from fastapi import APIRouter
from app.api.v1.teacher.statistics.endpoints.card import statistic_router

statistic_base_router = APIRouter(prefix="/statistic", tags=["Statistics"])
statistic_base_router.include_router(statistic_router)