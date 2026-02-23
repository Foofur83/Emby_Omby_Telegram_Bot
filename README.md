# 🤖 Emby Bot - Nederlandse Telegram Bot voor Ombi + Emby

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub issues](https://img.shields.io/github/issues/Foofur83/Emby_Omby_Telegram_Bot)](https://github.com/Foofur83/Emby_Omby_Telegram_Bot/issues)
[![GitHub stars](https://img.shields.io/github/stars/Foofur83/Emby_Omby_Telegram_Bot)](https://github.com/Foofur83/Emby_Omby_Telegram_Bot/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/Foofur83/Emby_Omby_Telegram_Bot)](https://github.com/Foofur83/Emby_Omby_Telegram_Bot/network)

Een krachtige Telegram bot voor het aanvragen van films en series via Ombi, met automatische notificaties en direct afspelen via Emby.

> 🇳🇱 **Volledig in het Nederlands** | 🎬 **Smart Detection** | 📺 **Episode Tracking** | 🌐 **Web Interface**

---

## 📑 Inhoudsopgave

- [Features](#-features)
- [Screenshots](#-screenshots)
- [Installatie](#-installatie)
- [Gebruik](#-gebruik--voor-eindgebruikers)
- [Admin Functies](#-admin-functies)
- [Configuratie](#-configuratie-opties)
- [Web Interface](WEB_INTERFACE.md)
- [Problemen Oplossen](#-problemen-oplossen)
- [Bijdragen](CONTRIBUTING.md)
- [Licentie](#-licentie)

---

## ✨ Features

### 🎬 Content Management
- **Natuurlijke taal aanvragen** - Type gewoon "Dune" of "Breaking Bad"
- **Slimme detectie** - Bot zoekt automatisch in Ombi en vraagt alleen "film of serie?" wanneer beide gevonden zijn
- **Direct beschikbaar** - Als content al in Emby staat, krijg je meteen een afspeelknop
- **Automatische notificaties** - Krijg een bericht wanneer je aanvraag beschikbaar is

### 📺 Series Functies
- **Seizoen & aflevering selectie** - Kies exacte aflevering via menu's
- **Nieuwe afleveringen** - Automatische notificatie bij nieuwe afleveringen van series die je kijkt
- **Continue watching** - Bot monitort welke series je aan het kijken bent
- **Hervatten** - Vraagt of je wilt hervatten waar je gebleven was

### ▶️ Playback Controle
- **1-click afspelen** - Direct afspelen op je Emby apparaten
- **Apparaat selectie** - Kies automatisch of handmatig je apparaat
- **Resume functie** - Hervat vanaf vorige positie of start opnieuw
- **Progress tracking** - Emby houdt bij waar je gebleven bent

### 👥 User Management
- **Registratie systeem** - Gebruikers registreren via `/register`
- **Admin approval** - Koppel gebruikers aan Emby accounts
- **Toegangsbeheer** - Alleen goedgekeurde gebruikers kunnen aanvragen doen
- **Notificatie voorkeuren** - Gebruikers kunnen aflevering notificaties in/uitschakelen

### 🌐 Web Interface
- **Dashboard** - Statistieken en overzichten
- **Configuratie** - Wijzig instellingen via browser
- **Gebruikersbeheer** - Keur nieuwe gebruikers goed
- **Aanvragen overzicht** - Bekijk en beheer alle aanvragen

### 🔧 Technisch
- **Smart polling** - Controleert automatisch op nieuwe content
- **Poster detectie** - Toont filmposters en banners
- **Error handling** - Duidelijke foutmeldingen
- **Logging** - Uitgebreide logs voor debugging

## � Screenshots

> 📝 Voor screenshots en demo's, zie [SCREENSHOTS.md](SCREENSHOTS.md)

**Telegram Bot Features:**
- 🎬 Smart content zoeken met automatische detectie
- 📺 Seizoen/aflevering selectie menu's
- ▶️ Direct playback met apparaat keuze
- 🔔 Automatische notificaties

**Web Interface Features:**
- 📊 Dashboard met statistieken
- 👥 Gebruikersbeheer met approval systeem
- ⚙️ Live configuratie editor
- 📖 Ingebouwde handleiding

## �📋 Installatie

### Stap 1: Vereisten

**Python 3.10 of hoger** is vereist.

### Stap 2: Clone Repository

```bash
git clone https://github.com/Foofur83/Emby_Omby_Telegram_Bot.git
cd Emby_Omby_Telegram_Bot
```

### Stap 3: Virtual Environment (Aanbevolen)

**Windows:**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Stap 4: Installeer Dependencies

```bash
pip install -r requirements.txt
```

### Stap 5: Configuratie

1. **Kopieer het voorbeeld configuratiebestand:**
   ```bash
   cp config.yaml.example config.yaml
   ```

2. **Bewerk `config.yaml`:**
   ```yaml
   telegram:
     bot_token: "JOUW_TELEGRAM_BOT_TOKEN"
     admin_telegram_id: 123456789  # Jouw Telegram User ID

   ombi:
     url: "https://ombi.jouwdomein.nl"
     api_key: "JOUW_OMBI_API_KEY"

   emby:
     url: "https://emby.jouwdomein.nl"
     api_key: "JOUW_EMBY_API_KEY"

   settings:
     poll_interval: 60  # Seconden tussen checks
   ```

### Stap 6: Telegram Bot Aanmaken

1. Open Telegram en zoek **@BotFather**
2. Stuur `/newbot`
3. Volg de instructies en kies een naam
4. Kopieer de **bot token** naar `config.yaml`

### Stap 7: Telegram User ID Ophalen

1. Open Telegram en zoek **@userinfobot**
2. Start een chat - je krijgt je User ID
3. Kopieer dit nummer naar `admin_telegram_id` in `config.yaml`

### Stap 8: Ombi API Key

1. Log in op Ombi
2. Ga naar **Settings → Ombi**
3. Scroll naar **API Key**
4. Kopieer de key naar `config.yaml`

### Stap 9: Emby API Key

1. Log in op Emby Dashboard
2. Ga naar **Advanced → API Keys**
3. Klik **New API Key**
4. Geef een naam (bijv. "Telegram Bot")
5. Kopieer de key naar `config.yaml`

## 🚀 Starten

### Methode 1: Interactive Menu (Aanbevolen)

**Windows:**
```cmd
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

Dit opent een menu met opties:
1. **Start Telegram Bot** - Alleen de bot
2. **Start Web Interface** - Alleen web UI (poort 5000)
3. **Start Both** - Bot + Web Interface
4. **Exit** - Afsluiten

### Methode 2: Direct Starten

**Bot + Web Interface:**
```bash
python main.py
```

**Alleen Bot:**
```bash
python bot.py
```

**Alleen Web Interface:**
```bash
python web_ui.py
```

### Methode 3: Docker (Productie)

1. **Bewerk `docker-compose.yml` indien nodig**
2. **Start services:**
   ```bash
   docker-compose up -d
   ```
3. **Bekijk logs:**
   ```bash
   docker-compose logs -f
   ```
4. **Stop services:**
   ```bash
   docker-compose down
   ```

## 📱 Gebruik - Voor Eindgebruikers

### Eerste Keer

1. **Open de Telegram bot** (link van admin)
2. **Druk op Start** of type `/start`
3. **Type `/register`** om toegang aan te vragen
4. **Wacht op goedkeuring** - Admin krijgt notificatie
5. **Ontvang bevestiging** - Je krijgt een bericht bij goedkeuring

### Dag

elijks Gebruik

**Film of serie aanvragen:**
```
Dune
Breaking Bad
The Matrix
```

De bot zoekt automatisch en toont resultaten. Kies het juiste resultaat.

**Series afspelen:**
1. Type de titel: `Breaking Bad`
2. Als beschikbaar, klik **▶️ Afspelen**
3. Kies **seizoen** uit het menu
4. Kies **aflevering** uit het menu
5. Selecteer je **apparaat**
6. Afspelen begint!

**Films afspelen:**
1. Type de titel: `Inception`
2. Als beschikbaar, klik **▶️ Afspelen**
3. Selecteer je **apparaat**
4. Genieten maar!

### Commands voor Gebruikers

- `/start` - Welkomstbericht en uitleg
- `/help` - Overzicht van functies
- `/register` - Account aanvragen
- `/status` - Bekijk je aanvragen
- `/notifications` - Schakel aflevering notificaties aan/uit
- `/recent` - Laatst toegevoegd aan Emby
- `/myshows` - Jouw aangevraagde series
- `/updates` - Check nieuwe afleveringen

### Notificaties

**Je ontvangt automatisch een bericht bij:**
- ✅ Aanvraag is goedgekeurd in Ombi
- 📺 Content is beschikbaar in Emby (afspeelknop!)
- 🆕 Nieuwe aflevering van een serie die je kijkt

**Aflevering notificaties uitzetten:**
```
/notifications
```

## 🛠️ Admin Functies

### Via Telegram Bot

**Gebruiker goedkeuren:**
```
/approve <telegram_id> <emby_username>
```
Voorbeeld: `/approve 123456789 john_doe`

**Gebruiker weigeren:**
```
/deny <telegram_id>
```

### Via Web Interface

1. **Open browser:** `http://localhost:5000`
2. **Login** met wachtwoord (standaard: `admin123`)
3. **Dashboard** - Bekijk statistieken
4. **Configuratie** - Wijzig instellingen
5. **Gebruikers** - Beheer accounts
6. **Aanvragen** - Bekijk alle aanvragen

**⚠️ BELANGRIJK:** Wijzig het admin wachtwoord in `web_ui.py`!

Zoek deze regel:
```python
ADMIN_PASSWORD = "admin123"  # ⚠️ WIJZIG DIT!
```

## 🔧 Configuratie Opties

### telegram
- `bot_token` - Telegram Bot API token
- `admin_telegram_id` - Telegram User ID van admin

### ombi
- `url` - Ombi server URL (bijv. `https://ombi.domain.nl`)
- `api_key` - Ombi API sleutel

### emby
- `url` - Emby server URL (bijv. `https://emby.domain.nl`)
- `api_key` - Emby API sleutel

### settings
- `poll_interval` - Seconden tussen automatische checks (standaard: 60)

## 📊 Data Bestanden

Alle data wordt opgeslagen in de `data/` folder:

- **`requests.json`** - Alle media aanvragen
- **`users.json`** - Geregistreerde gebruikers en voorkeuren
- **`episode_notifications.json`** - Tracking voor aflevering notificaties

**Backup maken:**
```bash
cp -r data/ data_backup/
```

## 🐛 Problemen Oplossen

### Bot start niet

**Check Python versie:**
```bash
python --version  # Minimaal 3.10
```

**Check dependencies:**
```bash
pip install -r requirements.txt --upgrade
```

**Check logs:**
```bash
tail -f logs/bot.log  # Als je logging hebt ingesteld
```

### "Unauthorized" errors

- ✅ Check `bot_token` in `config.yaml`
- ✅ Zorg dat bot nog actief is in BotFather
- ✅ Test met `/start` in Telegram

### Ombi verbinding mislukt

- ✅ Check `ombi.url` (met https:// of http://)
- ✅ Controleer `api_key`
- ✅ Test URL in browser: `https://ombi.domain.nl/api/v1/Status`

### Emby verbinding mislukt

- ✅ Check `emby.url` (met https:// of http://)
- ✅ Controleer `api_key`
- ✅ Test URL: `https://emby.domain.nl/emby/System/Info?api_key=KEY`

### Geen notificaties

- ✅ Check `poll_interval` in config (niet te hoog)
- ✅ Verifieer bot draait continu (niet alleen bij gebruik)
- ✅ Check `episode_notifications` in `data/users.json` (moet `true` zijn)

### Web interface niet bereikbaar

- ✅ Check of `web_ui.py` draait
- ✅ Probeer `http://localhost:5000`
- ✅ Check firewall instellingen
- ✅ Poort in gebruik? Wijzig in `web_ui.py`: `app.run(port=8080)`

### Series hebben geen posters

- Dit is normaal - Ombi TV search geeft `banner` field terug
- Posters worden automatisch gedetecteerd indien beschikbaar

## 🚀 Geavanceerd

### Productie Deployment

**1. Gebruik systemd (Linux):**

Create `/etc/systemd/system/emby-bot.service`:
```ini
[Unit]
Description=Emby Telegram Bot
After=network.target

[Service]
Type=simple
User=jouw-user
WorkingDirectory=/pad/naar/emby-bot
Environment="PATH=/pad/naar/emby-bot/.venv/bin"
ExecStart=/pad/naar/emby-bot/.venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable en start:**
```bash
sudo systemctl enable emby-bot
sudo systemctl start emby-bot
sudo systemctl status emby-bot
```

**2. Gebruik Docker Compose (Aanbevolen):**

Zie `docker-compose.yml` - gewoon `docker-compose up -d`

**3. Reverse Proxy (HTTPS voor web interface):**

**Nginx voorbeeld:**
```nginx
server {
    listen 443 ssl;
    server_name emby-bot.domain.nl;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Monitoring

**Check logs:**
```bash
# Realtime logs
docker-compose logs -f

# Of zonder Docker
tail -f bot.log
```

**Check data bestanden:**
```bash
# Aantal aanvragen
cat data/requests.json | jq '. | length'

# Goedgekeurde gebruikers
cat data/users.json | jq '[.[] | select(.approved == true)] | length'
```

## 🤝 Bijdragen

Verbeteringen zijn welkom! Zie [CONTRIBUTING.md](CONTRIBUTING.md) voor richtlijnen.

## 📄 Licentie

MIT License - zie [LICENSE](LICENSE) bestand

## 🙏 Credits

- **python-telegram-bot** - Telegram Bot API wrapper
- **aiohttp** - Async HTTP client
- **Flask** - Web framework
- **Ombi** - Media request management
- **Emby** - Media server

## 📞 Support

Problemen? Vragen? Suggesties?

- 🐛 [Open een Issue](https://github.com/Foofur83/Emby_Omby_Telegram_Bot/issues)
- 💬 [Discussies](https://github.com/Foofur83/Emby_Omby_Telegram_Bot/discussions)
- ⭐ [Star dit project](https://github.com/Foofur83/Emby_Omby_Telegram_Bot) als je het nuttig vindt!

## 🌟 Hoogtepunten

- ✅ **Volledig Nederlands** - Alle berichten en documentatie in het Nederlands
- ✅ **Smart Detection** - Automatische type detectie (film/serie)
- ✅ **Episode Tracking** - Intelligent volgen van series die je kijkt
- ✅ **One-Click Playback** - Direct afspelen zonder configuratie
- ✅ **Web Management** - Moderne web interface voor admins
- ✅ **Production Ready** - Docker support en systemd examples

---

**Gemaakt met ❤️ voor de Nederlandse Emby community**

[![GitHub Repo](https://img.shields.io/badge/GitHub-Emby__Omby__Telegram__Bot-blue?logo=github)](https://github.com/Foofur83/Emby_Omby_Telegram_Bot)

