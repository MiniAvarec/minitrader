from datetime import datetime
from pydantic import BaseModel


class TfBreakdown(BaseModel):
    tf: str
    rsi: float | None
    macd_hist: float | None
    ema20: float | None
    ema50: float | None
    vote: int


class Signal(BaseModel):
    symbol: str
    side: str  # "buy" | "sell"
    confidence: float  # 0..100
    entry: float
    sl: float | None
    tp: float | None
    breakdown: list[TfBreakdown]
    news_refs: list[dict] = []
    created_at: datetime
