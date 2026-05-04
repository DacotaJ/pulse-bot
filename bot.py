import logging
import asyncio
import os
import json
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ChatAction
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from aiohttp import web

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8564626704:AAH4u4qTJhmfg5qJGCIcZoSvl7gI6uJir3g"
SPREADSHEET_ID = "1hNQfcs-Zk2ZjanjuZP1yZDlPc3ADNbp0s9In_kFSHu4"
SHEET_NAME = "Лиды с бота"
YOUR_TG = "https://t.me/ТВОЙ_НИК"
YOUR_CHAT_ID = None

# Anthropic API ключ — берётся из переменных Railway
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ЮКасса — берётся из переменных Railway
YUKASSA_SHOP_ID = os.environ.get("YUKASSA_SHOP_ID", "1345951")
YUKASSA_SECRET_KEY = os.environ.get("YUKASSA_SECRET_KEY", "")

logging.basicConfig(level=logging.INFO)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_creds_json = os.environ.get("GOOGLE_CREDS_JSON", "{}")
CREDS_INFO = json.loads(_creds_json)

# --- ДАННЫЕ ПО НИШАМ ---
NICHES = {
    "school": {
        "name": "Онлайн-школа",
        "case": "Онлайн-школа английского нашла 180 000 ₽ потерь за первые 5 дней",
        "report": (
            "📊 <b>ОТЧЁТ · Онлайн-школа · 09:00</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "📥 Новые заявки:       <b>47</b>\n"
            "📚 Записаны на урок:   <b>18</b>\n"
            "💳 Оплатили курс:      <b>11</b>\n"
            "💰 Выручка:            <b>218 900 ₽</b>\n"
            "📈 Конверсия:          <b>38%</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Без ответа >2ч:     <b>9</b>"
        ),
        "alert": (
            "🔴 <b>АЛЕРТ — ПОТЕРИ</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "9 заявок без ответа больше 2 часов\n\n"
            "При вашем среднем чеке 15 200 ₽:\n"
            "<b>9 × 15 200 ₽ = 136 800 ₽</b>\n\n"
            "Эти студенты сейчас смотрят конкурентов 👀"
        ),
        "realtime_alert": (
            "⚡️ <b>АЛЕРТ · 11:34</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Новая заявка от Марины К. — без ответа уже <b>3 часа</b>\n"
            "Потенциальная потеря: <b>15 200 ₽</b>\n\n"
            "💬 Написать Марине →"
        ),
        "weekly": (
            "📅 <b>ИТОГИ НЕДЕЛИ · Онлайн-школа</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Заявок за неделю:    <b>284</b> (+12% к прошлой)\n"
            "Выручка:             <b>1 240 000 ₽</b>\n"
            "Лучший день:         <b>Вторник</b> — 67 заявок\n"
            "Конверсия:           <b>41%</b> (была 35%)\n"
            "━━━━━━━━━━━━━━━━\n"
            "🟢 Тренд: <b>рост 3 недели подряд</b>"
        ),
        "question": "У вас бывает что заявки зависают без ответа по несколько часов?"
    },
    "clinic": {
        "name": "Клиника",
        "case": "Стоматология нашла 91 000 ₽ потерь за первую неделю — 7 пациентов без перезвона",
        "report": (
            "📊 <b>ОТЧЁТ · Клиника · 09:00</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "📥 Новых обращений:    <b>31</b>\n"
            "📅 Записано на приём:  <b>24</b>\n"
            "💰 Выручка:            <b>186 000 ₽</b>\n"
            "📈 Конверсия:          <b>77%</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Не перезвонили:     <b>7</b>"
        ),
        "alert": (
            "🔴 <b>АЛЕРТ — ПОТЕРИ</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "7 пациентов ждут звонка прямо сейчас\n\n"
            "При среднем чеке 13 000 ₽:\n"
            "<b>7 × 13 000 ₽ = 91 000 ₽</b>\n\n"
            "Каждый час — они уходят в другую клинику 👀"
        ),
        "realtime_alert": (
            "⚡️ <b>АЛЕРТ · 11:34</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Пациент Алексей Н. оставил заявку — без ответа уже <b>4 часа</b>\n"
            "Потенциальная потеря: <b>13 000 ₽</b>\n\n"
            "💬 Перезвонить Алексею →"
        ),
        "weekly": (
            "📅 <b>ИТОГИ НЕДЕЛИ · Клиника</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Обращений за неделю: <b>187</b> (+8% к прошлой)\n"
            "Выручка:             <b>980 000 ₽</b>\n"
            "Лучший день:         <b>Среда</b> — 41 обращение\n"
            "Конверсия:           <b>79%</b> (была 72%)\n"
            "━━━━━━━━━━━━━━━━\n"
            "🟢 Тренд: <b>конверсия растёт 2 недели подряд</b>"
        ),
        "question": "Бывает что пациенты не дожидаются обратного звонка?"
    },
    "realty": {
        "name": "Недвижимость",
        "case": "Агентство недвижимости нашло 480 000 ₽ потерь за неделю — 6 лидов без контакта",
        "report": (
            "📊 <b>ОТЧЁТ · Недвижимость · 09:00</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "📥 Новых лидов:        <b>19</b>\n"
            "🏠 Назначено показов:  <b>7</b>\n"
            "🤝 Сделок закрыто:     <b>2</b>\n"
            "⏱ Среднее время ответа:<b>2.5 ч</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Без перезвона:      <b>6</b>"
        ),
        "alert": (
            "🔴 <b>АЛЕРТ — ПОТЕРИ</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "6 лидов без контакта\n"
            "Лид в недвижимости остывает за 30 минут\n\n"
            "При комиссии 80 000 ₽:\n"
            "<b>6 × 80 000 ₽ = 480 000 ₽</b>\n\n"
            "Эти клиенты уже звонят другим агентам 👀"
        ),
        "realtime_alert": (
            "⚡️ <b>АЛЕРТ · 11:34</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Новый лид — Дмитрий С. смотрел 3-комнатные. Без ответа <b>45 минут</b>\n"
            "Потенциальная потеря: <b>80 000 ₽</b>\n\n"
            "💬 Позвонить Дмитрию →"
        ),
        "weekly": (
            "📅 <b>ИТОГИ НЕДЕЛИ · Недвижимость</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Лидов за неделю:     <b>94</b> (+15% к прошлой)\n"
            "Показов:             <b>31</b>\n"
            "Сделок:              <b>8</b>\n"
            "Среднее время ответа:<b>1.8 ч</b> (было 3.2 ч)\n"
            "━━━━━━━━━━━━━━━━\n"
            "🟢 Тренд: <b>время ответа сократилось вдвое</b>"
        ),
        "question": "Как быстро ваши агенты перезванивают по новым лидам?"
    },
    "agency": {
        "name": "Агентство",
        "case": "Маркетинговое агентство предотвратило потерю 3 клиентов — увидели просрочку утром",
        "report": (
            "📊 <b>ОТЧЁТ · Агентство · 09:00</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "📁 Активных проектов:  <b>14</b>\n"
            "📥 Новых лидов:        <b>8</b>\n"
            "💰 Выручка:            <b>380 000 ₽</b>\n"
            "✅ Задач выполнено:    <b>31</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Просрочено задач:   <b>7</b>"
        ),
        "alert": (
            "🔴 <b>АЛЕРТ — РИСК ПОТЕРИ КЛИЕНТОВ</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "7 задач просрочено по активным клиентам\n\n"
            "Средний контракт 30 000 ₽/мес:\n"
            "<b>риск потери ~210 000 ₽/мес</b>\n\n"
            "Клиент не скажет — просто не продлит контракт 👀"
        ),
        "realtime_alert": (
            "⚡️ <b>АЛЕРТ · 11:34</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Клиент «Мегастрой» — дедлайн по отчёту <b>просрочен на 2 дня</b>\n"
            "Контракт: <b>45 000 ₽/мес</b>\n\n"
            "💬 Написать менеджеру проекта →"
        ),
        "weekly": (
            "📅 <b>ИТОГИ НЕДЕЛИ · Агентство</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Новых лидов:         <b>34</b> (+20% к прошлой)\n"
            "Выручка:             <b>1 840 000 ₽</b>\n"
            "Просрочек:           <b>2</b> (было 9)\n"
            "Удержание клиентов:  <b>94%</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "🟢 Тренд: <b>просрочки снизились в 4 раза</b>"
        ),
        "question": "Как вы сейчас контролируете просроченные задачи по клиентам?"
    },
    "service": {
        "name": "Сервисный бизнес",
        "case": "Автосервис нашёл 74 000 ₽ потерь — 8 клиентов ждали ответа больше 4 часов",
        "report": (
            "📊 <b>ОТЧЁТ · Сервис · 09:00</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "📥 Новых заявок:       <b>34</b>\n"
            "⚙️ В работе:           <b>21</b>\n"
            "💰 Выручка:            <b>127 000 ₽</b>\n"
            "✅ Закрыто:            <b>18</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Клиенты ждут >4ч:  <b>8</b>"
        ),
        "alert": (
            "🔴 <b>АЛЕРТ — ПОТЕРИ</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "8 клиентов ждут ответа больше 4 часов\n\n"
            "При среднем чеке 9 200 ₽:\n"
            "<b>8 × 9 200 ₽ = 73 600 ₽</b>\n\n"
            "Клиент который ждёт — уже ищет другой сервис 👀"
        ),
        "realtime_alert": (
            "⚡️ <b>АЛЕРТ · 11:34</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Заявка от Игоря М. на ремонт — без ответа <b>5 часов</b>\n"
            "Потенциальная потеря: <b>9 200 ₽</b>\n\n"
            "💬 Позвонить Игорю →"
        ),
        "weekly": (
            "📅 <b>ИТОГИ НЕДЕЛИ · Сервис</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Заявок за неделю:    <b>198</b> (+9% к прошлой)\n"
            "Выручка:             <b>742 000 ₽</b>\n"
            "Среднее время ответа:<b>1.2 ч</b> (было 4.5 ч)\n"
            "Потерь:              <b>3</b> (было 21)\n"
            "━━━━━━━━━━━━━━━━\n"
            "🟢 Тренд: <b>потери снизились в 7 раз</b>"
        ),
        "question": "Сколько времени в среднем уходит на ответ новому клиенту?"
    },
    "hr": {
        "name": "HR / Рекрутинг",
        "case": "HR-отдел предотвратил срыв 3 вакансий — увидели выпавших кандидатов утром",
        "report": (
            "📊 <b>ОТЧЁТ · HR / Рекрутинг · 09:00</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "📋 Активных вакансий:  <b>12</b>\n"
            "👤 Новых кандидатов:   <b>28</b>\n"
            "🎯 На интервью:        <b>6</b>\n"
            "✅ Офферов выдано:     <b>2</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ Без обратной связи: <b>14</b>"
        ),
        "alert": (
            "🔴 <b>АЛЕРТ — ПОТЕРИ КАНДИДАТОВ</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "14 кандидатов без обратной связи\n"
            "9 из них выпали из воронки\n\n"
            "Закрытие 1 вакансии стоит ~40 000 ₽:\n"
            "<b>риск срыва 3 вакансий = 120 000 ₽</b>\n\n"
            "Хорошие кандидаты уже приняли другой оффер 👀"
        ),
        "realtime_alert": (
            "⚡️ <b>АЛЕРТ · 11:34</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Кандидат Анна В. на вакансию Senior — без ответа <b>2 дня</b>\n"
            "Риск потери: <b>закрытие вакансии сорвётся</b>\n\n"
            "💬 Написать Анне →"
        ),
        "weekly": (
            "📅 <b>ИТОГИ НЕДЕЛИ · HR</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Кандидатов за неделю:<b>134</b> (+18% к прошлой)\n"
            "Офферов выдано:      <b>9</b>\n"
            "Принято офферов:     <b>7</b> (78%)\n"
            "Выпало из воронки:   <b>4</b> (было 19)\n"
            "━━━━━━━━━━━━━━━━\n"
            "🟢 Тренд: <b>потери кандидатов снизились в 5 раз</b>"
        ),
        "question": "Как быстро ваши рекрутеры дают обратную связь кандидатам?"
    }
}


def save_to_sheet(row):
    try:
        creds = Credentials.from_service_account_info(CREDS_INFO, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        # Всегда добавляем новую строку в конец
        sheet.append_row(row, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
    except Exception as e:
        logging.error(f"Sheets error: {e}")


def save_lead(username, first_name, niche):
    save_to_sheet([
        datetime.now().strftime("%d.%m.%Y %H:%M"),
        f"@{username}" if username else "нет ника",
        first_name or "",
        NICHES.get(niche, {}).get("name", niche),
        "bot_start"
    ])


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
        InlineKeyboardButton(
            "🚀 Открыть Pulse AI",
            web_app={"url": "https://dacotaj.github.io/pulse-miniapp/pulse_miniapp_v5.html"}
        )
    ]]

    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я — <b>Pulse AI</b>, ежедневная аналитика роста и потерь для вашего бизнеса.\n\n"
        "Нажмите кнопку ниже — и узнайте как это работает прямо сейчас 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старые callback кнопки — перенаправляем в Mini App"""
    query = update.callback_query
    await query.answer()
    keyboard = [[
        InlineKeyboardButton(
            "🚀 Открыть Pulse AI",
            web_app={"url": "https://dacotaj.github.io/pulse-miniapp/pulse_miniapp_v5.html"}
        )
    ]]
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Откройте мини-приложение Pulse AI — там всё гораздо удобнее 👇",
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

        import uuid
        idempotence_key = str(uuid.uuid4())

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.yookassa.ru/v3/payments",
                auth=(YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY),
                headers={
                    "Content-Type": "application/json",
                    "Idempotence-Key": idempotence_key,
                },
                json={
                    "amount": {"value": str(amount) + ".00", "currency": "RUB"},
                    "confirmation": {"type": "embedded"},
                    "capture": True,
                    "description": description,
                },
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
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()

    asyncio.run(run_all())


if __name__ == "__main__":
    main()
