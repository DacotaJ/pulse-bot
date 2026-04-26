import logging
import asyncio
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ChatAction
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8564626704:AAH4u4qTJhmfg5qJGCIcZoSvl7gI6uJir3g"
SPREADSHEET_ID = "1hNQfcs-Zk2ZjanjuZP1yZDlPc3ADNbp0s9In_kFSHu4"
SHEET_NAME = "Лиды с бота"
YOUR_TG = "https://t.me/ТВОЙ_НИК"  # замени на свой ник
YOUR_CHAT_ID = None  # замени на свой Telegram ID (узнай у @userinfobot)

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
        sheet.append_row(row)
    except Exception as e:
        logging.error(f"Sheets error: {e}")


def save_lead(username, first_name, niche):
    save_to_sheet([
        datetime.now().strftime("%d.%m.%Y %H:%M"),
        f"@{username}" if username else "нет ника",
        first_name or "",
        NICHES.get(niche, {}).get("name", niche),
        "bot_demo_v4"
    ])


async def typing(chat_id, context, seconds=1.5):
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(seconds)


async def send(chat_id, context, text, keyboard=None, delay=1.5):
    await typing(chat_id, context, delay)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎓 Онлайн-школа", callback_data="school"),
         InlineKeyboardButton("🏥 Клиника", callback_data="clinic")],
        [InlineKeyboardButton("🏠 Недвижимость", callback_data="realty"),
         InlineKeyboardButton("📈 Агентство", callback_data="agency")],
        [InlineKeyboardButton("🔧 Сервис", callback_data="service"),
         InlineKeyboardButton("👥 HR / Рекрутинг", callback_data="hr")],
    ]
    user = update.message.from_user
    save_to_sheet([
        datetime.now().strftime("%d.%m.%Y %H:%M"),
        f"@{user.username}" if user.username else "нет ника",
        user.first_name or "",
        "—",
        "bot_start"
    ])
    if YOUR_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=YOUR_CHAT_ID,
                text=f"👤 Новый пользователь зашёл в бота!\n\nИмя: {user.first_name}\nUsername: @{user.username or 'нет'}\nВремя: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
        except Exception as e:
            logging.error(f"Notify error: {e}")

    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я покажу как работает <b>Pulse</b> — система ежедневных отчётов "
        "для владельцев бизнеса.\n\n"
        "Это не презентация — я покажу всё вживую, как будто "
        "вы уже подключены.\n\n"
        "Выберите вашу нишу 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    niche = query.data
    chat_id = query.message.chat_id

    # Настройки
    if niche == "settings_demo":
        await show_settings(chat_id, context)
        return

    if niche in ("settings_mode", "settings_freq", "settings_threshold", "settings_team"):
        await handle_settings(niche, chat_id, context)
        return

    if niche in ("mode_full", "mode_report", "mode_alerts", "freq_1", "freq_2", "freq_3",
                 "threshold_3", "threshold_5", "threshold_10", "team_yes", "team_no"):
        await handle_settings(niche, chat_id, context)
        return

    # Кнопки алертов
    if niche == "alert_snooze":
        await send(chat_id, context,
            "🔕 <b>Напомню через час</b>\n\n"
            "Поставил напоминание на 12:34.\n"
            "Если не обработаете — пришлю снова.",
            delay=0.5)
        return

    if niche == "alert_done":
        await send(chat_id, context,
            "✅ <b>Отлично!</b>\n\n"
            "Заявка отмечена как обработанная.\n"
            "Так держать — ни один клиент не потерян 💪",
            delay=0.5)
        return

    if niche == "alert_show_all":
        await send(chat_id, context,
            "📋 <b>Необработанные заявки:</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "1. Марина К. — ждёт 3 часа · 15 200 ₽\n"
            "2. Сергей П. — ждёт 2.5 часа · 15 200 ₽\n"
            "3. Анна В. — ждёт 2 часа · 15 200 ₽\n"
            "4. Дмитрий Л. — ждёт 1.5 часа · 15 200 ₽\n"
            "5. Ольга М. — ждёт 1 час · 15 200 ₽\n"
            "━━━━━━━━━━━━━━━━\n"
            "⚠️ В реальном боте — ваши данные из CRM",
            delay=0.8)
        return

    # Тарифы
    if niche in ("tariff_start", "tariff_business"):
        await send(chat_id, context,
            "🔗 <b>Ссылка на оплату</b>\n\n"
            "Оплата будет доступна в ближайшее время.\n\n"
            "Пока можете написать напрямую 👇",
            keyboard=[[InlineKeyboardButton("✍️ Написать напрямую", url=YOUR_TG)]],
            delay=0.5)
        return

    user = query.from_user
    data = NICHES.get(niche, NICHES["school"])

    save_lead(user.username, user.first_name, niche)

    if YOUR_CHAT_ID:
        try:
            niche_name = NICHES.get(niche, {}).get("name", niche)
            await context.bot.send_message(
                chat_id=YOUR_CHAT_ID,
                text=f"🔥 Лид выбрал нишу!\n\nИмя: {user.first_name}\nUsername: @{user.username or 'нет'}\nНиша: {niche_name}\nВремя: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
        except Exception as e:
            logging.error(f"Notify error: {e}")

    # === АКТ 1: Утренний отчёт ===
    await send(chat_id, context,
        "☀️ <b>Доброе утро!</b>\n\nСобираю данные вашего бизнеса за вчера...",
        delay=1.5)

    await send(chat_id, context, data["report"], delay=2.5)

    # === АКТ 2: Большой алерт (сводный) ===
    alert_keyboard = [
        [InlineKeyboardButton("📋 Показать всех", callback_data="alert_show_all")],
        [InlineKeyboardButton("🔕 Отложить на 1 час", callback_data="alert_snooze")],
    ]
    await send(chat_id, context, data["alert"], keyboard=alert_keyboard, delay=2.0)

    # === АКТ 3: Кейс ===
    await send(chat_id, context,
        f"💡 <b>Кейс из вашей ниши:</b>\n\n<i>{data['case']}</i>",
        delay=2.5)

    # === АКТ 4: Персональный алерт ===
    await send(chat_id, context,
        "⏰ А теперь представьте...\n\n"
        "Вы на встрече. 11:30. И вдруг приходит это:",
        delay=2.0)

    realtime_keyboard = [
        [InlineKeyboardButton("✅ Обработано", callback_data="alert_done")],
        [InlineKeyboardButton("🔕 Отложить на 1 час", callback_data="alert_snooze")],
    ]
    await send(chat_id, context, data["realtime_alert"], keyboard=realtime_keyboard, delay=1.5)

    await send(chat_id, context,
        "Вы узнали о потере <b>до того</b>, как клиент ушёл.\n"
        "Не вечером. Не в пятницу. Прямо сейчас.",
        delay=2.0)

    # === АКТ 5: Еженедельная сводка ===
    await send(chat_id, context,
        "📅 А каждое воскресенье вечером приходит итог недели:",
        delay=2.5)

    await send(chat_id, context, data["weekly"], delay=1.5)

    # === АКТ 6: Настройки ===
    await send(chat_id, context,
        "⚙️ И всё это настраивается прямо в боте.\nНажмите любую кнопку ниже — и увидите финал 👇\n\n"
        "👇 Нажмите любую кнопку ниже — и увидите финал демо",
        delay=2.5)

    await show_settings(chat_id, context)


async def show_settings(chat_id, context):
    keyboard = [
        [InlineKeyboardButton("📋 Режим отчётов", callback_data="settings_mode"),
         InlineKeyboardButton("🕐 Частота", callback_data="settings_freq")],
        [InlineKeyboardButton("🔔 Порог алерта", callback_data="settings_threshold"),
         InlineKeyboardButton("👥 Командный режим", callback_data="settings_team")],
    ]
    await typing(chat_id, context, 1.0)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "⚙️ <b>Настройки Pulse</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Режим:        <b>Полный отчёт + алерты</b>\n"
            "Время:        <b>09:00</b>\n"
            "Порог алерта: <b>5 необработанных</b>\n"
            "Команда:      <b>только вы</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "Нажмите чтобы изменить 👇"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_settings(niche, chat_id, context):
    responses = {
        "settings_mode": {
            "text": "📋 <b>Режим отчётов</b>\n\nВыберите что присылать:",
            "keyboard": [
                [InlineKeyboardButton("✅ Полный отчёт + алерты", callback_data="mode_full")],
                [InlineKeyboardButton("📊 Только отчёт (без алертов)", callback_data="mode_report")],
                [InlineKeyboardButton("🔔 Только алерты", callback_data="mode_alerts")],
            ]
        },
        "settings_freq": {
            "text": "🕐 <b>Частота отчётов</b>\n\nСколько раз в день:",
            "keyboard": [
                [InlineKeyboardButton("1 раз · утром в 09:00", callback_data="freq_1")],
                [InlineKeyboardButton("2 раза · 09:00 и 18:00", callback_data="freq_2")],
                [InlineKeyboardButton("3 раза · 09:00, 13:00, 18:00", callback_data="freq_3")],
            ]
        },
        "settings_threshold": {
            "text": "🔔 <b>Порог алерта</b>\n\nПрисылать тревогу если необработанных больше:",
            "keyboard": [
                [InlineKeyboardButton("3 заявки", callback_data="threshold_3")],
                [InlineKeyboardButton("5 заявок", callback_data="threshold_5")],
                [InlineKeyboardButton("10 заявок", callback_data="threshold_10")],
            ]
        },
        "settings_team": {
            "text": "👥 <b>Командный режим</b>\n\nКому присылать отчёт:",
            "keyboard": [
                [InlineKeyboardButton("Только мне", callback_data="team_no")],
                [InlineKeyboardButton("Мне + РОП / партнёр", callback_data="team_yes")],
            ]
        },
        "mode_full": {"text": "✅ <b>Готово!</b> Режим: полный отчёт + алерты", "keyboard": None, "final": True},
        "mode_report": {"text": "✅ <b>Готово!</b> Режим: только отчёт без алертов", "keyboard": None, "final": True},
        "mode_alerts": {"text": "✅ <b>Готово!</b> Режим: только алерты при превышении порога", "keyboard": None, "final": True},
        "freq_1": {"text": "✅ <b>Готово!</b> Отчёт будет приходить в 09:00", "keyboard": None, "final": True},
        "freq_2": {"text": "✅ <b>Готово!</b> Отчёт будет приходить в 09:00 и 18:00", "keyboard": None, "final": True},
        "freq_3": {"text": "✅ <b>Готово!</b> Отчёт будет приходить в 09:00, 13:00 и 18:00", "keyboard": None, "final": True},
        "threshold_3": {"text": "✅ <b>Готово!</b> Алерт при 3+ необработанных заявках", "keyboard": None, "final": True},
        "threshold_5": {"text": "✅ <b>Готово!</b> Алерт при 5+ необработанных заявках", "keyboard": None, "final": True},
        "threshold_10": {"text": "✅ <b>Готово!</b> Алерт при 10+ необработанных заявках", "keyboard": None, "final": True},
        "team_no": {"text": "✅ <b>Готово!</b> Отчёт приходит только вам", "keyboard": None, "final": True},
        "team_yes": {"text": "✅ <b>Готово!</b> Добавьте Telegram вашего РОПа или партнёра — пришлём им тоже", "keyboard": None, "final": True},
    }

    r = responses.get(niche, {})
    await send(chat_id, context, r["text"],
               keyboard=r.get("keyboard"), delay=0.8)

    if r.get("final"):
        await asyncio.sleep(2)
        await show_final_offer(chat_id, context)


async def show_final_offer(chat_id, context):
    keyboard = [
        [InlineKeyboardButton("✅ Хочу так же на своих данных", url="https://pulse-pro.ru/#finalcta")],
        [InlineKeyboardButton("✍️ Написать напрямую", url=YOUR_TG)],
    ]
    await send(chat_id, context,
        "Вот и всё демо 🎯\n\n"
        "Это именно то что вы получите:\n"
        "— утренний отчёт каждый день в 09:00\n"
        "— алерты когда что-то идёт не так\n"
        "— еженедельная сводка\n"
        "— настройки прямо в боте\n\n"
        "<b>Подключаем за 1–3 дня на ваших реальных данных.\n"
        "Первый отчёт — бесплатно.</b>",
        keyboard=keyboard,
        delay=1.5)

    await asyncio.sleep(2)
    await show_tariffs(chat_id, context)


async def show_tariffs(chat_id, context):
    await typing(chat_id, context, 1.0)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "💎 <b>START · 7 000 ₽/мес</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "— Ежедневный отчёт в Telegram\n"
            "— До 2 алертов\n"
            "— 1 источник данных\n"
            "— Запуск за 1–3 дня"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Выбрать START →", callback_data="tariff_start")]
        ])
    )

    await asyncio.sleep(1.5)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "⭐ <b>BUSINESS · 15 000 ₽/мес</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "— Всё из START\n"
            "— До 5 алертов\n"
            "— До 3 источников данных\n"
            "— Ежемесячные доработки"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Выбрать BUSINESS →", callback_data="tariff_business")]
        ])
    )

    await asyncio.sleep(1.5)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🚀 <b>PRO · 25 000 ₽/мес</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            "— Всё из BUSINESS\n"
            "— Кастомные метрики\n"
            "— Любое число источников\n"
            "— Разбор метрик с командой"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Обсудить PRO →", url=YOUR_TG)]
        ])
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
