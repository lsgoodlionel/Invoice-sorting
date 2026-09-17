"""批次/导出/统计测试共用的 API 构造函数（本文件不含测试用例）。"""

import io
import itertools

from PIL import Image

_COLORS = itertools.count(1)


def png_bytes(size: tuple[int, int] = (12, 12)) -> bytes:
    """每次生成颜色不同的 PNG，避免文件哈希重复。"""
    value = next(_COLORS)
    color = (value % 256, (value // 256) % 256, (value // 65536) % 256)
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def category_id(client, name: str) -> int:
    categories = client.get("/api/categories").json()["data"]
    return next(item["id"] for item in categories if item["name"] == name)


def project_id(client, name: str) -> int:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def upload(client, expense_id: int, files: list[tuple[str, bytes]], kind: str | None = None):
    multipart = [("files", (name, content, "application/octet-stream")) for name, content in files]
    data = {"kind": kind} if kind else {}
    response = client.post(f"/api/expenses/{expense_id}/attachments", files=multipart, data=data)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def make_expense(
    client,
    *,
    spent_on: str = "2026-09-15",
    cents: int = 96000,
    merchant: str = "京东",
    with_invoice: bool = True,
    **fields,
) -> dict:
    """默认无分类、带一张发票图片：必需项齐全（状态“凭证齐全”）。"""
    payload = {"spent_on": spent_on, "amount_cents": cents, "merchant": merchant, **fields}
    response = client.post("/api/expenses", json=payload)
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    if with_invoice:
        detail = upload(client, detail["id"], [("发票.png", png_bytes())], kind="invoice")
    return detail


def make_batch(client, name: str = "2026-09 第1批", **fields) -> dict:
    response = client.post("/api/batches", json={"name": name, **fields})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def add_items(client, batch_id: int, ids: list[int], force: bool = False):
    return client.post(f"/api/batches/{batch_id}/items", json={"add": ids, "force": force})


def batch_with(client, count: int, name: str = "第1批", **expense_fields) -> tuple[dict, list]:
    batch = make_batch(client, name)
    expenses = [
        make_expense(client, cents=10000 + index * 123, merchant=f"商家{index}", **expense_fields)
        for index in range(count)
    ]
    response = add_items(client, batch["id"], [expense["id"] for expense in expenses])
    assert response.status_code == 200, response.text
    return response.json()["data"], expenses


def expense_detail(client, expense_id: int) -> dict:
    return client.get(f"/api/expenses/{expense_id}").json()["data"]
