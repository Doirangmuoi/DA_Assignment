"""Deterministic synthetic data shared by the demo and the MySQL seeder."""

import random
from datetime import timedelta

import pandas as pd


def demo_tables():
    rng = random.Random(2512)
    plans = pd.DataFrame([
        (1, "Starter", 39, 500_000),
        (2, "Growth", 129, 2_500_000),
        (3, "Scale", 399, 10_000_000),
    ], columns=["plan_id", "plan_name", "monthly_price", "ai_token_limit"])
    customers, logs, subscriptions = [], [], []
    prefixes = ["Lotus", "Mekong", "Orbit", "Nova", "Atlas", "Bamboo", "Pixel", "Cloud"]
    suffixes = ["Labs", "Studio", "Commerce", "Digital", "Works", "Systems"]
    months = [month.date() for month in pd.date_range("2025-11-01", "2026-10-01", freq="MS")]
    for cid in range(1, 181):
        segment = rng.choices(["Startup", "SMB", "Enterprise"], [0.46, 0.36, 0.18])[0]
        pid = {"Startup": 1, "SMB": 2, "Enterprise": 3}[segment]
        plan = plans.iloc[pid - 1]
        signup_index = 0 if cid <= 95 else rng.randrange(1, 10)
        signup = months[signup_index] - timedelta(days=rng.randrange(0, 20))
        customers.append((cid, f"{rng.choice(prefixes)} {rng.choice(suffixes)} {cid:03}", segment, signup.isoformat(), pid))
        subscriptions.append((len(subscriptions) + 1, cid, "Active", None, signup.isoformat()))
        pressure = rng.random()
        churn_index = None
        if rng.random() < (0.34 if segment == "Startup" else 0.15):
            churn_index = rng.randrange(min(signup_index + 2, 11), 12)
        upgraded = False
        for idx, month in enumerate(months):
            if idx < signup_index or (churn_index is not None and idx > churn_index):
                continue
            factor = rng.uniform(0.12, 0.85) + (0.72 if pressure > 0.68 else 0) + idx * 0.012
            tokens = int(int(plan.ai_token_limit) * factor)
            tickets = rng.randrange(0, 3) + (rng.randrange(2, 5) if factor > 1 else 0)
            cost = round(tokens / 1_000_000 * rng.uniform(9, 19), 2)
            logs.append((len(logs) + 1, cid, month.isoformat(), tokens, cost, tickets))
            if idx == churn_index:
                reason = "Chi phí vượt ngân sách" if pressure > 0.68 else rng.choice(["Thiếu tính năng", "Trải nghiệm hỗ trợ", "Không còn nhu cầu"])
                subscriptions.append((len(subscriptions) + 1, cid, "Churned", reason, (month + timedelta(days=19)).isoformat()))
            elif not upgraded and idx >= signup_index + 4 and pressure < 0.16:
                subscriptions.append((len(subscriptions) + 1, cid, "Upgraded", None, (month + timedelta(days=9)).isoformat()))
                upgraded = True
    return {
        "Plans": plans,
        "Customers": pd.DataFrame(customers, columns=["customer_id", "customer_name", "company_size", "signup_date", "plan_id"]),
        "UsageLogs": pd.DataFrame(logs, columns=["log_id", "customer_id", "usage_month", "tokens_consumed", "ai_api_cost", "support_tickets_opened"]),
        "Subscriptions": pd.DataFrame(subscriptions, columns=["subscription_id", "customer_id", "status", "churn_reason", "updated_at"]),
    }
