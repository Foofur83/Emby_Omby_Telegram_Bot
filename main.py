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
    # Check if config exists; if not, create from example or write a placeholder
    if not os.path.exists("config.yaml"):
        if os.path.exists("config.example.yaml"):
            try:
                shutil.copyfile("config.example.yaml", "config.yaml")
                print("\nℹ️  `config.yaml` not found — created from `config.example.yaml`. Please review and edit.")
            except Exception as e:
                print(f"\n⚠️ Failed to create config.yaml from example: {e}")
        else:
            # Write a minimal placeholder config so the app can start
            placeholder = (
                "admin_telegram_id: 0\n"
                "emby_api_key: \"\"\n"
                "emby_url: \"http://127.0.0.1:8096\"\n"
                "ombi_api_key: \"\"\n"
                "ombi_api_key_header: ApiKey\n"
                "ombi_url: \"http://127.0.0.1:3579\"\n"
                "poll_interval_seconds: 60\n"
                "telegram_token: \"\"\n"
            )
            try:
                with open("config.yaml", "w", encoding="utf-8") as f:
                    f.write(placeholder)
                print("\nℹ️  `config.yaml` not found — a placeholder `config.yaml` has been created. Please edit with your settings.")
            except Exception as e:
                print(f"\n⚠️ Failed to create placeholder config.yaml: {e}")
    
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
