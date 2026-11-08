# Vilona AI v2 - AI-Powered Trading Agent

Upgraded decompiled Vilona AI v1. Supports crypto exchanges via CCXT and MT5,
Telegram monitoring, optional multi-agent personas, headless/VPS deployment.

## 📸 Visuals

### Telegram Command Center
The all-in-one mobile dashboard for your bot.
![Telegram UI](https://placehold.co/300x400/1a1a2e/00d9ff?text=Telegram+UI+Demo)

### Terminal Dashboard
Bloomberg-style CLI for VPS and local server monitoring.
![Terminal Dashboard](https://placehold.co/600x400/1a1a2e/00d9ff?text=Terminal+Dashboard+Demo)

### System Tray (Windows)
Lightweight background presence with native notifications.
![System Tray](https://placehold.co/400x120/1a1a2e/00d9ff?text=System+Tray+Demo)

---

## ✨ Features

- **Rich Telegram UI**: Persistent menu buttons, inline control panels, MarkdownV2 styled cards, AI trade alerts with reasoning.
- **Multi-exchange support**: Binance, Bybit, OKX, Kraken (via CCXT) + **MetaTrader 5**.
- **Telegram Command Center**: No more typing commands. Use sleek inline buttons for Start/Stop, Close All, and refresh views.
- **Terminal Dashboard**: Professional CLI using `rich` library. Fixed headers, live P/L tracking, color-coded logs.
- **System Tray App (Windows)**: Discrete background presence with right-click quick access and native toast notifications.
- **Proactive Intelligence**: Bot automatically pushes AI-driven trade alerts with entry reasoning, SL/TP, and P/L updates.
- **Optional headless mode**: Run on VPS without display.
- **Agent personas**: Optional researcher/trader/risk_manager/judge layers.
- **Preserved Vilona AI logic**: Break-even, trailing stop, drift cancellation.
- **SQLite persistence**: Survives restarts, tracks positions & trades.
- **SystemOne integration**: Connect to JEV ecosystem (optional).
- **Single executable**: Nuitka build for Windows (.exe) and Linux.

## 🚀 Quick Start

### Telegram Commands

No commands needed! Use the persistent button menu:

| Button | Description |
|--------|-------------|
| 📊 Status | View open positions, daily P/L, win rate |
| 💰 Balance | Account equity for CCXT or MT5 |
| ⚙️ Control | Start/Stop/Restart scanner |
| 📜 Logs | Recent trading activity |

## Architecture

```
app_server.py (Bridge initialization)
│
├── Trading (bridge_ccxt.py / bridge_mt5.py)
│   └── trade_executor_v2.py (BE/Trailing/Drift)
├── UI / UX Overhaul
│   ├── telegram_controller.py (Command Center)
│   ├── terminal_dashboard.py (Rich CLI)
│   └── system_tray.py (Desktop Presence)
├── Agents (researcher.py, trader.py, risk_manager.py, judge.py)
├── LLM Integration
└── Persistence (SQLite)
```

## License

Original Vilona AI logic preserved. New code MIT licensed.
