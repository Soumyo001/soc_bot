FROM python:3.12.11-slim

# -------------------- Metadata -----------------------
LABEL maintainer="www.soumyo@gmail.com"
LABEL description="SOC Bot - Telegram bot for centralized alerts"

# -------------------- Environment Vars ---------------
# Ensures stdout/stderr logs are shown immediately
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# -------------------- Working directory --------------
WORKDIR /app

# -------------------- System deps --------------------
# (optional: add curl, vim, etc. if needed for debugging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# -------------------- Copy dependency list -----------
COPY requirements.txt .

# -------------------- Install dependencies -----------
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# -------------------- Copy project files -------------
COPY . .

# -------------------- Expose port (optional, if API)-
EXPOSE 8080

# -------------------- Start the bot -----------------
CMD ["python", "soc_bot.py"]
