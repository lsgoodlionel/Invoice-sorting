"""旧版数据库启动时自动补齐新增列，已有数据保留。"""

import sqlite3

from sqlalchemy import inspect

from invoice_sorting.db.session import create_db_engine, init_db


def test_init_db_adds_missing_columns_to_existing_tables(tmp_path):
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE invoice_data (attachment_id INTEGER PRIMARY KEY, invoice_no VARCHAR(50))"
        )
        conn.execute(
            "CREATE TABLE attachment (id INTEGER PRIMARY KEY, file_path VARCHAR(500), "
            "original_name VARCHAR(300), sha256 VARCHAR(64), mime VARCHAR(100), size INTEGER)"
        )
        conn.execute("INSERT INTO invoice_data VALUES (1, 'A001')")
    engine = create_db_engine(f"sqlite:///{db_path}")

    init_db(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("invoice_data")}
    assert {"region_name", "order_no", "tax_category", "seller_name"} <= columns
    attachment_columns = {
        column["name"] for column in inspect(engine).get_columns("attachment")
    }
    assert {
        "source_document_id",
        "source_page_start",
        "source_page_end",
        "source_splitter",
    } <= attachment_columns
    assert "source_document" in inspect(engine).get_table_names()
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT invoice_no, region_name FROM invoice_data").one()
    assert tuple(row) == ("A001", "")
