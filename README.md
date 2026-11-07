# Vilona AI v2 - AI-Powered Trading Agent

Upgraded from decompiled Vilona AI v1. Supports crypto exchanges via CCXT,
Telegram monitoring, optional multi-agent personas, and headless/VPS deployment.

## Features

- **Multi-exchange support**: Binance, Bybit, OKX, Kraken, etc. via CCXT
- **Telegram bot**: Monitor positions, control scanner, close trades
- **Optional headless mode**: Run on VPS without display
- **Agent personas**: Optional researcher/trader/risk_manager/judge layers
- **Preserved Vilona AI logic**: Break-even, trailing stop, drift cancellation
- **SQLite persistence**: Survives restarts, tracks positions & trades
- **SystemOne integration**: Connect to JEV ecosystem (optional)
- **Single executable**: Nuitka build for Windows (.exe) and Linux

## Quick Start

```bash
# Clone and setup
git clone https://github.com/oyi77/vilona-ai
cd vilona-v2
./setup.sh

# Configure (copy env example)
cp .env.example .env
nano .env  # Add your exchange API keys and Telegram bot token

# Run (paper trading mode)
./scripts/run_vilona.sh paper

# Run (live trading mode)
./scripts/run_vilona.sh live
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Show status and available commands |
| `/status` | Current positions and daily P/L |
| `/balance` | Account balance |
| `/closeall` | Close all open positions |
| `/stop` | Stop the scanner |
| `/run` | Restart the scanner |
| `/log` | Recent activity log |

## Configuration

Environment variables or `.env` file:

```bash
vilona_EXCHANGE=binance
vilona_EXCHANGE_API_KEY=your_key
vilona_EXCHANGE_API_SECRET=your_secret
vilona_TELEGRAM_BOT_TOKEN=your_bot_token
vilona_TELEGRAM_CHAT_IDS=123456789
vilona_SYMBOLS=BTC/USDT,ETH/USDT
vilona_LLM_PROVIDER=openrouter
vilona_LLM_API_KEY=your_llm_key
vilona_LLM_MODEL=anthropic/claude-3.5-sonnet
vilona_PERSONAS=researcher,trader,risk_manager,judge
vilona_SYSTEMONE_ENABLED=false
```

## Building Executables

```bash
# Install build dependencies
pip install nuitka

# Build for current platform
python scripts/build.py

# Build for all platforms
python scripts/build.py all
```

Output:
- Windows: `build/Vilona AI-v2.exe`
- Linux: `build/Vilona AI-v2-linux`
- macOS: `build/Vilona AI-v2.app`

## Architecture

```
app_server.py          # Main entry point
├── config/           # Configuration management
├── trading/
│   ├── bridge_ccxt.py        # CCXT integration (replaces MT5)
│   └── trade_executor_v2.py  # BE/Trailing/Drift logic (from v1)
├── agents/           # Optional agent personas
│   ├── researcher.py
│   ├── trader.py
│   ├── risk_manager.py
│   └── judge.py
├── llm/              # LLM clients and reasoning
├── ui/
│   └── telegram_controller.py  # Telegram bot
└── core/             # Database, state, logging
```

## SystemOne (JEV) Integration

Set `vilona_SYSTEMONE_ENABLED=true` and configure endpoint/API key.
Exchange signals and positions will be synced to your JEV system.

## License

Original Vilona AI logic preserved. New code MIT licensed.
