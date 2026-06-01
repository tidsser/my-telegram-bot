import asyncio
import random
import string
import sqlite3
import os
from datetime import datetime
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------- ТВОИ ДАННЫЕ ----------
TOKEN = "8869240435:AAGySmGttt7CEOskqjX7ciBkKgxAR0UEESw"
BOT_USERNAME = "protectionDeals_bot"
MANAGER_USERNAME = "@ManagerProtection"
SUPPORT_USERNAME = "@Protection_D_Support"
PORT = 8080

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- ПОСТОЯННАЯ ПАПКА ДЛЯ БАЗЫ ДАННЫХ ----------
DATA_DIR = "/opt/render/project/src/data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "deals.db")

# ---------- БАЗА ДАННЫХ ----------
conn = sqlite3.connect(DB_PATH)
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

def currency_keyboard_for_req():
    btns = []
    for c in CURRENCIES:
        btns.append([InlineKeyboardButton(text=c, callback_data=f"reqcurr_{c}")])
    btns.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def back_to_main_btn():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])

# ---------- ЗАГЛУШКА ДЛЯ RENDER ----------
async def handle(request):
    return web.Response(text="Bot is running!")

app = web.Application()
app.router.add_get("/", handle)

async def run_web():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web server started on port {PORT}")

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
            if deal:
                seller_id = deal[1]
                current_buyer = deal[2]
                deal_status = deal[6]
                
                if current_buyer and current_buyer != user_id and deal_status != 'waiting_buyer':
                    await message.answer("❌ Сделка недоступна или уже занята.")
                    return
                
                if seller_id == user_id:
                    await message.answer("❌ Вы не можете присоединиться к собственной сделке.")
                    return
                
                cur.execute("UPDATE deals SET buyer_id=?, status='buyer_joined' WHERE id=?",
                            (user_id, int(deal_id)))
                conn.commit()
                
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
                cur.execute("UPDATE deals SET deal_code=? WHERE id=?", (code, int(deal_id)))
                conn.commit()
                
                buyer_username = f"@{username}" if username != "нет" else "без username"
                
                await bot.send_message(seller_id,
                    f"✅ Покупатель присоединился к сделке #{deal_id}\n"
                    f"👤 {buyer_username}\n"
                    f"🔑 Код сделки: {code}")
                
                await message.answer("🔗 Вы успешно присоединились к сделке. Ожидайте подтверждения от продавца.")
                
                await asyncio.sleep(60)
                
                current_deal = cur.execute("SELECT status FROM deals WHERE id=?", (int(deal_id),)).fetchone()
                if current_deal and current_deal[0] == 'buyer_joined':
                    await bot.send_message(seller_id,
                        f"💰 Покупатель успешно перевёл деньги!\n\n"
                        f"📦 Переведите NFT-подарок менеджеру: {MANAGER_USERNAME}\n"
                        f"После проверки вам отправят деньги, а подарок будет отдан покупателю.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Подтвердить отправку подарка",
                                                  callback_data=f"confirm_gift_{deal_id}")]
                        ]))
                return
            else:
                await message.answer("❌ Сделка не найдена.")
        else:
            await message.answer("❌ Неверная ссылка.")
    else:
        await message.answer_video(
            video=types.FSInputFile("116671438_0p.mp4"),
            caption=(
                "👋 Добро пожаловать в protection!\n\n"
                "✨ Надёжный сервис для безопасных сделок!\n\n"
                "🚀 Автоматизировано, быстро и без лишних хлопот!\n\n"
                "💎 Комиссия за услугу: 2%\n"
                f"💎 Менеджер: {MANAGER_USERNAME}\n"
                f"💎 Поддержка: {SUPPORT_USERNAME}\n\n"
                "💌 Теперь ваши сделки под защитой!"
            ),
            reply_markup=main_menu()
        )

# ---------- МОИ РЕКВИЗИТЫ ----------
@dp.callback_query(F.data == "my_req")
async def my_requisites(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    reqs = cur.execute("SELECT currency, card_number FROM requisites WHERE user_id=?", (user_id,)).fetchall()
    if reqs:
        text = "💳 Ваши сохранённые реквизиты:\n\n"
        for currency, card in reqs:
            text += f"• {currency}: {card}\n"
        text += "\nВыберите валюту, чтобы добавить или изменить реквизит:"
    else:
        text = "У вас нет сохранённых реквизитов.\nВыберите валюту, чтобы добавить:"
    
    await state.set_state(RequisiteState.waiting_currency)
    await call.message.answer(text, reply_markup=currency_keyboard_for_req())
    await call.answer()

# ---------- ВЫБОР ВАЛЮТЫ ДЛЯ РЕКВИЗИТОВ ----------
@dp.callback_query(F.data.startswith("reqcurr_"), RequisiteState.waiting_currency)
async def choose_req_currency(call: types.CallbackQuery, state: FSMContext):
    currency = call.data.split("_")[1]
    user_id = call.from_user.id
    
    existing = cur.execute("SELECT card_number FROM requisites WHERE user_id=? AND currency=?",
                          (user_id, currency)).fetchone()
    if existing:
        hint = f"У вас уже сохранён реквизит: {existing[0]}\nВведите новый номер карты для {currency}:"
    else:
        hint = f"Введите номер карты для {currency}:"
    
    await state.update_data(currency=currency)
    await state.set_state(RequisiteState.waiting_card)
    await call.message.answer(hint, reply_markup=back_to_main_btn())
    await call.answer()

# ---------- ВЫБОР ВАЛЮТЫ ДЛЯ СДЕЛКИ ----------
@dp.callback_query(F.data.startswith("curr_"))
async def choose_deal_currency(call: types.CallbackQuery, state: FSMContext):
    currency = call.data.split("_")[1]
    user_id = call.from_user.id
    req = cur.execute("SELECT card_number FROM requisites WHERE user_id=? AND currency=?",
                      (user_id, currency)).fetchone()
    if not req:
        await call.answer("❌ У вас нет привязанного реквизита для этой валюты!\nСначала добавьте реквизит в разделе «Мои реквизиты».", show_alert=True)
        return
    await state.update_data(currency=currency)
    await state.set_state(DealState.waiting_amount)
    await call.message.answer(f"💳 Ваша карта: {req[0]}\n\nВведите сумму сделки:", reply_markup=back_to_main_btn())
    await call.answer()

# ---------- СОХРАНЕНИЕ КАРТЫ ----------
@dp.message(RequisiteState.waiting_card)
async def save_card(message: types.Message, state: FSMContext):
    data = await state.get_data()
    currency = data["currency"]
    user_id = message.from_user.id
    card = message.text.strip()
    
    cur.execute("REPLACE INTO requisites (user_id, currency, card_number) VALUES (?, ?, ?)",
                (user_id, currency, card))
    conn.commit()
    
    reqs = cur.execute("SELECT currency, card_number FROM requisites WHERE user_id=?", (user_id,)).fetchall()
    text = f"✅ Реквизит для {currency} сохранён!\n\n💳 Все ваши реквизиты:\n"
    for curr, c in reqs:
        text += f"• {curr}: {c}\n"
    
    await message.answer(text, reply_markup=main_menu())
    await state.clear()

# ---------- СОЗДАТЬ СДЕЛКУ ----------
@dp.callback_query(F.data == "create_deal")
async def create_deal(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(DealState.waiting_currency)
    await call.message.answer("Выберите валюту для сделки:", reply_markup=currency_keyboard())
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
        f"🎊 Ссылка для покупателя:\n<a href='{link}'>{link}</a>",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await state.clear()

# ---------- ПОДТВЕРЖДЕНИЕ ОТПРАВКИ ПОДАРКА ----------
@dp.callback_query(F.data.startswith("confirm_gift_"))
async def confirm_gift(call: types.CallbackQuery):
    deal_id = int(call.data.split("_")[2])
    cur.execute("UPDATE deals SET status='sent_to_manager' WHERE id=?", (deal_id,))
    conn.commit()
    await call.message.answer("📦 Менеджер проверяет сделку. Ожидайте уведомления.")
    await call.answer()

# ---------- МОИ СДЕЛКИ ----------
@dp.callback_query(F.data == "my_deals")
async def my_deals(call: types.CallbackQuery):
    user_id = call.from_user.id
    deals = cur.execute("SELECT COUNT(*), SUM(amount) FROM deals WHERE seller_id=? OR buyer_id=?",
                        (user_id, user_id)).fetchone()
    count = deals[0] if deals[0] else 0
    total = deals[1] if deals[1] else 0
    await call.message.answer(
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
        await call.message.answer(
            "🎉 Вы подключены к партнёрской программе!\n\n"
            "Скоро здесь появится информация о ваших рефералах и бонусах.",
            reply_markup=back_to_main_btn()
        )
    await call.answer()

# ---------- ПОДДЕРЖКА ----------
@dp.callback_query(F.data == "support")
async def support(call: types.CallbackQuery):
    await call.message.answer(
        f"🆘 Поддержка: {SUPPORT_USERNAME}\n"
        f"👤 Менеджер: {MANAGER_USERNAME}",
        reply_markup=back_to_main_btn()
    )
    await call.answer()

# ---------- НАЗАД ----------
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(
        "👋 Добро пожаловать в protection!\n\n"
        "✨ Надёжный сервис для безопасных сделок!\n\n"
        "🚀 Автоматизировано, быстро и без лишних хлопот!\n\n"
        "💎 Комиссия за услугу: 2%\n"
        f"💎 Менеджер: {MANAGER_USERNAME}\n"
        f"💎 Поддержка: {SUPPORT_USERNAME}\n\n"
        "💌 Теперь ваши сделки под защитой!",
        reply_markup=main_menu()
    )
    await call.answer()

# ---------- ЗАПУСК ----------
async def main():
    print("Бот запущен!")
    await asyncio.gather(
        run_web(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
