# Author: Foofur83
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

# Kopieer applicatie code (alles zodat config.example.yaml en modules in de image zitten)
COPY . .

# Verify templates were copied - debug
RUN ls -la /app/templates/ || echo "WARNING: Templates directory not found!"

# Maak data en config directories, supervisor log dir
RUN mkdir -p /app/data /app/config /var/log/supervisor

# Volumes voor persistent data en config
VOLUME ["/app/data", "/app/config"]

# Supervisord config (plaats naar /etc)
COPY supervisor/emby.conf /etc/supervisor/conf.d/emby.conf
RUN printf "[supervisord]\n[nodaemon]\n[include]\nfiles = /etc/supervisor/conf.d/*.conf\n" > /etc/supervisor/supervisord.conf

EXPOSE 5000

# Start supervisord in foreground
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
