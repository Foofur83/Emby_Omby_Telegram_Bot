"""
Emby Bot - Central Launcher
Start de Telegram bot EN web interface (beide!)
"""
import sys
import subprocess
import os
import time
import shutil
import yaml

def main():
    # Ensure a usable config file exists. Prefer a mounted ./config directory
    # (mounted as /app/config) and create /app/config/config.yaml if missing.
    app_cwd = os.getcwd()
    dir_config_path = os.path.join(app_cwd, "config", "config.yaml")
    root_config_path = os.path.join(app_cwd, "config.yaml")

    def _create_from_example(target_path):
        if os.path.exists("config.example.yaml"):
            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copyfile("config.example.yaml", target_path)
                print(f"\nℹ️  Created {target_path} from config.example.yaml. Please review and edit.")
                return True
            except Exception as e:
                print(f"\n⚠️ Failed to create {target_path} from example: {e}")
                return False
        return False

    if not os.path.exists(dir_config_path):
        # Try to create inside ./config first
        created = _create_from_example(dir_config_path)
        if not created:
            # Fallback to root-level config.yaml
            if not os.path.exists(root_config_path):
                if _create_from_example(root_config_path):
                    pass
                else:
                    # Create a minimal placeholder in the preferred directory
                    try:
                        os.makedirs(os.path.dirname(dir_config_path), exist_ok=True)
                        with open(dir_config_path, "w", encoding="utf-8") as f:
                            f.write(
                                "admin_telegram_id: 0\n"
                                "emby_api_key: \"\"\n"
                                "emby_url: \"http://127.0.0.1:8096\"\n"
                                "ombi_api_key: \"\"\n"
                                "ombi_api_key_header: ApiKey\n"
                                "ombi_url: \"http://127.0.0.1:3579\"\n"
                                "poll_interval_seconds: 60\n"
                                "telegram_token: \"\"\n"
                            )
                        print(f"\nℹ️  Created placeholder config at {dir_config_path}. Please edit with real values.")
                    except Exception as e:
                        print(f"\n⚠️ Failed to create placeholder config at {dir_config_path}: {e}")
    
    print("\n" + "="*60)
    print("🤖 EMBY BOT - Starting beide services...")
    print("="*60 + "\n")
    
    # Start web interface in separate console window (Windows) or background (Linux)
    # Determine port from config.yaml if present so message matches actual port
    web_port = 5000
    try:
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
                web_port = int(cfg.get('web_ui_port') or cfg.get('web_port') or web_port)
    except Exception:
        web_port = 5000

    print(f"🌐 Starting Web Interface op http://localhost:{web_port}")
    if sys.platform == 'win32':
        # Windows: open in new console window
        web_process = subprocess.Popen(
            [sys.executable, "web_ui.py"],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    else:
        # Linux/Mac: background process
        web_process = subprocess.Popen([sys.executable, "web_ui.py"])
    
    time.sleep(2)
    print("✅ Web Interface gestart!\n")
    
    # Start bot in THIS console (foreground)
    print("🤖 Starting Telegram Bot...")
    print("="*60 + "\n")
    
    try:
        bot_process = subprocess.Popen([sys.executable, "bot.py"])
        bot_process.wait()  # Wait for bot to finish
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping services...")
    finally:
        # Clean up both processes
        if 'bot_process' in locals():
            bot_process.terminate()
            try:
                bot_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                bot_process.kill()
        
        web_process.terminate()
        try:
            web_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            web_process.kill()
        
        print("✅ Alle services gestopt")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Tot ziens!")
        sys.exit(0)
