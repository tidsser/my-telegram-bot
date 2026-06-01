import asyncio
import random
import string
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------- ТВОИ ДАННЫЕ ----------
TOKEN = "8869240435:AAE0bpAu-73zinTvPiwZeC6cCCs2pJccPyo"
BOT_USERNAME = "protectionDeals_bot"
MANAGER_USERNAME = "@protectionManager"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- БАЗА ДАННЫХ ----------
conn = sqlite3.connect("deals.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS requisites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    currency TEXT,
    card_number TEXT,
    UNIQUE(user_id, currency)
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER,
    buyer_id INTEGER,
    currency TEXT,
    amount REAL,
    description TEXT,
    status TEXT DEFAULT 'waiting_buyer',
    deal_code TEXT,
    created_at TEXT
)
""")
conn.commit()

# ---------- Валюты СНГ ----------
CURRENCIES = ["RUB", "KZT", "UAH", "KGS", "EUR", "USD"]

# ---------- Состояния (FSM) ----------
class RequisiteState(StatesGroup):
    waiting_currency = State()
    waiting_card = State()

class DealState(StatesGroup):
    waiting_currency = State()
    waiting_amount = State()
    waiting_description = State()

# ---------- КЛАВИАТУРЫ ----------
def main_menu():
    buttons = [
        [InlineKeyboardButton(text="💳 Мои реквизиты", callback_data="my_req")],
        [InlineKeyboardButton(text="🤝 Создать сделку", callback_data="create_deal")],
        [InlineKeyboardButton(text="📊 Мои сделки", callback_data="my_deals")],
        [InlineKeyboardButton(text="👥 Партнёрская программа", callback_data="partner")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def currency_keyboard():
    btns = []
    for c in CURRENCIES:
        btns.append([InlineKeyboardButton(text=c, callback_data=f"curr_{c}")])
    btns.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def back_to_main_btn():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])

# ---------- ОБРАБОТЧИК /start ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username or "нет"
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

    args = command.args
    if args and args.startswith("deal_"):
        deal_id = args.split("_")[1]
        if deal_id.isdigit():
            deal = cur.execute("SELECT * FROM deals WHERE id=?", (int(deal_id),)).fetchone()
            if deal and deal[6] == 'waiting_buyer' and deal[1] != user_id:
                cur.execute("UPDATE deals SET buyer_id=?, status='buyer_joined' WHERE id=?",
                            (user_id, int(deal_id)))
                conn.commit()
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
                cur.execute("UPDATE deals SET deal_code=? WHERE id=?", (code, int(deal_id)))
                conn.commit()
                buyer_name = message.from_user.full_name
                await bot.send_message(deal[1],
                    f"✅ Покупатель присоединился к сделке #{deal_id}\n"
                    f"👤 {buyer_name} (@{username})\n"
                    f"🔑 Код сделки: {code}")
                await asyncio.sleep(30)
                await bot.send_message(deal[1],
                    f"💰 Покупатель оплатил!\n"
                    f"📦 Отправьте NFT-подарок менеджеру на проверку: {MANAGER_USERNAME}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Подтвердить отправку подарка",
                                              callback_data=f"confirm_gift_{deal_id}")]
                    ]))
                await message.answer("🔗 Вы успешно присоединились к сделке. Ожидайте подтверждения от продавца.")
                return
            else:
                await message.answer("❌ Сделка недоступна или уже занята.")
        else:
            await message.answer("❌ Неверная ссылка.")
    else:
        # Приветствие с видео
        await message.answer_video(
            video=types.FSInputFile("116671438_0p.mp4"),
            caption=(
                "👋 Добро пожаловать в protection!\n\n"
                "✨ Надёжный сервис для безопасных сделок!\n\n"
                "🚀 Автоматизировано, быстро и без лишних хлопот!\n\n"
                "💎 Комиссия за услугу: 2%\n"
                "💎 Поддержка: @protectionManager\n\n"
                "💌 Теперь ваши сделки под защитой!"
            ),
            reply_markup=main_menu()
        )

# ---------- ОБРАБОТКА КНОПОК ГЛАВНОГО МЕНЮ ----------
@dp.callback_query(F.data == "my_req")
async def my_requisites(call: types.CallbackQuery):
    await call.message.edit_text("Выберите валюту для реквизитов:", reply_markup=currency_keyboard())
    await call.answer()

@dp.callback_query(F.data.startswith("curr_"))
async def choose_currency(call: types.CallbackQuery, state: FSMContext):
    currency = call.data.split("_")[1]
    current_state = await state.get_state()
    if current_state is None:
        await state.update_data(currency=currency)
        await state.set_state(RequisiteState.waiting_card)
        await call.message.edit_text(f"Введите номер карты для {currency}:", reply_markup=back_to_main_btn())
    else:
        user_id = call.from_user.id
        req = cur.execute("SELECT * FROM requisites WHERE user_id=? AND currency=?",
                          (user_id, currency)).fetchone()
        if not req:
            await call.answer("У вас нет привязанного реквизита для этой валюты!", show_alert=True)
            return
        await state.update_data(currency=currency)
        await state.set_state(DealState.waiting_amount)
        await call.message.edit_text("Введите сумму сделки:", reply_markup=back_to_main_btn())
    await call.answer()

@dp.message(RequisiteState.waiting_card)
async def save_card(message: types.Message, state: FSMContext):
    data = await state.get_data()
    currency = data["currency"]
    user_id = message.from_user.id
    card = message.text.strip()
    cur.execute("REPLACE INTO requisites (user_id, currency, card_number) VALUES (?, ?, ?)",
                (user_id, currency, card))
    conn.commit()
    await message.answer(f"✅ Реквизиты для {currency} сохранены!", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "create_deal")
async def create_deal(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(DealState.waiting_currency)
    await call.message.edit_text("Выберите валюту для сделки:", reply_markup=currency_keyboard())
    await call.answer()

@dp.message(DealState.waiting_amount)
async def deal_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    await state.update_data(amount=amount)
    await state.set_state(DealState.waiting_description)
    await message.answer("Опишите, что вы предлагаете в сделке (например: три банана и яблоко):",
                         reply_markup=back_to_main_btn())

@dp.message(DealState.waiting_description)
async def deal_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    currency = data["currency"]
    amount = data["amount"]
    description = message.text
    user_id = message.from_user.id

    cur.execute("INSERT INTO deals (seller_id, currency, amount, description, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, currency, amount, description, datetime.now().isoformat()))
    deal_id = cur.lastrowid
    conn.commit()

    link = f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"
    await message.answer(
        f"✅ Сделка успешно создана!\n\n"
        f"Тип сделки: 🎁 Подарки\n\n"
        f"Отдаёте: {description}\n"
        f"Получаете: {amount} {currency}\n\n"
        f"🎊 Ссылка для покупателя:\n{link}",
        reply_markup=main_menu()
    )
    await state.clear()

# ---------- ПОДТВЕРЖДЕНИЕ ОТПРАВКИ ПОДАРКА ----------
@dp.callback_query(F.data.startswith("confirm_gift_"))
async def confirm_gift(call: types.CallbackQuery):
    deal_id = int(call.data.split("_")[2])
    cur.execute("UPDATE deals SET status='sent_to_manager' WHERE id=?", (deal_id,))
    conn.commit()
    await call.message.edit_text("📦 Менеджер проверяет сделку. Ожидайте уведомления.")
    await call.answer()

# ---------- МОИ СДЕЛКИ ----------
@dp.callback_query(F.data == "my_deals")
async def my_deals(call: types.CallbackQuery):
    user_id = call.from_user.id
    deals = cur.execute("SELECT COUNT(*), SUM(amount) FROM deals WHERE seller_id=? OR buyer_id=?",
                        (user_id, user_id)).fetchone()
    count = deals[0] if deals[0] else 0
    total = deals[1] if deals[1] else 0
    await call.message.edit_text(
        f"📊 Ваша статистика:\n"
        f"🔹 Количество сделок: {count}\n"
        f"💰 Общая сумма: {total:.2f}",
        reply_markup=back_to_main_btn()
    )
    await call.answer()

# ---------- ПАРТНЁРСКАЯ ПРОГРАММА ----------
@dp.callback_query(F.data == "partner")
async def partner_program(call: types.CallbackQuery):
    user_id = call.from_user.id
    deals_count = cur.execute(
        "SELECT COUNT(*) FROM deals WHERE seller_id=? AND status='sent_to_manager'",
        (user_id,)
    ).fetchone()[0]

    if deals_count < 5:
        await call.answer(
            f"❌ Для подключения партнёрской программы нужно минимум 5 сделок. У вас пока {deals_count}.",
            show_alert=True
        )
    else:
        await call.message.edit_text(
            "🎉 Вы подключены к партнёрской программе!\n\n"
            "Скоро здесь появится информация о ваших рефералах и бонусах.",
            reply_markup=back_to_main_btn()
        )
    await call.answer()

# ---------- ПОДДЕРЖКА ----------
@dp.callback_query(F.data == "support")
async def support(call: types.CallbackQuery):
    await call.message.edit_text(f"🆘 Поддержка: {MANAGER_USERNAME}", reply_markup=back_to_main_btn())
    await call.answer()

# ---------- НАЗАД ----------
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "👋 Добро пожаловать в protection!\n\n"
        "✨ Надёжный сервис для безопасных сделок!\n\n"
        "🚀 Автоматизировано, быстро и без лишних хлопот!\n\n"
        "💎 Комиссия за услугу: 2%\n"
        "💎 Поддержка: @protectionManager\n\n"
        "💌 Теперь ваши сделки под защитой!",
        reply_markup=main_menu()
    )
    await call.answer()

# ---------- ЗАПУСК ----------
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
