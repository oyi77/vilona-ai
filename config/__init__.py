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
    min_volume_usd: float = 100.0
    
    be_trigger_atr_mult: float = 1.5
    be_offset_atr_mult: float = 0.5
    trailing_atr_mult: float = 2.0
    trailing_step_atr_mult: float = 0.5
    
    max_drift_points: int = 100
    max_drift_candles: int = 12
    drift_timeframe: str = "15m"


@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: str = "vilona_v2.db"


@dataclass
class BuildConfig:
    """Build configuration for packaging"""
    version: str = "2.0.0"
    app_name: str = "Vilona AI-v2"
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
        config.trading.max_risk_per_trade_pct = float(os.getenv("vilona_MAX_RISK_PCT", str(config.trading.max_risk_per_trade_pct)))
        config.trading.max_daily_loss_pct = float(os.getenv("vilona_MAX_DAILY_LOSS_PCT", str(config.trading.max_daily_loss_pct)))
        config.trading.paper_trading = os.getenv("vilona_PAPER_TRADING", "true").lower() == "true"
        
        config.headless = os.getenv("vilona_HEADLESS", "true").lower() == "true"
        config.debug = os.getenv("vilona_DEBUG", "false").lower() == "true"
        config.log_level = os.getenv("vilona_LOG_LEVEL", config.log_level)
        
        personas_str = os.getenv("vilona_PERSONAS", "")
        if personas_str:
            config.enabled_personas = [x.strip() for x in personas_str.split(",")]
        
        config.systemone_enabled = os.getenv("vilona_SYSTEMONE_ENABLED", "false").lower() == "true"
        config.systemone_endpoint = os.getenv("vilona_SYSTEMONE_ENDPOINT", config.systemone_endpoint)
        config.systemone_api_key = os.getenv("vilona_SYSTEMONE_API_KEY", config.systemone_api_key)
        
        return config
    
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
