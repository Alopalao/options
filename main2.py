import yfinance as yf
import pandas as pd
import time
from datetime import datetime

month_names = {
    "01": "January",
    "02": "February",
    "03": "March",
    "04": "April",
    "05": "May",
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    "10": "October",
    "11": "November",
    "12": "December",
}

def get_nasdaq_tickers():
    """Fetches the official list of Nasdaq-listed stocks."""
    print("Fetching updated ticker list from Nasdaq...")
    url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
    try:
        #raise Exception("Simulated error for testing") # Uncomment to test error handling
        df = pd.read_csv(url, sep="|")
        # Filter for standard stocks (remove headers/footers)
        tickers = df[(df['Test Issue'] == 'N') & (df['Symbol'].str.len() <= 4)]['Symbol'].dropna().tolist()
        # Clean: only letters, length <= 4
        return tickers
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return ["PTEN", "AAPL", "GOOGL"] # Fallback test list

def filter_out_noisy_months(expirations) -> list:
    dates_by_month = {}
    for date_str in expirations:
        month_key = date_str[:7] # Extracts 'YYYY-MM'
        dates_by_month.setdefault(month_key, []).append(date_str)

    # Keep only the months that have FEWER than 3 expiration dates listed
    clean_expirations = []
    for date_str in expirations:
        month_key = date_str[:7]
        if len(dates_by_month[month_key]) > 1:
            continue
        clean_expirations.append(date_str)
    return clean_expirations

def get_category_by_market_cap(market_cap):
    """Categorizes companies based on market capitalization."""
    if market_cap < 300_000_000:
        return "Micro-Cap"
    elif market_cap < 2_000_000_000:
        return "Small-Cap"
    elif market_cap < 10_000_000_000:
        return "Mid-Cap"
    else:
        return "Large-Cap+"

def get_date_by_name(date) -> str:
    """Converts from 2026-08-21 to 2026-August-21"""
    cur_year = date.split('-')[0]
    cur_day = date.split('-')[2]
    cur_month = date.split('-')[1]
    return f"{cur_year}-{month_names[cur_month]}-{cur_day}"

def get_last_price_stock(ticker: yf.Ticker) -> float:
    """Fetches the last closing price of the stock."""
    try:
        historical_data = ticker.history(period="1d")
        return historical_data['Close'].iloc[-1]
    except Exception as e:
        print(f"Error fetching last price: {e}")
        return None

def analyze_ticker(symbol):
    plays = []
    try:
        ticker = yf.Ticker(symbol)
        
        market_cap = ticker.info.get('marketCap')
        if not market_cap or market_cap == 0:
            return plays
            
        expirations = ticker.options
        if not expirations:
            return plays
        
        stock_price = get_last_price_stock(ticker)
        if stock_price is None or stock_price == "ERROR":
            return plays
        
        clean_expirations = filter_out_noisy_months(expirations)

        for date in clean_expirations:
            opt_chain = ticker.option_chain(date)
            calls = opt_chain.calls
            if calls.empty:
                continue

            # Only track speculative upside: strikes at least 5% above stock price
            calls = calls[calls['strike'] >= (stock_price * 0.9)]
            if calls.empty:
                continue

            # Drop missing essential rows to prevent math errors
            calls = calls.dropna(subset=['lastPrice', 'openInterest', 'volume'])
            
            # Calculate absolute dollar premium values
            calls['total_oi_premium'] = calls['openInterest'] * calls['lastPrice'] * 100
            calls['total_vol_premium'] = calls['volume'] * calls['lastPrice'] * 100

            # Dynamic Thresholds based on company size
            vol_cutoff = max(market_cap * 0.0001, 250_000)
            oi_cutoff = max(market_cap * 0.0004, 1_000_000)

            # Evaluate both rules independently
            is_active_block = (calls['total_vol_premium'] > vol_cutoff) & (calls['volume'] > (calls['openInterest'] * 0.5))
            is_massive_oi = (calls['total_oi_premium'] > oi_cutoff)

            # Filter rows that trigger at least one alert
            unusual_calls = calls[is_active_block | is_massive_oi]

            for index, row in unusual_calls.iterrows():
                # Determine the text label for Excel filtering
                if is_active_block.loc[index] and is_massive_oi.loc[index]:
                    alert_label = "BOTH"
                elif is_massive_oi.loc[index]:
                    alert_label = "Structural Whale (OI)"
                else:
                    alert_label = "Daily Volume Spike"

                plays.append({
                    'Ticker': symbol,
                    'Alert_Type': alert_label,  # <-- Your new Excel filter column
                    'Expiration': get_date_by_name(date),
                    'Strike': row['strike'],
                    'LastPrice': f"${row['lastPrice']:.2f}",
                    'Volume': f"{row['volume']:,.0f}",
                    'OI': f"{row['openInterest']:,.0f}", 
                    'TotalValue $': f"{row['total_oi_premium']:,.2f}",
                    'CashVsCompanyValue': f"{(row['total_oi_premium'] / market_cap) * 100:.4f}%",
                    'CompanySize': get_category_by_market_cap(market_cap),
                    'StockPrice': f"${stock_price:.2f}",
                    'LastDateTrade': row['lastTradeDate']
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
    counter = 0
    for i, symbol in enumerate(tickers):
        counter += 1
        if i % 10 == 0:
            print(f"Progress: {i}/{len(tickers)} processed. Found {len(results)} plays so far.")

        found_plays = analyze_ticker(symbol)
        if found_plays:
            results.extend(found_plays)
        #if counter == 1:
        #    break
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