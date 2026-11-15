# 💰 AI-Powered Personal Finance Dashboard
Flask · pandas · matplotlib · SQLite

## Features
- Add/delete/search transactions, CSV import & export, pagination
- KPIs: income, expenses, net savings, savings rate
- **Savings prediction**: linear-trend regression on monthly savings (± std band) + per-category next-month forecast
- Charts: monthly cash flow + forecast, category donut, daily spend with 7-day average
- Monthly category budgets with warning (80%) / over-budget alerts
- JSON API: `/api/summary`, `/api/transactions`, `/health`

## Run
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                  # http://127.0.0.1:5000  -> click "Load demo data"
pytest                         # run tests
```
## Deploy
```bash
docker build -t finance-dashboard .
docker run -p 8000:8000 -v finance-data:/data -e SECRET_KEY=your-secret finance-dashboard
```
## Scaling notes
- App factory + env-based config; stateless workers behind Gunicorn
- SQLite in WAL mode with indexes; move to PostgreSQL by swapping `db.py` (SQL is standard)
- Dashboard results cached 30s (replace `cachetools_lite` with Redis for multi-instance)
- Charts use `matplotlib.figure.Figure` (no global pyplot state -> thread-safe)
- Next steps: user auth (Flask-Login), per-user `user_id` column, Celery for heavy reports
