<!-- Author: Foofur83 -->
# Emby Bot Web Interface

## 🌐 Web Interface Gebruiken

De web interface biedt een gebruiksvriendelijk admin panel voor het beheren van de bot.

### Starten

**Lokaal:**
```bash
python web_ui.py
```

**Docker:**
```bash
docker-compose up -d web-ui
```

De interface is beschikbaar op: **http://localhost:5000**

### Standaard Inloggegevens

⚠️ **BELANGRIJK: Wijzig het wachtwoord na eerste gebruik!**

- Wachtwoord: `admin123`

Om het wachtwoord te wijzigen, bewerk `ADMIN_PASSWORD` in `web_ui.py`

## 📋 Functies

### Dashboard
- **Statistieken**: Overzicht van aanvragen en gebruikers
- **Recente aanvragen**: Laatste 10 aanvragen met status

### Configuratie
- Wijzig alle bot instellingen via web interface
- Telegram token
- Admin Telegram ID  
- Ombi URL en API key
- Emby URL en API key
- Poll interval

⚠️ **Let op**: Herstart de bot na het wijzigen van configuratie!

### Gebruikersbeheer
- Bekijk alle geregistreerde gebruikers
- Keur nieuwe gebruikers goed
- Koppel Telegram accounts aan Emby gebruikers
- Verwijder gebruikers

### Aanvragen Overzicht
- Bekijk alle media aanvragen
- Filter op status (beschikbaar/wachtend)
- Bekijk gebruiker informatie

## 🔒 Beveiliging

### Productie Tips:

1. **Verander het admin wachtwoord** in `web_ui.py`

2. **Gebruik HTTPS** via reverse proxy (nginx/caddy):
   ```nginx
   server {
       listen 443 ssl;
       server_name emby-bot.example.com;
       
       location / {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

3. **Beperk toegang** tot lokaal netwerk of specifieke IPs

4. **Gebruik een database** voor user authenticatie (optioneel)

## 🐳 Docker Tips

```yaml
# Port mapping wijzigen in docker-compose.yml
ports:
  - "8080:5000"  # Toegankelijk op poort 8080
```

## 🛠️ Technische Details

- **Framework**: Flask
- **Template Engine**: Jinja2
- **Styling**: Pure CSS (dark theme)
- **Data Storage**: JSON files + YAML config

## 📱 Mobile Responsive

De interface is volledig responsive en werkt op:
- Desktop
- Tablets  
- Smartphones

## 🆘 Problemen Oplossen

**Kan niet inloggen:**
- Check het wachtwoord in `web_ui.py`
- Clear browser cookies

**Configuratie niet opgeslagen:**
- Check bestandspermissies op `config.yaml`
- Herstart de bot na wijzigingen

**Port 5000 al in gebruik:**
- Wijzig de port in `web_ui.py`: `app.run(port=8080)`
- Pas docker-compose.yml aan: `"8080:8080"`

## 🚀 Toekomstige Features

Mogelijke uitbreidingen:
- Real-time statistieken met WebSockets
- Media browser integratie
- Request approval workflow
- User request limits
- Email notificaties
- Audit logging
