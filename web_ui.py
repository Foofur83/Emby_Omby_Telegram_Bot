"""
Web interface voor Emby Bot configuratie en beheer
"""
import os
import json
import yaml
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)

CONFIG_FILE = "config.yaml"
DATA_DIR = "data"
REQUESTS_FILE = os.path.join(DATA_DIR, "requests.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

# Simpele authenticatie (vervang met beter systeem in productie)
ADMIN_PASSWORD = "admin123"  # VERANDER DIT!


def require_auth(f):
    """Decorator voor admin authenticatie"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.cookies.get('admin_auth')
        if auth != 'authenticated':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login pagina"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            response = redirect(url_for('dashboard'))
            response.set_cookie('admin_auth', 'authenticated', max_age=86400)  # 24 uur
            return response
        else:
            flash('Onjuist wachtwoord', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Uitloggen"""
    response = redirect(url_for('login'))
    response.set_cookie('admin_auth', '', max_age=0)
    return response


@app.route('/')
@require_auth
def dashboard():
    """Dashboard met statistieken"""
    # Laad data
    requests = load_json(REQUESTS_FILE)
    users = load_json(USERS_FILE)
    
    # Bereken stats
    stats = {
        'total_requests': len(requests),
        'pending_requests': len([r for r in requests if not r.get('notified')]),
        'completed_requests': len([r for r in requests if r.get('notified')]),
        'total_users': len(users),
        'approved_users': len([u for u in users if u.get('approved')]),
        'pending_users': len([u for u in users if not u.get('approved')]),
    }
    
    # Recente aanvragen
    recent_requests = sorted(requests, key=lambda x: x.get('requested_at', ''), reverse=True)[:10]
    
    return render_template('dashboard.html', stats=stats, recent_requests=recent_requests)


@app.route('/config', methods=['GET', 'POST'])
@require_auth
def config():
    """Configuratie editor"""
    if request.method == 'POST':
        # Update config
        new_config = {
            'telegram_token': request.form.get('telegram_token'),
            'admin_telegram_id': int(request.form.get('admin_telegram_id', 0)),
            'ombi_url': request.form.get('ombi_url'),
            'ombi_api_key': request.form.get('ombi_api_key'),
            'ombi_api_key_header': request.form.get('ombi_api_key_header'),
            'emby_url': request.form.get('emby_url'),
            'emby_api_key': request.form.get('emby_api_key'),
            'poll_interval_seconds': int(request.form.get('poll_interval_seconds', 60)),
        }
        
        save_yaml(CONFIG_FILE, new_config)
        flash('Configuratie opgeslagen! Herstart de bot om wijzigingen toe te passen.', 'success')
        return redirect(url_for('config'))
    
    # Laad huidige config
    current_config = load_yaml(CONFIG_FILE)
    return render_template('config.html', config=current_config)


@app.route('/users')
@require_auth
def users():
    """Gebruikersbeheer"""
    user_list = load_json(USERS_FILE)
    return render_template('users.html', users=user_list)


@app.route('/users/<int:telegram_id>/approve', methods=['POST'])
@require_auth
def approve_user(telegram_id):
    """Gebruiker goedkeuren via web interface"""
    emby_username = request.form.get('emby_username')
    
    if not emby_username:
        return jsonify({'error': 'Emby gebruikersnaam is verplicht'}), 400
    
    users = load_json(USERS_FILE)
    user = next((u for u in users if u.get('telegram_user_id') == telegram_id), None)
    
    if not user:
        return jsonify({'error': 'Gebruiker niet gevonden'}), 404
    
    user['approved'] = True
    user['emby_username'] = emby_username
    user['approved_at'] = datetime.now().isoformat()
    user['needs_notification'] = True  # Flag voor bot om notificatie te sturen
    
    save_json(USERS_FILE, users)
    
    flash(f'Gebruiker {user.get("telegram_first_name")} goedgekeurd! Bot zal notificatie sturen.', 'success')
    return redirect(url_for('users'))


@app.route('/users/<int:telegram_id>/delete', methods=['POST'])
@require_auth
def delete_user(telegram_id):
    """Gebruiker verwijderen"""
    users = load_json(USERS_FILE)
    users = [u for u in users if u.get('telegram_user_id') != telegram_id]
    save_json(USERS_FILE, users)
    
    flash('Gebruiker verwijderd!', 'success')
    return redirect(url_for('users'))


@app.route('/requests')
@require_auth
def requests_view():
    """Alle aanvragen"""
    requests = load_json(REQUESTS_FILE)
    # Sorteer op datum (nieuwste eerst)
    requests = sorted(requests, key=lambda x: x.get('requested_at', ''), reverse=True)
    return render_template('requests.html', requests=requests)


@app.route('/requests/<int:request_id>/delete', methods=['POST'])
@require_auth
def delete_request(request_id):
    """Individuele aanvraag verwijderen"""
    requests = load_json(REQUESTS_FILE)
    if 0 <= request_id < len(requests):
        deleted_request = requests.pop(request_id)
        save_json(REQUESTS_FILE, requests)
        flash(f'Aanvraag voor "{deleted_request.get("title")}" verwijderd!', 'success')
    else:
        flash('Aanvraag niet gevonden!', 'error')
    return redirect(url_for('requests_view'))


@app.route('/requests/clear-completed', methods=['POST'])
@require_auth
def clear_completed_requests():
    """Wis alle voltooide (notified) aanvragen"""
    requests = load_json(REQUESTS_FILE)
    completed_count = len([r for r in requests if r.get('notified')])
    requests = [r for r in requests if not r.get('notified')]
    save_json(REQUESTS_FILE, requests)
    flash(f'{completed_count} voltooide aanvragen gewist!', 'success')
    return redirect(url_for('requests_view'))


@app.route('/requests/clear-all', methods=['POST'])
@require_auth
def clear_all_requests():
    """Wis ALLE aanvragen (met bevestiging)"""
    confirm = request.form.get('confirm')
    if confirm == 'yes':
        requests = load_json(REQUESTS_FILE)
        count = len(requests)
        save_json(REQUESTS_FILE, [])
        flash(f'Alle {count} aanvragen gewist!', 'success')
    else:
        flash('Actie geannuleerd - bevestiging ontbreekt', 'warning')
    return redirect(url_for('requests_view'))


@app.route('/guide')
@require_auth
def guide():
    """Gebruikershandleiding voor de web interface"""
    return render_template('guide.html')


# Helper functies
def load_yaml(filepath):
    """Laad YAML bestand"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def save_yaml(filepath, data):
    """Sla YAML bestand op"""
    with open(filepath, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def load_json(filepath):
    """Laad JSON bestand"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_json(filepath, data):
    """Sla JSON bestand op"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    # Lees poort (config.yaml) indien aanwezig, anders fallback naar 5000
    cfg = load_yaml(CONFIG_FILE)
    try:
        port = int(cfg.get('web_ui_port') or cfg.get('web_port') or 5000)
    except Exception:
        port = 5000
    host = cfg.get('web_ui_host', '0.0.0.0')

    print(f"🌐 Web interface gestart op http://localhost:{port}")
    print("📝 Standaard wachtwoord: admin123 (VERANDER DIT!)")
    app.run(host=host, port=port, debug=True)
