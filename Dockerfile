FROM python:3.12-slim
WORKDIR /app
COPY engine ./engine
COPY web ./web
RUN useradd --create-home game && mkdir /data && chown game:game /data
USER game
EXPOSE 8000
VOLUME ["/data"]
CMD ["python", "-m", "engine.server", "--host", "0.0.0.0", "--db", "/data/theplan.sqlite3"]
