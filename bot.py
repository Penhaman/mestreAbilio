import os
import requests
import pandas as pd
import ta
import telebot
import schedule
import time
from flask import Flask, request

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
GRUPO_CHAT_ID = os.getenv('GRUPO_CHAT_ID')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

def obter_top_200_coingecko():
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 200,
        'page': 1,
        'sparkline': False
    }
    response = requests.get(url, params=params)
    data = response.json()
    return [coin['symbol'].upper() + 'USDT' for coin in data]

def limpar_dados(df):
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.fillna(0)

def get_klines(symbol, interval, limit=100):
    url = f'https://api.binance.com/api/v1/klines'
    params = {'symbol': symbol.upper(), 'interval': interval, 'limit': limit}
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
        sinal += "Engolfo de baixa detetado 🔴\n"
    return sinal

def analisar_sinal(df, symbol, interval):
    df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    
    sinal = ""
    if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1]:
        sinal += f"📈 Sinal Long para {symbol} ({interval})\n"
    else:
        sinal += f"📉 Sinal Short para {symbol} ({interval})\n"

    if df['RSI'].iloc[-1] < 30:
        sinal += "RSI indica sobrevenda 🟢\n"
    elif df['RSI'].iloc[-1] > 70:
        sinal += "RSI indica sobrecompra 🔴\n"

    if df['volume'].iloc[-1] > df['volume'].mean():
        sinal += "Volume acima da média 📊\n"

    padroes = verificar_padrao_candle(df)
    if padroes:
        sinal += padroes

    return sinal.strip() if sinal else None

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Bem-vindo! Use /help para ver os comandos disponíveis.")

@bot.message_handler(commands=['help'])
def help(message):
    texto = (
        "📘 Comandos disponíveis:\n"
        "/start - Inicia o bot\n"
        "/help - Mostra esta mensagem\n"
        "/siga [PAR] [INTERVALO] - Verifica sinal para um par (ex: /siga BTCUSDT 1d)\n"
        "/sinais - Executa varredura em todos os pares do Top 200 no intervalo 1d\n"
    )
    bot.reply_to(message, texto)

@bot.message_handler(commands=['siga'])
def siga(message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "Uso correto: /siga BTCUSDT 1d")
            return

        symbol, interval = parts[1].upper(), parts[2]
        df = get_klines(symbol, interval, 100)
        if df.empty:
            bot.reply_to(message, f"Erro ao obter dados para {symbol}")
            return

        sinal = analisar_sinal(df, symbol, interval)
        if sinal:
            bot.reply_to(message, f"Sinal para {symbol} ({interval}):\n{sinal}")
        else:
            bot.reply_to(message, f"Sem sinal para {symbol} ({interval}).")
    except Exception as e:
        bot.reply_to(message, f"Erro: {e}")

@bot.message_handler(commands=['sinais'])
def sinais(message):
    bot.reply_to(message, "🔎 A verificar sinais no Top 200 (1d)...")
    symbols = obter_top_200_coingecko()
    for symbol in symbols:
        df = get_klines(symbol, "1d", 100)
        if df.empty:
            continue
        sinal = analisar_sinal(df, symbol, "1d")
        if sinal:
            bot.send_message(message.chat.id, f"{symbol} (1d):\n{sinal}")

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

@app.route('/')
def index():
    return 'Bot ativo!'

def configurar_webhook():
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f'{WEBHOOK_URL}/{BOT_TOKEN}')

if __name__ == '__main__':
    configurar_webhook()
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
