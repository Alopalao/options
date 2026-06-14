import yfinance as yf
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURATION ---
# Set these thresholds based on your risk tolerance
MIN_TOTAL_PREMIUM = 250000    # Minimum $250,000 on the line
MIN_OI_THRESHOLD = 5000       # Minimum 5,000 contracts for "High OI"
# ---------------------

def get_nasdaq_tickers():
    """Fetches the official list of Nasdaq-listed stocks."""
    print("Fetching updated ticker list from Nasdaq...")
    url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
    try:
        #raise Exception("Simulated error for testing")
        df = pd.read_csv(url, sep="|")
        # Filter for standard stocks (remove headers/footers)
        tickers = df[df['File Creation Time'].isna()]['Symbol'].tolist()
        # Clean: only letters, length <= 4
        return [t for t in tickers if t.isalpha() and len(t) <= 4]
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return ["PTEN", "AAPL", "GOOGL"] # Fallback test list

def analyze_ticker(symbol):
    """Checks a specific ticker for unusual option activity."""
    plays = []
    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return plays

        # Only check the next 3 months to avoid over-scraping
        ### First 3 months is not a good idea since I want to be from august to december.
        ### This means after the first 3 expiration dates for some stocks
        ### Better to check by date rather than by number of date in list.
        for date in expirations[:3]:
            opt_chain = ticker.option_chain(date)
            calls = opt_chain.calls
            if calls.empty:
                continue

            # Calculate total dollar value on the line
            # Open Interest * Price * 100 shares per contract
            calls = calls.dropna(subset=['lastPrice', 'openInterest'])
            #print(f"CALLS: \n{calls}")
            calls['total_oi_premium'] = calls['openInterest'] * calls['lastPrice'] * 100
            calls['total_vol_premium'] = calls['volume'] * calls['lastPrice'] * 100

            # CRITERIA:
            # 1. "Hidden Whale": Massive established Open Interest (accumulated position)
            # 2. "Active Whale": Massive Volume today (fresh institutional entry)
            is_hidden_whale = (calls['total_oi_premium'] > 1000000) & (calls['openInterest'] > MIN_OI_THRESHOLD)
            is_active_whale = (calls['total_vol_premium'] > MIN_TOTAL_PREMIUM)

            unusual_calls = calls[is_hidden_whale | is_active_whale]

            for _, row in unusual_calls.iterrows():
                plays.append({
                    'Ticker': symbol,
                    'Expiration': date,
                    'Strike': row['strike'],
                    'LastPrice': row['lastPrice'],
                    'Volume': row['volume'],
                    'OI': row['openInterest'],
                    'TotalValue': row['total_oi_premium']
                })
        return plays
    except Exception:
        return []

def main():
    tickers = get_nasdaq_tickers()
    results = []
    
    # Optional: Limit the list for the first test run
    # tickers = tickers[:50] 

    print(f"Starting scan of {len(tickers)} stocks...")
    
    for i, symbol in enumerate(tickers):
        if i % 10 == 0:
            print(f"Progress: {i}/{len(tickers)} processed. Found {len(results)} plays so far.")
            
        found_plays = analyze_ticker(symbol)
        if found_plays:
            results.extend(found_plays)
        
        # Be polite to the server
        time.sleep(0.5)

    if results:
        df = pd.DataFrame(results)
        filename = f"whale_report_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        print(f"Done! Found {len(results)} potential plays. Saved to {filename}")
    else:
        print("No matches found.")

if __name__ == "__main__":
    main()