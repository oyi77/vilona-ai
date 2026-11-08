# Vilona AI v2 - UI/UX Design Document

**Version**: v2.1
**Date**: 2026-11-08
**Status**: Ready for Execution

---

## Executive Summary

Vilona AI v2 operates as a **headless trading server** controlled via **Telegram**. This document defines the complete UI/UX layer, including:

1. **Telegram Command Center** - Rich, button-driven dashboard
2. **Rich Terminal Dashboard** - Professional CLI UX for local/server use
3. **System Tray App** - Low-overhead Windows desktop presence
4. **Proactive Intelligence** - Real-time trade alerts with AI reasoning

---

## 1. Telegram Command Center

### 1.1 Navigation Model

**Primary Control**: Persistent `ReplyKeyboardMarkup` with 4 main sections:

```
[📊 Status]    [💰 Balance]
[⚙️ Control]   [📜 Logs]
```

- Always visible, no typing required
- Each section opens a dedicated view
- All actions use `InlineKeyboardMarkup` for quick interactions

### 1.2 View Specifications

#### Status View (`/status` or "📊 Status")

**Content Structure**:
```
*📊 Trading Status*

*Positions Open:* `3`
*Daily P/L:* `+124.50` USDT 🟢
*Win Rate:* `12/15`

*Open Trades:*
• `101` 📈 *BTC/USDT* 
  `43,250.00000` | `0.15` lot | P/L: `+45.20` 🟢
  SL: `42,800.00` | TP: `44,500.00`
• `102` 📉 *ETH/USDT* 
  `2,340.00000` | `2.50` lot | P/L: `-12.30` 🔴
  SL: `2,280.00` | TP: `2,450.00`
```

**Interactive Elements**:
- `🔴 Close All` button (admin-only, with confirmation)
- `🔄 Refresh` button (refreshes status without navigating back)

**Formatting Rules**:
- Use `MarkdownV2` with `*bold*` headers
- Prices in backtick code blocks
- P/L emojis: 🟢 (profit), 🔴 (loss), ⚪ (neutral)
- Direction arrows: 📈 (buy), 📉 (sell)

#### Balance View (`/balance` or "💰 Balance")

**CCXT Mode**:
```
*💰 Account Balance*

*USDT Total:* `15,420.50`
*USDT Free:* `12,300.00`
```

**MT5 Mode**:
```
*💰 Account Balance*

*Balance:* `50,000.00`
*Equity:* `50,124.50`
*Margin:* `1,200.00`
*Free Margin:* `48,924.50`
```

**Exchange-Aware**: Auto-detects `bridge.type` (`ccxt` vs `mt5`)

#### Control View (`/control` or "⚙️ Control")

**Content Structure**:
```
*⚙️ Scanner Control*

*State:* 🟢 Running
_Mode_: `LIVE`
_Exchange_: `MT5`

[▶️ Start]  [⏹️ Stop]
[🔄 Restart]
```

**Interactive Elements**:
- `▶️ Start` - Starts scanner (admin-only)
- `⏹️ Stop` - Stops scanner (admin-only)
- `🔄 Restart` - Restart scanner sequence (admin-only)

**Confirmation Flow**:
- Stop/Restart triggers confirmation dialog
- Close All requires double-confirmation (initial + final)

#### Logs View (`/logs` or "📜 Logs")

**Content Structure**:
```
*📜 Recent Logs*

`2026-11-08 14:30:12 | BUY | BTC/USDT | 43,250.00 | AI: "Breakout confirmed"`
`2026-11-08 14:28:45 | SELL | ETH/USDT | 2,340.00 | AI: "Rejection at resistance"`
`2026-11-08 14:25:10 | CLOSE | BTC/USDT | P/L: +45.20 | AI: "Target hit"`
```

**Formatting**:
- Monospace code blocks for log entries
- Color-coded actions: GREEN (buy), RED (sell), BLUE (close)

### 1.3 Proactive Notifications

**Trade Alerts** (auto-sent on open/close):

```
*🚨 Trade Opened*

`BTC/USDT` BUY
*Volume*: `0.15` | *Price*: `43,250.00`
*SL*: `42,800.00` | *TP*: `44,500.00`

*AI Logic:*
_Breakout above 43,200 with volume confirmation_
```

**Daily Reports** (scheduled 00:00 UTC):

```
*📈 Daily Summary - 2026-11-08*

*Trades*: 15 total (12 wins, 3 losses)
*P/L*: +124.50 USDT
*Best Trade*: +45.20 (BTC/USDT)
*Worst Trade*: -12.30 (ETH/USDT)
*Equity*: 50,124.50
```

### 1.4 Command Reference

| Command | Description | Access |
|---------|-------------|--------|
| `/start` | Show welcome + main menu | Authorized |
| `/status` | Trading status card | Authorized |
| `/balance` | Account balance | Authorized |
| `/control` | Scanner control panel | Authorized |
| `/logs` | Recent activity | Authorized |
| `/closeall` | Close all positions | Admin only |
| `/stats` | Advanced stats | Admin only |

---

## 2. Rich Terminal Dashboard

### 2.1 Design Philosophy

When running locally or on a VPS, users interact via **terminal**. Current state: raw Python logs. Target state: **professional trading dashboard**.

**Requirements**:
- No external GUI dependencies
- Pure Python (use `rich` library for terminal formatting)
- Works in any terminal emulator (Windows, macOS, Linux)
- Real-time updates without screen flicker

### 2.2 Dashboard Layout

**Header (Fixed)**:
```
┌─────────────────────────────────────────────────────────────┐
│  🤖 Vilona AI v2 | LIVE | MT5 | SCANNING... | P/L: +124.50 │
└─────────────────────────────────────────────────────────────┘
```

**Main Body (Scrolling)**:
```
[14:30:12] ✅ BUY  BTC/USDT  43,250.00  vol=0.15  AI: Breakout confirmed
[14:28:45] ❌ SELL ETH/USDT  2,340.00  vol=2.50  AI: Rejection at resistance
[14:25:10] 🔄 CLOSE BTC/USDT  P/L: +45.20  AI: Target hit
[14:20:33] ℹ️ SCAN  3 symbols  M15  12 candles  completed
```

**Footer (Fixed)**:
```
Uptime: 4h 32m | Positions: 3 | Last Scan: 14:30:12 | Mode: PAPER
```

### 2.3 Implementation Details

**Library**: `rich` (terminal formatting)

**Key Components**:
- `rich.panel` for header/footer
- `rich.table` for log entries
- `rich.console` for real-time updates
- `rich.live` for continuous refresh

**Color Coding**:
- GREEN: Success, Buy signals, Profit
- RED: Failure, Sell signals, Loss
- YELLOW: Warnings, Scanning
- BLUE: Info, System events

**Terminal Commands**:
- `q` - Quit
- `h` - Hide/show dashboard
- `s` - Toggle scanner

### 2.4 File Structure

```
ui/terminal_dashboard.py
├── class Dashboard:
│   ├── def __init__(self, bridge, config)
│   ├── def start(self) -> None
│   ├── def stop(self) -> None
│   ├── def _update_header(self) -> Panel
│   ├── def _update_logs(self, new_logs) -> Table
│   └── def _update_footer(self) -> Panel
```

---

## 3. System Tray App (Windows)

### 3.1 Design Philosophy

For Windows users running as desktop app, provide **lightweight presence** without heavy GUI framework.

**Requirements**:
- No PyQt/PySide dependency
- Minimal memory footprint (< 50MB)
- Native Windows notifications
- System tray icon with right-click menu

### 3.2 Implementation

**Library**: `pystray` + `Pillow`

**Features**:
- Tray icon: Vilona AI logo (16x16 or 32x32)
- Right-click menu:
  - Status (shows current state)
  - Start/Stop Scanner
  - Open Telegram Bot (launches browser)
  - View Logs
  - Exit
- Native toast notifications for trade alerts

### 3.3 File Structure

```
ui/system_tray.py
├── class SystemTrayApp:
│   ├── def __init__(self, bridge, config)
│   ├── def start(self) -> None
│   ├── def _build_menu(self) -> menu
│   ├── def _notify_trade(self, alert) -> None
│   └── def _update_icon(self, status) -> None
```

---

## 4. Configuration & Auth

### 4.1 Config Structure

```python
# config/settings.yaml
exchange:
  type: mt5  # or ccxt
  name: mt5  # or binance, bybit, etc.
  api_key: ""
  api_secret: ""

telegram:
  bot_token: "123456:ABC-DEF..."
  chat_ids: [123456789]
  authorized_users: [123456789]
  admin_users: [123456789]

trading:
  paper_mode: true
  symbols: ["BTC/USDT", "ETH/USDT"]
  risk_per_trade: 0.01  # 1%
  max_positions: 5

ui:
  terminal_dashboard: true
  system_tray: true
  notifications:
    trade_alerts: true
    daily_reports: true
```

### 4.2 Auth Model

- **Authorized User**: Can view status, balance, logs
- **Admin User**: Can control scanner, close positions, modify settings

**Implementation**: `ui/auth.py`
```python
def is_authorized(chat_id: int) -> bool:
    """Check if user is in authorized_users list"""
    
def is_admin(chat_id: int) -> bool:
    """Check if user is in admin_users list"""
```

---

## 5. Execution Plan

### Phase 1: Telegram UX (Week 1)
- [ ] Implement `ReplyKeyboardMarkup` main menu
- [ ] Build `InlineKeyboardMarkup` for control panels
- [ ] Add `MarkdownV2` formatting for all views
- [ ] Create proactive trade alert system
- [ ] Implement daily report scheduler

**Files**:
- `ui/telegram_controller.py` (rewrite)
- `ui/alerts.py` (new)

### Phase 2: Terminal Dashboard (Week 2)
- [ ] Add `rich` to dependencies
- [ ] Implement `Dashboard` class
- [ ] Integrate with `app_server.py` main loop
- [ ] Add terminal commands (q, h, s)

**Files**:
- `ui/terminal_dashboard.py` (new)
- `app_server.py` (update)

### Phase 3: System Tray (Week 3)
- [ ] Add `pystray`, `Pillow` to dependencies
- [ ] Implement `SystemTrayApp` class
- [ ] Create tray icon assets
- [ ] Integrate with Windows notification API

**Files**:
- `ui/system_tray.py` (new)
- `assets/tray_icon.png` (new)

### Phase 4: Polish & Testing (Week 4)
- [ ] End-to-end testing
- [ ] Documentation updates
- [ ] Performance profiling
- [ ] Release v2.1

---

## 6. Dependencies

**Add to `requirements.txt`**:
```
rich>=13.0.0
pystray>=0.19.0
Pillow>=10.0.0
```

**Existing** (no change):
```
ccxt>=4.0.0
numpy>=1.24.0
aiohttp>=3.8.0
python-telegram-bot>=21.0
nuitka>=2.0
pyyaml>=6.0
sqlite-utils>=3.0
MetaTrader5
```

---

## 7. Success Metrics

- **User Retention**: 80%+ of users complete 1+ trading session
- **Alert Accuracy**: 100% of trades trigger correct alerts
- **Dashboard Uptime**: 99.9% (no crashes during trading)
- **System Tray Performance**: <50MB memory, <2% CPU

---

**End of Document**
