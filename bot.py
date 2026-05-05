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
from datetime import datetime
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


async def health(request):
    return web.Response(text="OK")


async def run_web():
    app = web.Application()
    app.router.add_post("/claude", claude_proxy)
    app.router.add_route("OPTIONS", "/claude", claude_proxy)
    app.router.add_post("/create-payment", create_payment)
    app.router.add_route("OPTIONS", "/create-payment", create_payment)
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
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()

    asyncio.run(run_all())


if __name__ == "__main__":
    main()
