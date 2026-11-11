FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home agent
COPY --chown=agent:agent . .
RUN mkdir -p /app/data && chown agent:agent /app/data
USER agent
EXPOSE 8000
CMD ["python", "app.py", "--host", "0.0.0.0"]
