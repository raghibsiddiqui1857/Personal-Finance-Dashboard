"""Data analysis, forecasting and chart rendering (pandas + numpy + matplotlib)."""
import base64
import io

import numpy as np
import pandas as pd
from matplotlib.figure import Figure  # no pyplot -> thread-safe under gunicorn

PALETTE = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4",
           "#a855f7", "#ec4899", "#84cc16", "#f97316", "#14b8a6"]


def load_df(db):
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date", db)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")
    return df


def totals(df):
    if df.empty:
        return dict(income=0, expense=0, savings=0, rate=0)
    inc = df.loc[df.type == "income", "amount"].sum()
    exp = df.loc[df.type == "expense", "amount"].sum()
    return dict(income=inc, expense=exp, savings=inc - exp,
                rate=(inc - exp) / inc * 100 if inc else 0)


def monthly_table(df):
    if df.empty:
        return pd.DataFrame(columns=["income", "expense", "savings"])
    m = (df.pivot_table(index="month", columns="type", values="amount",
                        aggfunc="sum", fill_value=0)
           .reindex(columns=["income", "expense"], fill_value=0))
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0)
    m["savings"] = m["income"] - m["expense"]
    return m


def forecast_savings(m):
    """Linear-trend forecast of next month's savings with a +/- 1 std band."""
    if m.empty:
        return None
    y = m["savings"].to_numpy(dtype=float)
    n = len(y)
    if n >= 3:
        slope, intercept = np.polyfit(np.arange(n), y, 1)
        pred = slope * n + intercept
        std = float(np.std(y - (slope * np.arange(n) + intercept)))
        trend = "improving" if slope > 0 else "declining"
    else:
        pred, std, trend = float(y.mean()), 0.0, "insufficient data"
    return dict(month=str(m.index[-1] + 1), value=float(pred), std=std,
                trend=trend, months_used=n)


def forecast_categories(df, window=3):
    """Expected next-month spend per category (rolling mean of last N months)."""
    exp = df[df.type == "expense"]
    if exp.empty:
        return {}
    p = exp.pivot_table(index="month", columns="category", values="amount",
                        aggfunc="sum", fill_value=0).tail(window)
    return p.mean().sort_values(ascending=False).round(2).to_dict()


def budget_status(df, budgets):
    if df.empty or not budgets:
        return []
    cur = df["month"].max()
    spent = df[(df.type == "expense") & (df.month == cur)].groupby("category")["amount"].sum()
    out = []
    for b in budgets:
        s = float(spent.get(b["category"], 0))
        pct = s / b["monthly_limit"] * 100
        out.append(dict(category=b["category"], limit=b["monthly_limit"], spent=s,
                        pct=min(pct, 100), over=pct > 100,
                        warn=80 <= pct <= 100))
    return out


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", transparent=False)
    return base64.b64encode(buf.getvalue()).decode()


def chart_trend(m, fc):
    fig = Figure(figsize=(8, 3.6))
    ax = fig.subplots()
    if m.empty:
        ax.text(0.5, 0.5, "No data yet", ha="center"); ax.axis("off")
        return _png(fig)
    x = np.arange(len(m)); w = 0.38
    ax.bar(x - w / 2, m["income"], w, label="Income", color="#22c55e")
    ax.bar(x + w / 2, m["expense"], w, label="Expense", color="#ef4444")
    ax.plot(x, m["savings"], marker="o", color="#6366f1", label="Savings", lw=2)
    labels = [str(p) for p in m.index]
    if fc:
        fx = len(m)
        ax.errorbar([fx], [fc["value"]], yerr=[fc["std"]], fmt="D", color="#f59e0b",
                    capsize=4, label="Forecast")
        ax.plot([fx - 1, fx], [m["savings"].iloc[-1], fc["value"]], "--", color="#f59e0b")
        labels.append(fc["month"])
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=8)
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_title("Monthly cash flow & savings forecast")
    ax.legend(fontsize=8, ncol=4, loc="upper left"); ax.grid(axis="y", alpha=0.25)
    return _png(fig)


def chart_categories(df):
    fig = Figure(figsize=(5, 3.6))
    ax = fig.subplots()
    exp = df[df.type == "expense"] if not df.empty else df
    if exp.empty:
        ax.text(0.5, 0.5, "No expenses yet", ha="center"); ax.axis("off")
        return _png(fig)
    s = exp.groupby("category")["amount"].sum().sort_values(ascending=False)
    if len(s) > 7:
        s = pd.concat([s.iloc[:7], pd.Series({"Other": s.iloc[7:].sum()})])
    ax.pie(s, labels=s.index, autopct="%1.0f%%", startangle=90, colors=PALETTE,
           wedgeprops=dict(width=0.45, edgecolor="white"), textprops=dict(fontsize=8))
    ax.set_title("Spending by category")
    return _png(fig)


def chart_daily(df):
    fig = Figure(figsize=(8, 2.6))
    ax = fig.subplots()
    exp = df[df.type == "expense"] if not df.empty else df
    if exp.empty:
        ax.text(0.5, 0.5, "No expenses yet", ha="center"); ax.axis("off")
        return _png(fig)
    d = exp.groupby("date")["amount"].sum().asfreq("D", fill_value=0).tail(60)
    ax.fill_between(d.index, d.values, color="#6366f1", alpha=0.25)
    ax.plot(d.index, d.rolling(7, min_periods=1).mean(), color="#6366f1", lw=2,
            label="7-day avg")
    ax.set_title("Daily spending (last 60 days)"); ax.legend(fontsize=8)
    ax.grid(alpha=0.25); fig.autofmt_xdate()
    return _png(fig)
