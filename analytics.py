"""Monthly snapshot metrics, transparent forecasts, and safe report exports."""

from io import BytesIO

import pandas as pd


def monthly_metrics(frame, start, end):
    work = frame.assign(
        revenue=frame["monthly_price"].where(frame["status"].isin(["Active", "Upgraded"]), 0),
        churned=frame["status"].eq("Churned").astype(int),
    )
    monthly = work.groupby("usage_month").agg(
        mrr=("revenue", "sum"), ai_cost=("ai_api_cost", "sum"),
        customers=("customer_id", "nunique"), churned=("churned", "sum"),
        tickets=("support_tickets_opened", "sum"),
    )
    index = pd.date_range(pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1), freq="MS")
    monthly = monthly.reindex(index, fill_value=0).rename_axis("usage_month")
    monthly = monthly.astype(float)
    denominator = monthly["customers"].where(monthly["customers"] > 0)
    monthly["churn_rate"] = (monthly["churned"] / denominator * 100).fillna(0)
    monthly["avg_tickets"] = (monthly["tickets"] / denominator).fillna(0)
    monthly["net_profit"] = monthly["mrr"] - monthly["ai_cost"]
    return monthly.reset_index()


def forecast_next(monthly):
    # shortcut: linear extrapolation of six monthly snapshots, upgrade after out-of-sample validation on real data.
    recent = monthly.tail(6)
    if len(recent) < 3 or (recent["customers"] == 0).any():
        return None
    n = len(recent)
    x = list(range(n))
    center = (n - 1) / 2
    denominator = sum((i - center) ** 2 for i in x)
    result = {}
    for key in ("mrr", "churn_rate"):
        mean = float(recent[key].mean())
        slope = sum((i - center) * (float(y) - mean) for i, y in zip(x, recent[key])) / denominator
        result[key] = max(0, mean + slope * (n - center))
    result["churn_rate"] = min(100, result["churn_rate"])
    return result


def business_insights(latest):
    if latest.empty:
        return []
    results = []
    risk = latest[(latest.high_risk == 1) & (latest.status != "Churned")]
    results.append(("Ưu tiên giữ chân", f"{len(risk):,} khách đang sử dụng có dấu hiệu rủi ro, chiếm {len(risk) / len(latest):.1%} tập khách đang lọc.",
                    "Customer Success liên hệ nhóm này, ưu tiên khách vừa vượt token vừa có hơn 3 vé hỗ trợ."))
    costs = latest.groupby("plan_name").ai_api_cost.sum().sort_values(ascending=False)
    total = float(costs.sum())
    leader = costs.index[0]
    results.append(("Kiểm soát chi phí AI", f"Gói {leader} chiếm {float(costs.iloc[0]) / total:.1%} chi phí AI (${float(costs.iloc[0]):,.2f})." if total else "Chưa phát sinh chi phí AI trong tháng này.",
                    "Product rà soát định tuyến model và cảnh báo hạn mức cho gói có chi phí cao nhất."))
    churned = latest[latest.status == "Churned"]
    if not churned.empty:
        reasons = churned.churn_reason.fillna("Chưa ghi nhận").replace("", "Chưa ghi nhận").value_counts()
        results.append(("Xử lý nguyên nhân rời bỏ", f"“{reasons.index[0]}” đứng đầu với {int(reasons.iloc[0])}/{len(churned)} khách đã rời bỏ trong ảnh chụp tháng.",
                        "Customer Success phỏng vấn nhóm này; Product kiểm tra nguyên nhân trước khi chọn thử nghiệm giữ chân."))
    else:
        results.append(("Theo dõi trải nghiệm hỗ trợ", f"{int((latest.support_tickets_opened > 3).sum())} khách mở hơn 3 vé hỗ trợ trong tháng.",
                        "Customer Success phân loại vấn đề lặp lại và thống nhất thời hạn phản hồi."))
    return results


def export_report(frame, kind):
    safe = frame.copy()
    for col in safe.select_dtypes(include=["object", "string"]).columns:
        safe[col] = safe[col].map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value)
    if kind == "csv":
        return safe.to_csv(index=False).encode("utf-8-sig")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        safe.to_excel(writer, index=False, sheet_name="Customers")
        sheet = writer.sheets["Customers"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    return output.getvalue()
