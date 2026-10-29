import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import classify


def metrics(close=120, sma20=110, sma50=100, rsi14=60):
    return {
        "symbol": "TEST",
        "date": "2026-01-01",
        "close": close,
        "sma20": sma20,
        "sma50": sma50,
        "rsi14": rsi14,
    }


def test_bullish_candidate():
    signal, _ = classify(metrics())
    assert signal == "BUY CANDIDATE"


def test_wait_when_not_bullish_or_exit():
    signal, _ = classify(metrics(close=105, sma20=110, sma50=100, rsi14=45))
    assert signal == "REVIEW / EXIT CANDIDATE"


def test_wait_middle_zone():
    signal, _ = classify(metrics(close=115, sma20=110, sma50=100, rsi14=45))
    assert signal == "WAIT"
