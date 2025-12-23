# Check Stock Price

Retrieves the latest stock price for a given symbol using Yahoo Finance.

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

# Example Usage
check_stock_price("NVDA")      # US Stock
check_stock_price("SHOP.TO")   # Canadian Stock (TSX)
```
