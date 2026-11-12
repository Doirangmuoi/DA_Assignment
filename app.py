import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from analytics import business_insights, export_report, forecast_next, monthly_metrics
from data import SEGMENTS, build_query, date_bounds, fetch_data, get_engine, mysql_settings, rendered_sql

st.set_page_config(page_title="SaaS Pulse | Churn & AI", page_icon="◈", layout="wide")
st.html("""<style>
    .block-container {max-width: 1560px; padding-top: 5rem; padding-bottom: 3rem;}
    h1 {font-size: 2.35rem !important; letter-spacing: -0.065rem; font-weight: 750 !important;}
    h2 {font-size: 1.45rem !important; letter-spacing: -0.025rem;}
    h3 {font-size: 1.12rem !important;}
    [data-testid="stSidebar"] {border-right: 1px solid #dce5ef;}
    [data-testid="stMetric"] {background: white; border-top: 3px solid #16766e;
        padding: 1.1rem 1.2rem; border-radius: 5px; min-height: 145px;}
    [data-testid="stMetricValue"] {font-variant-numeric: tabular-nums; font-size: 1.9rem;}
    [data-testid="stMetricLabel"] {color: #465873;}
    [data-testid="stCaptionContainer"] p {color: #52647C;}
    [data-testid="stTabs"] {margin-top: 0.8rem;}
    .brand {font-size: 1.4rem; font-weight: 750; color: #172b4d; margin-bottom: 0.2rem;}
    .brand span {color: #16766e;}
    .sidebar-note {font-size: 0.85rem; color: #465873; line-height: 1.6;}
    @media (max-width: 700px) {h1 {font-size: 1.85rem !important;}}
</style>""")

COLORS = {"Starter": "#16766E", "Growth": "#3774C4", "Scale": "#8562B8",
          "Ổn định": "#3774C4", "Có tín hiệu rủi ro": "#DE8B2D", "Đã rời bỏ": "#CF4B4B"}


def chart_style(fig, height=330):
    fig.update_layout(height=height, margin=dict(l=12, r=20, t=20, b=20),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Arial, sans-serif", color="#465873", size=12),
                      legend=dict(orientation="h", y=1.12, x=0, title_text=""),
                      hoverlabel=dict(bgcolor="white", font_size=13))
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#E3EAF2", zeroline=False)
    return fig


def draw(fig, key):
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False}, key=key)


def main():
    settings = mysql_settings()
    with st.sidebar:
        st.html('<div class="brand">◈ SaaS <span>Pulse</span></div>')
        st.caption("Churn & AI cost analytics")
        st.divider()
        source = st.selectbox("Nguồn dữ liệu", ["Demo", "MySQL"])
        if source == "Demo":
            st.info("Dữ liệu mô phỏng · 180 khách hàng")
        else:
            st.caption("Dữ liệu MySQL · làm mới mỗi 5 phút")
        if st.button("Làm mới dữ liệu", width="stretch"):
            fetch_data.clear()
            date_bounds.clear()
        try:
            lower, upper = date_bounds(source, settings)
        except (SQLAlchemyError, ValueError, KeyError, OSError):
            st.error("Không kết nối được MySQL. Kiểm tra dịch vụ, schema và .streamlit/secrets.toml, rồi bấm Làm mới dữ liệu.")
            st.stop()
        if lower is None:
            st.warning("Chưa có lịch sử sử dụng. Nhập dữ liệu UsageLogs hoặc chọn Demo.")
            st.stop()
        st.subheader("Bộ lọc phân tích")
        bounds = st.date_input("Khoảng thời gian", value=(lower, upper), min_value=lower,
                               max_value=(pd.Timestamp(upper) + pd.offsets.MonthEnd()).date(),
                               format="DD/MM/YYYY", key=f"date_{source}")
        st.caption("Lấy trọn các tháng chứa ngày đã chọn.")
        segments = st.multiselect("Quy mô doanh nghiệp", SEGMENTS, default=list(SEGMENTS))
        status = st.selectbox("Trạng thái dịch vụ", ["Tất cả", "Active", "Churned", "Upgraded"])
        st.divider()
        st.html('<p class="sidebar-note">Đọc tín hiệu rời bỏ cùng chi phí AI để ưu tiên giữ chân khách hàng và bảo vệ doanh thu thuê bao.</p>')
    if len(bounds) != 2:
        st.info("Chọn thêm ngày kết thúc để xem phân tích.")
        st.stop()
    start, end = bounds
    try:
        sql, params = build_query(start, end, segments, status)
        frame = fetch_data(source, settings, sql, params)
    except (SQLAlchemyError, ValueError):
        st.error("Không tải được báo cáo. Kiểm tra bảng, quyền SELECT và phiên bản MySQL 8.0.16 trở lên.")
        st.stop()

    headline, badge = st.columns([4, 1])
    with headline:
        st.title("Sức khỏe thuê bao & chi phí AI")
        st.caption("Theo dõi doanh thu. Nhận diện rủi ro. Chọn hành động tiếp theo.")
    with badge:
        st.write("")
        st.badge("Dữ liệu mô phỏng" if source == "Demo" else "MySQL", icon=":material/database:")
        st.caption(f"{start:%m/%Y} đến {end:%m/%Y} · USD")
    if frame.empty:
        st.info("Không có khách hàng phù hợp. Chọn thêm phân khúc hoặc đổi trạng thái, thời gian.")
    monthly = monthly_metrics(frame, start, end)
    last = monthly.iloc[-1]
    previous = monthly.iloc[-2] if len(monthly) > 1 else None
    latest = frame[frame.usage_month == last.usage_month]
    month_label = last.usage_month.strftime("%m/%Y")
    st.caption(f"Ảnh chụp tháng {month_label} · {len(latest):,} khách hàng trong bộ lọc")
    cols = st.columns(4)
    metric_definitions = [
        ("MRR", "mrr", f"${last.mrr:,.0f}", "normal", "Tổng giá gói của khách Active và Upgraded trong tháng cuối được chọn."),
        ("Tỷ lệ churn", "churn_rate", f"{last.churn_rate:.1f}%", "inverse", "Số khách có trạng thái Churned cuối tháng / tổng khách trong bộ lọc. Đây là tỷ lệ trạng thái, không phải tỷ lệ rời bỏ mới."),
        ("Lợi nhuận sau chi phí AI", "net_profit", f"${last.net_profit:,.0f}", "normal", "MRR trừ toàn bộ chi phí API AI tháng đó. Đây là số tiền, chưa trừ chi phí vận hành khác."),
        ("Vé hỗ trợ / khách", "avg_tickets", f"{last.avg_tickets:.2f}", "inverse", "Tổng vé trong tháng / tổng khách, gồm khách không có log sử dụng."),
    ]
    for col, (label, key, value, color, help_text) in zip(cols, metric_definitions):
        delta = None
        if previous is not None:
            difference = last[key] - previous[key]
            if key == "churn_rate":
                delta = f"{difference:+.1f} điểm %"
            elif key == "avg_tickets":
                delta = f"{difference:+.2f} vé"
            else:
                delta = f"{difference:+,.0f} USD"
        col.metric(label, value, delta=delta, delta_color=color, help=help_text)
    st.caption("Mức thay đổi so với tháng liền trước trong khoảng chọn. Các bộ lọc áp dụng cho cả tử số và mẫu số.")

    overview, customers_tab, method = st.tabs(["Tổng quan", "Khách hàng & báo cáo", "Phương pháp & SQL"])
    with overview:
        left, right = st.columns([3, 1], gap="large")
        with left:
            st.subheader("Doanh thu tăng có đi cùng giữ chân khách hàng?")
            fig = px.line(monthly, x="usage_month", y="mrr", markers=True,
                          labels={"usage_month": "Tháng", "mrr": "MRR (USD)"})
            fig.update_traces(name="MRR", showlegend=True, line_color="#16766E", line_width=3,
                              hovertemplate="%{x|%m/%Y}<br>MRR: $%{y:,.2f}<extra></extra>")
            churn_fig = px.line(monthly, x="usage_month", y="churn_rate", markers=True)
            for trace in churn_fig.data:
                trace.update(name="Tỷ lệ churn", yaxis="y2", showlegend=True, line=dict(color="#CF4B4B", width=2, dash="dot"),
                             hovertemplate="%{x|%m/%Y}<br>Churn: %{y:.1f}%<extra></extra>")
                fig.add_trace(trace)
            chart_style(fig, 350)
            fig.update_layout(yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, max(5, float(monthly.churn_rate.max()) * 1.15)], tickmode="linear", tick0=0, dtick=5 if monthly.churn_rate.max() <= 40 else 20, tickformat=".0f", ticksuffix="%", showgrid=False), hovermode="x unified")
            fig.update_xaxes(dtick="M2", tickformat="%m/%y")
            draw(fig, "trend")
        with right:
            st.subheader("Tháng tiếp theo")
            forecast = forecast_next(monthly)
            if forecast is None:
                st.info("Cần ít nhất 3 tháng liên tiếp có khách hàng để ngoại suy xu hướng.")
            else:
                st.caption((last.usage_month + pd.offsets.MonthBegin()).strftime("Dự báo %m/%Y"))
                st.metric("MRR dự kiến", f"${forecast['mrr']:,.0f}")
                st.metric("Churn dự kiến", f"{forecast['churn_rate']:.1f}%", delta_color="inverse")
                st.caption("Ngoại suy tuyến tính tối đa 6 tháng cuối. Chỉ là kịch bản tham khảo, chưa có kiểm định độ chính xác.")

        st.divider()
        left, right = st.columns([1.2, 1], gap="large")
        with left:
            st.subheader("Khách dùng nhiều AI đang tạo bao nhiêu chi phí?")
            st.caption("Mỗi điểm là một khách hàng trong một tháng thuộc khoảng chọn.")
            if frame.empty:
                st.info("Chưa có dữ liệu để phân tích chi phí.")
            else:
                scatter = px.scatter(frame, x="tokens_consumed", y="ai_api_cost", color="plan_name", color_discrete_map=COLORS,
                                     hover_name="customer_name", hover_data={"usage_month": "|%m/%Y", "company_size": True, "status": True},
                                     labels={"tokens_consumed": "AI tokens tiêu thụ", "ai_api_cost": "Chi phí API AI (USD)", "plan_name": "Gói"}, opacity=0.7)
                scatter.update_traces(marker_size=7)
                draw(chart_style(scatter), "costs")
        with right:
            st.subheader("Lý do nào cần được xử lý trước?")
            st.caption(f"Khách có trạng thái Churned tại cuối tháng {month_label}.")
            churned = latest[latest.status == "Churned"]
            if churned.empty:
                st.info("Không có khách đã rời bỏ trong ảnh chụp tháng này.")
            else:
                reasons = churned.churn_reason.fillna("Chưa ghi nhận").replace("", "Chưa ghi nhận").value_counts().rename_axis("Lý do").reset_index(name="Khách hàng")
                reasons = reasons.sort_values("Khách hàng")
                bars = px.bar(reasons, x="Khách hàng", y="Lý do", orientation="h", text="Khách hàng", color_discrete_sequence=["#CF4B4B"])
                bars.update_traces(textposition="outside", cliponaxis=False)
                bars.update_xaxes(dtick=1)
                draw(chart_style(bars), "reasons")
        st.divider()
        left, right = st.columns([1.1, 1], gap="large")
        with left:
            st.subheader("Tập trung giữ chân ở phân khúc nào?")
            st.caption(f"Phân bố khách hàng tháng {month_label}; tín hiệu rủi ro không phải xác suất churn.")
            if latest.empty:
                st.info("Chưa có khách trong tháng cuối của bộ lọc.")
            else:
                distribution = latest.assign(risk_band=latest.apply(
                    lambda row: "Đã rời bỏ" if row.status == "Churned" else "Có tín hiệu rủi ro" if row.high_risk else "Ổn định", axis=1))
                counts = distribution.groupby(["company_size", "risk_band"]).size().reset_index(name="customers")
                risk = px.bar(counts, x="company_size", y="customers", color="risk_band", barmode="group", color_discrete_map=COLORS,
                              category_orders={"company_size": list(SEGMENTS), "risk_band": ["Ổn định", "Có tín hiệu rủi ro", "Đã rời bỏ"]},
                              labels={"company_size": "Quy mô doanh nghiệp", "customers": "Khách hàng", "risk_band": "Trạng thái"})
                draw(chart_style(risk, 360), "risk")
        with right:
            st.subheader("Từ số liệu đến hành động")
            st.caption("Insight tính lại theo bộ lọc và ảnh chụp tháng cuối.")
            for title, finding, action in business_insights(latest):
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    st.write(finding)
                    st.caption(action)

    with customers_tab:
        st.subheader(f"Danh sách cần theo dõi · {month_label}")
        st.caption("Tra cứu ảnh chụp tháng cuối. Tìm kiếm và chế độ rủi ro bên dưới chỉ tác động bảng và tệp xuất.")
        search_col, risk_col = st.columns([2, 1])
        search = search_col.text_input("Tìm theo tên hoặc mã khách hàng", placeholder="Ví dụ: Lotus hoặc 012")
        risk_only = risk_col.toggle("Chỉ khách đang sử dụng có rủi ro", value=True,
                                    help="Active/Upgraded và vượt giới hạn token HOẶC mở hơn 3 vé hỗ trợ trong tháng.")
        try:
            table_sql, table_params = build_query(start, end, segments, status, search, risk_only, latest_only=True)
            detail = fetch_data(source, settings, table_sql, table_params)
        except (SQLAlchemyError, ValueError):
            st.error("Không tải được danh sách. Thử làm mới dữ liệu.")
            st.stop()
        st.caption(f"{len(detail):,} khách hàng · bấm tiêu đề cột để sắp xếp · tệp xuất giữ đúng bộ lọc và tìm kiếm")
        if detail.empty:
            st.info("Không có khách phù hợp. Tắt bộ lọc rủi ro hoặc đổi từ khóa để xem thêm.")
        st.dataframe(detail, hide_index=True, width="stretch", height=420, column_config={
            "customer_id": st.column_config.NumberColumn("Mã khách", format="%d"),
            "customer_name": "Khách hàng", "company_size": "Quy mô", "usage_month": st.column_config.DateColumn("Tháng", format="MM/YYYY"),
            "plan_name": "Gói", "monthly_price": st.column_config.NumberColumn("Giá gói", format="$%.2f"),
            "ai_token_limit": st.column_config.NumberColumn("Hạn mức token", format="localized"),
            "tokens_consumed": st.column_config.NumberColumn("Token đã dùng", format="localized"),
            "ai_api_cost": st.column_config.NumberColumn("Chi phí AI", format="$%.2f"),
            "support_tickets_opened": "Vé hỗ trợ", "status": "Trạng thái", "churn_reason": "Lý do rời bỏ",
            "high_risk": st.column_config.CheckboxColumn("Tín hiệu rủi ro")})
        csv_col, excel_col, _ = st.columns([1, 1, 3])
        csv_col.download_button("Tải CSV", export_report(detail, "csv"), f"saas-customers-{last.usage_month:%Y-%m}.csv", "text/csv", width="stretch")
        excel_col.download_button("Tải Excel", export_report(detail, "xlsx"), f"saas-customers-{last.usage_month:%Y-%m}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        st.caption("Bản xuất chứa dữ liệu theo bộ lọc, không giữ thứ tự sắp xếp tạm thời trên giao diện bảng.")

    with method:
        st.subheader("Định nghĩa rõ để đọc đúng số liệu")
        st.markdown("""
- **MRR**: giá gói của khách Active/Upgraded tại cuối mỗi tháng, mỗi khách tính một lần.
- **Churn**: tỷ trọng khách có trạng thái Churned ở cuối tháng trên tổng khách trong bộ lọc. Khách đã churn tiếp tục nằm trong ảnh chụp các tháng sau.
- **Lợi nhuận sau AI**: MRR trừ chi phí API AI trong tháng, tính bằng USD; chưa trừ chi phí khác.
- **Rủi ro**: khách đang sử dụng có tổng token tháng vượt hạn mức **hoặc** tổng vé hỗ trợ tháng lớn hơn 3. Quy tắc cảnh báo, không phải mô hình dự đoán xác suất.
- **Lịch sử**: lấy sự kiện trạng thái cuối cùng trước đầu tháng kế tiếp. Nếu chưa có sự kiện, mặc định Active từ ngày đăng ký. Khi hai sự kiện cùng ngày, subscription_id lớn hơn được ưu tiên.
- **Giới hạn schema**: giá và gói trong Customers/Plans là giá trị hiện tại. Muốn tính chính xác doanh thu trước khi đổi gói/giá cần bổ sung lịch sử gói hoặc hóa đơn. Upgraded không tự tạo giá gói mới.
- **Khoảng ngày**: chuẩn hóa thành tháng đầy đủ; dữ liệu tháng đang diễn ra có thể chưa hoàn tất. Nên chọn các tháng đã đóng để đọc dự báo.
""")
        st.caption("Truy vấn dùng tham số bind. Bản SQL dưới đây được dựng từ đúng truy vấn và tham số đã chạy; không có thông tin đăng nhập.")
        engine = get_engine(source, settings)
        with st.expander("SQL JOIN cho biểu đồ và KPI"):
            st.code(rendered_sql(sql, params, engine), language="sql")
        with st.expander("SQL JOIN / GROUP BY / HAVING cho bảng và tệp xuất"):
            st.code(rendered_sql(table_sql, table_params, engine), language="sql")
        st.caption("Demo dùng SQLite trong bộ nhớ, cùng truy vấn với MySQL 8. Không tự chuyển sang demo khi MySQL gặp lỗi.")


if __name__ == "__main__":
    main()
