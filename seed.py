"""Seed an empty MySQL database; never overwrite existing rows."""

import tomllib
from pathlib import Path

from sqlalchemy import URL, create_engine, text

from demo import demo_tables


def main():
    path = Path(".streamlit/secrets.toml")
    if not path.exists():
        raise SystemExit("Tạo .streamlit/secrets.toml từ tệp .example trước khi chạy seed.")
    config = tomllib.loads(path.read_text(encoding="utf-8-sig"))["mysql"]
    url = URL.create("mysql+pymysql", username=config["username"], password=config["password"],
                     host=config["host"], port=int(config.get("port", 3306)),
                     database=config.get("database", "SaaS_AI_DB"), query={"charset": "utf8mb4"})
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    tables = demo_tables()
    with engine.begin() as conn:
        for name in tables:
            if conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one():
                raise SystemExit(f"Dừng: bảng {name} đã có dữ liệu. Không ghi đè.")
        for name, frame in tables.items():
            frame.to_sql(name, conn, if_exists="append", index=False)
    engine.dispose()
    print("Đã thêm dữ liệu mô phỏng: 180 khách hàng, 12 tháng. Không phải dữ liệu kinh doanh thực.")


if __name__ == "__main__":
    main()
