FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Note: --fix mode requires Claude Code CLI (npm package) which is not
# included in this image. Docker usage is for review-only mode.
# For --fix, run arc locally with Claude Code CLI installed.
ENTRYPOINT ["python", "arc.py"]
