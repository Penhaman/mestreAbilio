import telebot
import requests
import pandas as pd
import ta
import schedule
import time
import os  # Para acessar variáveis de ambiente

# Acessar as variáveis de ambiente do Railway
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Token do bot armazenado no Railway
GRUPO_CHAT_ID = os.getenv('GRUPO_CHAT_ID')  # ID do grupo armazenado no Railway


# Verifica se as variáveis de ambiente foram configuradas corretamente
if not BOT_TOKEN or not GRUPO_CHAT_ID:
    print("Erro: As variáveis de ambiente BOT_TOKEN ou GRUPO_CHAT_ID não estão configuradas!")
    exit(1)

# Criar o bot
bot = telebot.TeleBot(BOT_TOKEN)

# Função para obter o Top 200 criptomoedas do CoinGecko
def obter_top_200_coingecko():
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',  # Os preços vão ser em USD
        'order': 'market_cap_desc',  # Ordena por capitalização de mercado (do maior para o menor)
        'per_page': 200,  # Limita para as 200 moedas mais populares
        'page': 1,  # Página inicial
        'sparkline': False,  # Não inclui dados do gráfico (sparkline)
    }

    response = requests.get(url, params=params)
    data = response.json()
    
    pares = []
    for crypto in data:
        symbol = crypto['symbol'].upper()  # Simbolos em maiúsculo
        pares.append(f"{symbol}USDT")  # Adiciona o par com USDT (pode ser ajustado para outros pares)
    
    return pares

# Função para garantir que as colunas numéricas sejam convertidas corretamente
def limpar_dados(df):
    # Verifica se há valores não numéricos e os converte para NaN
    df['close'] = pd.to_numeric(df['close'], errors='coerce')  # 'coerce' transforma valores inválidos em NaN
    df['open'] = pd.to_numeric(df['open'], errors='coerce')
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

    # Substitui os NaN por 0
    df = df.fillna(0)

    return df

# Função para obter os dados históricos do par
def get_klines(symbol, interval, limit=100):
    url = f'https://api.binance.com/api/v1/klines'
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    # Converte para DataFrame
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    
    # Limpa e converte os dados
    df = limpar_dados(df)

    return df

# Função para análise do sinal
def verificar_padrao_candle(df):
    sinal = ""

    # Martelo Invertido
    if df['close'].iloc[-1] < df['open'].iloc[-1] and (df['high'].iloc[-1] - df['close'].iloc[-1]) > 2 * (df['close'].iloc[-1] - df['open'].iloc[-1]):
        sinal += "Inverted hammer candlestick detected ⚠️\n"
    
    # Martelo
    if df['close'].iloc[-1] > df['open'].iloc[-1] and (df['close'].iloc[-1] - df['low'].iloc[-1]) > 2 * (df['open'].iloc[-1] - df['close'].iloc[-1]):
        sinal += "Hammer candlestick detected 🛑\n"
    
    # Doji
    if abs(df['close'].iloc[-1] - df['open'].iloc[-1]) <= 0.1 * (df['high'].iloc[-1] - df['low'].iloc[-1]):
        sinal += "Doji candlestick detected 🔲\n"
    
    # Engolfo de Alta
    if df['close'].iloc[-1] > df['open'].iloc[-1] and df['close'].iloc[-2] < df['open'].iloc[-2] and df['close'].iloc[-1] > df['open'].iloc[-2] and df['open'].iloc[-1] < df['close'].iloc[-2]:
        sinal += "Bullish Engulfing candlestick detected 🟢\n"
    
    # Engolfo de Baixa
    if df['close'].iloc[-1] < df['open'].iloc[-1] and df['close'].iloc[-2] > df['open'].iloc[-2] and df['close'].iloc[-1] < df['open'].iloc[-2] and df['open'].iloc[-1] > df['close'].iloc[-2]:
        sinal += "Bearish Engulfing candlestick detected 🔴\n"
    
    # Estrela da Manhã
    if df['close'].iloc[-1] > df['open'].iloc[-1] and df['close'].iloc[-2] < df['open'].iloc[-2] and df['close'].iloc[-3] < df['open'].iloc[-3]:
        sinal += "Morning Star candlestick detected 🌅\n"
    
    # Estrela da Noite
    if df['close'].iloc[-1] < df['open'].iloc[-1] and df['close'].iloc[-2] > df['open'].iloc[-2] and df['close'].iloc[-3] > df['open'].iloc[-3]:
        sinal += "Evening Star candlestick detected 🌙\n"

    return sinal
    
    # Verifica cruzamento da EMA9 e EMA21
    if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1]:
        sinal += f"Long signal detected for {symbol} on {interval} 📈\n"
    else:
        sinal += f"Short signal detected for {symbol} on {interval} 📉\n"
    
    # Verifica RSI (Exemplo: comprar se RSI < 30, vender se RSI > 70)
    if df['RSI'].iloc[-1] < 30:
        sinal += "RSI indica sobrevenda (Potencial compra!) 🟢\n"
    elif df['RSI'].iloc[-1] > 70:
        sinal += "RSI indica sobrecompra (Potencial venda!) 🔴\n"
    
    # Verifica volume
    if df['Volume'].iloc[-1] > df['Volume'].mean():
        sinal += "Volume alto detetado 📊\n"
    
    # Verifica padrões de candle, por exemplo, martelo invertido
    if df['close'].iloc[-1] < df['open'].iloc[-1] and (df['high'].iloc[-1] - df['close'].iloc[-1]) > 2 * (df['close'].iloc[-1] - df['open'].iloc[-1]):
        sinal += "Martelo invertido detetado ⚠️\n"
    
    # Se houver sinal, retorne
    if sinal:
        return sinal
    else:
        return None

# Função para enviar sinal agendado
def tarefa_agendada():
    print("⏰ Execução automática de sinais...")
    symbols = obter_top_200_coingecko()  # Obtém os 200 pares mais populares
    intervals = ["1d", "1w"]
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval, 100)
            sinal = analisar_sinal(df, symbol, interval)
            if sinal:
                bot.send_message(GRUPO_CHAT_ID, f"[AGENDADO]\n{sinal}")

# Comando /siga
@bot.message_handler(commands=['siga'])
def siga(message):
    try:
        params = message.text.split()[1:]  # Obtém o par e o intervalo do comando
        if len(params) != 2:
            bot.reply_to(message, "Por favor, forneça o par e o intervalo. Exemplo: /siga BTCUSDT 1d")
            return
        
        symbol, interval = params
        df = get_klines(symbol, interval, 100)
        sinal = analisar_sinal(df, symbol, interval)
        if sinal:
            bot.reply_to(message, f"Sinal para {symbol} ({interval}):\n{sinal}")
        else:
            bot.reply_to(message, f"Sem sinal para {symbol} ({interval}).")
    
    except Exception as e:
        bot.reply_to(message, f"Erro ao processar o comando: {e}")

# Comando /sinais para listar sinais armazenados (exemplo, apenas envia uma resposta fictícia)
@bot.message_handler(commands=['sinais'])
def sinais(message):
    bot.reply_to(message, "Exemplo de sinais armazenados:\nBTCUSDT 1d: Long signal 📈\nETHUSDT 1w: Short signal 📉")

# Agendamento de tarefas automáticas
schedule.every().day.at("09:00").do(tarefa_agendada)

# Função para rodar o bot e agendamento
def run():
    while True:
        schedule.run_pending()
        time.sleep(1)
        bot.polling(none_stop=True, interval=0)

if __name__ == "__main__":
    run()

