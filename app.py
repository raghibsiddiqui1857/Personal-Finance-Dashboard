import io
import re
from datetime import date

import numpy as np
import pandas as pd
from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, url_for)
from cachetools_lite import TTLCache

import analytics as an
import db as database
from config import Config

CATEGORIES = ["Food", "Rent", "Transport", "Shopping", "Bills", "Health",
              "Entertainment", "Education", "Travel", "Salary", "Freelance", "Other"]
CACHE = TTLCache(ttl=30)


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    database.init_app(app)

    @app.context_processor
    def inject():
        return dict(cur=app.config["CURRENCY"], categories=CATEGORIES, today=date.today())

    @app.template_filter("money")
    def money(v):
        return f"{app.config['CURRENCY']}{v:,.0f}"

    # ---------- helpers ----------
    def valid_row(f):
        try:
            d = pd.to_datetime(f["date"]).date().isoformat()
            amt = round(float(f["amount"]), 2)
            typ = f["type"].strip().lower()
            cat = re.sub(r"\s+", " ", f["category"].strip().title())[:40]
        except (KeyError, ValueError, TypeError):
            return None
        if amt <= 0 or typ not in ("income", "expense") or not cat:
            return None
        return (d, typ, cat, amt, (f.get("note") or "")[:200])

    def invalidate():
        CACHE.clear()

    def dashboard_data():
        cached = CACHE.get("dash")
        if cached:
            return cached
        db = database.get_db()
        df = an.load_df(db)
        m = an.monthly_table(df)
        fc = an.forecast_savings(m)
        budgets = [dict(r) for r in db.execute("SELECT * FROM budgets ORDER BY category")]
        data = dict(
            totals=an.totals(df), forecast=fc, cat_fc=an.forecast_categories(df),
            budgets=an.budget_status(df, budgets),
            trend=an.chart_trend(m, fc), pie=an.chart_categories(df),
            daily=an.chart_daily(df),
            months=[dict(month=str(i), **r) for i, r in m.iterrows()][::-1],
        )
        CACHE.set("dash", data)
        return data

    # ---------- routes ----------
    @app.get("/")
    def index():
        page = max(request.args.get("page", 1, type=int), 1)
        per = app.config["PER_PAGE"]
        q = request.args.get("q", "").strip()
        db = database.get_db()
        where, args = "", []
        if q:
            where = "WHERE category LIKE ? OR note LIKE ?"
            args = [f"%{q}%"] * 2
        total = db.execute(f"SELECT COUNT(*) FROM transactions {where}", args).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM transactions {where} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
            args + [per, (page - 1) * per]).fetchall()
        pages = max((total + per - 1) // per, 1)
        return render_template("index.html", d=dashboard_data(), rows=rows,
                               page=page, pages=pages, q=q)

    @app.post("/add")
    def add():
        row = valid_row(request.form)
        if not row:
            flash("Invalid transaction – check date, type, category and amount.", "error")
        else:
            db = database.get_db()
            db.execute("INSERT INTO transactions(date,type,category,amount,note) "
                       "VALUES (?,?,?,?,?)", row)
            db.commit(); invalidate()
            flash("Transaction added.", "ok")
        return redirect(url_for("index"))

    @app.post("/delete/<int:tx_id>")
    def delete(tx_id):
        db = database.get_db()
        db.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        db.commit(); invalidate()
        return redirect(request.referrer or url_for("index"))

    @app.post("/budget")
    def budget():
        cat = request.form.get("category", "").strip().title()
        try:
            limit = float(request.form["monthly_limit"])
            assert limit > 0 and cat
        except (KeyError, ValueError, AssertionError):
            flash("Invalid budget.", "error")
            return redirect(url_for("index"))
        db = database.get_db()
        db.execute("INSERT INTO budgets(category,monthly_limit) VALUES(?,?) "
                   "ON CONFLICT(category) DO UPDATE SET monthly_limit=excluded.monthly_limit",
                   (cat, limit))
        db.commit(); invalidate()
        flash(f"Budget set for {cat}.", "ok")
        return redirect(url_for("index"))

    @app.post("/import")
    def import_csv():
        f = request.files.get("file")
        if not f or not f.filename.lower().endswith(".csv"):
            flash("Upload a .csv file with columns: date,type,category,amount,note", "error")
            return redirect(url_for("index"))
        try:
            df = pd.read_csv(io.BytesIO(f.read()))
            df.columns = [c.strip().lower() for c in df.columns]
            rows = [r for r in (valid_row(x) for x in df.fillna("").to_dict("records")) if r]
        except Exception:
            flash("Could not parse CSV.", "error")
            return redirect(url_for("index"))
        db = database.get_db()
        db.executemany("INSERT INTO transactions(date,type,category,amount,note) "
                       "VALUES (?,?,?,?,?)", rows)
        db.commit(); invalidate()
        flash(f"Imported {len(rows)} of {len(df)} rows.", "ok")
        return redirect(url_for("index"))

    @app.get("/export")
    def export_csv():
        df = pd.read_sql_query("SELECT date,type,category,amount,note FROM transactions "
                               "ORDER BY date", database.get_db())
        return Response(df.to_csv(index=False), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=transactions.csv"})

    @app.post("/seed")
    def seed():
        """Load 9 months of realistic demo data."""
        rng = np.random.default_rng(42)
        rows = []
        for k in range(9, 0, -1):
            start = (pd.Timestamp.today().normalize().replace(day=1)
                     - pd.DateOffset(months=k - 1))
            rows.append((start.date().isoformat(), "income", "Salary", 60000 + 1500 * (9 - k), "Monthly salary"))
            rows.append(((start + pd.Timedelta(days=1)).date().isoformat(), "expense", "Rent", 15000, "Rent"))
            for cat, base in [("Food", 7000), ("Transport", 2500), ("Shopping", 4000),
                              ("Bills", 3000), ("Entertainment", 2000), ("Health", 1200)]:
                for _ in range(rng.integers(3, 7)):
                    day = start + pd.Timedelta(days=int(rng.integers(2, 27)))
                    if day > pd.Timestamp.today():
                        continue
                    amt = round(float(base / 4.5 * rng.uniform(0.5, 1.5)), 2)
                    rows.append((day.date().isoformat(), "expense", cat, amt, ""))
        db = database.get_db()
        db.executemany("INSERT INTO transactions(date,type,category,amount,note) "
                       "VALUES (?,?,?,?,?)", rows)
        db.commit(); invalidate()
        flash(f"Loaded {len(rows)} demo transactions.", "ok")
        return redirect(url_for("index"))

    # ---------- JSON API (for mobile / React front-ends later) ----------
    @app.get("/api/summary")
    def api_summary():
        d = dashboard_data()
        return jsonify(totals={k: float(v) for k, v in d["totals"].items()},
                       forecast=d["forecast"], category_forecast=d["cat_fc"],
                       budgets=d["budgets"], monthly=d["months"])

    @app.get("/api/transactions")
    def api_tx():
        rows = database.get_db().execute(
            "SELECT * FROM transactions ORDER BY date DESC LIMIT ?",
            (min(request.args.get("limit", 100, type=int), 1000),)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
