"""搬迁导入的错误类型：放在独立模块，restore、package 与账号恢复都能引用而不互相循环导入。"""

from invoice_sorting.common.errors import AppError


class ImportRejectedError(AppError):
    """校验失败：搬迁包不合法、版本过新或目标账套不可用。未写入任何数据。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message, status_code=status_code)
