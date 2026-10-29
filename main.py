"""Educational daily-market signal bot. Alerts only; never places orders."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("market-signal-bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SCAN_HOURS = max(1, int(os.getenv("SCAN_HOURS", "6")))
STATE_PATH = Path(os.getenv("STATE_PATH", "state.json"))
AI_PROVIDER = os.getenv("AI_PROVIDER", "none").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest").strip()

# Yahoo Finance symbols. Crypto quotes are USD, stocks are typically INR.
DEFAULT_WATCHLIST = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "INFY.NS": "Infosys",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
}
raw_watchlist = os.getenv("WATCHLIST", "").strip()
WATCHLIST = {}
if raw_watchlist:
    for entry in raw_watchlist.split(","):
        symbol = entry.strip()
        if symbol:
            WATCHLIST[symbol] = symbol
else:
    WATCHLIST = DEFAULT_WATCHLIST.copy()


def send_telegram(message: str) -> None:
    """Send one Telegram message. Raises on failed delivery."""
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError(
            "Telegram is not configured. Copy .env.example to .env "
            "and set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": message},
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError("Telegram API did not confirm message delivery.")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("State file could not be read; starting with empty state.")
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def get_daily_metrics(symbol: str) -> dict[str, Any]:
    """Fetch daily candles and compute indicators from completed candles only."""
    data = yf.Ticker(symbol).history(
        period="1y",
        interval="1d",
        auto_adjust=True,
        actions=False,
    )
    if data is None or data.empty:
        raise ValueError(f"No market data returned for {symbol}")

    data = data.dropna(subset=["Close"]).copy()
    # Exclude the latest row to avoid an unfinished daily candle.
    if len(data) > 1:
        data = data.iloc[:-1]
    if len(data) < 60:
        raise ValueError(f"Insufficient completed daily candles for {symbol}")

    close = data["Close"].astype(float)
    data["SMA20"] = close.rolling(20, min_periods=20).mean()
    data["SMA50"] = close.rolling(50, min_periods=50).mean()

    # Wilder-style smoothed RSI via exponential moving averages.
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    data["RSI14"] = 100 - (100 / (1 + rs))
    data.loc[(avg_loss == 0) & (avg_gain > 0), "RSI14"] = 100
    data.loc[(avg_loss == 0) & (avg_gain == 0), "RSI14"] = 50

    latest = data.iloc[-1]
    if pd.isna(latest["SMA20"]) or pd.isna(latest["SMA50"]) or pd.isna(latest["RSI14"]):
        raise ValueError(f"Indicators unavailable for {symbol}")

    idx = data.index[-1]
    if getattr(idx, "tzinfo", None) is not None:
        candle_date = idx.tz_convert("UTC").date().isoformat()
    else:
        candle_date = idx.date().isoformat()

    return {
        "symbol": symbol,
        "date": candle_date,
        "close": float(latest["Close"]),
        "sma20": float(latest["SMA20"]),
        "sma50": float(latest["SMA50"]),
        "rsi14": float(latest["RSI14"]),
    }


def classify(metrics: dict[str, Any]) -> tuple[str, str]:
    """Simple illustrative rules, not a validated profitable strategy."""
    close = metrics["close"]
    sma20 = metrics["sma20"]
    sma50 = metrics["sma50"]
    rsi = metrics["rsi14"]

    if close > sma20 > sma50 and 50 <= rsi <= 68:
        return (
            "BUY CANDIDATE",
            "Close > SMA20 > SMA50 and RSI14 is between 50 and 68.",
        )
    if close < sma20 or sma20 < sma50:
        return (
            "REVIEW / EXIT CANDIDATE",
            "Close is below SMA20 or SMA20 is below SMA50. "
            "Review existing exposure; this is not a short-selling instruction.",
        )
    return "WAIT", "No complete setup under the configured rules."


def optional_ai_review(metrics: dict[str, Any], signal: str, reason: str) -> str:
    """Optional AI explanation; rules-only mode costs nothing for AI."""
    prompt = (
        "Review this educational technical-market signal cautiously. "
        "Do not invent facts, news, prices, probabilities, or financial data. "
        "Explain what indicators suggest and cannot prove, give two risks or "
        "missing checks, and end with 'review further' or 'wait'. No order advice "
        "or guaranteed returns. No live news was supplied.\n\n"
        f"Symbol: {metrics['symbol']}\n"
        f"Completed daily candle: {metrics['date']}\n"
        f"Close: {metrics['close']:.6f}\n"
        f"SMA20: {metrics['sma20']:.6f}\n"
        f"SMA50: {metrics['sma50']:.6f}\n"
        f"RSI14: {metrics['rsi14']:.2f}\n"
        f"Rule result: {signal}\nReason: {reason}\n"
        "Limit your response to 100 words."
    )

    try:
        if AI_PROVIDER == "openai":
            if not OPENAI_API_KEY:
                return "AI review skipped: OPENAI_API_KEY is missing."
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY, timeout=30)
            response = client.responses.create(
                model=OPENAI_MODEL,
                instructions=(
                    "You are a cautious research assistant. Separate facts "
                    "from uncertainty. Never promise profits."
                ),
                input=prompt,
                max_output_tokens=180,
            )
            return response.output_text.strip() or "AI returned no text."
        if AI_PROVIDER == "anthropic":
            if not ANTHROPIC_API_KEY:
                return "AI review skipped: ANTHROPIC_API_KEY is missing."
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=30)
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=180,
                system="Be cautious, state uncertainty, never promise profits.",
                messages=[{"role": "user", "content": prompt}],
            )
            return "\n".join(
                block.text for block in response.content
                if getattr(block, "type", "") == "text"
            ) or "AI returned no text."
        return "AI review disabled; this alert uses technical rules only."
    except Exception:
        log.exception("Optional AI review failed")
        return "AI review failed. Review the technical indicators manually."


def format_alert(
    name: str,
    metrics: dict[str, Any],
    signal: str,
    reason: str,
    ai_review: str,
) -> str:
    is_crypto = metrics["symbol"].endswith("-USD")
    currency = "USD quote (verify on your chosen venue)" if is_crypto else (
        "usually INR quote (verify with the exchange)"
    )
    return (
        "MARKET RESEARCH ALERT — NOT AN ORDER\n\n"
        f"Asset: {name} ({metrics['symbol']})\n"
        f"Signal: {signal}\n"
        f"Completed candle date: {metrics['date']}\n"
        f"Close: {metrics['close']:.6f}\n"
        f"SMA20: {metrics['sma20']:.6f}\n"
        f"SMA50: {metrics['sma50']:.6f}\n"
        f"RSI14: {metrics['rsi14']:.2f}\n"
        f"Quote note: {currency}\n\n"
        f"Rule explanation: {reason}\n\n"
        f"Optional AI review:\n{ai_review}\n\n"
        "Verify current prices, data freshness, fees, liquidity and risks. "
        "This is not financial advice. No broker order was placed."
    )


def scan_once() -> None:
    state = load_state()
    for symbol, name in WATCHLIST.items():
        try:
            metrics = get_daily_metrics(symbol)
            signal, reason = classify(metrics)
            previous = state.get(symbol, {})
            new_candidate = signal in ("BUY CANDIDATE", "REVIEW / EXIT CANDIDATE")
            duplicate = (
                previous.get("signal") == signal
                and previous.get("date") == metrics["date"]
            )

            if new_candidate and not duplicate:
                ai_text = optional_ai_review(metrics, signal, reason)
                message = format_alert(name, metrics, signal, reason, ai_text)
                # Persist alert state only after Telegram confirms success.
                send_telegram(message)

            state[symbol] = {"signal": signal, "date": metrics["date"]}
            save_state(state)
            log.info("%s %s %s", symbol, signal, metrics["date"])
        except Exception:
            # A failed symbol does not stop the rest of the watchlist.
            log.exception("Scan failed for %s", symbol)


def main() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit(
            "Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first."
        )
    send_telegram(
        "Market Signal Bot started.\n"
        "Daily candles, educational signals, alerts only. No orders are placed."
    )
    while True:
        scan_once()
        log.info("Next scan in %s hour(s).", SCAN_HOURS)
        time.sleep(SCAN_HOURS * 3600)


if __name__ == "__main__":
    main()
