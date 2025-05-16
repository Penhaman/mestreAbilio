import telebot
import requests
import pandas as pd
import ta
import schedule
import threading
import time
import os

# Variáveis de ambiente
BOT_TOKEN = os.getenv('BOT_TOKEN')
GRUPO_CHAT_ID = os.getenv('GRUPO_CHAT_ID')

if not BOT_TOKEN or not GRUPO_CHAT_ID:
    print("Erro: BOT_TOKEN ou GRUPO_CHAT_ID não configurados!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
sinais_ativos = []

def obter_top_200_coingecko():
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 200, 'page': 1, 'sparkline': False}
    response = requests.get(url, params=params)
    data = response.json()
    return [f"{coin['symbol'].upper()}USDT" for coin in data if 'symbol' in coin]

def limpar_dados(df):
    for col in ['close', 'open', 'high', 'low', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.fillna(0)

def get_klines(symbol, interval, limit=100):
    url = f'https://api.binance.com/api/v1/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    response = requests.get(url, params=params)
    data = response.json()
    if not data or 'code' in data:
        return pd.DataFrame()
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                                     'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume',
                                     'taker_buy_quote_asset_volume', 'ignore'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    return limpar_dados(df)

def detectar_oco(df):
    closes = df['close']
    if len(closes) < 10: return False
    a, b, c = closes.iloc[-7], closes.iloc[-5], closes.iloc[-3]
    return b > a and b > c and a > c

def detectar_ocoi(df):
    closes = df['close']
    if len(closes) < 10: return False
    a, b, c = closes.iloc[-7], closes.iloc[-5], closes.iloc[-3]
    return b < a and b < c and a < c

def verificar_padrao_candle(df):
    sinal = ""
    if df['close'].iloc[-1] < df['open'].iloc[-1] and (df['high'].iloc[-1] - df['close'].iloc[-1]) > 2 * (df['close'].iloc[-1] - df['open'].iloc[-1]):
        sinal += "Martelo invertido detetado ⚠️\n"
    if df['close'].iloc[-1] > df['open'].iloc[-1] and (df['close'].iloc[-1] - df['low'].iloc[-1]) > 2 * (df['open'].iloc[-1] - df['close'].iloc[-1]):
        sinal += "Martelo detetado 🛑\n"
    if abs(df['close'].iloc[-1] - df['open'].iloc[-1]) <= 0.1 * (df['high'].iloc[-1] - df['low'].iloc[-1]):
        sinal += "Doji detetado 🔲\n"
    if df['close'].iloc[-1] > df['open'].iloc[-1] and df['close'].iloc[-2] < df['open'].iloc[-2] and df['close'].iloc[-1] > df['open'].iloc[-2] and df['open'].iloc[-1] < df['close'].iloc[-2]:
        sinal += "Engolfo de Alta detetado 🟢\n"
    if df['close'].iloc[-1] < df['open'].iloc[-1] and df['close'].iloc[-2] > df['open'].iloc[-2] and df['close'].iloc[-1] < df['open'].iloc[-2] and df['open'].iloc[-1] > df['close'].iloc[-2]:
        sinal += "Engolfo de Baixa detetado 🔴\n"
    if df['close'].iloc[-1] > df['open'].iloc[-1] and df['close'].iloc[-2] < df['open'].iloc[-2] and df['close'].iloc[-3] < df['open'].iloc[-3]:
        sinal += "Morning Star detetada 🌅\n"
    if df['close'].iloc[-1] < df['open'].iloc[-1] and df['close'].iloc[-2] > df['open'].iloc[-2] and df['close'].iloc[-3] > df['open'].iloc[-3]:
        sinal += "Evening Star detetada 🌙\n"
    return sinal

def analisar_sinal(df, symbol, interval):
    df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['MA50'] = ta.trend.sma_indicator(df['close'], window=50)
    df['MA200'] = ta.trend.sma_indicator(df['close'], window=200)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    sinal = f"📊 Sinal para {symbol} ({interval}):\n"

    sinal += "• Tendência: Long 📈\n" if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1] else "• Tendência: Short 📉\n"
    rsi = df['RSI'].iloc[-1]
    sinal += f"• RSI {rsi:.1f}: Sobrevendido 🟢\n" if rsi < 30 else (f"• RSI {rsi:.1f}: Sobrecomprado 🔴\n" if rsi > 70 else "")
    if df['volume'].iloc[-1] > df['volume'].mean():
        sinal += "• Volume acima da média 📊\n"
    if df['MA50'].iloc[-2] < df['MA200'].iloc[-2] and df['MA50'].iloc[-1] > df['MA200'].iloc[-1]:
        sinal += "• Golden Cross detetado ✨\n"
    elif df['MA50'].iloc[-2] > df['MA200'].iloc[-2] and df['MA50'].iloc[-1] < df['MA200'].iloc[-1]:
        sinal += "• Death Cross detetado ⚰️\n"
    sinal += verificar_padrao_candle(df)
    if detectar_oco(df): sinal += "• Padrão OCO detetado 🟥\n"
    if detectar_ocoi(df): sinal += "• Padrão OCOI detetado 🟩\n"
    return sinal.strip()

def obter_fear_and_greed():
    try:
        res = requests.get("https://api.alternative.me/fng/?limit=1")
        data = res.json()
        valor = data['data'][0]['value']
        classificacao = data['data'][0]['value_classification']
        return f"\n\n📉 Fear & Greed Index: {valor} ({classificacao})"
    except:
        return ""

def tarefa_agendada():
    print("⏰ Analisando sinais agendados...")
    symbols = obter_top_200_coingecko()
    intervals = ["1d", "1w"]
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval)
            if df.empty: continue
            sinal = analisar_sinal(df, symbol, interval)
            if sinal:
                bot.send_message(GRUPO_CHAT_ID, sinal)

def verificar_agendamentos():
    while True:
        schedule.run_pending()
        time.sleep(10)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "✅ Bot ativo!")

@bot.message_handler(commands=['siga'])
def siga(message):
    try:
        params = message.text.split()[1:]
        if len(params) != 2:
            bot.reply_to(message, "Exemplo: /siga BTCUSDT 1d")
            return
        symbol, interval = params
        df = get_klines(symbol, interval)
        if df.empty:
            bot.reply_to(message, f"Erro ao obter dados para {symbol}.")
            return
        sinal = analisar_sinal(df, symbol, interval)
        bot.reply_to(message, sinal or "Sem sinal identificado.")
    except Exception as e:
        bot.reply_to(message, f"Erro: {str(e)}")

@bot.message_handler(commands=['sinais'])
def sinais_handler(message):
    bot.reply_to(message, "⏳ Buscando sinais...")
    symbols = obter_top_200_coingecko()
    intervals = ["1d", "1w"]
    enviados = 0
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval)
            if df.empty: continue
            sinal = analisar_sinal(df, symbol, interval)
            if sinal:
                bot.send_message(GRUPO_CHAT_ID, sinal)
                enviados += 1
    bot.reply_to(message, f"✅ {enviados} sinais enviados.{obter_fear_and_greed()}")

schedule.every().day.at("08:00").do(tarefa_agendada)
schedule.every(30).minutes.do(tarefa_agendada)

threading.Thread(target=verificar_agendamentos).start()

bot.polling(none_stop=True)
