import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_port_listener():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# Запускаем "обманщик портов" в фоновом потоке
threading.Thread(target=run_port_listener, daemon=True).start()

import json
import os
from datetime import datetime, date

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ─────────────────────────────────────────────
# НАСТРОЙКИ — замени на свои
# ─────────────────────────────────────────────
TOKEN = "8862704513:AAGBmXzbc82tYIv_2_z7bA3FktYIv9xDYlQ"
GROUP_CHAT_ID = -5365467144 # ID вашей группы (отрицательное число)

# Дата старта отсчёта (день 15 = завтра)
# Если завтра 17 июня 2026 — день 15 → день 1 был 3 июня 2026
CHALLENGE_START_DATE = date(2026, 6, 3)  # дата первого дня челленджа

PARTICIPANTS = ["Артём", "Валера", "Дима", "Денис"]

DATA_FILE = "pushup_data.json"
# ─────────────────────────────────────────────


def get_current_day() -> int:
    """Возвращает текущий день челленджа (1–100)."""
    delta = (date.today() - CHALLENGE_START_DATE).days + 1
    return max(1, min(delta, 100))


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "days": {}}


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_summary(data: dict, day: int) -> str:
    """Строит текстовую сводку за день."""
    day_key = str(day)
    done = data["days"].get(day_key, [])

    lines = [f"💪 *День {day} / 100 — итог*\n"]
    for name in PARTICIPANTS:
        if name in done:
            lines.append(f"✅ {name} — сделал!")
        else:
            lines.append(f"❌ {name} — не сделал")

    total = len(done)
    lines.append(f"\n🏆 Выполнили: {total}/{len(PARTICIPANTS)}")
    return "\n".join(lines)


def get_name_by_user_id(data: dict, user_id: int) -> str | None:
    return data["users"].get(str(user_id))


# ─────────────────────────────────────────────
# КОМАНДЫ
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот челленджа 100 отжиманий.\n\n"
        "Команды:\n"
        "/register Имя — зарегистрироваться (пример: /register Артём)\n"
        "/status — посмотреть статус сегодня\n"
        "/day — узнать текущий день челленджа\n\n"
        "Чтобы отметить отжимания — просто напиши + в чат."
    )


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text("Напиши своё имя: /register Артём")
        return

    name = context.args[0].strip()
    if name not in PARTICIPANTS:
        await update.message.reply_text(
            f"❗ Имя «{name}» не в списке участников.\n"
            f"Участники: {', '.join(PARTICIPANTS)}"
        )
        return

    data["users"][user_id] = name
    save_data(data)
    await update.message.reply_text(f"✅ {name}, ты зарегистрирован! Теперь пиши + каждый день.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    day = get_current_day()
    summary = build_summary(data, day)
    await update.message.reply_text(summary, parse_mode="Markdown")


async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = get_current_day()
    await update.message.reply_text(f"📅 Сегодня день *{day}* из 100.", parse_mode="Markdown")


# ─────────────────────────────────────────────
# ОБРАБОТКА + В ЧАТ
# ─────────────────────────────────────────────

async def handle_plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() != "+":
        return

    data = load_data()
    user_id = update.effective_user.id
    name = get_name_by_user_id(data, user_id)

    if not name:
        await update.message.reply_text(
            "❗ Сначала зарегистрируйся командой /register Имя"
        )
        return

    day = get_current_day()
    day_key = str(day)

    if day_key not in data["days"]:
        data["days"][day_key] = []

    if name in data["days"][day_key]:
        await update.message.reply_text(f"👍 {name}, ты уже отметился сегодня!")
        return

    data["days"][day_key].append(name)
    save_data(data)

    # Строим ответ
    done = data["days"][day_key]
    not_done = [p for p in PARTICIPANTS if p not in done]

    lines = [f"💪 *День {day} / 100*\n", f"✅ {name} сделал отжимания!\n"]

    if not_done:
        lines.append("Ещё не отметились:")
        for n in not_done:
            lines.append(f"⏳ {n}")
    else:
        lines.append("🎉 Все участники сегодня отжались!")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─────────────────────────────────────────────
# ЕЖЕДНЕВНЫЙ ИТОГ В 23:00
# ─────────────────────────────────────────────

async def send_daily_summary(app):
    data = load_data()
    day = get_current_day()
    summary = build_summary(data, day)
    await app.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=summary,
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("day", cmd_day))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plus))

    # Планировщик — итог в 23:00 каждый день
    scheduler = AsyncIOScheduler(timezone="Europe/Kiev")
    scheduler.add_job(
        send_daily_summary,
        "cron",
        hour=23,
        minute=0,
        args=[app],
    )
    scheduler.start()

    print("🤖 Бот запущен!")
    app.run_polling()


import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Умный перехватчик: обманываем планировщик только на момент его запуска
orig_start = AsyncIOScheduler.start

def patched_start(self, *args, **kwargs):
    orig_get = asyncio.get_running_loop
    asyncio.get_running_loop = lambda: asyncio.get_event_loop()
    try:
        return orig_start(self, *args, **kwargs)
    finally:
        asyncio.get_running_loop = orig_get  # Сразу возвращаем всё на место

AsyncIOScheduler.start = patched_start

if __name__ == "__main__":
    # Создаем стабильное окружение для Python 3.10
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    main()



