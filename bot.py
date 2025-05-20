import os
import time
import requests
import pandas as pd
import ta
import telebot
from flask import Flask, request

# ============ Configuração Inicial ============

BOT_TOKEN = os.getenv('BOT_TOKEN')
GRUPO_CHAT_ID = os.getenv('GRUPO_CHAT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Ex: https://worker-production-xxxx.up.railway.app

if not BOT_TOKEN or not GRUPO_CHAT_ID or not WEBHOOK_URL:
    raise Exception("Erro: BOT_TOKEN, GRUPO_CHAT_ID ou WEBHOOK_URL não definidos!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ============ Funções auxiliares ============

def obter_top_200_coingecko():
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 200, 'page': 1}
    response = requests.get(url, params=params)
    data = response.json()
    return [crypto['symbol'].upper() + 'USDT' for crypto in data]

def limpar_dados(df):
    for col in ['close', 'open', 'high', 'low', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.fillna(0)

def get_klines(symbol, interval, limit=100):
    url = f'https://api.binance.com/api/v1/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    response = requests.get(url, params=params)
    data = response.json()
    if not data or isinstance(data, dict):
        return pd.DataFrame()
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume',
                                     'close_time', 'quote_asset_volume', 'number_of_trades',
                                     'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    return limpar_dados(df)

def verificar_padrao_candle(df):
    s = ""
    c, o, h, l = df['close'], df['open'], df['high'], df['low']
    # Martelo Invertido
    if c.iloc[-1] < o.iloc[-1] and (h.iloc[-1] - c.iloc[-1]) > 2 * (c.iloc[-1] - o.iloc[-1]):
        s += "Martelo invertido detetado ⚠️\n"
    # Martelo
    if c.iloc[-1] > o.iloc[-1] and (c.iloc[-1] - l.iloc[-1]) > 2 * (o.iloc[-1] - c.iloc[-1]):
        s += "Martelo detetado 🛑\n"
    # Doji
    if abs(c.iloc[-1] - o.iloc[-1]) <= 0.1 * (h.iloc[-1] - l.iloc[-1]):
        s += "Doji detetado 🔲\n"
    # Engolfos
    if c.iloc[-1] > o.iloc[-1] and c.iloc[-2] < o.iloc[-2] and c.iloc[-1] > o.iloc[-2] and o.iloc[-1] < c.iloc[-2]:
        s += "Engolfo de Alta detetado 🟢\n"
    if c.iloc[-1] < o.iloc[-1] and c.iloc[-2] > o.iloc[-2] and c.iloc[-1] < o.iloc[-2] and o.iloc[-1] > c.iloc[-2]:
        s += "Engolfo de baixa detetado 🔴\n"
    # Estrela da Manhã
    if c.iloc[-3] < o.iloc[-3] and abs(c.iloc[-2] - o.iloc[-2]) < 0.1 and c.iloc[-1] > o.iloc[-1]:
        s += "Morning Star detetada 🌅\n"
    # Estrela da Noite
    if c.iloc[-3] > o.iloc[-3] and abs(c.iloc[-2] - o.iloc[-2]) < 0.1 and c.iloc[-1] < o.iloc[-1]:
        s += "Evening Star detetada 🌙\n"
    return s

def analisar_sinal(df, symbol, interval):
    df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)

    msg = f"Sinal {'Long 📈' if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1] else 'Short 📉'} para {symbol} em {interval}\n"

    rsi = df['RSI'].iloc[-1]
    if rsi < 30:
        msg += "RSI indica sobrevenda 🟢\n"
    elif rsi > 70:
        msg += "RSI indica sobrecompra 🔴\n"

    if df['volume'].iloc[-1] > df['volume'].mean():
        msg += "Alto volume detetado 📊\n"

    padrao = verificar_padrao_candle(df)
    if padrao:
        msg += padrao

    return msg

# ============ Comandos Telegram ============

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    bot.reply_to(msg, "✅ Bot ativo! Use /help para ver os comandos disponíveis.")

@bot.message_handler(commands=["help"])
def cmd_help(msg):
    bot.reply_to(msg, """📘 Comandos disponíveis:
/start - Ativa o bot
/help - Lista os comandos
/sinais - Analisa os principais pares em 1D
/siga PAR INTERVALO - Ex: /siga BTCUSDT 1d""")

@bot.message_handler(commands=["siga"])
def cmd_siga(msg):
    try:
        _, par
