# Story 10.6: Stock Market Analysis Tool

Status: done

## Story

As a **user**,
I want **Annie to analyze stocks and provide market insights**,
So that **I can make informed investment decisions**.

*Moved from Epic 4 Story 4.2*

## Acceptance Criteria

**AC #1:** Given `get_stock_data` MCP tool, when called with ticker, then tool fetches real-time price data via Yahoo Finance and returns structured analysis including current_price, change_1d, change_1d_pct, 52_week_high, 52_week_low, market_cap, pe_ratio, volume, avg_volume

**AC #2:** Given stock analysis, when technical data requested, then tool returns RSI (Relative Strength Index), moving averages (50-day, 200-day), trend direction (bullish/bearish/neutral), and volume analysis (above/below average)

**AC #3:** Given `get_stock_history` tool, when called with ticker and period, then returns historical prices for 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y including open, high, low, close, volume per period

**AC #4:** Given user asks "How is Apple doing?", then Annie calls `get_stock_data` with ticker "AAPL" and responds with clear market analysis

**AC #5:** Given invalid ticker or API failure, then tool returns clear error message and Annie responds: "I couldn't find data for that ticker. Please check the symbol and try again."

## Tasks / Subtasks

- [x] **Task 1: Add yfinance dependency** (AC: #1, #3)
  - [x] Add `yfinance>=0.2.48` to `mcp_server/requirements.txt`
  - [x] Rebuild Docker container

- [x] **Task 2: Create get_stock_data MCP tool** (AC: #1, #2, #4, #5)
  - [x] Create `get_stock_data_tool_handler()` in `mcp_server/tools.py`
  - [x] Fetch real-time data via `yfinance.Ticker(ticker).info`
  - [x] Calculate technical indicators (RSI, moving averages)
  - [x] Return structured analysis object
  - [x] Add error handling for invalid tickers
  - [x] Add Langfuse tracing with `@observe` decorators

- [x] **Task 3: Create get_stock_history MCP tool** (AC: #3, #5)
  - [x] Create `get_stock_history_tool_handler()` in `mcp_server/tools.py`
  - [x] Support periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y
  - [x] Return OHLCV data (open, high, low, close, volume)
  - [x] Add error handling for invalid tickers/periods

- [x] **Task 4: Register tools in MCP server** (AC: #1, #3)
  - [x] Register `get_stock_data_tool` in `mcp_server/server.py`
  - [x] Register `get_stock_history_tool` in `mcp_server/server.py`

- [ ] **Task 5: Testing** (AC: #1, #2, #3, #4, #5)
  - [ ] Test via Telegram: Ask "How is AAPL doing?"
  - [ ] Test via Telegram: Ask "Show me GOOGL price history"
  - [ ] Test invalid ticker handling
  - [ ] Verify Langfuse traces appear

## Dev Notes

### Yahoo Finance Integration

Using `yfinance` library for free, reliable stock data:

```python
import yfinance as yf

ticker = yf.Ticker("AAPL")
info = ticker.info  # Contains all fundamental data
history = ticker.history(period="1mo")  # OHLCV DataFrame
```

### Key Data Points from yfinance

| Field | Description |
|-------|-------------|
| `currentPrice` | Real-time price |
| `previousClose` | Yesterday's close |
| `dayHigh` / `dayLow` | Today's range |
| `fiftyTwoWeekHigh/Low` | 52-week range |
| `marketCap` | Market capitalization |
| `trailingPE` | P/E ratio |
| `volume` | Today's volume |
| `averageVolume` | Average daily volume |

### Technical Indicators

RSI calculation (14-day):
```python
delta = prices.diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
rsi = 100 - (100 / (1 + rs))
```

Moving averages:
```python
ma_50 = prices.rolling(window=50).mean().iloc[-1]
ma_200 = prices.rolling(window=200).mean().iloc[-1]
```

### Caching Strategy

- Cache stock data for 5 minutes to reduce API calls
- Use Redis with key pattern: `stock:{ticker}:info`
- Note: Initial implementation may skip caching for simplicity

### Files to Modify

- **Modify:** `mcp_server/requirements.txt` - Add yfinance
- **Modify:** `mcp_server/tools.py` - Add stock analysis tools
- **Modify:** `mcp_server/server.py` - Register tools

### Example Tool Response

```json
{
  "status": "success",
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "current_price": 175.50,
  "previous_close": 173.20,
  "change_1d": 2.30,
  "change_1d_pct": 1.33,
  "day_high": 176.00,
  "day_low": 172.50,
  "52_week_high": 199.62,
  "52_week_low": 124.17,
  "market_cap": "2.8T",
  "pe_ratio": 28.5,
  "volume": 45000000,
  "avg_volume": 52000000,
  "rsi_14": 55.3,
  "ma_50": 170.25,
  "ma_200": 165.50,
  "trend": "bullish",
  "volume_analysis": "below_average"
}
```

## References

- Epic 10: `docs/epics/epic-10-portfolio-management.md`
- MCP tools pattern: `mcp_server/tools.py`
- Yahoo Finance library: https://github.com/ranaroussi/yfinance
- Previous story: Story 10.3 (Portfolio Context Injection)
