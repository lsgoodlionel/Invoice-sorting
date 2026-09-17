"""文件名键：入库时计算；旧附件在启动时补算一次（幂等，只处理 file_key 为空的记录）。"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import Attachment
from invoice_sorting.evidence import file_key

logger = logging.getLogger(__name__)


def compute_file_key(original_name: str) -> str:
    """计算失败只记录日志并返回空串（空键不参与分组与匹配）。"""
    try:
        return file_key(original_name or "")
    except Exception:
        logger.exception("计算文件名键失败：%s", original_name)
        return ""


def backfill_file_keys(session: Session) -> int:
    """为 file_key 为空的附件补算文件名键并提交；返回更新条数。"""
    query = select(Attachment).where(Attachment.file_key == "")
    updated = 0
    for attachment in session.scalars(query):
        key = compute_file_key(attachment.original_name)
        if key:
            attachment.file_key = key
            updated += 1
    session.commit()
    return updated
