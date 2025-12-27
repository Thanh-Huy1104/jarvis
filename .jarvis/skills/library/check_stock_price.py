import yfinance as yf

def check_stock_price(symbol: str) -> str:
    """
    Retrieves the latest stock price for a given symbol using Yahoo Finance.
    Handles standard tickers (e.g., 'AAPL', 'NVDA') and regional ones (e.g., 'SHOP.TO').
    """
    try:
        print(f"Fetching data for: {symbol}...")
        ticker = yf.Ticker(symbol)
        
        # 'fast_info' often contains the most recent price (last_price)
        price = ticker.fast_info.last_price
        
        # Fallback if fast_info is unavailable
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
