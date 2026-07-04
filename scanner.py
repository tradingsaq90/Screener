import io
import pandas as pd
import requests
import urllib3
import yfinance as yf
import pandas_ta as ta
import concurrent.futures

# Suppress insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Module-level dictionary to cache company names mapped from Wikipedia
TICKER_COMPANY_MAP = {}

def fetch_sp500_tickers():
    """
    Scrapes the S&P 500 tickers from Wikipedia, replacing dots with hyphens 
    to be fully compatible with yfinance.
    """
    global TICKER_COMPANY_MAP
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]
        tickers = []
        for _, row in df.iterrows():
            sym = row['Symbol'].replace('.', '-')
            TICKER_COMPANY_MAP[sym] = row['Security']
            tickers.append(sym)
        return tickers
    except Exception as e:
        print(f"Error scraping S&P 500 tickers from Wikipedia: {e}")
        # Return fallback high-liquidity stock list
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "LLY", "AVGO", "V", "JPM", "UNH", "XOM", "TSM"]

def get_custom_session():
    """
    Returns a requests.Session pre-configured to bypass SSL verification 
    and identify as a modern web browser to avoid 403 / verification errors.
    """
    session = requests.Session()
    session.verify = False
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    return session

def process_single_stock(ticker, ticker_data, min_price, rsi_min, rsi_max, volume_min, use_avg_volume):
    """
    Calculates technical indicators for a single stock's historical DataFrame 
    and checks if it matches all filtering conditions.
    """
    try:
        df = ticker_data.dropna(subset=['Close'])
        if len(df) < 20:  # Need at least 20 periods for SMA(20)
            return None, None
        
        # Create copies of columns to avoid setting with copy warning
        df = df.copy()
        
        # Technical calculations using pandas_ta
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['RSI_14'] = ta.rsi(df['Close'], length=14)
        df['Vol_Avg_10'] = ta.sma(df['Volume'], length=10)
        
        # Calculate Bollinger Bands (20, 2)
        bb = ta.bbands(df['Close'], length=20, std=2.0)
        if bb is not None and not bb.empty:
            df['BB_Lower'] = bb.iloc[:, 0]
            df['BB_Upper'] = bb.iloc[:, 2]
        
        if len(df) < 2 or pd.isna(df['SMA_20'].iloc[-1]) or pd.isna(df['RSI_14'].iloc[-1]):
            return None, None
            
        curr_close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2])
        curr_sma20 = float(df['SMA_20'].iloc[-1])
        curr_rsi14 = float(df['RSI_14'].iloc[-1])
        curr_volume = float(df['Volume'].iloc[-1])
        avg_volume10 = float(df['Vol_Avg_10'].iloc[-1]) if pd.notna(df['Vol_Avg_10'].iloc[-1]) else 0.0
        
        # Primary Filtering Conditions Evaluation:
        # 1. Price vs Moving Average: Close > SMA(20)
        cond_price_sma = curr_close > curr_sma20
        
        # 2. RSI Range: rsi_min <= RSI(14) < rsi_max
        cond_rsi = (curr_rsi14 >= rsi_min) and (curr_rsi14 < rsi_max)
        
        # 3. Significant Trading Volume: Average 10d Volume > threshold OR Current Volume > threshold
        if use_avg_volume:
            cond_volume = avg_volume10 > volume_min
        else:
            cond_volume = curr_volume > volume_min
            
        # 4. Minimum Share Price Threshold: Close > min_price
        cond_price_threshold = curr_close > min_price
        
        # 5. Upward Price Momentum: Close > Prev Close
        cond_momentum = curr_close > prev_close
        
        # Evaluation check
        passed = cond_price_sma and cond_rsi and cond_volume and cond_price_threshold and cond_momentum
        
        if passed:
            result_item = {
                "Ticker": ticker,
                "Company": TICKER_COMPANY_MAP.get(ticker, ticker),
                "Price": curr_close,
                "SMA(20)": curr_sma20,
                "RSI(14)": curr_rsi14,
                "Volume": curr_volume,
                "10d Avg Volume": avg_volume10,
                "Daily Change %": ((curr_close - prev_close) / prev_close) * 100
            }
            return result_item, df
            
    except Exception as e:
        print(f"Error processing ticker {ticker}: {e}")
        
    return None, None

def scan_stocks(tickers, min_price=30.0, rsi_min=55.0, rsi_max=65.0, volume_min=5000000.0, use_avg_volume=True, timeframe="Daily", progress_callback=None):
    """
    Downloads historical data for all tickers, calculates indicators, 
    and filters stocks based on screener criteria and selected timeframe (Daily, Weekly, Monthly).
    """
    session = get_custom_session()
    
    # Map timeframe to yfinance period and interval parameters
    timeframe_map = {
        "Daily": {"interval": "1d", "period": "3mo"},
        "Weekly": {"interval": "1wk", "period": "2y"},
        "Monthly": {"interval": "1mo", "period": "5y"}
    }
    config = timeframe_map.get(timeframe, timeframe_map["Daily"])
    interval = config["interval"]
    period = config["period"]
    
    print(f"Downloading {timeframe} data (period={period}, interval={interval}) for {len(tickers)} stocks...")
    try:
        data = yf.download(
            tickers, 
            period=period, 
            interval=interval, 
            group_by='ticker', 
            session=session, 
            threads=True,
            progress=False
        )
    except Exception as e:
        print(f"Fatal error during yfinance batch download: {e}")
        return pd.DataFrame(), {}, tickers

    passed_stocks = []
    passed_dfs = {}
    failed_tickers = []
    
    # Process each ticker
    total = len(tickers)
    for idx, ticker in enumerate(tickers):
        if progress_callback:
            progress_callback(idx / total, f"Evaluating {ticker} ({idx+1}/{total})...")
            
        try:
            # Handle MultiIndex vs Single level index download return formats
            if isinstance(data.columns, pd.MultiIndex):
                has_data = ticker in data.columns.levels[0]
                ticker_df = data[ticker] if has_data else None
            else:
                ticker_df = data
                has_data = not ticker_df.empty
                
            if not has_data or ticker_df is None or ticker_df.empty:
                failed_tickers.append(ticker)
                continue
                
            result_item, processed_df = process_single_stock(
                ticker=ticker,
                ticker_data=ticker_df,
                min_price=min_price,
                rsi_min=rsi_min,
                rsi_max=rsi_max,
                volume_min=volume_min,
                use_avg_volume=use_avg_volume
            )
            
            if result_item:
                passed_stocks.append(result_item)
                passed_dfs[ticker] = processed_df
                
        except Exception as e:
            print(f"Error processing {ticker} in batch scan loop: {e}")
            failed_tickers.append(ticker)

    if progress_callback:
        progress_callback(1.0, f"Scanning completed. Found {len(passed_stocks)} stocks.")

    # Convert results to DataFrame
    passed_df = pd.DataFrame(passed_stocks)
    if not passed_df.empty:
        # Reorder columns for visual clarity
        passed_df = passed_df[[
            "Ticker", "Company", "Price", "Daily Change %", "RSI(14)", "SMA(20)", "Volume", "10d Avg Volume"
        ]]
        
    return passed_df, passed_dfs, failed_tickers
