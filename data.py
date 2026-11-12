"""Read-only, parameterized customer-month queries for MySQL 8 and demo SQLite."""

import os

import pandas as pd
import streamlit as st
from sqlalchemy import URL, create_engine, text
from sqlalchemy.pool import StaticPool

from demo import demo_tables

SEGMENTS = ("Startup", "SMB", "Enterprise")
STATUSES = ("Active", "Churned", "Upgraded")


def mysql_settings():
    try:
        settings = dict(st.secrets.get("mysql", {}))
    except FileNotFoundError:
        settings = {}
    if not settings and os.getenv("DB_HOST"):
        settings = {"host": os.environ["DB_HOST"], "port": os.getenv("DB_PORT", "3306"),
                    "database": os.getenv("DB_NAME", "SaaS_AI_DB"),
                    "username": os.getenv("DB_USER", "saas_app"), "password": os.getenv("DB_PASSWORD", "")}
    return settings


@st.cache_resource
def get_engine(source, settings):
    if source == "Demo":
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        with engine.begin() as conn:
            for table, frame in demo_tables().items():
                frame.to_sql(table, conn, index=False)
        return engine
    if not settings:
        raise ValueError("Chưa cấu hình MySQL")
    url = URL.create("mysql+pymysql", username=settings["username"], password=settings["password"],
                     host=settings["host"], port=int(settings.get("port", 3306)),
                     database=settings.get("database", "SaaS_AI_DB"), query={"charset": "utf8mb4"})
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args={"connect_timeout": 5})


@st.cache_data(ttl=300, max_entries=8)
def date_bounds(source, settings):
    with get_engine(source, settings).connect() as conn:
        row = conn.execute(text("SELECT MIN(usage_month), MAX(usage_month) FROM UsageLogs")).one()
    return tuple(pd.Timestamp(value).date() if value is not None else None for value in row)


def build_query(start, end, segments, status="Tất cả", search="", risk_only=False, latest_only=False):
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("Ngày bắt đầu phải trước ngày kết thúc")
    if not set(segments).issubset(SEGMENTS) or status not in (*STATUSES, "Tất cả"):
        raise ValueError("Bộ lọc không hợp lệ")
    months = pd.date_range(pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1), freq="MS")
    if len(months) > 120:
        raise ValueError("Chọn tối đa 120 tháng mỗi lần")
    params = {"risk_only": int(risk_only), "search": search.strip()}
    calendar = []
    for i, month in enumerate(months):
        calendar.append(f"SELECT :month_{i} AS usage_month, :next_{i} AS next_month")
        params[f"month_{i}"] = month.date().isoformat()
        params[f"next_{i}"] = (month + pd.offsets.MonthBegin()).date().isoformat()
    conditions = ["1=1"]
    if segments:
        conditions.append("c.company_size IN (" + ", ".join(f":segment_{i}" for i in range(len(segments))) + ")")
        params.update({f"segment_{i}": value for i, value in enumerate(segments)})
    else:
        conditions.append("1=0")
    if status != "Tất cả":
        conditions.append("COALESCE(s.status, 'Active') = :status")
        params["status"] = status
    if latest_only:
        conditions.append("m.usage_month = :latest_month")
        params["latest_month"] = months[-1].date().isoformat()
    sql = """WITH months AS (
    {calendar}
), ranked_status AS (
    SELECT c.customer_id, m.usage_month, s.status, s.churn_reason,
           ROW_NUMBER() OVER (
               PARTITION BY c.customer_id, m.usage_month
               ORDER BY s.updated_at DESC, s.subscription_id DESC
           ) AS rn
    FROM Customers c
    JOIN months m ON c.signup_date < m.next_month
    LEFT JOIN Subscriptions s ON s.customer_id = c.customer_id
        AND s.updated_at < m.next_month
), monthly AS (
    SELECT c.customer_id, c.customer_name, c.company_size, m.usage_month,
           p.plan_name, p.monthly_price, p.ai_token_limit,
           COALESCE(s.status, 'Active') AS status, s.churn_reason,
           COALESCE(SUM(u.tokens_consumed), 0) AS tokens_consumed,
           COALESCE(SUM(u.ai_api_cost), 0) AS ai_api_cost,
           COALESCE(SUM(u.support_tickets_opened), 0) AS support_tickets_opened
    FROM Customers c
    JOIN Plans p ON p.plan_id = c.plan_id
    JOIN months m ON c.signup_date < m.next_month
    JOIN ranked_status s ON s.customer_id = c.customer_id
        AND s.usage_month = m.usage_month AND s.rn = 1
    LEFT JOIN UsageLogs u ON u.customer_id = c.customer_id
        AND u.usage_month >= m.usage_month AND u.usage_month < m.next_month
    WHERE {conditions}
    GROUP BY c.customer_id, c.customer_name, c.company_size, m.usage_month,
             p.plan_name, p.monthly_price, p.ai_token_limit, s.status, s.churn_reason
    HAVING (:risk_only = 0 OR (
        COALESCE(s.status, 'Active') <> 'Churned' AND (
            COALESCE(SUM(u.tokens_consumed), 0) > p.ai_token_limit
            OR COALESCE(SUM(u.support_tickets_opened), 0) > 3)))
)
SELECT *, CASE WHEN tokens_consumed > ai_token_limit OR support_tickets_opened > 3
               THEN 1 ELSE 0 END AS high_risk
FROM monthly
WHERE (:search = '' OR INSTR(LOWER(customer_name), LOWER(:search)) > 0
       OR CAST(customer_id AS CHAR) = :search)
ORDER BY usage_month, customer_id""".format(calendar="\n    UNION ALL\n    ".join(calendar), conditions="\n      AND ".join(conditions))
    return sql, params


@st.cache_data(ttl=300, max_entries=64)
def fetch_data(source, settings, sql, params):
    with get_engine(source, settings).connect() as conn:
        frame = pd.read_sql_query(text(sql), conn, params=params)
    frame["usage_month"] = pd.to_datetime(frame["usage_month"])
    for col in ("monthly_price", "ai_api_cost", "tokens_consumed", "ai_token_limit", "support_tickets_opened", "high_risk"):
        frame[col] = pd.to_numeric(frame[col])
    return frame


def rendered_sql(sql, params, engine):
    return str(text(sql).bindparams(**params).compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}))
