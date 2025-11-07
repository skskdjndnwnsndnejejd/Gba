#!/usr/bin/env python3
# main.py — Gift Castle (aiogram 3.x)
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, Text
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# ---------------- CONFIG ----------------
BOT_TOKEN = __import__("os").environ.get("BOT_TOKEN")
OWNER_ID = 6828395702  # владелец бота для команды /gb
PHOTO_ID = "AgACAgIAAxkBAAMEaQ4BT_HrLKNH6naa15zKYnt8z6UAAjsPaxuAI3BI-o-YrxQPN8gBAAMCAAN4AAM2BA"
DATA_FILE = Path("data.json")
# ----------------------------------------

if not BOT_TOKEN:
    raise SystemExit("Ошибка: переменная окружения BOT_TOKEN не задана")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
dp = Dispatcher(storage=MemoryStorage())

# ----------------- Helpers -----------------
def load_data() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        default = {"users": {}, "deals": {}, "chats": {}}
        DATA_FILE.write_text(json.dumps(default, ensure_ascii=False, indent=2))
        return default
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

def save_data(data: Dict[str, Any]):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

DATA = load_data()

def ensure_user(uid: int):
    uid_s = str(uid)
    if uid_s not in DATA["users"]:
        DATA["users"][uid_s] = {"balance": 0.0, "username": None}
        save_data(DATA)

def gen_deal_id() -> str:
    # Формат: #A123 где буква A..Z случайная, число 1..999999
    import random, string
    letter = random.choice(string.ascii_uppercase)
    number = random.randint(1, 999999)
    return f"#{letter}{number}"

def valid_deal_id_format(did: str) -> bool:
    # ожидаем латинскую букву и 1-6 цифр, с # впереди
    return bool(re.fullmatch(r"#[A-Z]\d{1,6}", did))

def get_chat_record(chat_id: int) -> Dict[str, Any]:
    k = str(chat_id)
    return DATA["chats"].get(k, {})

def set_last_message(chat_id: int, message_id: int):
    DATA["chats"][str(chat_id)] = {"last_message_id": message_id}
    save_data(DATA)

def get_last_message_id(chat_id: int) -> int | None:
    rec = DATA["chats"].get(str(chat_id), {})
    return rec.get("last_message_id")

# ----------------- FSM States -----------------
class SellerStates(StatesGroup):
    waiting_type = State()
    waiting_name = State()
    waiting_description = State()
    waiting_price = State()

class BuyerStates(StatesGroup):
    waiting_deal_id = State()

# ----------------- Keyboards -----------------
def kb_start_continue():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продолжить", callback_data="start_continue")]
    ])
    return kb

def kb_main():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛡️ Создать сделку", callback_data="create_deal"),
            InlineKeyboardButton(text="💰 Баланс", callback_data="show_balance")
        ],
        [InlineKeyboardButton(text="❓ Помощь", url="https://t.me/GiftCastleRelayer")]
    ])
    return kb

def kb_role_choice():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧑‍💼 Продавец", callback_data="role_seller"),
         InlineKeyboardButton(text="🧑‍💻 Покупатель", callback_data="role_buyer")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="go_back_main")]
    ])
    return kb

def kb_deal_actions():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продолжить ✔️", callback_data="deal_continue"),
         InlineKeyboardButton(text="Отмена ❌", callback_data="deal_cancel")]
    ])
    return kb

def kb_after_create_to_share(deal_id: str):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить покупателю", switch_inline_query=deal_id)],
        [InlineKeyboardButton(text="↩️ Вернуться в меню", callback_data="go_back_main")]
    ])
    return kb

def kb_in_process_for_seller():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Товар Передан", callback_data="item_transferred")]
    ])
    return kb

def kb_wait_buyer_confirm():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я получил товар — Продолжить", callback_data="buyer_confirm_receive")]
    ])
    return kb

def kb_balance_withdraw():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запросить вывод", url="https://t.me/GiftCastleRelayer")],
        [InlineKeyboardButton(text="↩️ Вернуться в меню", callback_data="go_back_main")]
    ])
    return kb

# ----------------- Messaging Content -----------------
def start_welcome_text(username: str) -> str:
    # >=20 words, Markdown formatting
    text = (
        f"👋 *Здравствуйте, {username}!*  \n\n"
        "_Добро пожаловать в официальный гарантийный сервис Gift Castle!_  \n\n"
        "В нашем уютном и надёжном пространстве мы внимательно сопровождаем каждую сделку, "
        "обеспечиваем безопасность участников, контролируем передачу товара и финальные расчёты, "
        "а также предоставляем оперативную поддержку при необходимости. Доверяйте процессу — "
        "ваши интересы находятся под надёжной защитой Gift Castle."
    )
    return text

def intro_screen_text() -> str:
    text = (
        "🏰 *Gift Castle — ваш надёжный партнёр в торговле на платформе Telegram!*  \n\n"
        "🔒 _Ваши сделки находятся под строгим контролем и проводятся по принципу escrow_, "
        "что исключает риск непредвиденных потерь и гарантирует справедливое завершение операции. "
        "Бот размещён на надёжном хостинге и работает стабильно, без лишних задержек — "
        "мы ценим ваше время и репутацию."
    )
    return text

# ----------------- Handlers -----------------
@dp.message(Command(commands=["start"]))
async def cmd_start(m: Message, state: FSMContext):
    ensure_user(m.from_user.id)
    DATA["users"][str(m.from_user.id)]["username"] = m.from_user.username or m.from_user.full_name
    save_data(DATA)

    caption = start_welcome_text("@" + (m.from_user.username or m.from_user.full_name))
    # send photo and save last message id to edit in future
    sent = await bot.send_photo(
        chat_id=m.chat.id,
        photo=PHOTO_ID,
        caption=caption,
        reply_markup=kb_start_continue()
    )
    set_last_message(m.chat.id, sent.message_id)

@dp.callback_query(Text("start_continue"))
async def on_start_continue(c: CallbackQuery):
    await c.answer()
    caption = "*🎖️ Gift Castle — Эталон безопасных сделок!*  \n\n"
    caption += intro_screen_text()
    # include small decorative line and buttons
    last_id = get_last_message_id(c.message.chat.id)
    try:
        await bot.edit_message_caption(
            chat_id=c.message.chat.id,
            message_id=last_id or c.message.message_id,
            caption=caption,
            reply_markup=kb_main()
        )
        set_last_message(c.message.chat.id, last_id or c.message.message_id)
    except Exception:
        # fallback: send new
        sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_main())
        set_last_message(c.message.chat.id, sent.message_id)

@dp.callback_query(Text("go_back_main"))
async def go_back(c: CallbackQuery):
    await c.answer()
    caption = intro_screen_text()
    last_id = get_last_message_id(c.message.chat.id)
    try:
        await bot.edit_message_caption(chat_id=c.message.chat.id, message_id=last_id or c.message.message_id, caption=caption, reply_markup=kb_main())
        set_last_message(c.message.chat.id, last_id or c.message.message_id)
    except Exception:
        sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_main())
        set_last_message(c.message.chat.id, sent.message_id)

# ----- Create deal flow -----
@dp.callback_query(Text("create_deal"))
async def create_deal_cb(c: CallbackQuery):
    await c.answer()
    caption = "📝 *Создание сделки*  \n\n• Пожалуйста, выберите роль в сделке для её создания.  \n\n" \
              "_Сделка — это соглашение между сторонами, направленное на передачу товара и оплату. " \
              "Выберите роль, чтобы начать процесс._"
    last_id = get_last_message_id(c.message.chat.id)
    try:
        await bot.edit_message_caption(chat_id=c.message.chat.id, message_id=last_id or c.message.message_id, caption=caption, reply_markup=kb_role_choice())
        set_last_message(c.message.chat.id, last_id or c.message.message_id)
    except Exception:
        sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_role_choice())
        set_last_message(c.message.chat.id, sent.message_id)

# Seller path
@dp.callback_query(Text("role_seller"))
async def role_seller(c: CallbackQuery):
    await c.answer()
    caption = "🧑‍💼 *Продавец*  \n\nПродавец — сторона, которая обязуется передать товар в собственность покупателя и получить за него плату.  \n\n" \
              "Нажмите *Продолжить*, чтобы задать параметры товара и создать сделку."
    last_id = get_last_message_id(c.message.chat.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продолжить", callback_data="seller_start")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="go_back_main")]
    ])
    try:
        await bot.edit_message_caption(chat_id=c.message.chat.id, message_id=last_id or c.message.message_id, caption=caption, reply_markup=kb)
        set_last_message(c.message.chat.id, last_id or c.message.message_id)
    except Exception:
        sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb)
        set_last_message(c.message.chat.id, sent.message_id)

@dp.callback_query(Text("seller_start"))
async def seller_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(SellerStates.waiting_type)
    await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID,
                         caption="🧾 *Продавец — создание лота*  \n\nПожалуйста, введите *тип товара* (например: NFT).  \n\n_Укажите точный тип, чтобы покупатель понимал предмет сделки._")

@dp.message(SellerStates.waiting_type)
async def seller_receive_type(m: Message, state: FSMContext):
    await state.update_data(item_type=m.text.strip())
    await state.set_state(SellerStates.waiting_name)
    await m.reply("📛 *Введите название товара* — напишите короткое и понятное имя товара.", reply=False)

@dp.message(SellerStates.waiting_name)
async def seller_receive_name(m: Message, state: FSMContext):
    await state.update_data(item_name=m.text.strip())
    await state.set_state(SellerStates.waiting_description)
    await m.reply("✍️ *Введите описание товара* — подробное описание, чтобы покупатель видел что получает.", reply=False)

@dp.message(SellerStates.waiting_description)
async def seller_receive_description(m: Message, state: FSMContext):
    await state.update_data(item_description=m.text.strip())
    await state.set_state(SellerStates.waiting_price)
    await m.reply("💵 *Введите стоимость товара в ₽* — цифрами, без символов.", reply=False)

@dp.message(SellerStates.waiting_price)
async def seller_receive_price(m: Message, state: FSMContext):
    txt = m.text.strip().replace(",", ".")
    try:
        price = float(re.sub(r"[^\d.]", "", txt))
    except Exception:
        await m.reply("⚠️ Неверный формат суммы. Введите только числа, например: 1234 или 1234.56", reply=False)
        return
    data = await state.get_data()
    deal_id = gen_deal_id()
    seller_uid = m.from_user.id
    ensure_user(seller_uid)
    DATA["deals"][deal_id] = {
        "id": deal_id,
        "type": data.get("item_type"),
        "name": data.get("item_name"),
        "description": data.get("item_description"),
        "price": price,
        "seller_id": seller_uid,
        "seller_username": m.from_user.username or m.from_user.full_name,
        "buyer_id": None,
        "status": "open"  # open -> in_process -> transferred -> completed or cancelled
    }
    save_data(DATA)
    await state.clear()
    caption = f"✅ *Сделка {deal_id} успешно создана!*  \n\n• *Тип товара:* {DATA['deals'][deal_id]['type']}  \n• *Название товара:* {DATA['deals'][deal_id]['name']}  \n• *Описание:* {DATA['deals'][deal_id]['description']}  \n• *Цена:* {DATA['deals'][deal_id]['price']} ₽  \n\nОтправьте покупателю номер сделки для присоединения — он подключится к операции и процесс пойдёт дальше."
    sent = await bot.send_photo(chat_id=m.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_after_create_to_share(deal_id))
    set_last_message(m.chat.id, sent.message_id)

# Buyer path
@dp.callback_query(Text("role_buyer"))
async def role_buyer(c: CallbackQuery):
    await c.answer()
    await BuyerStates.waiting_deal_id.set()
    # ask for deal id
    sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID,
                         caption="🧾 *Покупатель*  \n\nВведите номер сделки в формате `#A123` для присоединения к сделке.  \n\n_Пример: #A1, #B12, #C1234 — буква латинская + 1–6 цифр._")
    set_last_message(c.message.chat.id, sent.message_id)

@dp.message(BuyerStates.waiting_deal_id)
async def buyer_enter_deal_id(m: Message, state: FSMContext):
    text = m.text.strip().upper()
    if not valid_deal_id_format(text):
        await m.reply("❗ Формат номера сделки неверный. Пример правильного формата: `#A123` — латинская буква и 1–6 цифр.", parse_mode="Markdown")
        return
    if text not in DATA["deals"]:
        await m.reply("⚠️ Сделка с таким номером не найдена. Проверьте корректность и попробуйте снова.")
        return
    deal = DATA["deals"][text]
    if deal["status"] != "open":
        await m.reply("ℹ️ Эта сделка уже не доступна для присоединения — проверьте статус у продавца.")
        return
    buyer_uid = m.from_user.id
    ensure_user(buyer_uid)
    # show deal summary with actions
    caption = (
        f"*Сделка {text}*  \n\n"
        f"👨‍💼 *Продавец:* @{deal['seller_username']}  \n"
        f"✅ *Товар:* \"{deal['name']}\"  \n"
        f"🗒️ *Описание:* {deal['description']}  \n"
        f"💵 *Стоимость:* {deal['price']} ₽  \n\n"
        "Для продолжения нажмите *Продолжить ✔️*, для отмены — *Отмена ❌*."
    )
    # store buyer choice in temp session
    await state.update_data(joining_deal=text)
    sent = await bot.send_photo(chat_id=m.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_deal_actions())
    set_last_message(m.chat.id, sent.message_id)

@dp.callback_query(Text("deal_continue"))
async def buyer_continue_cb(c: CallbackQuery, state: FSMContext):
    await c.answer()
    ctx = await state.get_data()
    deal_id = ctx.get("joining_deal")
    if not deal_id or deal_id not in DATA["deals"]:
        await bot.send_message(chat_id=c.from_user.id, text="Ошибка: данные о сделке потеряны. Попробуйте снова.")
        await state.clear()
        return
    deal = DATA["deals"][deal_id]
    buyer_uid = c.from_user.id
    ensure_user(buyer_uid)
    buyer_balance = DATA["users"][str(buyer_uid)]["balance"]
    price = float(deal["price"])
    if buyer_balance < price:
        caption = "⚠️ *Ошибка:* Недостаточно средств для продолжения сделки.  \n\n" \
                  "Пожалуйста, пополните баланс или свяжитесь с поддержкой для уточнений."
        await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_balance_withdraw())
        return
    # списываем средства с покупателя (виртуально) и переводим в эскроу (внутр. поле)
    DATA["users"][str(buyer_uid)]["balance"] = round(buyer_balance - price, 6)
    deal["buyer_id"] = buyer_uid
    deal["buyer_username"] = c.from_user.username or c.from_user.full_name
    deal["status"] = "in_process"
    # эскроу: сохраняем в поле escrow_amount (виртуально)
    deal["escrow_amount"] = price
    save_data(DATA)

    # уведомления
    caption = f"💳 *Покупатель присоединился к сделке {deal_id}!*  \n\n" \
              f"Вы присоединились к сделке {deal_id}; ожидайте ответа от продавца. " \
              f"Средства в размере *{price} ₽* зарезервированы в гарант-аккаунте до подтверждения передачи товара."
    sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption)
    set_last_message(c.message.chat.id, sent.message_id)

    # уведомить продавца в личку (если доступно)
    seller_id = deal["seller_id"]
    try:
        caption2 = f"🔔 *Уведомление:* @{deal.get('buyer_username','покупатель')} присоединился к сделке {deal_id}.  \n\n" \
                   "Для продолжения передайте товар поддержке @GiftCastleRelayer и нажмите кнопку *Товар Передан*."
        await bot.send_photo(chat_id=seller_id, photo=PHOTO_ID, caption=caption2, reply_markup=kb_in_process_for_seller())
    except Exception:
        # не критично, можно не доставить
        pass

@dp.callback_query(Text("deal_cancel"))
async def deal_cancel_cb(c: CallbackQuery, state: FSMContext):
    await c.answer("Вы отменили продолжение сделки; вернитесь в меню.", show_alert=False)
    await state.clear()
    caption = "Вы отменили продолжение сделки. Возвращайтесь в меню и начните заново, когда будете готовы."
    sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_main())
    set_last_message(c.message.chat.id, sent.message_id)

# Seller confirms transferred to support
@dp.callback_query(Text("item_transferred"))
async def seller_transferred_cb(c: CallbackQuery):
    await c.answer()
    # find deal where this seller has in_process status
    seller_id = c.from_user.id
    # find the most recent in_process deal by this seller (simplified)
    deal = None
    for d in DATA["deals"].values():
        if d["seller_id"] == seller_id and d["status"] == "in_process":
            deal = d
            break
    if not deal:
        await bot.send_message(chat_id=c.from_user.id, text="ℹ️ Сделка в статусе 'в процессе' не найдена. Возможно, она уже обработана.")
        return
    deal_id = deal["id"]
    deal["status"] = "transferred"
    save_data(DATA)
    # notify buyer
    buyer_id = deal.get("buyer_id")
    if buyer_id:
        caption = f"📦 *Сделка {deal_id} — Товар передан!*  \n\nПродавец подтвердил передачу товара поддержке. " \
                  "После получения товара нажмите кнопку *Я получил товар — Продолжить*, чтобы завершить сделку и освободить средства продавцу."
        try:
            sent = await bot.send_photo(chat_id=buyer_id, photo=PHOTO_ID, caption=caption, reply_markup=kb_wait_buyer_confirm())
            set_last_message(buyer_id, sent.message_id)
        except Exception:
            pass
    # confirm to seller
    await bot.send_message(chat_id=c.from_user.id, text=f"✅ Вы подтвердили передачу товара по сделке {deal_id}. Ожидайте подтверждения от покупателя.")

# Buyer confirms receipt -> complete deal
@dp.callback_query(Text("buyer_confirm_receive"))
async def buyer_confirm_cb(c: CallbackQuery):
    await c.answer()
    # find deal by this buyer with status transferred
    buyer_id = c.from_user.id
    deal = None
    for d in DATA["deals"].values():
        if d.get("buyer_id") == buyer_id and d["status"] == "transferred":
            deal = d
            break
    if not deal:
        await bot.send_message(chat_id=c.from_user.id, text="ℹ️ Подтверждаемых сделок не найдено. Проверьте статусы.")
        return
    deal_id = deal["id"]
    amount = float(deal.get("escrow_amount", 0.0))
    seller_id = deal["seller_id"]
    # credit seller balance
    ensure_user(seller_id)
    DATA["users"][str(seller_id)]["balance"] = round(DATA["users"][str(seller_id)]["balance"] + amount, 6)
    deal["status"] = "completed"
    # cleanup escrow
    deal["escrow_amount"] = 0.0
    save_data(DATA)

    # notify both
    try:
        await bot.send_photo(chat_id=seller_id, photo=PHOTO_ID,
                             caption=f"🎉 *Сделка {deal_id} успешно завершена!*  \n\nТовар доставлен, средства в размере *{amount} ₽* зачислены на ваш баланс.")
    except Exception:
        pass
    await bot.send_photo(chat_id=c.from_user.id, photo=PHOTO_ID,
                         caption=f"✅ *Сделка {deal_id} завершена!*  \n\nСпасибо за сделку — средства переведены продавцу, баланс обновлён.")

# ----- Balance flow -----
@dp.callback_query(Text("show_balance"))
async def show_balance_cb(c: CallbackQuery):
    await c.answer()
    uid = c.from_user.id
    ensure_user(uid)
    bal = DATA["users"][str(uid)]["balance"]
    caption = f"💰 *Ваш баланс: {bal} TON*  \n\n" \
              "Это внутренний баланс бота Gift Castle, предназначенный для взаимодействия в рамках сделок и управления расчетами. " \
              "Для вывода средств обратитесь в поддержку и ожидайте ответ от наших сотрудников."
    last_id = get_last_message_id(c.message.chat.id)
    try:
        await bot.edit_message_caption(chat_id=c.message.chat.id, message_id=last_id or c.message.message_id, caption=caption, reply_markup=kb_balance_withdraw())
        set_last_message(c.message.chat.id, last_id or c.message.message_id)
    except Exception:
        sent = await bot.send_photo(chat_id=c.message.chat.id, photo=PHOTO_ID, caption=caption, reply_markup=kb_balance_withdraw())
        set_last_message(c.message.chat.id, sent.message_id)

# ----- Owner command: /gb id сумма -----
@dp.message(Command(commands=["gb"]))
async def cmd_gb(m: Message):
    if m.from_user.id != OWNER_ID:
        await m.reply("_Команда доступна только владельцу бота._")
        return
    parts = m.text.split()
    if len(parts) != 3:
        await m.reply("Использование: /gb <user_id> <сумма>\nПример: /gb 123456789 10.5")
        return
    try:
        target_id = int(parts[1])
        amount = float(parts[2])
    except Exception:
        await m.reply("Неверный формат. ID должен быть числом, сумма — число (может содержать точку).")
        return
    ensure_user(target_id)
    DATA["users"][str(target_id)]["balance"] = round(DATA["users"][str(target_id)]["balance"] + amount, 6)
    save_data(DATA)
    await m.reply(f"✅ Баланс пользователя {target_id} успешно изменён на +{amount} TON. Текущий баланс: {DATA['users'][str(target_id)]['balance']} TON")

# ----- Inline query support (публикация номера сделки в чате) -----
@dp.inline_query()
async def inline_q(inline_query: types.InlineQuery):
    q = inline_query.query.strip().upper()
    results = []
    # если пустой запрос — предложим инструкцию
    if q == "":
        articles = types.InlineQueryResultArticle(
            id="howto",
            title="Отправить номер сделки покупателю",
            input_message_content=types.InputTextMessageContent(message_text="Отправьте номер сделки покупателю, чтобы он мог присоединиться: #A123"),
            description="Отправьте покупателю ссылку/номер сделки"
        )
        results.append(articles)
    else:
        # допускаем, что пользователь вводит #A123 — найдем сделку
        if q in DATA["deals"]:
            d = DATA["deals"][q]
            txt = f"*Сделка {q}* — {d['name']} — {d['price']} ₽  \nПрисоединяйтесь, чтобы участвовать в безопасной сделке."
            results.append(types.InlineQueryResultArticle(
                id=q, title=f"Сделка {q}", input_message_content=types.InputTextMessageContent(message_text=txt, parse_mode="Markdown"),
                description=f"{d['name']} — {d['price']} ₽"
            ))
    await inline_query.answer(results=results, cache_time=0)

# ----- Generic help and fallback -----
@dp.callback_query(Text("help"))
async def help_cb(c: CallbackQuery):
    await c.answer()
    await bot.send_message(chat_id=c.from_user.id, text="Для помощи свяжитесь с поддержкой: @GiftCastleRelayer")

@dp.message()
async def fallback(m: Message):
    # стараемся держать общение в рамках >20 слов; если короткое, даём объёмный ответ
    txt = (
        "Здравствуйте! Я — бот Gift Castle. Если вы хотите создать сделку — нажмите «Создать сделку» в меню, "
        "если хотите проверить баланс — нажмите «Баланс», или воспользуйтесь помощью, чтобы связаться с поддержкой. "
        "Я сопровождаю процесс сделки, резервирую средства и информирую стороны о статусах до завершения операции."
    )
    await m.reply(txt)

# ----------------- Startup/Shutdown -----------------
async def on_startup():
    logging.info("Gift Castle Bot starting...")

async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
