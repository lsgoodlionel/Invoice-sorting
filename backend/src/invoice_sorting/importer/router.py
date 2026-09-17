"""导入 API。由对应模块负责实现。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["导入"])
