import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from binance import Client
import pandas as pd
import numpy as np

API_TOKEN = '8064418325:AAFshIlqpz79-0RUcxXOqj1C5jUqqaUFeDY'
BINANCE_API_KEY = 'rJ2AoAMMI2hiz6osor7L3GW5bvNK4AJv62dymXxs5MWUwl73bTsjSpvzDhEioN2e'
BINANCE_SECRET_KEY = 'qENg4zUki2EB8xT3o7zSSEA0VnfTFv2DpOA9jiHSv6S4ETN3Iqs2IveO53Xls0VE'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTCUSDT", callback_data="BTCUSDT")],
        [InlineKeyboardButton(text="ETHUSDT", callback_data="ETHUSDT")],
        [InlineKeyboardButton(text="XAUUSDT (Золото)", callback_data="XAUUSDT")],
    ])
    await message.reply("Вибери пару для аналізу:", reply_markup=keyboard)

async def analyze_pair(pair: str) -> str:
    klines = binance_client.get_klines(symbol=pair, interval=Client.KLINE_INTERVAL_1HOUR, limit=100)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                       'close_time', 'quote_asset_volume', 'trades', 
                                       'taker_buy_base', 'taker_buy_quote', 'ignored'])
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
    prices = df['close']
    current_price = prices.iloc[-1]

    sma20 = prices.rolling(window=20).mean().iloc[-1]
    sma50 = prices.rolling(window=50).mean().iloc[-1]
    trend = "висхідний" if sma20 > sma50 else "низхідний" if sma20 < sma50 else "боковий"

    support = prices.min()
    resistance = prices.max()
    last_move = resistance - support
    fib_618 = support + last_move * 0.618

    high_low = df['high'] - df['low']
    atr = high_low.rolling(window=14).mean().iloc[-1]

    if trend == "висхідний" and current_price < sma20 + atr:
        entry = current_price + atr * 0.5
        sl = current_price - atr * 1.5
        tp = current_price + atr * 3
        advice = (
            f"Пара: {pair}\n"
            f"Тренд: висхідний (SMA20: {sma20:.2f} > SMA50: {sma50:.2f})\n"
            f"Ціна: ${current_price:.2f}\n"
            f"Вхід: ${entry:.2f}\nSL: ${sl:.2f}\nTP: ${tp:.2f}\n"
            f"Ризик/прибуток: {(tp - entry) / (entry - sl):.2f}:1"
        )
    elif trend == "низхідний" and current_price > sma20 - atr:
        entry = current_price - atr * 0.5
        sl = current_price + atr * 1.5
        tp = current_price - atr * 3
        advice = (
            f"Пара: {pair}\n"
            f"Тренд: низхідний (SMA20: {sma20:.2f} < SMA50: {sma50:.2f})\n"
            f"Ціна: ${current_price:.2f}\n"
            f"Вхід: ${entry:.2f}\nSL: ${sl:.2f}\nTP: ${tp:.2f}\n"
            f"Ризик/прибуток: {(entry - tp) / (sl - entry):.2f}:1"
        )
    else:
        advice = f"Пара: {pair}\nЦіна: ${current_price:.2f}\nНемає чіткого сигналу."
    return advice

@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    pair = callback.data
    advice = await analyze_pair(pair)
    await callback.message.answer(advice)
    await callback.answer()

async def auto_analyze():
    pairs = ["BTCUSDT", "ETHUSDT", "XAUUSDT"]
    while True:
        for pair in pairs:
            try:
                advice = await analyze_pair(pair)
                if "Вхід" in advice:
                    await bot.send_message(chat_id=1002623933177, text=advice)
            except Exception as e:
                print(f"Помилка: {e}")
        await asyncio.sleep(300)

async def main():
    asyncio.create_task(auto_analyze())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())