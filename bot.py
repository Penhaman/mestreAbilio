import ccxt
import pandas as pd
import requests
import time
import os

# === CONFIGURAÇÕES ===
CMC_API_KEY = os.getenv('CMC_API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DEFAULT_TIMEFRAME = '1d'
ALLOWED_TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
EMA_SHORT = 9
EMA_LONG = 21
RSI_PERIOD = 14
VOLUME_PERIOD = 14
EXCHANGE = ccxt.binance({'enableRateLimit': True})

# Guardar sinais detectados
last_signals = []

# === Pegar Top 200 moedas ===
def get_top_200_symbols():
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
    parameters = {'start': '1', 'limit': '200', 'convert': 'USD'}
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': CMC_API_KEY}
    response = requests.get(url, headers=headers, params=parameters)
    data = response.json()
    symbols = [coin['symbol'] for coin in data['data']]
    return symbols

# === Buscar candles da Binance ===
def fetch_ohlcv(symbol, timeframe=DEFAULT_TIMEFRAME):
    pair = symbol + '/USDT'
    try:
        ohlcv = EXCHANGE.fetch_ohlcv(pair, timeframe=timeframe)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Erro ao buscar {pair} ({timeframe}): {e}")
        return None

# === Calcular RSI ===
def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, min_periods=period).mean()
    avg_loss = loss.ewm(span=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    df['RSI'] = rsi

# === Gerar sinal ===
def generate_signal(df):
    df['EMA_short'] = df['close'].ewm(span=EMA_SHORT).mean()
    df['EMA_long'] = df['close'].ewm(span=EMA_LONG).mean()
    calculate_rsi(df, RSI_PERIOD)
    df['Volume_MA'] = df['volume'].rolling(window=VOLUME_PERIOD).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    long_conditions = (
        prev['EMA_short'] <= prev['EMA_long'] and last['EMA_short'] > last['EMA_long'] and
        last['RSI'] > 50 and
        last['volume'] > last['Volume_MA'] and
        last['close'] > last['open']
    )

    short_conditions = (
        prev['EMA_short'] >= prev['EMA_long'] and last['EMA_short'] < last['EMA_long'] and
        last['RSI'] < 50 and
        last['volume'] > last['Volume_MA'] and
        last['close'] < last['open']
    )

    if long_conditions:
        return 'LONG'
    elif short_conditions:
        return 'SHORT'
    else:
        return None

# === Enviar mensagem para Telegram ===
def send_telegram(message, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': chat_id, 'text': message}
    requests.post(url, data=payload)

# === Responder comando /siga ===
def handle_siga_command(command, chat_id):
    parts = command.split()
    if len(parts) < 2:
        send_telegram("Uso correto: /siga BTC 4h (ou /siga BTC)", chat_id)
        return
    
    symbol = parts[1].upper()
    timeframe = parts[2] if len(parts) > 2 else DEFAULT_TIMEFRAME

    if timeframe not in ALLOWED_TIMEFRAMES:
        allowed = ", ".join(ALLOWED_TIMEFRAMES)
        send_telegram(f"⛔ Timeframe inválido. Use: {allowed}", chat_id)
        return

    df = fetch_ohlcv(symbol, timeframe)
    if df is None or len(df) < EMA_LONG + RSI_PERIOD:
        send_telegram(f"Não consegui buscar dados para {symbol}/USDT no timeframe {timeframe}.", chat_id)
        return
    
    signal = generate_signal(df)
    if signal:
        message = f"SINAL {signal} para {symbol}/USDT no gráfico {timeframe} 🚀"
    else:
        message = f"Sem sinal atual para {symbol}/USDT no gráfico {timeframe}."
    
    send_telegram(message, chat_id)

# === Responder comando /sinais ===
def handle_sinais_command(chat_id):
    if not last_signals:
        send_telegram("Nenhum sinal encontrado na última análise.", chat_id)
    else:
        signals_text = "Últimos sinais detectados:\n\n" + "\n".join(last_signals)
        send_telegram(signals_text, chat_id)

# === Monitorar comandos do Telegram ===
def check_telegram_updates(last_update_id=None):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates'
    if last_update_id:
        url += f'?offset={last_update_id + 1}'
    response = requests.get(url)
    data = response.json()
    return data.get('result', [])

# === Função principal ===
def main():
    global last_signals
    last_update_id = None

    while True:
        try:
            print("Buscando novas mensagens...")
            updates = check_telegram_updates(last_update_id)
            for update in updates:
                if 'message' in update:
                    message_text = update['message'].get('text', '')
                    chat_id = update['message']['chat']['id']
                    last_update_id = update['update_id']

                    if message_text.startswith('/siga'):
                        handle_siga_command(message_text, chat_id)
                    elif message_text.startswith('/sinais'):
                        handle_sinais_command(chat_id)

            print("Analisando sinais automáticos...")
            last_signals = []  # Limpa lista
            symbols = get_top_200_symbols()

            for symbol in symbols:
                df = fetch_ohlcv(symbol, DEFAULT_TIMEFRAME)
                if df is not None and len(df) > EMA_LONG + RSI_PERIOD:
                    signal = generate_signal(df)
                    if signal:
                        sig_msg = f"{signal} - {symbol}/USDT [{DEFAULT_TIMEFRAME}]"
                        print(sig_msg)
                        send_telegram(sig_msg)
                        last_signals.append(sig_msg)
                else:
                    print(f"Dados insuficientes para {symbol}/USDT.")

            print("Aguardando 24h para nova varredura automática...")
            time.sleep(60 * 60 * 24)

        except Exception as e:
            print(f"Erro geral: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
