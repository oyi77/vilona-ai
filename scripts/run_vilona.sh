
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
LOG_FILE="$APP_DIR/logs/vilona.log"
PID_FILE="$APP_DIR/vilona.pid"
DATABASE="$APP_DIR/vilona_v2.db"

MODE="${1:-paper}"
DEBUG="${2:-}"

export vilona_PAPER_TRADING="${MODE}"
export vilona_LOG_LEVEL="${DEBUG:+DEBUG:-INFO}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[Vilona AI v2]${NC} Starting in ${MODE} mode..."
echo -e "${GREEN}[Vilona AI v2]${NC} Log file: ${LOG_FILE}"

mkdir -p "$APP_DIR/logs"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[Error]${NC} python3 not found. Install Python 3.10+"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[Setup]${NC} Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo -e "${YELLOW}[Setup]${NC} Installing dependencies..."
pip install -q -r "$APP_DIR/requirements.txt"

echo -e "${GREEN}[Running]${NC} Starting Vilona AI v2..."
cd "$APP_DIR"
exec python3 app_server.py >> "$LOG_FILE" 2>&1
