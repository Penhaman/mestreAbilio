import os
import time
import requests
import telebot
import pandas as pd
from datetime import datetime, timedelta

# Variáveis de ambiente
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

bot = telebot.TeleBot(BOT_TOKEN)

# Utilitário: Obter dados da Binance
def get_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'])

        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)

        return df
    except Exception as e:
        print(f"Erro ao obter dados de {symbol}: {e}")
        return None

# Indicadores

def calcular_ema(df, periodo):
    return df['close'].ewm(span=periodo).mean()

def calcular_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def candle_type(candle):
    body = abs(candle['close'] - candle['open'])
    shadow = candle['high'] - candle['low']
    if candle['close'] > candle['open'] and body > shadow * 0.6:
        return "Bullish"
    elif candle['open'] > candle['close'] and body > shadow * 0.6:
        return "Bearish"
    elif candle['high'] - max(candle['open'], candle['close']) > 2 * body:
        return "Martelo Invertido"
    return "Indeciso"

def verificar_golden_cross(ema_short, ema_long):
    return ema_short.iloc[-1] > ema_long.iloc[-1] and ema_short.iloc[-2] <= ema_long.iloc[-2]

def verificar_death_cross(ema_short, ema_long):
    return ema_short.iloc[-1] < ema_long.iloc[-1] and ema_short.iloc[-2] >= ema_long.iloc[-2]

def verificar_oco(df):
    if len(df) < 5:
        return False
    hs = df.iloc[-5:]
    return hs['high'].iloc[1] > hs['high'].iloc[0] and hs['high'].iloc[1] > hs['high'].iloc[2] and hs['high'].iloc[3] < hs['high'].iloc[1]

def verificar_ocoi(df):
    if len(df) < 5:
        return False
    ls = df.iloc[-5:]
    return ls['low'].iloc[1] < ls['low'].iloc[0] and ls['low'].iloc[1] < ls['low'].iloc[2] and ls['low'].iloc[3] > ls['low'].iloc[1]

def verificar_black_swan(df):
    última = df.iloc[-1]
    return (última['high'] - última['low']) > 2 * abs(última['close'] - última['open'])

def analisar_sinal(df, symbol, interval):
    if df is None or df.empty:
        return None

    ema9 = calcular_ema(df, 9)
    ema21 = calcular_ema(df, 21)
    rsi = calcular_rsi(df)
    vol = df['volume']
    candle = {
        'open': df['open'].iloc[-1],
        'close': df['close'].iloc[-1],
        'high': df['high'].iloc[-1],
        'low': df['low'].iloc[-1]
    }
    tipo = candle_type(candle)
    sentimento = "Positivo" if rsi.iloc[-1] > 50 else "Negativo"

    sinais = []

    if verificar_golden_cross(ema9, ema21):
        sinais.append("🔶 Golden Cross")
    if verificar_death_cross(ema9, ema21):
        sinais.append("🔻 Death Cross")
    if verificar_oco(df):
        sinais.append("🛑 OCO Detectado")
    if verificar_ocoi(df):
        sinais.append("🔁 OCOI Detectado")
    if verificar_black_swan(df):
        sinais.append("⚠️ Black Swan")

    if not sinais:
        return None

    mensagem = f"\n📊 Sinal Detectado para {symbol} ({interval})\n"
    mensagem += f"RSI: {rsi.iloc[-1]:.2f}\nTipo de Candle: {tipo}\nSentimento: {sentimento}\n"
    mensagem += "\n".join(sinais)
    return mensagem

# Comando /siga
@bot.message_handler(commands=['siga'])
def siga_handler(message):
    bot.reply_to(message, "🔍 A procurar sinais... Aguarde.")
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]  # Exemplos, pode ser top 200
    intervals = ["1d", "1w"]
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval, 100)
            sinal = analisar_sinal(df, symbol, interval)
            if sinal:
                bot.send_message(message.chat.id, sinal)

# Comando /sinais
@bot.message_handler(commands=['sinais'])
def sinais_handler(message):
    bot.reply_to(message, "🔔 Sinais ativos: use /siga para buscar sinais sob pedido.")

@bot.message_handler(func=lambda m: True)
def debug_chat_id(message):
    bot.reply_to(message, f"Chat ID: {message.chat.id}")



# Inicialização
if __name__ == "__main__":
    print("🤖 Bot está ativo...")
    bot.infinity_polling()
