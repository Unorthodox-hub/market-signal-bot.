# Market Signal Bot (educational, alerts-only)

Python prototype that watches a small stock/crypto list, computes SMA20, SMA50 and RSI14 from daily candles, and sends Telegram research alerts. Optional OpenAI or Anthropic review explains a rule-based candidate signal.

**It does not place trades. It is not a proven profitable strategy or financial advice.**

## What it does
- Uses daily historical candles from `yfinance` for a small prototype watchlist.
- Excludes the newest row to avoid using a potentially unfinished candle.
- Calculates SMA20, SMA50 and RSI14.
- Sends a Telegram alert only when a candidate signal changes or a new completed candle changes the signal.
- Optional AI review is only called for new candidate alerts.
- Stores alert state locally in `state.json`.
- Continues scanning other symbols if one symbol fails.

## Important data limitations
`yfinance` is an unofficial interface to Yahoo Finance and is not an exchange-certified data feed. Data can be delayed, incomplete, rate-limited, adjusted, unavailable, or unsuitable for commercial use. Crypto symbols here are quoted in USD and may not match the price on an Indian exchange. Verify all prices and venue-specific liquidity before making any decision. Do not use this prototype for intraday execution.

## Requirements
- Python 3.11+
- Telegram account
- Optional paid API account if enabling OpenAI or Anthropic

## Setup
1. Create a Telegram bot with the official `@BotFather` and copy its token.
2. Open the bot and press **Start**, then send it a message.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser and find `message.chat.id`. Keep this URL and token private.
4. Copy `.env.example` to `.env`; fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
5. Install and run:

   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   python main.py
   ```

6. You should receive a startup message. Leave the process running to keep polling.

## Optional AI
Start with `AI_PROVIDER=none`, which avoids AI API costs. To enable OpenAI, set `AI_PROVIDER=openai` and `OPENAI_API_KEY`. To use Anthropic, set `AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. API billing is separate from consumer chat subscriptions; check current provider prices before enabling it. Do not put keys into source code or commit `.env`.

## Watchlist
Set `WATCHLIST` to comma-separated Yahoo Finance symbols, for example:
`RELIANCE.NS,TCS.NS,BTC-USD,ETH-USD`

This is a tiny watchlist, not a scanner of every listed stock or token. Symbols and data availability vary.

## Signal rules (illustrative only)
- `BUY CANDIDATE`: close > SMA20 > SMA50 and RSI14 between 50 and 68.
- `REVIEW / EXIT CANDIDATE`: close < SMA20 or SMA20 < SMA50.
- `WAIT`: neither condition.

These simple rules have not been demonstrated to be profitable. Signals are not orders. Backtest without look-ahead bias, include spreads/fees/taxes, and paper-trade for at least 30 days before considering any real capital.

## Costs
- Python and Telegram basic bot messaging: generally free.
- Market data: no direct `yfinance` API fee, but no uptime, freshness, or data rights guarantee.
- AI: optional usage-based API fees.
- Hosting: free if run locally, but the device must remain on; always-on hosting may cost money.

## Safety
- No broker integration, no order placement, no leverage.
- Never share your Telegram bot token or AI API keys.
- Never commit `.env`.
- Do not rely on an alert without checking current price, timestamp, liquidity, costs, and relevant news.
- Before any future broker integration, check current SEBI/exchange rules and the broker's official API terms.
