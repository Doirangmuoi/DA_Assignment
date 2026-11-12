from io import BytesIO
from datetime import date
import os
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine, text
from streamlit.testing.v1 import AppTest

from analytics import business_insights, export_report, forecast_next, monthly_metrics
from data import SEGMENTS, build_query, fetch_data, get_engine, mysql_settings, rendered_sql
from demo import demo_tables


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    tables = {
        "Plans": pd.DataFrame([(1, "Starter", 100, 1000)], columns=["plan_id", "plan_name", "monthly_price", "ai_token_limit"]),
        "Customers": pd.DataFrame([
            (1, "Alpha", "Startup", "2026-01-01", 1),
            (2, "Beta", "SMB", "2026-01-15", 1),
            (3, "Future", "Startup", "2026-03-01", 1),
        ], columns=["customer_id", "customer_name", "company_size", "signup_date", "plan_id"]),
        "Subscriptions": pd.DataFrame([
            (1, 1, "Active", None, "2026-01-01"),
            (2, 1, "Churned", "Budget", "2026-02-20"),
            (3, 1, "Active", None, "2026-02-20"),
            (4, 1, "Churned", "Budget", "2026-03-01"),
        ], columns=["subscription_id", "customer_id", "status", "churn_reason", "updated_at"]),
        "UsageLogs": pd.DataFrame([
            (1, 1, "2026-01-01", 600, 10, 2),
            (2, 1, "2026-01-01", 500, 20, 2),
            (3, 1, "2026-02-01", 1000, 5, 3),
        ], columns=["log_id", "customer_id", "usage_month", "tokens_consumed", "ai_api_cost", "support_tickets_opened"]),
    }
    with engine.begin() as conn:
        for table, frame in tables.items():
            frame.to_sql(table, conn, index=False)
    yield engine
    engine.dispose()


def query(engine, **kwargs):
    args = dict(start="2026-01-01", end="2026-02-28", segments=["Startup", "SMB"])
    args.update(kwargs)
    sql, params = build_query(**args)
    with engine.connect() as conn:
        result = pd.read_sql(text(sql), conn, params=params)
    result["usage_month"] = pd.to_datetime(result.usage_month)
    return result


def test_month_end_status_zero_usage_and_no_fanout(database):
    frame = query(database)
    assert len(frame) == 4
    assert not frame.duplicated(["customer_id", "usage_month"]).any()
    alpha = frame[frame.customer_id == 1]
    assert list(alpha.status) == ["Active", "Active"]
    assert list(alpha.tokens_consumed) == [1100, 1000]
    assert list(alpha.high_risk) == [1, 0]  # Strict thresholds, aggregated logs.
    monthly = monthly_metrics(frame, "2026-01-01", "2026-02-28")
    assert list(monthly.mrr) == [200, 200]  # Beta pays despite zero logs.
    assert list(monthly.ai_cost) == [30, 5]
    assert list(monthly.net_profit) == [170, 195]
    assert list(monthly.avg_tickets) == [2, 1.5]
    march = query(database, end="2026-03-31", latest_only=True)
    assert march[march.customer_id == 1].status.item() == "Churned"
    march_kpi = monthly_metrics(march, "2026-03-01", "2026-03-31").iloc[0]
    assert march_kpi.churn_rate == pytest.approx(100 / 3)


def test_filters_risk_having_and_injection(database):
    assert query(database, segments=[]).empty
    assert len(query(database, segments=["SMB"])) == 2
    assert query(database, status="Churned").empty
    assert query(database, search="' OR 1=1 --").empty
    assert len(query(database, search="ALPHA")) == 2
    assert len(query(database, risk_only=True)) == 1
    assert query(database, risk_only=True, latest_only=True).empty
    with pytest.raises(ValueError):
        query(database, segments=["invalid"])
    with pytest.raises(ValueError):
        query(database, start="2026-03-01")
    with pytest.raises(ValueError):
        query(database, end="2040-01-01")


def test_sql_viewer_reproduces_query(database):
    sql, params = build_query("2026-01-01", "2026-02-28", ["Startup"], search="Alpha")
    literal_sql = rendered_sql(sql, params, database)
    with database.connect() as conn:
        bound = pd.read_sql(text(sql), conn, params=params)
        literal = pd.read_sql(text(literal_sql), conn)
    pd.testing.assert_frame_equal(bound, literal)


def test_empty_metrics_forecast_and_insights(database):
    empty = query(database, segments=[])
    metrics = monthly_metrics(empty, "2026-01-01", "2026-03-31")
    assert metrics.mrr.sum() == 0
    assert not metrics.isna().any().any()
    assert forecast_next(metrics) is None
    assert business_insights(empty) == []
    linear = pd.DataFrame({"mrr": [100, 200, 300], "churn_rate": [80, 90, 100], "customers": [2, 3, 4]})
    assert forecast_next(linear) == {"mrr": 400, "churn_rate": 100}
    linear["mrr"] = [300, 100, 0]
    assert forecast_next(linear)["mrr"] == 0


def test_exports_preserve_rows_unicode_and_block_formulas():
    frame = pd.DataFrame({"customer_name": ["Khách Việt", "=1+1", "  @SUM(1)", "-cmd"], "ai_api_cost": [1, 2, 3, 4]})
    csv = pd.read_csv(BytesIO(export_report(frame, "csv")))
    assert csv.customer_name.tolist() == ["Khách Việt", "'=1+1", "'  @SUM(1)", "'-cmd"]
    book = load_workbook(BytesIO(export_report(frame, "xlsx")))
    assert book.active.max_row == 5
    assert book.active["A3"].data_type == "s"
    assert book.active["A3"].value == "'=1+1"
    assert frame.customer_name.iloc[1] == "=1+1"


def test_demo_is_reproducible_and_complete():
    first, second = demo_tables(), demo_tables()
    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])
    assert len(first["Customers"]) == 180
    assert first["UsageLogs"].usage_month.nunique() == 12


def test_streamlit_user_filters_and_empty_states(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 4
    assert len(app.metric) == 6
    assert len(app.get("download_button")) == 2
    app.date_input[0].set_value((date(2026, 8, 15), date(2026, 9, 15))).run()
    assert not app.exception
    assert app.dataframe[0].value.usage_month.dt.month.eq(9).all()
    app.date_input[0].set_value((date(2025, 11, 1), date(2026, 10, 1))).run()
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert app.metric[0].value == "$0"
    app.multiselect[0].set_value(["Startup"]).run()
    app.selectbox[1].set_value("Churned").run()
    assert not app.exception
    assert app.metric[0].value == "$0"
    assert len(app.dataframe[0].value) == 0
    app.toggle[0].set_value(False).run()
    assert not app.exception
    assert len(app.dataframe[0].value) > 0
    app.text_input[0].set_value("no-such-customer").run()
    assert not app.exception
    assert app.dataframe[0].value.empty


def test_streamlit_connection_error_is_actionable():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)
    app.secrets["mysql"] = {"host": "127.0.0.1", "port": 9, "database": "missing", "username": "invalid", "password": "invalid"}
    app.run()
    app.selectbox[0].set_value("MySQL").run()
    assert not app.exception
    assert "Không kết nối được MySQL" in app.error[0].value


@pytest.mark.skipif(os.getenv("RUN_MYSQL_TESTS") != "1", reason="Opt in against the seeded local MySQL database")
def test_mysql_matches_demo_for_all_filters():
    settings = mysql_settings()
    for options in ({}, {"segments": ["Startup"]}, {"status": "Churned"},
                    {"latest_only": True, "risk_only": True}, {"search": "' OR 1=1 --"}):
        args = dict(start="2025-11-01", end="2026-10-31", segments=SEGMENTS)
        args.update(options)
        sql, params = build_query(**args)
        mysql = fetch_data("MySQL", settings, sql, params)
        demo = fetch_data("Demo", {}, sql, params)
        pd.testing.assert_frame_equal(mysql, demo, check_dtype=False)
        with get_engine("MySQL", settings).connect() as conn:
            literal = pd.read_sql(text(rendered_sql(sql, params, get_engine("MySQL", settings))), conn)
        literal["usage_month"] = pd.to_datetime(literal.usage_month)
        pd.testing.assert_frame_equal(mysql, literal, check_dtype=False)
