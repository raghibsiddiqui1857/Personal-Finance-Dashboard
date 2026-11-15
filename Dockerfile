FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DATABASE_PATH=/data/finance.db MPLBACKEND=Agg
VOLUME /data
EXPOSE 8000
CMD ["gunicorn", "-w", "3", "--threads", "2", "-b", "0.0.0.0:8000", "app:app"]
