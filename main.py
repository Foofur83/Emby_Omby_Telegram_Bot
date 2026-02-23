"""
Emby Bot - Central Launcher
Start de Telegram bot EN web interface (beide!)
"""
import sys
import subprocess
import os
import time
import yaml

def main():
    # Check if config exists
    if not os.path.exists("config.yaml"):
        print("\n❌ ERROR: config.yaml not found!")
        print("📝 Copy config.yaml.example and fill in your details")
        sys.exit(1)
    
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
