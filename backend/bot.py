import os
import uuid
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from backend.config import BOT_TOKEN, WEBAPP_URL, UPLOAD_DIR
from backend.database import (
    get_user_by_telegram_id,
    create_user_and_family,
    join_family_by_code,
    add_expense_record,
    get_family_by_id,
    get_family_members,
    get_family_monthly_analytics,
    delete_expense_record
)
from backend.ai_service import parse_expense_text, scan_receipt_with_vision
from backend.routes.shortcuts import set_bot_instance

dp = Dispatcher()
bot = None

def get_main_keyboard():
    # Mini App WebApp button
    webapp_btn = KeyboardButton(
        text="💎 Открыть трекер",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/")
    )
    return ReplyKeyboardMarkup(
        keyboard=[
            [webapp_btn],
            [KeyboardButton(text="📊 Статистика за месяц"), KeyboardButton(text="📲 Команды на iPhone")],
            [KeyboardButton(text="🔗 Пригласить супругу"), KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    tg_id = message.from_user.id
    first_name = message.from_user.first_name or "Пользователь"
    username = message.from_user.username

    # Check for invite code in /start join_<code>
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    invite_code = None
    if args and args[0].startswith("join_"):
        invite_code = args[0].replace("join_", "").strip()

    user = await get_user_by_telegram_id(tg_id)

    if invite_code:
        # User is joining an existing family via invite link
        user = await join_family_by_code(tg_id, invite_code, first_name, username, role="Супруга")
        if user:
            family = await get_family_by_id(user["family_id"])
            await message.answer(
                f"🎉 <b>Добро пожаловать в семейный бюджет!</b>\n\n"
                f"Вы успешно подключились к семье: <b>{family['name']}</b>.\n"
                f"Теперь вы вдвоем можете быстро вносить траты, отправлять фото чеков и сразу видеть, кто сколько потратил!",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            # Notify spouse
            members = await get_family_members(user["family_id"])
            spouse = next((m for m in members if m["id"] != tg_id), None)
            if spouse and bot:
                await bot.send_message(
                    chat_id=spouse["id"],
                    text=f"💞 <b>{first_name}</b> присоединилась к семейному трекеру трат!",
                    parse_mode="HTML"
                )
            return
        else:
            await message.answer("⚠️ Код приглашения не найден или устарел.")

    if not user:
        user = await create_user_and_family(tg_id, first_name, username, role="Супруг")

    family = await get_family_by_id(user["family_id"])
    members = await get_family_members(user["family_id"])
    partner = next((m for m in members if m["id"] != tg_id), None)

    welcome_text = (
        f"👋 <b>Привет, {first_name}!</b>\n\n"
        f"Это <b>Семейный трекер финансов и общих трат</b>.\n\n"
        f"⚡️ <b>Как быстро записать расход:</b>\n"
        f"• Просто напишите в чат: <code>1500 продукты</code> или <code>Бензин 2500</code>\n"
        f"• Или отправьте <b>фото чека</b> — сумма и категория определятся сами!\n"
        f"• Или настройте <b>Команду на iPhone</b> для добавления в 1 клик с экрана блокировки.\n\n"
        f"👥 <b>Семья:</b> {family['name']}\n"
        f"👤 <b>Партнер:</b> {partner['first_name'] if partner else 'Еще не подключен(а)'}\n"
    )

    if not partner:
        bot_info = await bot.get_me() if bot else None
        bot_user = bot_info.username if bot_info else "FamilyFinanceBot"
        invite_link = f"https://t.me/{bot_user}?start=join_{family['invite_code']}"
        welcome_text += f"\n🔗 <b>Ссылка для подключения супруги:</b>\n{invite_link}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Открыть трекер (Mini App)", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))],
        [InlineKeyboardButton(text="📲 Настроить iPhone Команду", callback_data="show_shortcuts")]
    ])

    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())
    await message.answer("Нажмите кнопку ниже, чтобы открыть стеклянное мини-приложение:", reply_markup=kb)

@dp.message(F.text == "📊 Статистика за месяц")
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await create_user_and_family(message.from_user.id, message.from_user.first_name)

    stats = await get_family_monthly_analytics(user["family_id"])
    currency = stats["currency"]
    total = f"{stats['total_spent']:,.0f} {currency}".replace(",", " ")

    lines = [
        f"📊 <b>Сводка за {stats['month']}:</b>\n",
        f"💰 <b>Всего потрачено:</b> {total} (лимит: {stats['monthly_budget']:,.0f} {currency})\n".replace(",", " "),
        "👥 <b>Кто сколько потратил:</b>"
    ]

    for u in stats["users"]:
        u_total = f"{u['total_user']:,.0f} {currency}".replace(",", " ")
        lines.append(f"• {u['first_name']}: <b>{u_total}</b>")

    if stats.get("split") and stats["split"]["payer"]:
        lines.append(f"\n⚖️ <b>Баланс 50/50:</b>\n👉 {stats['split']['text']}")

    if stats["categories"]:
        lines.append("\n📁 <b>Топ категорий:</b>")
        for cat in stats["categories"][:5]:
            cat_tot = f"{cat['total']:,.0f} {currency}".replace(",", " ")
            lines.append(f"• {cat['icon']} {cat['name']}: {cat_tot} ({cat['percentage']}%)")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подробная аналитика в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))]
    ])

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)

@dp.message(F.text == "📲 Команды на iPhone")
@dp.message(Command("shortcuts"))
async def cmd_shortcuts(message: types.Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await create_user_and_family(message.from_user.id, message.from_user.first_name)

    token = user["api_token"]
    webhook_url = f"{WEBAPP_URL}/api/shortcuts/add"

    text = (
        f"📲 <b>Настройка Быстрых Команд на iPhone:</b>\n\n"
        f"Вы можете нажать иконку на экране "
        f"iPhone (или кнопку Action Button), ввести сумму и покупку, а бот сам определит категорию!\n\n"
        f"🔑 <b>Ваш личный токен:</b>\n<code>{token}</code>\n\n"
        f"🌐 <b>Адрес вебхука:</b>\n<code>{webhook_url}</code>\n\n"
        f"<b>Как собрать команду в приложении «Команды»:</b>\n"
        f"1. Добавьте действие <b>«Запросить ввод»</b> (Число) — Сумма.\n"
        f"2. Добавьте действие <b>«Запросить ввод»</b> (Текст) — Что купили?\n"
        f"3. Добавьте <b>«Получить содержимое URL»</b>:\n"
        f"   • Метод: POST\n"
        f"   • Заголовки: <code>Content-Type: application/json</code>\n"
        f"   • Тело (JSON):\n"
        f"     <code>token: {token}</code>\n"
        f"     <code>amount: [Предоставленный ввод 1]</code>\n"
        f"     <code>title: [Предоставленный ввод 2]</code>\n"
        f"4. Добавьте действие <b>«Показать уведомление»</b>.\n\n"
        f"👉 Подробная инструкция со скриншотами и готовой ссылкой доступна во вкладке «Семья» в приложении!"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Открыть инструкцию в Mini App", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.message(F.text == "🔗 Пригласить супругу")
@dp.message(Command("invite"))
async def cmd_invite(message: types.Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await create_user_and_family(message.from_user.id, message.from_user.first_name)

    family = await get_family_by_id(user["family_id"])
    bot_info = await bot.get_me() if bot else None
    bot_user = bot_info.username if bot_info else "FamilyFinanceBot"
    invite_link = f"https://t.me/{bot_user}?start=join_{family['invite_code']}"

    text = (
        f"💞 <b>Приглашение для супруги:</b>\n\n"
        f"Перешлите ей эту ссылку:\n{invite_link}\n\n"
        f"Или код приглашения: <code>{family['invite_code']}</code>\n\n"
        f"Как только она перейдет по ссылке и нажмет Start, вы будете вести общий бюджет вместе!"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.photo)
async def handle_photo_receipt(message: types.Message):
    """Handles receipt photos sent by the user."""
    tg_id = message.from_user.id
    user = await get_user_by_telegram_id(tg_id)
    if not user:
        user = await create_user_and_family(tg_id, message.from_user.first_name)

    await message.answer("🔍 <i>Обрабатываю чек... Распознаю сумму и магазин...</i>", parse_mode="HTML")

    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    filename = f"receipt_{uuid.uuid4().hex}.jpg"
    filepath = UPLOAD_DIR / filename

    await bot.download_file(file_info.file_path, filepath)

    with open(filepath, "rb") as f:
        img_bytes = f.read()

    # AI / Heuristic receipt scanning
    parsed = await scan_receipt_with_vision(img_bytes, filename)
    receipt_url = f"/uploads/receipts/{filename}"

    expense = await add_expense_record(
        family_id=user["family_id"],
        user_id=user["id"],
        amount=parsed["amount"],
        category_id=parsed["category_id"],
        description=parsed["store_name"],
        expense_date=parsed.get("date"),
        receipt_url=receipt_url,
        receipt_meta=parsed
    )

    amount_str = f"{parsed['amount']:,.0f} ₽".replace(",", " ")
    cat_name = expense.get("category_name", "Продукты")
    cat_icon = expense.get("category_icon", "🛒")

    reply_text = (
        f"🧾 <b>Чек успешно распознан и записан!</b>\n\n"
        f"🏪 <b>Магазин:</b> {parsed['store_name']}\n"
        f"💰 <b>Сумма:</b> <b>{amount_str}</b>\n"
        f"📁 <b>Категория:</b> {cat_icon} {cat_name}\n"
        f"👤 <b>Кто оплатил:</b> {user['first_name']}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Открыть в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))],
        [InlineKeyboardButton(text="❌ Удалить этот расход", callback_data=f"del_exp_{expense['id']}")]
    ])

    await message.answer(reply_text, parse_mode="HTML", reply_markup=kb)

    # Notify partner
    members = await get_family_members(user["family_id"])
    partner = next((m for m in members if m["id"] != tg_id), None)
    if partner and partner["id"] > 100:
        partner_text = (
            f"🧾 <b>{user['first_name']} добавил(а) чек:</b>\n"
            f"🏪 {parsed['store_name']}\n"
            f"💰 <b>{amount_str}</b> ({cat_icon} {cat_name})"
        )
        try:
            await bot.send_message(chat_id=partner["id"], text=partner_text, parse_mode="HTML")
        except Exception as e:
            print(f"Partner notification error: {e}")

@dp.message(F.text)
async def handle_text_expense(message: types.Message):
    """Handles natural language text expense entry."""
    text = message.text.strip()
    if text.startswith("/"):
        return

    tg_id = message.from_user.id
    user = await get_user_by_telegram_id(tg_id)
    if not user:
        user = await create_user_and_family(tg_id, message.from_user.first_name)

    parsed = await parse_expense_text(text)
    if not parsed.get("amount") or parsed["amount"] <= 0:
        await message.answer(
            "💡 Чтобы записать расход, укажите сумму и покупку.\n"
            "Например: <code>1500 продукты</code> или <code>Бензин 2500</code>\n"
            "Или отправьте фото кассового чека!",
            parse_mode="HTML"
        )
        return

    expense = await add_expense_record(
        family_id=user["family_id"],
        user_id=user["id"],
        amount=parsed["amount"],
        category_id=parsed["category_id"],
        description=parsed["description"]
    )

    amount_str = f"{parsed['amount']:,.0f} ₽".replace(",", " ")
    cat_name = expense.get("category_name", "Расход")
    cat_icon = expense.get("category_icon", "💳")

    reply_text = (
        f"✅ <b>Расход записан!</b>\n\n"
        f"💰 <b>{amount_str}</b>\n"
        f"📁 <b>Категория:</b> {cat_icon} {cat_name}\n"
        f"📝 <b>Описание:</b> {parsed['description']}\n"
        f"👤 <b>Кто оплатил:</b> {user['first_name']}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Открыть трекер", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))],
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_exp_{expense['id']}")]
    ])

    await message.answer(reply_text, parse_mode="HTML", reply_markup=kb)

    # Notify partner
    members = await get_family_members(user["family_id"])
    partner = next((m for m in members if m["id"] != tg_id), None)
    if partner and partner["id"] > 100:
        partner_text = (
            f"🔔 <b>{user['first_name']} записал(а) расход:</b>\n"
            f"💰 <b>{amount_str}</b> — {cat_icon} {cat_name} ({parsed['description']})"
        )
        try:
            await bot.send_message(chat_id=partner["id"], text=partner_text, parse_mode="HTML")
        except Exception as e:
            print(f"Partner notification error: {e}")

@dp.callback_query(F.data.startswith("del_exp_"))
async def cb_delete_expense(callback: types.CallbackQuery):
    exp_id = int(callback.data.replace("del_exp_", ""))
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user:
        await delete_expense_record(exp_id, user["family_id"])
        await callback.message.edit_text("🗑 <b>Расход удален.</b>", parse_mode="HTML")
    await callback.answer("Удалено")

@dp.callback_query(F.data == "show_shortcuts")
async def cb_show_shortcuts(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_shortcuts(callback.message)

async def start_bot():
    global bot
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN is not configured in .env. Telegram Bot polling disabled, but WebApp and Shortcuts API are running!")
        return None

    bot = Bot(token=BOT_TOKEN)
    set_bot_instance(bot)
    print("🤖 Telegram Bot started in background polling mode.")
    return bot, dp
