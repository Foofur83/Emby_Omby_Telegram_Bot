#!/bin/bash
# Emby Bot Launcher voor Linux/Mac
# Start ALTIJD beide services (Bot + Web)

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "================================================"
echo -e "${BLUE}          EMBY BOT - LAUNCHER${NC}"
echo "================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python 3 niet gevonden!${NC}"
    echo "Installeer Python 3.11+ via je package manager"
    exit 1
fi

# Check config
if [ ! -f "config.yaml" ]; then
    echo -e "${RED}[ERROR] config.yaml niet gevonden!${NC}"
    echo "Kopieer config.yaml.example en vul je gegevens in"
    exit 1
fi

echo -e "${GREEN}[*] Starting beide services...${NC}"
echo -e "${BLUE}[*] Web Interface: http://localhost:5000${NC}"
echo -e "${BLUE}[*] Telegram Bot: Running${NC}"
echo -e "${YELLOW}[*] Druk Ctrl+C om te stoppen${NC}"
echo ""
echo "================================================"
echo ""

# Start main.py which handles both services
python3 main.py

echo ""
echo "Tot ziens!"
