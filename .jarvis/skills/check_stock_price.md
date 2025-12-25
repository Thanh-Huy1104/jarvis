---
name: check-stock-price
description: Retrieves the latest stock price for a given symbol using Yahoo Finance.
version: 1.0.0
tools: [python]
dependencies: [yfinance]
---

# Check Stock Price

## Description
This skill retrieves the latest stock price for a given ticker symbol using the Yahoo Finance API (`yfinance`). It handles both standard US tickers (e.g., 'AAPL') and regional tickers (e.g., 'SHOP.TO'). It prioritizes `fast_info` for speed but includes a fallback to 1-day history if immediate data is unavailable.

## When to Use
- When the user asks for the current price of a stock.
- When checking market status for a specific company.
- Example queries: "What is the price of Nvidia?", "Check stock AAPL".

## How to Use
Call `check_stock_price(symbol)` with the ticker symbol as a string.

```python
price_info = check_stock_price("MSFT")
print(price_info)
```

## Dependencies
- `yfinance`: For fetching market data.

## Code

```python
import yfinance as yf

def check_stock_price(symbol):
    """
    Retrieves the latest stock price for a given symbol using Yahoo Finance.
    Handles standard tickers (e.g., 'AAPL', 'NVDA') and regional ones (e.g., 'SHOP.TO').
    """
    try:
        print(f"Fetching data for: {symbol}...")
        ticker = yf.Ticker(symbol)
        
        # 'fast_info' often contains the most recent price (last_price)
        # significantly faster than fetching history for just the current price
        price = ticker.fast_info.last_price
        
        # Fallback if fast_info is unavailable (e.g., some indices)
        if price is None:
            history = ticker.history(period='1d')
            if not history.empty:
                price = history['Close'].iloc[-1]
        
        if price:
            output = f"The current price of {symbol.upper()} is ${price:,.2f}"
            print(output)
            return output
        else:
            return f"Could not find price data for '{symbol}'."

    except Exception as e:
        return f"Error checking stock price: {str(e)}"
```

## Troubleshooting
- **Symbol Not Found**: Ensure the ticker is correct. For non-US stocks, append the exchange suffix (e.g., `.TO` for Toronto, `.L` for London).
- **Network Error**: Yahoo Finance API may occasionally rate limit or fail. Retry after a moment.