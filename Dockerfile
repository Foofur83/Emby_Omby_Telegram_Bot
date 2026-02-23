FROM python:3.11-slim

WORKDIR /app

# Install supervisor for process management
RUN apt-get update \
	&& apt-get install -y --no-install-recommends supervisor \
	&& rm -rf /var/lib/apt/lists/*

# Kopieer requirements en installeer Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
	&& python -m pip cache purge || true

# Kopieer applicatie code
COPY bot.py web_ui.py ./
COPY templates ./templates

# Maak data directory en supervisor log dir
RUN mkdir -p /app/data /var/log/supervisor

# Volume voor persistent data
VOLUME /app/data

# Supervisord config
COPY supervisor/emby.conf /etc/supervisor/conf.d/emby.conf
RUN printf "[supervisord]\n[nodaemon]\n[include]\nfiles = /etc/supervisor/conf.d/*.conf\n" > /etc/supervisor/supervisord.conf

EXPOSE 5000

# Start supervisord in foreground
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
