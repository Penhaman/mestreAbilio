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
    print("Erro: BOT_TOKEN ou GRUPO_CHAT_ID não configurado!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Função para obter o top 200 do CoinGecko
def obter_top_200_coingecko():
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 200,
        'page': 1,
        'sparkline': False,
    }
    response = requests.get(url, params=params)
    data = response.json()
    if 'error' in data:
        return []
    return [crypto['symbol'].upper() + "USDT" for crypto in data]

# Limpar dados

def limpar_dados(df):
    for col in ['close', 'open', 'high', 'low', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.fillna(0)

# Obter dados históricos

def get_klines(symbol, interval, limit=100):
    url = f'https://api.binance.com/api/v1/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    response = requests.get(url, params=params)
    data = response.json()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                                     'quote_asset_volume', 'number_of_trades',
                                     'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    return limpar_dados(df)

# Verificar padrões de velas

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
    if df['close'].iloc[-1] > df['open'].iloc[-1] and df['close'].iloc[-2] < df['open'].iloc[-2] and df['close'].iloc[-3] < df['open'].iloc[-3]:
        sinal += "Morning Star detetada 🌅\n"
    if df['close'].iloc[-1] < df['open'].iloc[-1] and df['close'].iloc[-2] > df['open'].iloc[-2] and df['close'].iloc[-3] > df['open'].iloc[-3]:
        sinal += "Evening Star detetada 🌙\n"
    return sinal

# Analisar sinal

def analisar_sinal(df, symbol, interval):
    df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    sinal = ''

    if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1]:
        sinal += f"Sinal Long detetado para {symbol} em {interval} 📈\n"
    else:
        sinal += f"Sinal Short detetado para {symbol} em {interval} 📉\n"

    if df['RSI'].iloc[-1] < 30:
        sinal += "RSI indica sobrevenda (Potencial Compra) 🟢\n"
    elif df['RSI'].iloc[-1] > 70:
        sinal += "RSI indica sobrecompra (Potencial Venda) 🔴\n"

    if df['volume'].iloc[-1] > df['volume'].mean():
        sinal += "Alto volume detetado 📊\n"

    padrao = verificar_padrao_candle(df)
    if padrao:
        sinal += padrao

    return sinal if sinal else None

# Funções de tarefa agendada
def tarefa_agendada():
    symbols = obter_top_200_coingecko()
    intervals = ["1d", "1w"]
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval, 100)
            if df.empty:
                continue
            sinal = analisar_sinal(df, symbol, interval)
            if sinal:
                bot.send_message(GRUPO_CHAT_ID, f"[AGENDADO]\n{sinal}")

# Comandos
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🤖 Bot de sinais ativo!")

@bot.message_handler(commands=['help'])
def help_command(message):
    ajuda = (
        "📘 *Comandos disponíveis:*
\n"
        "/start - Ativa o bot\n"
        "/help - Mostra esta ajuda\n"
        "/siga [par] [intervalo] - Verifica sinal manual. Ex: /siga BTCUSDT 1d\n"
        "/sinais - Verifica sinais diários (1D) para o top 200\n"
    )
    bot.reply_to(message, ajuda, parse_mode='Markdown')

@bot.message_handler(commands=['siga'])
def siga(message):
    try:
        params = message.text.split()[1:]
        if len(params) != 2:
            bot.reply_to(message, "Por favor, forneça o par e o intervalo. Exemplo: /siga BTCUSDT 1d")
            return
        symbol = params[0].upper()
        interval = params[1]
        df = get_klines(symbol, interval, 100)
        if df.empty:
            bot.reply_to(message, f"Erro: Não foi possível obter dados para {symbol}.")
            return
        sinal = analisar_sinal(df, symbol, interval)
        if sinal:
            bot.reply_to(message, f"Sinal para {symbol} ({interval}):\n{sinal}")
        else:
            bot.reply_to(message, f"Sem sinal para {symbol} ({interval}).")
    except Exception as e:
        bot.reply_to(message, f"Erro ao processar o comando: {str(e)}")

@bot.message_handler(commands=['sinais'])
def sinais(message):
    bot.send_message(message.chat.id, "🔍 A verificar sinais diários para o top 200...")
    symbols = obter_top_200_coingecko()
    for symbol in symbols:
        df = get_klines(symbol, "1d", 100)
        if df.empty:
            continue
        sinal = analisar_sinal(df, symbol, "1d")
        if sinal:
            bot.send_message(message.chat.id, f"[Manual]\n{sinal}")

# Agendamento em thread
schedule.every().day.at("08:00").do(tarefa_agendada)
threading.Thread(target=lambda: [schedule.run_pending() or time.sleep(10) for _ in iter(int, 1)]).start()

bot.polling(none_stop=True)
