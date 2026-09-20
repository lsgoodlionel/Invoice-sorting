"""授权接口的入参校验（系统边界，全部字段都限定长度与范围）。"""

from pydantic import BaseModel, Field


class LicenseVerifyRequest(BaseModel):
    """私有化实例提交的校验请求。"""

    license_key: str = Field(min_length=1, max_length=128)
    instance_id: str = Field(min_length=1, max_length=64)
    app_version: str = Field(default="", max_length=32)
    users: int = Field(default=0, ge=0, le=1_000_000)
    tenants: int = Field(default=0, ge=0, le=1_000_000)
