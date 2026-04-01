from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import numpy as np
from binance.client import Client
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 🚨 API KEYS (මෙහි ඔයාගේ Keys දෙක දාන්න, හැබැයි GitHub එකට upload කරන්න එපා!)
API_KEY = 'DoPIZohf4yWP0drsHtAq9s916PDiG0dKVi3w3wXROqtRViBExd9DBfC6V9jhNByW'
API_SECRET = 'J3qAhWHXFAWrpXv7zdCYoQbIHPuiwGmleWLbPPWbNhNfg84zZ0oOzWXZ9w2riLnO'

client = Client(API_KEY, API_SECRET)

# =====================================================================
# 🗄️ DATABASE SETUP
# =====================================================================
def init_db():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    
    # 1. Login system table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    
    # 2. Trade tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracked_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            entry_price REAL,
            tp_price REAL,
            sl_price REAL,
            status TEXT,
            created_at TEXT
        )
    ''')
    
    # Test user (Username: alex / Password: 123)
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("alex", "123"))
    except sqlite3.IntegrityError:
        pass 
        
    conn.commit()
    conn.close()

init_db()

def get_candles(symbol, interval, limit=200):
    try:
        valid_intervals = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w']
        if interval not in valid_intervals:
            interval = '15m'
            
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=['time','open','high','low','close','vol','ct','qv','nt','tb','tg','i'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        return df
    except Exception as e:
        print(f"Candle error for {symbol}: {e}")
        return None

# =====================================================================
# 🧠 REAL STABLE ACCURACY ALGORITHM
# =====================================================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_coin(df):
    try:
        if len(df) < 50:
            return None
            
        current_price = df['close'].iloc[-1] # Live price
        close_price = df['close'].iloc[-2]   # Previous close
        
        df['sma50'] = df['close'].rolling(window=50).mean()
        sma_val = df['sma50'].iloc[-2]
        is_uptrend = close_price > sma_val
        
        df['rsi'] = calculate_rsi(df['close'], period=14)
        current_rsi = df['rsi'].iloc[-2]
        
        volatility = (df['high'] - df['low']).rolling(window=14).mean().iloc[-2]
        
        accuracy = 50 
        trend = "SIDEWAYS"
        
        # BUY Signal
        if is_uptrend and current_rsi < 45:
            trend = "UPTREND"
            rsi_factor = (45 - current_rsi) * 1.5 
            trend_strength = ((close_price - sma_val) / sma_val) * 100 
            
            accuracy = 65 + rsi_factor + trend_strength
            
            entry = current_price
            tp1 = round(entry + (volatility * 1.5), 4)
            tp2 = round(entry + (volatility * 2.5), 4)
            tp3 = round(entry + (volatility * 3.5), 4)
            sl = round(entry - (volatility * 2.0), 4)
            
        # SELL Signal
        elif not is_uptrend and current_rsi > 55:
            trend = "DOWNTREND"
            rsi_factor = (current_rsi - 55) * 1.5 
            trend_strength = ((sma_val - close_price) / sma_val) * 100
            
            accuracy = 65 + rsi_factor + trend_strength
            
            entry = current_price
            tp1 = round(entry - (volatility * 1.5), 4)
            tp2 = round(entry - (volatility * 2.5), 4)
            tp3 = round(entry - (volatility * 3.5), 4)
            sl = round(entry + (volatility * 2.0), 4)
            
        else:
            trend = "SIDEWAYS"
            entry = current_price
            tp1 = tp2 = tp3 = sl = current_price
            accuracy = 40

        accuracy = min(int(accuracy), 98)
        
        return {
            "price": current_price,
            "trend": trend,
            "entry": entry,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
            "accuracy": accuracy
        }
    except Exception as e:
        print(f"Algorithm error: {e}")
        return None

# =====================================================================
# 🔐 AUTHENTICATION ENDPOINTS
# =====================================================================
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify({"status": "success", "message": "Login successful!"})
    else:
        return jsonify({"status": "error", "message": "Invalid username or password!"})

# =====================================================================
# 📌 TRADE TRACKING ENDPOINTS
# =====================================================================
@app.route('/book-trade', methods=['POST'])
def book_trade():
    data = request.json
    symbol = data.get('symbol').upper().replace("/USDT", "").replace("USDT", "")
    entry = float(data.get('entry'))
    tp = float(data.get('tp'))
    sl = float(data.get('sl'))
    
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tracked_trades (symbol, entry_price, tp_price, sl_price, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (symbol, entry, tp, sl, 'ON-GOING', datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return jsonify({"message": f"Trade for {symbol} booked successfully!"})

@app.route('/my-trades')
def get_my_trades():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tracked_trades ORDER BY id DESC')
    trades = cursor.fetchall()
    conn.close() 
    
    results = []
    for t in trades:
        db_id, symbol, entry, tp, sl, status, created_at = t
        current_price = entry
        
        if status == "ON-GOING":
            df = get_candles(symbol + "USDT", '15m', limit=5)
            if df is not None:
                current_price = df['close'].iloc[-1]
                
                # 🛡️ මෙතනදී අපි බලනවා trade එක Buy එකක්ද Sell එකක්ද කියලා.
                # TP එක Entry එකට වඩා වැඩියි නම් ඒක UPTREND (Buy) trade එකක්.
                is_buy_trade = tp > entry
                
                if is_buy_trade:
                    # Buy trade එකකදී Conditions
                    if current_price >= tp:
                        status = "TP HIT"
                        update_status(db_id, "TP HIT")
                    elif current_price <= sl:
                        status = "SL HIT"
                        update_status(db_id, "SL HIT")
                else:
                    # Sell (Downtrend) trade එකකදී Conditions
                    if current_price <= tp:
                        status = "TP HIT"
                        update_status(db_id, "TP HIT")
                    elif current_price >= sl:
                        status = "SL HIT"
                        update_status(db_id, "SL HIT")
                    
        results.append({
            "id": db_id, "symbol": symbol, "entry": entry,
            "tp": tp, "sl": sl, "status": status, "time": created_at,
            "current_price": current_price
        })
    return jsonify({"my_trades": results})

def update_status(trade_id, new_status):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE tracked_trades SET status = ? WHERE id = ?', (new_status, trade_id))
    conn.commit()
    conn.close()

# =====================================================================
# 🔍 SEARCH COIN
# =====================================================================
@app.route('/search-coin')
def search_coin():
    coin = request.args.get('symbol').upper().strip()
    tf = request.args.get('tf')
    
    if tf in ["50m", "45m"]: tf = "30m" 
    if not coin.endswith('USDT'): coin = coin + 'USDT'
        
    try:
        df = get_candles(coin, tf, limit=100)
        if df is None: return jsonify({"error": "No data found"}), 404
            
        analysis = analyze_coin(df)
        if analysis is None: return jsonify({"error": "Analysis failed"}), 404
            
        return jsonify({
            "symbol": coin.replace("USDT", ""),
            "price": analysis["price"],
            "trend": analysis["trend"],
            "entry": analysis["entry"],
            "tp1": analysis["tp1"], "tp2": analysis["tp2"], "tp3": analysis["tp3"],
            "sl": analysis["sl"],
            "accuracy": analysis["accuracy"]
        })
    except Exception as e:
        print(e)
        return jsonify({"error": "Coin not found"}), 404

# =====================================================================
# 📊 MARKET SCAN
# =====================================================================
@app.route('/get-all-data')
def get_all_data():
    tf = request.args.get('tf')
    if tf in ["50m", "45m"]: tf = "30m"
        
    best_coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT"]
    signals = []
    
    for coin in best_coins:
        try:
            df = get_candles(coin, tf, limit=100)
            if df is None: continue
                
            analysis = analyze_coin(df)
            if analysis is None: continue
                
            if analysis["accuracy"] < 75 or analysis["trend"] == "SIDEWAYS":
                continue
                
            signals.append({
                "symbol": coin.replace("USDT", ""),
                "price": analysis["price"],
                "trend": analysis["trend"],
                "entry": analysis["entry"],
                "tp1": analysis["tp1"], "tp2": analysis["tp2"], "tp3": analysis["tp3"],
                "sl": analysis["sl"],
                "accuracy": analysis["accuracy"]
            })
        except:
            continue
            
    return jsonify({"signals": signals, "has_long_term": True})

# =====================================================================
# 💰 LONG TERM SCAN
# =====================================================================
@app.route('/get-long-term')
def get_long_term():
    signals = []
    
    try:
        exchange_info = client.get_exchange_info()
        all_coins = [s['symbol'] for s in exchange_info['symbols'] if s['symbol'].endswith('USDT') and s['status'] == 'TRADING']
        
        for coin in all_coins[:150]: 
            try:
                df = get_candles(coin, '1w', limit=100)
                if df is None or len(df) < 50: 
                    continue
                    
                current_price = df['close'].iloc[-1]
                
                df['sma50'] = df['close'].rolling(window=50).mean()
                is_strong_uptrend = current_price > df['sma50'].iloc[-1]
                
                df['rsi'] = calculate_rsi(df['close'], period=14)
                current_rsi = df['rsi'].iloc[-1]
                
                volatility = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]
                
                if is_strong_uptrend and 30 < current_rsi < 50:
                    
                    accuracy = 92 if current_rsi < 40 else 85
                    
                    entry = current_price
                    tp_long = round(entry + (volatility * 4.0), 4)
                    sl_long = round(entry - (volatility * 2.0), 4)
                    
                    profit_pct = round(((tp_long - entry) / entry) * 100, 1)
                    
                    signals.append({
                        "symbol": coin.replace("USDT", ""),
                        "price": current_price,
                        "entry": entry,
                        "tp_long": tp_long,
                        "sl_long": sl_long,
                        "accuracy": accuracy,
                        "profit_percentage": profit_pct,
                        "estimated_duration": "1-3 Months"
                    })
            except:
                continue
                
    except Exception as e:
        print(f"Error fetching all coins: {e}")
        
    signals.sort(key=lambda x: x['accuracy'], reverse=True)
    return jsonify({"signals": signals})

import os

if __name__ == '__main__':
    # Render එකෙන් දෙන port එක ගන්නවා, නැත්නම් default 5000 ගන්නවා
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)