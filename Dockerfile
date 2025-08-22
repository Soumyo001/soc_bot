# Use official Python 3.12.11 slim image
FROM python:3.12.11-slim

# -------------------- Metadata -----------------------
LABEL maintainer="www.soumyo@gmail.com"
LABEL description="SOC Bot - Telegram bot for centralized alerts"

# -------------------- Working directory -------------
WORKDIR /app

# -------------------- Copy files --------------------
COPY requirements.txt .
COPY soc_bot.py .
COPY data ./data

# -------------------- Install dependencies ----------
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# -------------------- Start the bot -----------------
CMD ["python", "soc_bot.py"]
