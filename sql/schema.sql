CREATE DATABASE IF NOT EXISTS SaaS_AI_DB;
USE SaaS_AI_DB;

-- 1. Bảng Gói dịch vụ
CREATE TABLE Plans (
    plan_id INT AUTO_INCREMENT PRIMARY KEY,
    plan_name VARCHAR(50) NOT NULL,
    monthly_price DECIMAL(10, 2) NOT NULL,
    ai_token_limit INT NOT NULL
);

-- 2. Bảng Khách hàng
CREATE TABLE Customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    company_size VARCHAR(20) CHECK (company_size IN ('Startup', 'SMB', 'Enterprise')),
    signup_date DATE NOT NULL,
    plan_id INT,
    FOREIGN KEY (plan_id) REFERENCES Plans(plan_id)
);

-- 3. Bảng Lịch sử Sử dụng & Chi phí AI Hàng tháng
CREATE TABLE UsageLogs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT,
    usage_month DATE NOT NULL,
    tokens_consumed INT NOT NULL,
    ai_api_cost DECIMAL(10, 2) NOT NULL,
    support_tickets_opened INT DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id)
);

-- 4. Bảng Trạng thái Đăng ký (Subscription Status)
CREATE TABLE Subscriptions (
    subscription_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT,
    status VARCHAR(20) CHECK (status IN ('Active', 'Churned', 'Upgraded')),
    churn_reason VARCHAR(150),
    updated_at DATE NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id)
);

