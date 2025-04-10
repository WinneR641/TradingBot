import asyncio
import matplotlib.pyplot as plt
import mplfinance as mpf
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from binance import Client
import pandas as pd
import numpy as np
from datetime import datetime

API_TOKEN = '8064418325:AAFshIlqpz79-0RUcxXOqj1C5jUqqaUFeDY'  # Вставте ваш токен
BINANCE_API_KEY = 'rJ2AoAMMI2hiz6osor7L3GW5bvNK4AJv62dymXxs5MWUwl73bTsjSpvzDhEioN2e'  # Вставте ваш API Key
BINANCE_SECRET_KEY = 'qENg4zUki2EB8xT3o7zSSEA0VnfTFv2DpOA9jiHSv6S4ETN3Iqs2IveO53Xls0VE'  # Вставте ваш Secret Key
CHAT_ID = -1002623933177  # Вставте Chat ID групи

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTCUSDT", callback_data="BTCUSDT")],
        [InlineKeyboardButton(text="ETHUSDT", callback_data="ETHUSDT")],
    ])
    await message.reply("Вибери пару для аналізу:", reply_markup=keyboard)

async def analyze_pair(pair: str, interval: str, limit: int) -> tuple[pd.DataFrame, float]:
    klines = binance_client.get_klines(symbol=pair, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                       'close_time', 'quote_asset_volume', 'trades', 
                                       'taker_buy_base', 'taker_buy_quote', 'ignored'])
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    current_price = df['close'].iloc[-1]
    return df, current_price

async def generate_analysis(pair: str) -> tuple[str, str]:
    timeframes = {
        "1h": (Client.KLINE_INTERVAL_1HOUR, 100),
        "15m": (Client.KLINE_INTERVAL_15MINUTE, 50),
        "5m": (Client.KLINE_INTERVAL_5MINUTE, 30),
    }
    analysis_data = {}
    
    # Аналіз для всіх таймфреймів
    for tf, (interval, limit) in timeframes.items():
        df, current_price = await analyze_pair(pair, interval, limit)

        sma20 = df['close'].rolling(window=20).mean().iloc[-1]
        sma50 = df['close'].rolling(window=50 if tf == "1h" else 20).mean().iloc[-1]
        trend = "висхідний" if sma20 > sma50 else "низхідний"

        support = df['low'].min()
        resistance = df['high'].max()
        atr = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]

        # Ордерблок (зона перед найбільшим рухом)
        price_diffs = np.diff(df['close'])
        big_move_idx = np.argmax(np.abs(price_diffs))
        order_block = df['close'].iloc[big_move_idx] if big_move_idx > 0 else support

        # Імбаланс (FVG)
        fvg_levels = []
        for i in range(1, len(df) - 1):
            if df['high'].iloc[i-1] < df['low'].iloc[i+1]:  # Бичачий FVG
                fvg_levels.append((df['high'].iloc[i-1], df['low'].iloc[i+1], "бичачий"))
            elif df['low'].iloc[i-1] > df['high'].iloc[i+1]:  # Ведмежий FVG
                fvg_levels.append((df['low'].iloc[i-1], df['high'].iloc[i+1], "ведмежий"))

        analysis_data[tf] = {
            "df": df if tf == "5m" else None,  # Зберігаємо df тільки для 5m
            "current_price": current_price,
            "trend": trend,
            "support": support,
            "resistance": resistance,
            "order_block": order_block,
            "fvg_levels": fvg_levels[-3:],  # Останні 3 FVG
            "atr": atr
        }

    # Сигнал на основі 5m із урахуванням тренду 1h
    tf_5m = analysis_data["5m"]
    tf_1h = analysis_data["1h"]
    signal = "Немає сигналу"
    entry = sl = tp = confidence = 0
    for fvg_low, fvg_high, fvg_type in tf_5m["fvg_levels"]:
        if tf_1h["trend"] == "висхідний" and abs(tf_5m["current_price"] - fvg_low) < tf_5m["atr"] and fvg_type == "бичачий":
            entry = tf_5m["current_price"] + tf_5m["atr"] * 0.5
            sl = tf_5m["current_price"] - tf_5m["atr"] * 1.5
            tp = tf_5m["current_price"] + tf_5m["atr"] * 3
            signal = "Купівля"
            confidence = 0.9
            break
        elif tf_1h["trend"] == "низхідний" and abs(tf_5m["current_price"] - fvg_high) < tf_5m["atr"] and fvg_type == "ведмежий":
            entry = tf_5m["current_price"] - tf_5m["atr"] * 0.5
            sl = tf_5m["current_price"] + tf_5m["atr"] * 1.5
            tp = tf_5m["current_price"] - tf_5m["atr"] * 3
            signal = "Продаж"
            confidence = 0.9
            break

    # Генерація графіка тільки для 5m
    df_5m = tf_5m["df"]
    ap = [
        mpf.make_addplot([tf_5m["support"]] * len(df_5m), color='green', linestyle='--', label='Підтримка'),
        mpf.make_addplot([tf_5m["resistance"]] * len(df_5m), color='red', linestyle='--', label='Опір'),
        mpf.make_addplot([tf_5m["order_block"]] * len(df_5m), color='blue', linestyle='--', label='Ордерблок'),
    ]
    if tf_5m["fvg_levels"]:
        for fvg_low, fvg_high, _ in tf_5m["fvg_levels"]:
            ap.append(mpf.make_addplot([fvg_low] * len(df_5m), color='purple', linestyle='--', label='FVG Низ'))
            ap.append(mpf.make_addplot([fvg_high] * len(df_5m), color='purple', linestyle='--', label='FVG Верх'))
    if signal != "Немає сигналу":
        ap.extend([
            mpf.make_addplot([entry] * len(df_5m), color='lime', linestyle='--', label='Вхід'),
            mpf.make_addplot([sl] * len(df_5m), color='red', linestyle='--', label='SL'),
            mpf.make_addplot([tp] * len(df_5m), color='cyan', linestyle='--', label='TP'),
        ])
    img_path = f"{pair}_5m.png"
    mpf.plot(df_5m, type='candle', style='binance', addplot=ap, title=f"{pair} (5m)", 
             ylabel='Ціна', savefig=img_path)

    # Формування тексту
    advice = f"Аналіз для {pair}:\n"
    for tf in ["1h", "15m", "5m"]:
        data = analysis_data[tf]
        advice += (
            f"\nТаймфрейм: {tf}\n"
            f"Ціна: ${data['current_price']:.2f}\n"
            f"Тренд: {data['trend']}\n"
            f"Підтримка: ${data['support']:.2f}\n"
            f"Опір: ${data['resistance']:.2f}\n"
            f"FVG: {', '.join([f'{f[0]:.2f}-{f[1]:.2f} ({f[2]})' for f in data['fvg_levels']] or 'немає')}\n"
        )
    if signal != "Немає сигналу":
        advice += (
            f"\nСигнал (5m): {signal}\n"
            f"Вхід: ${entry:.2f}\n"
            f"SL: ${sl:.2f}\n"
            f"TP: ${tp:.2f}\n"
            f"AI Впевненість: {confidence*100:.0f}%\n"
        )
    else:
        advice += "\nНемає сигналу.\n"

    return advice, img_path

@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    pair = callback.data
    advice, img_path = await generate_analysis(pair)
    photo = FSInputFile(img_path)
    await bot.send_photo(chat_id=callback.message.chat.id, photo=photo)
    await bot.send_message(chat_id=callback.message.chat.id, text=advice)
    await callback.answer()

async def auto_analyze():
    pairs = ["BTCUSDT", "ETHUSDT"]
    while True:
        for pair in pairs:
            try:
                advice, img_path = await generate_analysis(pair)
                if "Сигнал" in advice:
                    photo = FSInputFile(img_path)
                    await bot.send_photo(chat_id=CHAT_ID, photo=photo)
                    await bot.send_message(chat_id=CHAT_ID, text=advice)
            except Exception as e:
                print(f"Помилка: {e}")
        await asyncio.sleep(300)

async def main():
    asyncio.create_task(auto_analyze())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())