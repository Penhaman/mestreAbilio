import telebot
import requests
import pandas as pd
import ta
import schedule
import threading
import time
import os

BOT_TOKEN = os.getenv('BOT_TOKEN')
GRUPO_CHAT_ID = os.getenv('GRUPO_CHAT_ID')

if not BOT_TOKEN or not GRUPO_CHAT_ID:
    print("Erro: As variáveis de ambiente BOT_TOKEN ou GRUPO_CHAT_ID não estão configuradas!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Lista global de sinais ativos
sinais_ativos = []

def obter_top_200_coingecko():
    try:
        url = 'https://api.coingecko.com/api/v3/coins/markets'
        params = {'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 200, 'page': 1, 'sparkline': False}
        response = requests.get(url, params=params)
        data = response.json()
        return [f"{coin['symbol'].upper()}USDT" for coin in data]
    except:
        return []

def limpar_dados(df):
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.fillna(0)

def get_klines(symbol, interval, limit=100):
    try:
        url = f'https://api.binance.com/api/v1/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        data = requests.get(url, params=params).json()
        df = pd.DataFrame(data, columns=[
            'time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        return limpar_dados(df)
    except:
        return pd.DataFrame()

def verificar_padrao_candle(df):
    sinal = ""
    c, o, h, l = df['close'], df['open'], df['high'], df['low']
    if c.iloc[-1] < o.iloc[-1] and (h.iloc[-1] - c.iloc[-1]) > 2 * (c.iloc[-1] - o.iloc[-1]):
        sinal += "Martelo invertido ⚠️\n"
    if c.iloc[-1] > o.iloc[-1] and (c.iloc[-1] - l.iloc[-1]) > 2 * (o.iloc[-1] - c.iloc[-1]):
        sinal += "Martelo 🛑\n"
    if abs(c.iloc[-1] - o.iloc[-1]) <= 0.1 * (h.iloc[-1] - l.iloc[-1]):
        sinal += "Doji 🔲\n"
    if c.iloc[-1] > o.iloc[-1] and c.iloc[-2] < o.iloc[-2] and c.iloc[-1] > o.iloc[-2] and o.iloc[-1] < c.iloc[-2]:
        sinal += "Engolfo de Alta 🟢\n"
    if c.iloc[-1] < o.iloc[-1] and c.iloc[-2] > o.iloc[-2] and c.iloc[-1] < o.iloc[-2] and o.iloc[-1] > c.iloc[-2]:
        sinal += "Engolfo de Baixa 🔴\n"
    if c.iloc[-1] > o.iloc[-1] and c.iloc[-2] < o.iloc[-2] and c.iloc[-3] < o.iloc[-3]:
        sinal += "Morning Star 🌅\n"
    if c.iloc[-1] < o.iloc[-1] and c.iloc[-2] > o.iloc[-2] and c.iloc[-3] > o.iloc[-3]:
        sinal += "Evening Star 🌙\n"
    return sinal

def analisar_sinal(df, symbol, interval):
    try:
        df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
        df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)

        sinal = ""
        if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1]:
            sinal += "Tendência: Long 📈\n"
        else:
            sinal += "Tendência: Short 📉\n"

        rsi = df['RSI'].iloc[-1]
        if rsi < 30:
            sinal += f"RSI {rsi:.1f}: Sobrevendido 🟢\n"
        elif rsi > 70:
            sinal += f"RSI {rsi:.1f}: Sobrecomprado 🔴\n"

        if df['volume'].iloc[-1] > df['volume'].mean():
            sinal += "Volume acima da média 📊\n"

        candle = verificar_padrao_candle(df)
        if candle:
            sinal += candle

        return sinal if sinal else None
    except Exception as e:
        print(f"[ERRO análise {symbol}] {e}")
        return None

def tarefa_agendada():
    print("🔁 Iniciando tarefa agendada...")
    sinais_ativos.clear()
    symbols = obter_top_200_coingecko()
    intervals = ["1d", "1w"]
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval)
            if df.empty: continue
            sinal = analisar_sinal(df, symbol, interval)
            if sinal:
                mensagem = f"🔔 Sinal detectado para {symbol} ({interval}):\n{sinal}"
                bot.send_message(GRUPO_CHAT_ID, mensagem)
                sinais_ativos.append(mensagem)

@bot.message_handler(commands=['siga'])
def siga(message):
    try:
        _, symbol, interval = message.text.strip().split()
        df = get_klines(symbol, interval)
        if df.empty:
            bot.reply_to(message, "Erro ao obter dados.")
            return
        sinal = analisar_sinal(df, symbol, interval)
        if sinal:
            bot.reply_to(message, f"Sinal para {symbol} ({interval}):\n{sinal}")
        else:
            bot.reply_to(message, f"Sem sinal para {symbol} ({interval}).")
    except Exception as e:
        bot.reply_to(message, f"Erro: {str(e)}")

@bot.message_handler(commands=["listar"])
def listar(message):
    if sinais_ativos:
        for sinal in sinais_ativos:
            bot.reply_to(message, sinal)
    else:
        bot.reply_to(message, "Nenhum sinal ativo no momento.")

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "🤖 Bot de sinais ativo! Use /siga ou /listar.")

def verificar_agendamentos():
    while True:
        schedule.run_pending()
        time.sleep(10)

# Agendamentos
schedule.every().day.at("08:00").do(tarefa_agendada)
schedule.every(30).minutes.do(tarefa_agendada)

threading.Thread(target=verificar_agendamentos).start()

# Iniciar o bot
if __name__ == '__main__':
    print("Bot iniciado.")
    bot.polling(none_stop=True)
