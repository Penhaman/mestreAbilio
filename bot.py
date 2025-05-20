import os
import telebot
from flask import Flask, request
from datetime import datetime
import threading

# ============ Configuração Inicial ============

BOT_TOKEN = os.getenv('BOT_TOKEN')
GRUPO_CHAT_ID = os.getenv('GRUPO_CHAT_ID')
WEBHOOK_URL = "https://worker-production-81f4.up.railway.app"


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

# Comando /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🤖 Olá! Sou o TEU BOT de sinais. Use /help para ver os comandos disponíveis.")

# Comando /help
@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """
📘 <b>Comandos disponíveis:</b>

/start - Iniciar o bot
/help - Ver esta mensagem de ajuda
/sinais - Verificar sinais imediatos (pares 1D)
/sinais1d - Verificar sinais para o período de 1D
/sinais1w - Verificar sinais para o período de 1W
"""
    bot.reply_to(message, help_text)

# Normalização dos pares
def normalizar_par(par):
    return par.upper()

# Simulação de verificação de sinal (substitua pela lógica real)
def verificar_sinais(periodo="1D"):
    exemplo = [
        f"✅ Sinal Detectado\n<b>Par:</b> BTC/USDT\n<b>Período:</b> {periodo}\n<b>Data:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    ]
    return exemplo

# Comando /sinais (1D apenas)
@bot.message_handler(commands=['sinais'])
def sinais_1d(message):
    sinais = verificar_sinais("1D")
    for sinal in sinais:
        bot.reply_to(message, sinal)

# Comando /sinais1d
@bot.message_handler(commands=['sinais1d'])
def sinais_1d_command(message):
    sinais = verificar_sinais("1D")
    for sinal in sinais:
        bot.reply_to(message, sinal)

# Comando /sinais1w
@bot.message_handler(commands=['sinais1w'])
def sinais_1w_command(message):
    sinais = verificar_sinais("1W")
    for sinal in sinais:
        bot.reply_to(message, sinal)

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

# Configurar o webhook ao iniciar
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Bot ativo!")

def configurar_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")

if __name__ == '__main__':
    configurar_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
