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
        conn.execute("INSERT INTO invoice_data VALUES (1, 'A001')")
    engine = create_db_engine(f"sqlite:///{db_path}")

    init_db(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("invoice_data")}
    assert {"region_name", "order_no", "tax_category", "seller_name"} <= columns
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT invoice_no, region_name FROM invoice_data").one()
    assert tuple(row) == ("A001", "")
