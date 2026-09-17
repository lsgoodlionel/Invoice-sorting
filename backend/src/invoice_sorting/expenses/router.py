"""支出记录 API。由对应模块负责实现。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["支出记录"])
