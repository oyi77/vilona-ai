"""
Vilona AI v2 Configuration Module

Centralized configuration management with environment variable overrides.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
import json


@dataclass
class ExchangeConfig:
    """Exchange connection configuration"""
    name: str = "binance"
    api_key: str = ""
    api_secret: str = ""
    password: str = ""
    sandbox: bool = False
    rate_limit: int = 1200
    market_type: str = "spot"


@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    bot_token: str = ""
    chat_ids: List[int] = field(default_factory=list)
    admin_chat_ids: List[int] = field(default_factory=list)
    polling_interval: float = 1.0


@dataclass
class LLMConfig:
    """LLM/Agent configuration"""
    provider: str = "openrouter"
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = "anthropic/claude-3.5-sonnet"
    reasoning_effort: str = "medium"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 30


@dataclass
class TradingConfig:
    """Trading engine configuration"""
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframes: List[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h"])
    scan_interval: int = 30
    
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_concurrent_positions: int = 5
    max_spread_pct: float = 0.1
    min_confidence: float = 0.55
    max_spread_pct_default: float = 0.15
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0
    min_volume_usd: float = 100.0
    
    be_trigger_atr_mult: float = 1.5
    be_offset_atr_mult: float = 0.5
    trailing_atr_mult: float = 2.0
    trailing_step_atr_mult: float = 0.5
    
    max_drift_points: int = 100
    max_drift_candles: int = 12
    drift_timeframe: str = "15m"
    paper_trading: bool = True
    max_data_age_seconds: int = 120

    news_guard_enabled: bool = False
    news_guard_before_min: int = 30
    news_guard_force_close_min: int = 5
    news_guard_after_min: int = 30
    budget_limit_daily: int = 0  # 0 = unlimited
    budget_on_limit: str = "stop"  # "stop" | "free"
    recorder_enabled: bool = True

@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: str = "vilona_v2.db"


@dataclass
class BuildConfig:
    """Build configuration for packaging"""
    version: str = "Vilona AI-v2.2"
    icon_path: Optional[str] = None


@dataclass
class Config:
    """Main configuration container"""
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    
    headless: bool = True
    paper_trading: bool = True
    autonomy_enabled: bool = False
    emergency_stop_file: str = "vilona.emergency_stop"
    debug: bool = False
    log_level: str = "INFO"
    
    enabled_personas: List[str] = field(default_factory=lambda: ["trader", "risk_manager"])
    
    systemone_enabled: bool = False
    systemone_endpoint: Optional[str] = None
    systemone_api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        config = cls()
        
        config.exchange.name = os.getenv("vilona_EXCHANGE", config.exchange.name)
        config.exchange.api_key = os.getenv("vilona_EXCHANGE_API_KEY", config.exchange.api_key)
        config.exchange.api_secret = os.getenv("vilona_EXCHANGE_API_SECRET", config.exchange.api_secret)
        config.exchange.password = os.getenv("vilona_EXCHANGE_PASSWORD", config.exchange.password)
        config.exchange.sandbox = os.getenv("vilona_EXCHANGE_SANDBOX", "false").lower() == "true"
        config.exchange.market_type = os.getenv("vilona_EXCHANGE_MARKET_TYPE", config.exchange.market_type)
        
        config.telegram.bot_token = os.getenv("vilona_TELEGRAM_BOT_TOKEN", config.telegram.bot_token)
        chat_ids_str = os.getenv("vilona_TELEGRAM_CHAT_IDS", "")
        if chat_ids_str:
            config.telegram.chat_ids = [int(x.strip()) for x in chat_ids_str.split(",")]
        admin_ids_str = os.getenv("vilona_TELEGRAM_ADMIN_IDS", "")
        if admin_ids_str:
            config.telegram.admin_chat_ids = [int(x.strip()) for x in admin_ids_str.split(",")]
        
        config.llm.provider = os.getenv("vilona_LLM_PROVIDER", config.llm.provider)
        config.llm.api_key = os.getenv("vilona_LLM_API_KEY", config.llm.api_key)
        config.llm.base_url = os.getenv("vilona_LLM_BASE_URL", config.llm.base_url)
        config.llm.model = os.getenv("vilona_LLM_MODEL", config.llm.model)
        config.llm.reasoning_effort = os.getenv("vilona_LLM_REASONING_EFFORT", config.llm.reasoning_effort)
        
        symbols_str = os.getenv("vilona_SYMBOLS", "")
        if symbols_str:
            config.trading.symbols = [x.strip() for x in symbols_str.split(",")]
        
        timeframes_str = os.getenv("vilona_TIMEFRAMES", "")
        if timeframes_str:
            config.trading.timeframes = [x.strip() for x in timeframes_str.split(",")]
        
        config.trading.scan_interval = int(os.getenv("vilona_SCAN_INTERVAL", str(config.trading.scan_interval)))
        config.trading.news_guard_enabled = os.getenv("vilona_NEWS_GUARD_ENABLED", str(config.trading.news_guard_enabled)).lower() == "true"
        config.trading.news_guard_before_min = int(os.getenv("vilona_NEWS_GUARD_BEFORE_MIN", str(config.trading.news_guard_before_min)))
        config.trading.news_guard_force_close_min = int(os.getenv("vilona_NEWS_GUARD_FORCE_CLOSE_MIN", str(config.trading.news_guard_force_close_min)))
        config.trading.news_guard_after_min = int(os.getenv("vilona_NEWS_GUARD_AFTER_MIN", str(config.trading.news_guard_after_min)))
        config.trading.budget_limit_daily = int(os.getenv("vilona_BUDGET_LIMIT_DAILY", str(config.trading.budget_limit_daily)))
        config.trading.budget_on_limit = os.getenv("vilona_BUDGET_ON_LIMIT", config.trading.budget_on_limit)
        config.trading.recorder_enabled = os.getenv("vilona_RECORDER_ENABLED", str(config.trading.recorder_enabled)).lower() == "true"
        config.trading.max_risk_per_trade_pct = float(os.getenv("vilona_MAX_RISK_PCT", str(config.trading.max_risk_per_trade_pct)))
        config.trading.max_daily_loss_pct = float(os.getenv("vilona_MAX_DAILY_LOSS_PCT", str(config.trading.max_daily_loss_pct)))
        config.trading.max_data_age_seconds = int(os.getenv("vilona_MAX_DATA_AGE_SECONDS", str(config.trading.max_data_age_seconds)))
        config.paper_trading = os.getenv("vilona_PAPER_TRADING", "true").lower() == "true"
        config.trading.paper_trading = config.paper_trading
        
        config.headless = os.getenv("vilona_HEADLESS", "true").lower() == "true"
        config.autonomy_enabled = os.getenv("vilona_AUTONOMY_ENABLED", "false").lower() == "true"
        config.emergency_stop_file = os.getenv("vilona_EMERGENCY_STOP_FILE", config.emergency_stop_file)
        config.debug = os.getenv("vilona_DEBUG", "false").lower() == "true"
        config.log_level = os.getenv("vilona_LOG_LEVEL", config.log_level)
        
        personas_str = os.getenv("vilona_PERSONAS", "")
        if personas_str:
            config.enabled_personas = [x.strip() for x in personas_str.split(",")]
        
        config.systemone_enabled = os.getenv("vilona_SYSTEMONE_ENABLED", "false").lower() == "true"
        config.systemone_endpoint = os.getenv("vilona_SYSTEMONE_ENDPOINT", config.systemone_endpoint)
        config.systemone_api_key = os.getenv("vilona_SYSTEMONE_API_KEY", config.systemone_api_key)
        
        return config

    def validate(self) -> List[str]:
        """Validate configuration and return list of error strings."""
        errors = []

        if not self.paper_trading:
            if self.exchange.name.lower() != 'mt5':
                if not self.exchange.api_key:
                    errors.append("paper_trading=False requires exchange.api_key")
                if not self.exchange.api_secret:
                    errors.append("paper_trading=False requires exchange.api_secret")
            if not self.telegram.bot_token:
                errors.append("telegram.bot_token must be non-empty")
            if not self.telegram.chat_ids:
                errors.append("telegram.chat_ids must be non-empty list")
            if not self.llm.api_key:
                errors.append("llm.api_key must be non-empty")

        if not self.trading.symbols:
            errors.append("trading.symbols must be non-empty")
        if self.trading.max_risk_per_trade_pct <= 0 or self.trading.max_risk_per_trade_pct > 10:
            errors.append("trading.max_risk_per_trade_pct must be > 0 and <= 10")
        if self.trading.max_daily_loss_pct <= 0 or self.trading.max_daily_loss_pct > 50:
            errors.append("trading.max_daily_loss_pct must be > 0 and <= 50")

        if not self.enabled_personas:
            errors.append("enabled_personas must be non-empty")
        if not 0.0 <= self.trading.min_confidence <= 1.0:
            errors.append("trading.min_confidence must be between 0 and 1")
        if self.trading.scan_interval <= 0:
            errors.append("trading.scan_interval must be greater than 0")
        if self.telegram.admin_chat_ids and not set(self.telegram.admin_chat_ids).issubset(self.telegram.chat_ids):
            errors.append("telegram.admin_chat_ids must be a subset of telegram.chat_ids")
        if self.trading.max_data_age_seconds <= 0:
            errors.append("trading.max_data_age_seconds must be greater than 0")
        if self.exchange.market_type not in {"spot", "margin", "swap", "future"}:
            errors.append("exchange.market_type must be spot, margin, swap, or future")

        return errors
    
    def to_dataclass(self) -> dict:
        """Convert Config into a plain dict with typed values and stripped secrets."""
        import copy
        safe = copy.deepcopy(self)
        # Strip secrets
        safe.exchange.api_key = "***" if safe.exchange.api_key else ""
        safe.exchange.api_secret = "***" if safe.exchange.api_secret else ""
        safe.exchange.password = "***" if safe.exchange.password else ""
        safe.telegram.bot_token = "***" if safe.telegram.bot_token else ""
        safe.llm.api_key = "***" if safe.llm.api_key else ""
        safe.systemone_api_key = "***" if safe.systemone_api_key else ""

        # Flatten trading fields for direct consumption
        d = copy.deepcopy(safe.trading.__dict__)
        d["exchange"] = copy.deepcopy(safe.exchange.__dict__)
        d["telegram"] = copy.deepcopy(safe.telegram.__dict__)
        d["llm"] = copy.deepcopy(safe.llm.__dict__)
        d["database"] = copy.deepcopy(safe.database.__dict__)
        d["build"] = copy.deepcopy(safe.build.__dict__)
        d["headless"] = safe.headless
        d["paper_trading"] = safe.paper_trading
        d["debug"] = safe.debug
        d["log_level"] = safe.log_level
        d["enabled_personas"] = list(safe.enabled_personas)
        d["systemone_enabled"] = safe.systemone_enabled
        d["systemone_endpoint"] = safe.systemone_endpoint
        d["systemone_api_key"] = safe.systemone_api_key
        return d

    def to_json(self) -> str:
        """Serialize config to JSON (excluding sensitive keys)"""
        import copy
        safe = copy.deepcopy(self)
        safe.exchange.api_key = "***" if safe.exchange.api_key else ""
        safe.exchange.api_secret = "***" if safe.exchange.api_secret else ""
        safe.exchange.password = "***" if safe.exchange.password else ""
        safe.telegram.bot_token = "***" if safe.telegram.bot_token else ""
        safe.llm.api_key = "***" if safe.llm.api_key else ""
        safe.systemone_api_key = "***" if safe.systemone_api_key else ""
        return json.dumps(safe.__dict__, indent=2, default=str)
    
    def save(self, path: str) -> None:
        """Save config to JSON file"""
        with open(path, 'w') as f:
            f.write(self.to_json())


_config: Optional[Config] = None


def get_config() -> Config:
    """Get global config instance (singleton)"""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set global config instance"""
    global _config
    _config = config


# --- KingAI-parity data paths (persisted across restarts) ---
import os as _os
import sys as _sys
from pathlib import Path as _Path


def _data_root() -> _Path:
    override = _os.environ.get('VILONA_DATA_ROOT')
    if override:
        return _Path(override)
    if not getattr(_sys, 'frozen', False):
        return _Path(__file__).resolve().parents[1]
    base = _Path(_os.environ.get('LOCALAPPDATA') or _Path.home() / 'AppData' / 'Local') / 'Vilona AI'
    try:
        (base / 'data').mkdir(parents=True, exist_ok=True)
    except OSError:
        return _Path(_sys.executable).resolve().parent
    return base


DATA_ROOT = _data_root()
DATA_DIR = DATA_ROOT / 'data'

CACHE_DIR = DATA_DIR / 'cache'

APP_NAME = 'Vilona AI'
APP_SLUG = 'vilona-ai'
APP_VERSION = '2.0.0'
PROJECT_ROOT = DATA_ROOT
