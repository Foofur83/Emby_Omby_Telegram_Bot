FROM python:3.11-slim

WORKDIR /app

# Kopieer requirements en installeer Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer applicatie code
COPY bot.py .
COPY config.yaml .

# Maak data directory voor requests.json
RUN mkdir -p /app/data

# Volume voor persistent data
VOLUME /app/data

# Start de bot
CMD ["python", "-u", "bot.py"]
