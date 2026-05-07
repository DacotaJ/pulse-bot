import logging
import asyncio
import os
import json
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ChatAction
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from aiohttp import web

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8564626704:AAH4u4qTJhmfg5qJGCIcZoSvl7gI6uJir3g"
SPREADSHEET_ID = "1hNQfcs-Zk2ZjanjuZP1yZDlPc3ADNbp0s9In_kFSHu4"
SHEET_NAME = "Лиды с бота"
YOUR_TG = "https://t.me/PulseReportBot"
OWNER_USERNAME = "dacotaj"
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "")

# Anthropic API ключ — берётся из переменных Railway
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ЮКасса — берётся из переменных Railway
YUKASSA_SHOP_ID = os.environ.get("YUKASSA_SHOP_ID", "1345951")
YUKASSA_SECRET_KEY = os.environ.get("YUKASSA_SECRET_KEY", "")

logging.basicConfig(level=logging.INFO)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_creds_json = os.environ.get("GOOGLE_CREDS_JSON", "{}")
CREDS_INFO = json.loads(_creds_json)



import time

MINI_APP_BASE = "https://dacotaj.github.io/pulse-miniapp/pulse_miniapp_v5.html"

def get_mini_app_url():
    """Добавляем timestamp чтобы Telegram не кэшировал страницу"""
    return f"{MINI_APP_BASE}?t={int(time.time())}"


def save_to_sheet(row):
    try:
        creds = Credentials.from_service_account_info(CREDS_INFO, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        sheet.append_row(row, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
    except Exception as e:
        logging.error(f"Sheets error: {e}")


# ── ПОДПИСКИ ──
SUBSCRIPTIONS_SHEET = "Подписки"

def get_subscriptions_sheet():
    creds = Credentials.from_service_account_info(CREDS_INFO, scopes=SCOPES)
    client = gspread.authorize(creds)
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SUBSCRIPTIONS_SHEET)
    except Exception:
        # Создаём лист если нет
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        sheet = spreadsheet.add_worksheet(SUBSCRIPTIONS_SHEET, rows=1000, cols=10)
        sheet.append_row(["chat_id", "username", "email", "тариф", "статус", "дата_начала", "дата_окончания", "напоминание_отправлено"])
    return sheet

def save_subscription(chat_id, username, email, tariff, status, start_date, end_date):
    try:
        sheet = get_subscriptions_sheet()
        rows = sheet.get_all_records()
        # Обновляем если уже есть
        for i, row in enumerate(rows, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                sheet.update(f"A{i}:H{i}", [[
                    str(chat_id), username, email, tariff, status,
                    start_date.strftime("%d.%m.%Y"),
                    end_date.strftime("%d.%m.%Y"), "нет"
                ]])
                return
        # Добавляем новую
        sheet.append_row([
            str(chat_id), username, email, tariff, status,
            start_date.strftime("%d.%m.%Y"),
            end_date.strftime("%d.%m.%Y"), "нет"
        ])
    except Exception as e:
        logging.error(f"Subscription save error: {e}")

def get_all_subscriptions():
    try:
        sheet = get_subscriptions_sheet()
        return sheet.get_all_records()
    except Exception as e:
        logging.error(f"Get subscriptions error: {e}")
        return []

def update_subscription_status(chat_id, status, reminder_sent=None):
    try:
        sheet = get_subscriptions_sheet()
        rows = sheet.get_all_records()
        for i, row in enumerate(rows, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                sheet.update_cell(i, 5, status)
                if reminder_sent is not None:
                    sheet.update_cell(i, 8, reminder_sent)
                return
    except Exception as e:
        logging.error(f"Update subscription error: {e}")


async def check_subscriptions(context):
    """Ежедневная проверка подписок — отключение и напоминания"""
    today = datetime.now().date()
    subscriptions = get_all_subscriptions()

    for sub in subscriptions:
        chat_id = sub.get("chat_id")
        status = sub.get("статус")
        end_date_str = sub.get("дата_окончания", "")
        reminder_sent = sub.get("напоминание_отправлено", "нет")
        tariff = sub.get("тариф", "")

        if not chat_id or status == "expired":
            continue

        try:
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y").date()
        except Exception:
            continue

        days_left = (end_date - today).days

        # За 3 дня — одно напоминание
        if days_left == 3 and reminder_sent == "нет":
            try:
                keyboard = [[InlineKeyboardButton("🚀 Открыть Pulse AI", web_app={"url": get_mini_app_url()})]]
                if status == "trial":
                    msg = (f"⏰ <b>До конца бесплатного периода — 3 дня</b>\n\n"
                           f"Как вам Pulse? Если понравилось — самое время выбрать тариф:\n\n"
                           f"• START — 7 000 ₽/мес: отчёт + алерты + 1 источник\n"
                           f"• BUSINESS — 15 000 ₽/мес: всё + AI-аналитик + 3 источника\n"
                           f"• PRO — 25 000 ₽/мес: несколько направлений + PDF + созвоны\n\n"
                           f"Оплатите сейчас — и продолжите без перерыва 👇")
                else:
                    msg = (f"⏰ <b>Подписка заканчивается через 3 дня</b>\n\n"
                           f"Тариф: {tariff.upper()}\n"
                           f"Дата окончания: {end_date_str}\n\n"
                           f"Продлите сейчас чтобы не прерывать отчёты 👇")
                await context.bot.send_message(chat_id=chat_id, text=msg,
                    parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
                update_subscription_status(chat_id, status, reminder_sent="да")
                # Уведомляем себя
                if OWNER_CHAT_ID:
                    await context.bot.send_message(chat_id=OWNER_CHAT_ID,
                        text=f"⏰ Напоминание отправлено клиенту {chat_id} — подписка {tariff} истекает {end_date_str}",
                        parse_mode="HTML")
            except Exception as e:
                logging.error(f"Reminder error {chat_id}: {e}")

        # Срок истёк — отключаем
        elif days_left < 0:
            try:
                keyboard = [[InlineKeyboardButton("🚀 Открыть Pulse AI", web_app={"url": get_mini_app_url()})]]
                if status == "trial":
                    msg = ("🔴 <b>Ваш бесплатный период завершён</b>\n\n"
                           "Надеемся, вам понравилось! 7 дней пролетели быстро 😊\n\n"
                           "<b>Выберите тариф чтобы продолжить:</b>\n"
                           "• START — 7 000 ₽/мес: отчёт + алерты + 1 источник\n"
                           "• BUSINESS — 15 000 ₽/мес: всё + AI-аналитик + 3 источника\n"
                           "• PRO — 25 000 ₽/мес: несколько направлений + PDF + созвоны\n\n"
                           "Нажмите кнопку ниже чтобы оплатить 👇")
                else:
                    msg = (f"🔴 <b>Подписка завершена</b>\n\n"
                           f"Тариф {tariff.upper()} истёк {end_date_str}.\n\n"
                           f"Продлите чтобы снова получать отчёты каждое утро 👇")
                await context.bot.send_message(chat_id=chat_id, text=msg,
                    parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
                update_subscription_status(chat_id, "expired")
                if OWNER_CHAT_ID:
                    await context.bot.send_message(chat_id=OWNER_CHAT_ID,
                        text=f"🔴 Подписка истекла у клиента {chat_id} — тариф {tariff}",
                        parse_mode="HTML")
            except Exception as e:
                logging.error(f"Expire error {chat_id}: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    save_to_sheet([
        datetime.now().strftime("%d.%m.%Y %H:%M"),
        f"@{user.username}" if user.username else "нет ника",
        user.first_name or "",
        "—",
        "bot_start"
    ])
    keyboard = [[
        InlineKeyboardButton("🚀 Открыть Pulse AI", web_app={"url": get_mini_app_url()})
    ]]
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я — <b>Pulse AI</b>, ежедневная аналитика роста и потерь для вашего бизнеса.\n\n"
        "Нажмите кнопку ниже — и узнайте как это работает прямо сейчас 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[
        InlineKeyboardButton("🚀 Открыть Pulse AI", web_app={"url": get_mini_app_url()})
    ]]
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Откройте мини-приложение Pulse AI 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )



async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пересылает сообщения лидов владельцу"""
    user = update.message.from_user
    text = update.message.text or ""
    username = f"@{user.username}" if user.username else f"id:{user.id}"
    name = user.first_name or ""

    # Пересылаем владельцу
    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=f"💬 <b>Новое сообщение от лида</b>\n\n"
                     f"👤 {name} ({username})\n"
                     f"💬 {text}\n\n"
                     f"<a href='tg://user?id={user.id}'>Ответить</a>",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Forward error: {e}")

    # Отвечаем лиду
    keyboard = [[InlineKeyboardButton("🚀 Открыть Pulse AI", web_app={"url": get_mini_app_url()})]]
    await update.message.reply_text(
        "Спасибо за сообщение! 👋\n\n"
        "Наш менеджер свяжется с вами в ближайшее время.\n"
        "Пока можете посмотреть как работает Pulse AI 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def create_payment(request):
    """Создаёт платёж в ЮКассе и возвращает confirmation_token для виджета"""
    if request.method == "OPTIONS":
        return web.Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
        )

    try:
        body = await request.json()
        amount = body.get("amount", 7000)
        description = body.get("description", "Pulse подписка")
        email = body.get("email", "")
        chat_id = body.get("chat_id", "")
        username = body.get("username", "")

        import uuid
        idempotence_key = str(uuid.uuid4())

        payment_body = {
            "amount": {"value": str(amount) + ".00", "currency": "RUB"},
            "confirmation": {"type": "embedded"},
            "capture": True,
            "description": description,
        }

        if email:
            payment_body["receipt"] = {
                "customer": {"email": email},
                "items": [{
                    "description": description,
                    "quantity": "1.00",
                    "amount": {"value": str(amount) + ".00", "currency": "RUB"},
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service"
                }]
            }

        # Предварительно записываем в подписки (статус pending до оплаты)
        if email and chat_id:
            tariff = "start"
            if "BUSINESS" in description.upper(): tariff = "business"
            elif "PRO" in description.upper(): tariff = "pro"
            start_date = datetime.now()
            end_date = start_date + timedelta(days=31)
            save_subscription(chat_id, username, email, tariff, "pending", start_date, end_date)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.yookassa.ru/v3/payments",
                auth=(YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY),
                headers={
                    "Content-Type": "application/json",
                    "Idempotence-Key": idempotence_key,
                },
                json=payment_body,
            )

        data = resp.json()
        confirmation_token = data.get("confirmation", {}).get("confirmation_token")

        if not confirmation_token:
            logging.error(f"YooKassa error: {data}")
            return web.Response(
                status=500,
                text=json.dumps({"error": "Не удалось создать платёж", "details": data}),
                content_type="application/json",
                headers={"Access-Control-Allow-Origin": "*"},
            )

        # Уведомляем владельца о новом платеже
        if OWNER_CHAT_ID:
            try:
                import asyncio
                bot_app = Application.builder().token(BOT_TOKEN).build()
                await bot_app.bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=f"💰 <b>Новый платёж!</b>\n\n"
                         f"💳 {description}\n"
                         f"💵 {amount} ₽\n"
                         f"📧 {email or 'email не указан'}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Notify error: {e}")

        return web.Response(
            text=json.dumps({"confirmation_token": confirmation_token}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    except Exception as e:
        logging.error(f"Payment error: {e}")
        return web.Response(
            status=500,
            text=json.dumps({"error": str(e)}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )


# ── CLAUDE API ПРОКСИ ──
async def claude_proxy(request):
    """Принимает запросы из Mini App и передаёт в Claude API с ключом"""
    if request.method == "OPTIONS":
        return web.Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
        )

    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json=body,
            )
        return web.Response(
            body=resp.content,
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logging.error(f"Claude proxy error: {e}")
        return web.Response(
            status=500,
            text=json.dumps({"error": str(e)}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )


async def start_trial_endpoint(request):
    """Запуск триала из мини аппа"""
    if request.method == "OPTIONS":
        return web.Response(headers={"Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"})
    try:
        body = await request.json()
        chat_id = str(body.get("chat_id", ""))
        username = body.get("username", "")
        name = body.get("name", "")
        tariff = body.get("tariff", "business")

        # Проверяем дубль по chat_id
        subs = get_all_subscriptions()
        for sub in subs:
            if str(sub.get("chat_id")) == chat_id and sub.get("статус") in ("trial", "paid"):
                return web.Response(
                    text='{"already_exists":true}',
                    content_type="application/json",
                    headers={"Access-Control-Allow-Origin": "*"}
                )

        start_date = datetime.now()
        end_date = start_date + timedelta(days=7)

        # Записываем триал
        save_subscription(chat_id, username, "", tariff, "trial", start_date, end_date)

        # Уведомляем себя
        if OWNER_CHAT_ID:
            try:
                bot_app = Application.builder().token(BOT_TOKEN).build()
                await bot_app.bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=f"🆕 <b>Новый триал!</b>\n\n"
                         f"👤 {name} (@{username})\n"
                         f"🆔 chat_id: {chat_id}\n"
                         f"💼 Тариф: {tariff.upper()}\n"
                         f"📅 До: {end_date.strftime('%d.%m.%Y')}\n\n"
                         f"<a href='tg://user?id={chat_id}'>Написать юзеру</a> — настрой сегодня!",
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Trial notify error: {e}")

        return web.Response(
            text='{"ok":true,"already_exists":false}',
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )
    except Exception as e:
        logging.error(f"Start trial error: {e}")
        return web.Response(status=500, text='{"error":"error"}',
            content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})


async def health(request):
    return web.Response(text="OK")


async def yookassa_webhook(request):
    """Webhook от ЮКассы — вызывается при успешной оплате"""
    try:
        body = await request.json()
        event = body.get("event", "")
        payment = body.get("object", {})

        if event == "payment.succeeded":
            amount = payment.get("amount", {}).get("value", "0")
            description = payment.get("description", "")
            email = payment.get("receipt", {}).get("customer", {}).get("email", "")
            payment_id = payment.get("id", "")

            # Определяем тариф и срок
            tariff = "start"
            if "BUSINESS" in description.upper():
                tariff = "business"
            elif "PRO" in description.upper():
                tariff = "pro"

            start_date = datetime.now()
            end_date = start_date + timedelta(days=31)

            # Записываем в таблицу по email (chat_id узнаем позже)
            try:
                sheet = get_subscriptions_sheet()
                rows = sheet.get_all_records()
                matched = False
                for i, row in enumerate(rows, start=2):
                    if row.get("email") == email:
                        sheet.update(f"A{i}:H{i}", [[
                            row.get("chat_id", ""), row.get("username", ""),
                            email, tariff, "paid",
                            start_date.strftime("%d.%m.%Y"),
                            end_date.strftime("%d.%m.%Y"), "нет"
                        ]])
                        matched = True
                        # Уведомляем клиента
                        chat_id = row.get("chat_id")
                        if chat_id:
                            keyboard = [[InlineKeyboardButton("🚀 Открыть Pulse AI", web_app={"url": get_mini_app_url()})]]
                            bot_app = Application.builder().token(BOT_TOKEN).build()
                            await bot_app.bot.send_message(
                                chat_id=chat_id,
                                text=f"✅ <b>Оплата прошла успешно!</b>\n\n"
                                     f"Тариф: {description}\n"
                                     f"Подписка активна до: {end_date.strftime('%d.%m.%Y')}\n\n"
                                     f"Мы свяжемся с вами в течение дня для настройки 👇",
                                parse_mode="HTML",
                                reply_markup=InlineKeyboardMarkup(keyboard)
                            )
                        break
                if not matched:
                    sheet.append_row([
                        "", "", email, tariff, "paid",
                        start_date.strftime("%d.%m.%Y"),
                        end_date.strftime("%d.%m.%Y"), "нет"
                    ])
            except Exception as e:
                logging.error(f"Webhook sheet error: {e}")

            # Уведомляем себя
            if OWNER_CHAT_ID:
                try:
                    bot_app = Application.builder().token(BOT_TOKEN).build()
                    await bot_app.bot.send_message(
                        chat_id=OWNER_CHAT_ID,
                        text=f"💰 <b>Оплата подтверждена!</b>\n\n"
                             f"💳 {description}\n"
                             f"💵 {amount} ₽\n"
                             f"📧 {email}\n"
                             f"🆔 {payment_id}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Webhook notify error: {e}")

        return web.Response(text="OK")
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return web.Response(status=500, text="Error")


async def run_web():
    app = web.Application()
    app.router.add_post("/claude", claude_proxy)
    app.router.add_route("OPTIONS", "/claude", claude_proxy)
    app.router.add_post("/create-payment", create_payment)
    app.router.add_route("OPTIONS", "/create-payment", create_payment)
    app.router.add_post("/start-trial", start_trial_endpoint)
    app.router.add_route("OPTIONS", "/start-trial", start_trial_endpoint)
    app.router.add_post("/webhook/yookassa", yookassa_webhook)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")


def main():
    async def run_all():
        await run_web()
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Ежедневная проверка подписок в 10:00
        if app.job_queue:
            from datetime import time as dt_time
            app.job_queue.run_daily(check_subscriptions, time=dt_time(10, 0))
        else:
            logging.warning("JobQueue не доступен — установите python-telegram-bot[job-queue]")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()

    asyncio.run(run_all())


if __name__ == "__main__":
    main()
