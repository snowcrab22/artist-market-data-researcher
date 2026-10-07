FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY artistscore ./artistscore
RUN pip install --no-cache-dir .
ENV ARTISTSCORE_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["artistscore", "serve", "--host", "0.0.0.0", "--port", "8000"]
