from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import time
import random
import re
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)


# Function to scrape insider trading data
def scrape_insider_data():
    url = "http://insider-monitor.com/insider_stock_purchases.html"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an error for bad status codes
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch data: {e}"}

    soup = BeautifulSoup(response.text, "html.parser")
    data = []
    symbols_list = []  # Maintain order

    table_rows = soup.select("table tr")

    for row in table_rows[1:]:  # Skip header row
        columns = row.find_all("td")
        if len(columns) < 7:  # Ensure enough columns exist
            continue  

        symbol = columns[0].text.strip() or "N/A"
        company = columns[1].text.strip()
        insider_name = columns[2].text.strip()
        trade_type = columns[3].text.strip()
        share_and_price = columns[4].text.strip()
        value = columns[5].text.strip()
        date_and_time = columns[6].text.strip()

        # Convert share_and_price and value to numbers
        try:
        # Extract only the first number from share_and_price before the dollar sign
            share_count_match = re.match(r'([\d,]+)\s*\$|([\d,]+)', share_and_price)
            share_count = int((share_count_match.group(1) or share_count_match.group(2)).replace(",", "")) if share_count_match else 0

        # Extract numeric value from 'value' (removing non-numeric characters except decimal point)
            total_value = float(re.sub(r'[^\d.]', '', value)) if value else 0.0

        # Calculate average price (with 5 decimal places), avoiding division by zero
            avg_price = f"{total_value / share_count:.2f}" if share_count > 0 else "N/A"

        except (ValueError, AttributeError, TypeError, ZeroDivisionError):
            avg_price = "N/A"  # Handle all possible errors gracefully


        data.append({
            "symbol": symbol,
            "company": company,
            "insider_name": insider_name,
            "trade_type": trade_type,
            "share_and_price": share_and_price,
            "value": value,
            "date_and_time": date_and_time,
            "avg_price": avg_price,  # Add calculated average price
        })

        symbols_list.append(symbol)

    # Fetch real-time stock prices
    stock_prices = fetch_stock_prices(tuple(symbols_list))  # Convert list to tuple

    # Attach prices to data
    for entry in data:
        entry["real_time_price"] = stock_prices.get(entry["symbol"], "N/A")

    return data


# Function to validate stock symbols
def is_valid_symbol(symbol):
    # Check if the symbol is valid
    if not symbol or symbol == "N/A" or not isinstance(symbol, str):
        return False
    if re.search(r"[#@/]", symbol):  # Symbols with #, @, / are invalid
        return False
    return True


# Function to fetch a single stock price
def fetch_single_price(symbol):
    try:
        stock = yf.Ticker(symbol)
        # Try to get real-time price
        try:
            price = stock.fast_info.get("last_price", "N/A")
            if price == "N/A":
                # Fallback to previous day's closing price
                data = stock.history(period="1d")
                price = data["Close"].iloc[-1] if not data.empty else "N/A"
        except (KeyError, TypeError, AttributeError):
            price = "N/A"
        return symbol, f"${price:.5f}" if price != "N/A" else "N/A"
    except Exception:
        return symbol, "N/A"


# Function to fetch real-time stock prices (with caching and batch processing)
@lru_cache(maxsize=100)
def fetch_stock_prices(symbols):  # Now accepts a tuple instead of a list
    valid_symbols = [symbol for symbol in symbols if is_valid_symbol(symbol)]
    if not valid_symbols:
        return {}

    results = {}

    # Use ThreadPoolExecutor to fetch prices in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_single_price, symbol) for symbol in valid_symbols]
        for future in futures:
            symbol, price = future.result()
            results[symbol] = price

    # Add a small delay to avoid overwhelming Yahoo Finance
    time.sleep(random.uniform(0.5, 1))

    return results


# API Endpoint to serve the data
@app.route("/api/data", methods=["GET"])
def get_data():
    try:
        data = scrape_insider_data()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
