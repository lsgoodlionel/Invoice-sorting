"""服务器端密文箱：用 Fernet 加密需要落库的凭据（目前只有网页填写的 SMTP 密码）。

密钥来源优先级：
1. 环境变量 `INVOICE_SORTING_SECRET_KEY`（base64 编码的 Fernet 密钥）；
2. 否则使用 `data_dir/secret.key`，**首次加密时**生成并以 0600 权限保存。

密钥不入库、不随账本搬迁包导出、不进诊断包。密钥丢失或更换后旧密文无法解开，
解密时抛出 `SecretUnavailableError`，由调用方提示“请重新填写”，绝不以 500 结束。
"""

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from invoice_sorting.config import Settings

logger = logging.getLogger(__name__)

KEY_FILE_MODE = 0o600

MSG_ENV_KEY_INVALID = "服务器密钥 INVOICE_SORTING_SECRET_KEY 格式无效，请联系运维核对"
MSG_KEY_FILE_UNREADABLE = "服务器密钥文件无法读取，请联系运维检查数据目录权限"
MSG_KEY_MISSING = "服务器密钥已丢失"
MSG_DECRYPT_FAILED = "密文与当前服务器密钥不匹配"


class SecretUnavailableError(Exception):
    """密钥缺失、无效或与密文不匹配；message 为可直接展示的中文说明（不含任何密钥内容）。"""


def _fernet_from(raw: bytes, invalid_message: str) -> Fernet:
    try:
        return Fernet(raw.strip())
    except (ValueError, TypeError) as error:
        raise SecretUnavailableError(invalid_message) from error


def _create_key_file(path: Path) -> None:
    """以 O_EXCL 创建，已有文件时不覆盖（并发时以先写成功者为准）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, KEY_FILE_MODE)
    except FileExistsError:
        return
    with os.fdopen(fd, "wb") as handle:
        handle.write(Fernet.generate_key())
    os.chmod(path, KEY_FILE_MODE)  # 不受 umask 影响
    logger.info("已生成服务器密钥文件：%s", path.name)


def load_fernet(settings: Settings, create: bool = False) -> Fernet:
    """取加解密器；create 为 False 时密钥文件不存在即视为丢失。"""
    env_key = settings.secret_key.get_secret_value()
    if env_key.strip():
        return _fernet_from(env_key.encode(), MSG_ENV_KEY_INVALID)
    path = settings.secret_key_path
    if create and not path.exists():
        try:
            _create_key_file(path)
        except OSError as error:
            raise SecretUnavailableError(MSG_KEY_FILE_UNREADABLE) from error
    if not path.exists():
        raise SecretUnavailableError(MSG_KEY_MISSING)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SecretUnavailableError(MSG_KEY_FILE_UNREADABLE) from error
    return _fernet_from(raw, MSG_KEY_FILE_UNREADABLE)


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    return load_fernet(settings, create=True).encrypt(plaintext.encode()).decode()


def decrypt_secret(settings: Settings, token: str) -> str:
    fernet = load_fernet(settings)
    try:
        return fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as error:
        raise SecretUnavailableError(MSG_DECRYPT_FAILED) from error
