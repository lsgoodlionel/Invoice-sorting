"""网页导入流程（设计 5）：登记 → 分片上传 → 合并校验并预览 → 确认后后台导入 → 查询结果。

接口层只负责把请求映射到当前账套（或平台指定的账套），流程与状态都在这里：

- uploading：登记后等待分片，同一片可重传，顺序不限；
- ready：分片已按序合并、整包 SHA-256 与 zip 结构都已核对，report 为预览；
- running → done / failed：确认后在后台导入，done 时 report 为导入结果，包文件随即删除。
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.db.models import now
from invoice_sorting.migration import engine_bridge
from invoice_sorting.migration.engine_bridge import MODE_REPLACE
from invoice_sorting.migration.restore import read_manifest
from invoice_sorting.migration.tenants import tenant_name
from invoice_sorting.migration.upload_files import (
    assemble,
    received_parts,
    sweep_all,
    sweep_root,
    write_part,
)
from invoice_sorting.migration.upload_store import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RUNNING,
    STATUS_UPLOADING,
    UploadSession,
    UploadStore,
    staging_root,
)

logger = logging.getLogger(__name__)

STATE_KEY = "import_uploads"

MSG_PART_INDEX = "分片序号超出范围：共 {count} 片，序号从 0 开始"
MSG_NOT_UPLOADING = "上传已完成，不能再修改分片；如需重传请取消后重新上传"
MSG_MISSING_PARTS = "账本包缺少分片：{parts}，请补传后再完成"
MSG_HASH_MISMATCH = "账本包整体校验和不符（上传过程中可能损坏），请取消后重新上传"
MSG_NOT_READY = "请先完成上传并生成预览，再确认导入"
MSG_CANNOT_COMPLETE = "该导入已开始或已结束，不能再次完成上传"
MSG_CONFIRM_NAME = "覆盖导入会整体替换当前账套，请输入账套名称「{name}」以确认"
MSG_RUNNING = "正在导入，无法取消；请等待导入结束"
MSG_IMPORT_FAILED = "导入失败，请查看服务端日志"
MSG_FAILED_REASON = "导入失败：{reason}"
MISSING_PREVIEW_LIMIT = 20


def install(app: Any) -> None:
    """装配会话存储并清理上次运行遗留的过期会话（启动时调用一次）。"""
    settings = app.state.settings
    setattr(app.state, STATE_KEY, UploadStore(settings))
    removed = sweep_all(settings, now())
    if removed:
        logger.info("启动时清理了 %s 个过期的导入会话", removed)


def store_of(app: Any) -> UploadStore:
    return getattr(app.state, STATE_KEY)


def start_upload(
    app: Any, slug: str, filename: str, total_size: int, part_size: int, sha256: str
) -> UploadSession:
    """登记上传会话；顺带清理该账套里超过 24 小时的旧会话。"""
    store = store_of(app)
    sweep_root(staging_root(app.state.settings, slug), now())
    session = store.create(slug, filename.strip(), total_size, part_size, sha256)
    logger.info("账套 %s 登记网页导入 %s（%s 字节）", slug, session.id, total_size)
    return session


async def receive_part(
    app: Any, slug: str, upload_id: str, index: int, chunks: AsyncIterator[bytes]
) -> UploadSession:
    """接收一片（流式落盘）；片号与大小不符 400，已完成的会话 409。"""
    store = store_of(app)
    session = store.require(slug, upload_id)
    if session.status != STATUS_UPLOADING:
        raise ConflictError(MSG_NOT_UPLOADING)
    if not 0 <= index < session.part_count:
        raise AppError(MSG_PART_INDEX.format(count=session.part_count))
    await write_part(chunks, store.parts_dir(session), index, session.part_bytes(index))
    return session


def complete_upload(app: Any, slug: str, upload_id: str, mode: str) -> UploadSession:
    """合并分片并校验整包，然后生成预览；已合并过的会话只重新预览（切换模式时用）。"""
    store = store_of(app)
    session = store.require(slug, upload_id)
    if session.status not in (STATUS_UPLOADING, STATUS_READY):
        raise ConflictError(MSG_CANNOT_COMPLETE)
    with store.exclusive(session):
        if session.status == STATUS_UPLOADING:
            session = _assemble_and_verify(store, session)
        report = engine_bridge.preview(*_engine_args(app, store, session), mode)
        return store.update(session, mode=mode, report=report, error="")


def _assemble_and_verify(store: UploadStore, session: UploadSession) -> UploadSession:
    """按序合并并核对 SHA-256 与 zip 结构；任何一步不通过都作废会话（数据无从修补）。"""
    missing = missing_parts(store, session)
    if missing:
        shown = "、".join(str(index) for index in missing[:MISSING_PREVIEW_LIMIT])
        raise AppError(MSG_MISSING_PARTS.format(parts=shown))
    package = store.package_path(session)
    try:
        digest = assemble(store.parts_dir(session), session.part_count, package, session.total_size)
        if digest != session.sha256:
            raise AppError(MSG_HASH_MISMATCH)
        read_manifest(package)  # zip 结构、清单、版本与成员路径安全体检
    except AppError as error:
        store.discard_data(session)
        store.update(session, status=STATUS_FAILED, error=error.message)
        raise
    store.discard_parts(session)
    return store.update(session, status=STATUS_READY)


def missing_parts(store: UploadStore, session: UploadSession) -> tuple[int, ...]:
    received = set(received_parts(store.parts_dir(session), session.part_count))
    return tuple(index for index in range(session.part_count) if index not in received)


def confirm_import(
    app: Any, slug: str, upload_id: str, mode: str, confirm_name: str
) -> UploadSession:
    """确认导入：校验状态与覆盖确认名后标记为 running，真正的导入由后台任务执行。"""
    store = store_of(app)
    session = store.require(slug, upload_id)
    if session.status != STATUS_READY:
        raise ConflictError(MSG_NOT_READY)
    if not engine_bridge.is_mode_available(mode):
        raise AppError(engine_bridge.MSG_MERGE_UNAVAILABLE)
    if mode == MODE_REPLACE:
        _check_confirm_name(app, slug, confirm_name)
    with store.exclusive(session):
        session = store.require(slug, upload_id)  # 取锁后再读一次，防止重复确认
        if session.status != STATUS_READY:
            raise ConflictError(MSG_NOT_READY)
        return store.update(session, status=STATUS_RUNNING, mode=mode, error="")


def _check_confirm_name(app: Any, slug: str, confirm_name: str) -> None:
    expected = tenant_name(app, slug).strip()
    if (confirm_name or "").strip() != expected:
        raise AppError(MSG_CONFIRM_NAME.format(name=expected))


def run_confirmed(app: Any, slug: str, upload_id: str) -> None:
    """后台任务：执行导入并记录结果；必须兜住所有异常，否则会话永远停在 running。"""
    store = store_of(app)
    session = store.require(slug, upload_id)
    try:
        report = engine_bridge.execute(*_engine_args(app, store, session), session.mode)
    except Exception as error:  # noqa: BLE001 - 后台任务兜底，原因写进会话供界面展示
        logger.exception("账套 %s 网页导入 %s 失败", slug, upload_id)
        store.update(session, status=STATUS_FAILED, error=_failure_reason(error))
        return
    store.discard_data(session)
    store.update(session, status=STATUS_DONE, report=report, error="")
    logger.info("账套 %s 网页导入 %s 完成（%s 模式）", slug, upload_id, session.mode)


def _engine_args(app: Any, store: UploadStore, session: UploadSession) -> tuple:
    """引擎约定的前四个参数：运行时、控制库会话工厂、包路径与目标账套。"""
    return (
        app.state.tenants,
        app.state.control_session_factory,
        store.package_path(session),
        session.slug,
    )


def _failure_reason(error: Exception) -> str:
    """业务错误原样告知用户；其他异常只给通用文案，细节只进服务端日志。"""
    if isinstance(error, AppError):
        return MSG_FAILED_REASON.format(reason=error.message)
    return MSG_IMPORT_FAILED


def cancel_upload(app: Any, slug: str, upload_id: str) -> None:
    """取消并删除会话的全部文件；导入进行中不允许取消。"""
    store = store_of(app)
    session = store.require(slug, upload_id)
    if session.status == STATUS_RUNNING:
        raise ConflictError(MSG_RUNNING)
    store.remove(session)
    logger.info("账套 %s 取消网页导入 %s", slug, upload_id)
