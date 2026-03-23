from typing import Optional
from fastapi import Query


class StudentFilterParams:
    def __init__(
        self,
        search: Optional[str] = Query(None, description="O'quvchi ismi bo'yicha qidirish"),
        class_name: Optional[str] = Query(None, description="Sinf bo'yicha filter"),
        status: Optional[str] = Query(None, description="Holat bo'yicha filter"),
        min_score: Optional[float] = Query(None, ge=0),
        max_score: Optional[float] = Query(None, le=100),
        ordering: str = Query("created_at", description="Sort field"),
        order_direction: str = Query("desc", pattern="^(asc|desc)$"),
    ):
        self.search = search
        self.class_name = class_name
        self.status = status
        self.min_score = min_score
        self.max_score = max_score
        self.ordering = ordering
        self.order_direction = order_direction