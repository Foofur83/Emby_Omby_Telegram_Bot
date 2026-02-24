# Author: Foofur83
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

# Always use config/ directory for consistency
CONFIG_FILE = "config/config.yaml"

# Ensure config directory and file exist at startup
if not os.path.exists(CONFIG_FILE):
    try:
        os.makedirs("config", exist_ok=True)
        if os.path.exists("config.example.yaml"):
            import shutil
            shutil.copyfile("config.example.yaml", CONFIG_FILE)
            print(f"✓ Created {CONFIG_FILE} from config.example.yaml")
        else:
            # Create minimal placeholder
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(
                    "admin_telegram_id: 0\n"
                    "emby_api_key: \"\"\n"
                    "emby_url: \"http://127.0.0.1:8096\"\n"
                    "ombi_api_key: \"\"\n"
                    "ombi_api_key_header: ApiKey\n"
                    "ombi_url: \"http://127.0.0.1:3579\"\n"
                    "poll_interval_seconds: 60\n"
                    "telegram_token: \"\"\n"
                    "web_ui_port: 5000\n"
                )
            print(f"✓ Created placeholder {CONFIG_FILE}")
    except Exception as e:
        print(f"⚠ Failed to create {CONFIG_FILE}: {e}")
    
DATA_DIR = "data"
REQUESTS_FILE = os.path.join(DATA_DIR, "requests.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def get_admin_password():
    """Load admin password from config.yaml, or return default"""
    config = load_yaml(CONFIG_FILE)
    return config.get('admin_password', 'admin123')


def save_admin_password(password):
    """Save admin password to config.yaml"""
    config = load_yaml(CONFIG_FILE)
    config['admin_password'] = password
    save_yaml(CONFIG_FILE, config)


def is_default_password():
    """Check if default password is still being used"""
    return get_admin_password() == "admin123"


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
        if password == get_admin_password():
            response = redirect(url_for('dashboard'))
            response.set_cookie('admin_auth', 'authenticated', max_age=86400)  # 24 uur
            return response
        else:
            flash('Onjuist wachtwoord', 'error')
    return render_template('login.html', is_default=is_default_password())


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
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         recent_requests=recent_requests,
                         is_default_password=is_default_password())


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
            'web_ui_port': int(request.form.get('web_ui_port', 5000)),
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


@app.route('/users/<int:telegram_id>/toggle_notifications', methods=['POST'])
@require_auth
def toggle_notifications(telegram_id):
    """Toggle notificaties aan/uit voor gebruiker"""
    users = load_json(USERS_FILE)
    user = next((u for u in users if u.get('telegram_user_id') == telegram_id), None)
    
    if not user:
        return jsonify({'error': 'Gebruiker niet gevonden'}), 404
    
    # Toggle episode_notifications
    current = user.get('episode_notifications', True)
    user['episode_notifications'] = not current
    
    save_json(USERS_FILE, users)
    
    status = "ingeschakeld" if user['episode_notifications'] else "uitgeschakeld"
    flash(f'Notificaties {status} voor {user.get("telegram_first_name")}!', 'success')
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
    # Add unique hash to each request for deletion
    for req in requests:
        req_hash = hash(f"{req.get('telegram_user_id')}_{req.get('title')}_{req.get('requested_at')}")
        req['_hash'] = abs(req_hash)
    # Sorteer op datum (nieuwste eerst)
    requests = sorted(requests, key=lambda x: x.get('requested_at', ''), reverse=True)
    return render_template('requests.html', requests=requests)


@app.route('/requests/<int:request_hash>/delete', methods=['POST'])
@require_auth
def delete_request_by_hash(request_hash):
    """Individuele aanvraag verwijderen via hash matching"""
    requests = load_json(REQUESTS_FILE)
    
    # Find matching request by hash
    to_delete = None
    for i, req in enumerate(requests):
        req_hash = hash(f"{req.get('telegram_user_id')}_{req.get('title')}_{req.get('requested_at')}")
        if abs(req_hash) == request_hash:
            to_delete = i
            break
    
    if to_delete is not None:
        deleted_request = requests.pop(to_delete)
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


@app.route('/change-password', methods=['GET', 'POST'])
@require_auth
def change_password():
    """Wachtwoord wijzigen"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validatie
        if not current_password or not new_password or not confirm_password:
            flash('Vul alle velden in', 'error')
        elif current_password != get_admin_password():
            flash('Huidig wachtwoord is onjuist', 'error')
        elif new_password != confirm_password:
            flash('Nieuwe wachtwoorden komen niet overeen', 'error')
        elif len(new_password) < 6:
            flash('Wachtwoord moet minimaal 6 tekens lang zijn', 'error')
        elif new_password == "admin123":
            flash('Kies een ander wachtwoord dan de standaard', 'warning')
        else:
            # Opslaan
            save_admin_password(new_password)
            flash('Wachtwoord succesvol gewijzigd!', 'success')
            return redirect(url_for('dashboard'))
    
    return render_template('change_password.html', is_default_password=is_default_password())


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
    if is_default_password():
        print("📝 Standaard wachtwoord: admin123 (VERANDER DIT!)")
    app.run(host=host, port=port, debug=True)
