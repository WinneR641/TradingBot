import asyncio
import matplotlib.pyplot as plt
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

async def analyze_pair(pair: str) -> tuple[str, str]:
    # Отримання даних
    klines = binance_client.get_klines(symbol=pair, interval=Client.KLINE_INTERVAL_1HOUR, limit=100)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                       'close_time', 'quote_asset_volume', 'trades', 
                                       'taker_buy_base', 'taker_buy_quote', 'ignored'])
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    prices = df['close']
    current_price = prices.iloc[-1]

    # Тренд (SMA)
    sma20 = prices.rolling(window=20).mean()
    sma50 = prices.rolling(window=50).mean()
    trend = "висхідний" if sma20.iloc[-1] > sma50.iloc[-1] else "низхідний"

    # Рівні підтримки/опору
    support = prices.min()
    resistance = prices.max()

    # Ордерблок (спрощено: зона перед найбільшим рухом)
    price_diffs = np.diff(prices)
    big_move_idx = np.argmax(np.abs(price_diffs))
    order_block = prices[big_move_idx] if big_move_idx > 0 else support

    # Імбаланс (спрощено: різкий рух без відкатів)
    imbalance = prices.iloc[-10:].max() - prices.iloc[-10:].min()

    # ATR для волатильності
    high_low = df['high'] - df['low']
    atr = high_low.rolling(window=14).mean().iloc[-1]

    # AI-логіка (спрощена): пошук точок входу біля ключових зон
    ai_confidence = 0
    if trend == "висхідний" and abs(current_price - support) < atr * 2 and abs(current_price - order_block) < atr * 2:
        entry = current_price + atr * 0.5
        sl = current_price - atr * 1.5
        tp = current_price + atr * 3
        ai_confidence = 0.85  # Імітація AI-оцінки
        signal = "Купівля"
    elif trend == "низхідний" and abs(current_price - resistance) < atr * 2 and abs(current_price - order_block) < atr * 2:
        entry = current_price - atr * 0.5
        sl = current_price + atr * 1.5
        tp = current_price - atr * 3
        ai_confidence = 0.85
        signal = "Продаж"
    else:
        signal = "Немає сигналу"
        entry = sl = tp = 0

    # Генерація графіка
    plt.figure(figsize=(10, 6))
    plt.plot(df['timestamp'], prices, label=f'{pair} Price')
    plt.axhline(y=support, color='g', linestyle='--', label='Підтримка')
    plt.axhline(y=resistance, color='r', linestyle='--', label='Опір')
    plt.axhline(y=order_block, color='b', linestyle='--', label='Ордерблок')
    if signal != "Немає сигналу":
        plt.plot(df['timestamp'].iloc[-1], entry, 'go', label='Вхід')
        plt.plot(df['timestamp'].iloc[-1], sl, 'ro', label='SL')
        plt.plot(df['timestamp'].iloc[-1], tp, 'bo', label='TP')
    plt.legend()
    plt.title(f"{pair} Аналіз")
    plt.xlabel("Час")
    plt.ylabel("Ціна")
    img_path = f"{pair}_chart.png"
    plt.savefig(img_path)
    plt.close()

    # Формування повідомлення
    advice = (
        f"Пара: {pair}\n"
        f"Ціна: ${current_price:.2f}\n"
        f"Тренд: {trend}\n"
        f"Підтримка: ${support:.2f}\n"
        f"Опір: ${resistance:.2f}\n"
        f"Ордерблок: ${order_block:.2f}\n"
        f"Імбаланс: ${imbalance:.2f}\n"
    )
    if signal != "Немає сигналу":
        advice += (
            f"Сигнал: {signal}\n"
            f"Вхід: ${entry:.2f}\n"
            f"SL: ${sl:.2f}\n"
            f"TP: ${tp:.2f}\n"
            f"AI Прогноз: {ai_confidence*100:.0f}%"
        )
    else:
        advice += "Немає сигналу."

    return advice, img_path

@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    pair = callback.data
    advice, img_path = await analyze_pair(pair)
    photo = FSInputFile(img_path)
    await bot.send_photo(chat_id=callback.message.chat.id, photo=photo, caption=advice)
    await callback.answer()

async def auto_analyze():
    pairs = ["BTCUSDT", "ETHUSDT"]
    while True:
        for pair in pairs:
            try:
                advice, img_path = await analyze_pair(pair)
                if "Сигнал" in advice:
                    photo = FSInputFile(img_path)
                    await bot.send_photo(chat_id=CHAT_ID, photo=photo, caption=advice)
            except Exception as e:
                print(f"Помилка: {e}")
        await asyncio.sleep(300)

async def main():
    asyncio.create_task(auto_analyze())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())