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
    print("Erro: BOT_TOKEN ou GRUPO_CHAT_ID não configurados.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Obter top 200 moedas do CoinGecko
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
    return [f"{crypto['symbol'].upper()}USDT" for crypto in data if 'symbol' in crypto]

# Limpeza de dados

def limpar_dados(df):
    for col in ['close', 'open', 'high', 'low', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.fillna(0)

# Obter dados históricos da Binance
def get_klines(symbol, interval, limit=100):
    url = f'https://api.binance.com/api/v1/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    response = requests.get(url, params=params)
    data = response.json()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    return limpar_dados(df)

# Verificação de padrões de candlestick
def verificar_padrao_candle(df):
    sinal = ""
    c, o, h, l = df['close'], df['open'], df['high'], df['low']

    if c.iloc[-1] < o.iloc[-1] and (h.iloc[-1] - c.iloc[-1]) > 2 * (c.iloc[-1] - o.iloc[-1]):
        sinal += "Martelo invertido detetado ⚠️\n"
    if c.iloc[-1] > o.iloc[-1] and (c.iloc[-1] - l.iloc[-1]) > 2 * (o.iloc[-1] - c.iloc[-1]):
        sinal += "Martelo detetado 🛑\n"
    if abs(c.iloc[-1] - o.iloc[-1]) <= 0.1 * (h.iloc[-1] - l.iloc[-1]):
        sinal += "Doji detetado 🔲\n"
    if (c.iloc[-1] > o.iloc[-1] and c.iloc[-2] < o.iloc[-2] and
            c.iloc[-1] > o.iloc[-2] and o.iloc[-1] < c.iloc[-2]):
        sinal += "Engolfo de Alta detetado 🟢\n"
    if (c.iloc[-1] < o.iloc[-1] and c.iloc[-2] > o.iloc[-2] and
            c.iloc[-1] < o.iloc[-2] and o.iloc[-1] > c.iloc[-2]):
        sinal += "Engolfo de baixa detetado 🔴\n"
    if c.iloc[-1] > o.iloc[-1] and c.iloc[-2] < o.iloc[-2] and c.iloc[-3] < o.iloc[-3]:
        sinal += "Morning Star detetada 🌅\n"
    if c.iloc[-1] < o.iloc[-1] and c.iloc[-2] > o.iloc[-2] and c.iloc[-3] > o.iloc[-3]:
        sinal += "Evening Star detetada 🌙\n"
    return sinal

# Análise de sinais
def analisar_sinal(df, symbol, interval):
    df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    sinal = ""

    if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1]:
        sinal += f"Sinal Long detetado para {symbol} em {interval} 📈\n"
    else:
        sinal += f"Sinal Short detetado para {symbol} em {interval} 📉\n"

    if df['RSI'].iloc[-1] < 30:
        sinal += "RSI indica sobrevenda (Compra) 🟢\n"
    elif df['RSI'].iloc[-1] > 70:
        sinal += "RSI indica sobrecompra (Venda) 🔴\n"

    if df['volume'].iloc[-1] > df['volume'].mean():
        sinal += "Alto volume detetado 📊\n"

    sinal += verificar_padrao_candle(df)
    return sinal if sinal.strip() else None

# Tarefa agendada para 1d e 1w
def tarefa_agendada():
    print("⏰ Executando tarefa agendada...")
    symbols = obter_top_200_coingecko()
    intervals = ["1d", "1w"]
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval)
            if df.empty:
                continue
            sinal = analisar_sinal(df, symbol, interval)
            if sinal:
                bot.send_message(GRUPO_CHAT_ID, f"[AGENDADO] {symbol} ({interval})\n{sinal}")

# Comando /sinais (apenas 1D)
@bot.message_handler(commands=['sinais'])
def sinais_diarios(message):
    try:
        bot.reply_to(message, "🔍 Verificando sinais no timeframe 1D...")
        symbols = obter_top_200_coingecko()
        resultados = []
        for symbol in symbols:
            df = get_klines(symbol, '1d')
            if df.empty:
                continue
            sinal = analisar_sinal(df, symbol, '1d')
            if sinal:
                resultados.append(f"{symbol} (1D):\n{sinal}\n")
        if resultados:
            for resultado in resultados[:10]:
                bot.send_message(message.chat.id, resultado)
        else:
            bot.reply_to(message, "Nenhum sinal encontrado no timeframe 1D.")
    except Exception as e:
        print(f"Erro no comando /sinais: {e}")
        bot.reply_to(message, f"❌ Erro ao processar sinais: {e}")

# Comando /siga [PAR] [INTERVALO]
@bot.message_handler(commands=['siga'])
def siga(message):
    try:
        params = message.text.split()[1:]
        if len(params) != 2:
            bot.reply_to(message, "Uso correto: /siga BTCUSDT 1d")
            return
        symbol, interval = params
        df = get_klines(symbol, interval)
        if df.empty:
            bot.reply_to(message, f"Erro: Não foi possível obter dados para {symbol}.")
            return
        sinal = analisar_sinal(df, symbol, interval)
        if sinal:
            bot.reply_to(message, f"Sinal para {symbol} ({interval}):\n{sinal}")
        else:
            bot.reply_to(message, f"Sem sinal para {symbol} ({interval}).")
    except Exception as e:
        print(f"Erro no comando /siga: {e}")
        bot.reply_to(message, f"Erro ao processar o comando: {str(e)}")

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "✅ Bot ativo e pronto para analisar sinais!")

# Thread para agendamentos
def verificar_agendamentos():
    while True:
        schedule.run_pending()
        time.sleep(10)

schedule.every().day.at("08:00").do(tarefa_agendada)
th = threading.Thread(target=verificar_agendamentos)
th.start()

# Iniciar polling
bot.polling(none_stop=True)
