# SaaS Pulse - Dashboard Churn & AI Cost

Ứng dụng Streamlit + MySQL cho đề tài **Unified SaaS & AI Cost Analytics Dashboard**. Giao diện tiếng Việt, tiền tệ USD. Có bộ lọc thời gian/phân khúc/trạng thái, 4 KPI, 4 biểu đồ Plotly tương tác, 3 insight kèm hành động, cảnh báo rủi ro, dự báo xu hướng, tra cứu khách hàng, tải CSV/Excel và SQL viewer.

`sql/schema.sql` giữ nguyên câu lệnh SQL được cung cấp trong đề bài, không bổ sung cột, chỉ mục hoặc ràng buộc.

## Chạy ngay với dữ liệu mô phỏng

Yêu cầu Python 3.11 trở lên. Tại thư mục dự án, PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mở http://localhost:8501. Mặc định chọn **Demo**: 180 khách hàng, 3 gói, 12 tháng từ 11/2025 đến 10/2026, dữ liệu sinh cố định để dễ kiểm tra. SQLite chỉ dùng trong bộ nhớ cho demo; không cần MySQL để xem giao diện. Các insight của demo không phải kết luận về doanh nghiệp thực tế.

## Chạy với MySQL

Yêu cầu MySQL 8.0.16 trở lên.

1. Mở [sql/schema.sql](sql/schema.sql) bằng MySQL Workbench hoặc MySQL client và chạy trên MySQL cục bộ để tạo database theo đề bài.
2. Sao chép `.streamlit/secrets.toml.example` thành `.streamlit/secrets.toml`, điền host, port, tài khoản và mật khẩu MySQL đang dùng. Cổng mặc định là `3306`.
3. Nếu cần dữ liệu mẫu, chạy `.\.venv\Scripts\python.exe seed.py` trên **database trống**. Seeder từ chối nếu bất kỳ bảng nào đã có dữ liệu, không xóa/ghi đè dữ liệu.
4. Chạy `.\.venv\Scripts\python.exe -m streamlit run app.py` và chọn **MySQL** trên sidebar.

Tài khoản cần quyền INSERT khi seed; tài khoản chạy dashboard chỉ cần SELECT. File mật khẩu `.streamlit/secrets.toml` được loại khỏi Git.

Khi kết nối thất bại, ứng dụng báo lỗi để sửa cấu hình, không âm thầm chuyển sang demo. Bộ nhớ đệm truy vấn có TTL 5 phút; nút **Làm mới dữ liệu** xóa cache truy vấn. Chỉ nên triển khai cho người có quyền xem toàn bộ dữ liệu; bản đồ án chưa có đăng nhập/phân quyền.

## Cách đọc và kiểm tra số liệu

- Mọi khoảng ngày được mở rộng thành **tháng đầy đủ**. 4 KPI là ảnh chụp **tháng cuối**; delta so với tháng liền trước trong khoảng chọn. MRR không cộng dồn các tháng.
- MRR = tổng giá gói của khách `Active` hoặc `Upgraded`. Khách không có usage log vẫn được tính doanh thu và nằm trong mẫu số. Chi phí/vé/token của họ bằng 0.
- Churn theo đúng công thức đề bài: số khách `Churned` ở cuối tháng / tổng khách ở cuối tháng. Đây là **tỷ lệ trạng thái tích lũy**, không phải số khách rời bỏ mới / khách đầu tháng. Bộ lọc Churned sẽ cho 100% churn khi có khách phù hợp.
- Lợi nhuận sau AI = MRR - toàn bộ chi phí API AI trong tháng, gồm chi phí phát sinh của khách đã churn. Là số tiền USD, chưa trừ chi phí vận hành khác.
- Vé hỗ trợ trung bình = tổng vé tháng / tổng khách tháng.
- Lấy sự kiện Subscriptions mới nhất trước tháng tiếp theo; nếu cùng ngày, ưu tiên subscription_id lớn hơn. Mỗi khách mặc định Active từ ngày đăng ký nếu chưa có sự kiện. Ghi lịch sử trạng thái bằng cách **thêm dòng**, không ghi đè sự kiện cũ. Sự kiện trước ngày signup không hợp lệ về nghiệp vụ.
- UsageLogs ghi ngày đầu tháng. Nhiều dòng cùng khách/tháng được xem là các phần sử dụng cần cộng lại. Không nhập lại cùng batch để tránh đếm đôi.
- Bảng chi tiết hiển thị **tháng cuối**, mặc định chỉ khách đang sử dụng có tổng token > hạn mức **hoặc** tổng vé > 3. Bỏ toggle để xem cả khách đã churn. CSV/Excel giữ nguyên bộ lọc và từ khóa của bảng, không giữ thao tác sort tạm trên trình duyệt. Chuỗi có thể được phần mềm bảng tính hiểu là công thức được thêm dấu nháy để mở file an toàn.
- Biểu đồ lý do dùng khách đã churn tại cuối tháng, đếm mỗi khách một lần. Scatter dùng tất cả khách-tháng trong khoảng chọn. Các insight mô tả số liệu, không suy diễn quan hệ nhân quả.
- Dự báo dùng hồi quy tuyến tính đơn giản trên tối đa 6 tháng cuối, yêu cầu ít nhất 3 tháng liên tục có khách, chặn MRR dưới 0 và churn ngoài 0-100%. Đây là kịch bản tham khảo, **chưa được kiểm định ngoài mẫu**, không phải xác suất churn cá nhân. Tránh dùng tháng chưa đóng để dự báo.
- Schema đề bài chỉ giữ **gói và giá hiện tại**. Không thể phục dựng doanh thu trước khi đổi gói/giá từ 4 bảng này. `Upgraded` chỉ là trạng thái; muốn thay giá phải cập nhật plan_id, và muốn lịch sử chính xác cần thêm lịch sử gói hoặc hóa đơn. Bản demo giữ gói/giá cố định.

## Cấu trúc

| Tệp | Vai trò |
| --- | --- |
| `app.py` | Giao diện, biểu đồ, bộ lọc và SQL viewer |
| `data.py` | Engine/cache, truy vấn bind JOIN/GROUP BY/HAVING/WHERE 1=1, ảnh chụp theo tháng |
| `analytics.py` | KPI, dự báo, insight và xuất file |
| `demo.py` / `seed.py` | Dữ liệu mô phỏng cố định / nhập MySQL trống bằng transaction |
| `sql/schema.sql` | Nguyên bản SQL đề bài: 4 bảng, khóa chính, khóa ngoại và CHECK |
| `tests/test_dashboard.py` | Kiểm thử dữ liệu, KPI, xuất file và luồng Streamlit |

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Đối chiếu SQL viewer và kết quả MySQL với demo sau khi seed vào database riêng cho đồ án:

```powershell
$env:RUN_MYSQL_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

Test gồm: JOIN không nhân đôi, tổng nhiều usage logs, khách không usage, sự kiện cùng ngày và tương lai, ranh giới token/ticket, bộ lọc trống, tìm kiếm có dấu nháy, SQL viewer khớp truy vấn, KPI rỗng, dự báo, Unicode và công thức khi xuất CSV/Excel; AppTest chạy luồng lọc/tìm kiếm/rủi ro. Khi kiểm tra trình duyệt, mở ứng dụng ở desktop và mobile, thử cả hai nguồn dữ liệu, tìm kiếm, tải hai định dạng báo cáo và mở SQL viewer.

API cache và kiểm thử dựa trên [tài liệu Streamlit](https://docs.streamlit.io/develop/concepts/architecture/caching). Giao diện dùng màu xanh cho doanh thu, đỏ cho churn, cam cho cảnh báo, đồng thời luôn có nhãn chữ.
