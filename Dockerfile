FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5050
ENTRYPOINT ["python", "-c", "import os, subprocess; port = os.environ.get('PORT', '5050'); subprocess.run(['gunicorn', 'scripts.dashboard:app', '--bind', f'0.0.0.0:{port}', '--workers', '2'])"]
