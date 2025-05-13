import telebot
import requests
import pandas
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
    print("🔄 Obtendo o top 200 de criptomoedas do CoinGecko...")
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
    
    if 'error' in data:
        print(f"Erro ao obter dados do CoinGecko: {data['error']}")
        return []

    pares = []
    for crypto in data:
        symbol = crypto['symbol'].upper()  # Simbolos em maiúsculo
        pares.append(f"{symbol}USDT")  # Adiciona o par com USDT (pode ser ajustado para outros pares)
    
    print(f"Obtidos {len(pares)} pares de moedas.")
    return pares

# Função para garantir que as colunas numéricas sejam convertidas corretamente
def limpar_dados(df):
    print("🔄 Limpando dados...")
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
    print(f"🔄 Obtendo dados históricos para {symbol} no intervalo {interval}...")
    url = f'https://api.binance.com/api/v1/klines'
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    if not data:
        print(f"Erro ao obter dados históricos para {symbol} no intervalo {interval}.")
        return pd.DataFrame()  # Retorna um DataFrame vazio em caso de erro
    
    # Converte para DataFrame
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    
    # Limpa e converte os dados
    df = limpar_dados(df)

    return df

# Função para análise do sinal
def analisar_sinal(df, symbol, interval):
    print(f"🔄 Analisando sinal para {symbol} no intervalo {interval}...")
    # Indicadores técnicos (EMA, RSI, Volume) usando a biblioteca 'ta'
    df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)  # Cálculo correto do RSI
    df['Volume'] = df['volume']
    
    sinal = ''
    
    # Verifica cruzamento da EMA9 e EMA21
    if df['EMA9'].iloc[-1] > df['EMA21'].iloc[-1]:
        sinal += f"Long signal detected for {symbol} on {interval} 📈\n"
    else:
        sinal += f"Short signal detected for {symbol} on {interval} 📉\n"
    
    # Verifica RSI (Exemplo: comprar se RSI < 30, vender se RSI > 70)
    if df['RSI'].iloc[-1] < 30:
        sinal += "RSI indicates oversold condition (Potential Buy) 🟢\n"
    elif df['RSI'].iloc[-1] > 70:
        sinal += "RSI indicates overbought condition (Potential Sell) 🔴\n"
    
    # Verifica volume
    if df['Volume'].iloc[-1] > df['Volume'].mean():
        sinal += "High volume detected 📊\n"
    
    # Padrões de candlestick
    if verificar_padrao_candle(df):
        sinal += verificar_padrao_candle(df)  # Adiciona o padrão identificado à mensagem

    # Se houver sinal, retorne
    if sinal:
        return sinal
    else:
        return None

# Função para verificar padrões de candlestick
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

# Função para enviar sinal agendado
def tarefa_agendada():
    print("⏰ Execução automática de sinais...")
    symbols = obter_top_200_coingecko()  # Obtém os 200 pares mais populares
    if not symbols:
        print("Nenhum par encontrado para enviar sinais.")
        return
    intervals = ["1d", "1w"]
    for symbol in symbols:
        for interval in intervals:
            df = get_klines(symbol, interval, 100)
            if df.empty:
                continue
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
        print(f"Erro ao processar o comando: {str(e)}")

# Iniciar o bot
if __name__ == '__main__':
    # Agendar o envio automático de sinais
    schedule.every(30).minutes.do(tarefa_agendada)
    
    # Iniciar o bot e agendar as tarefas
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            print(f"Erro na execução: {e}")
