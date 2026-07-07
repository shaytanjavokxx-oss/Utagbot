import logging
import random
import sqlite3
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from config import BOT_TOKEN, ADMINS, DB_FILE, BOT_INFO, ALL_JOKES

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ═══════════ BAZA ═══════════
def db():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            phone TEXT,
            verified INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS members (
            chat_id INTEGER,
            user_id INTEGER,
            first_name TEXT,
            username TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    conn.commit()
    conn.close()


def save_member(chat_id, user_id, first_name, username):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO members (chat_id, user_id, first_name, username) "
        "VALUES (?,?,?,?)",
        (chat_id, user_id, first_name, username)
    )
    conn.commit()
    conn.close()


def get_members(chat_id):
    conn = db()
    rows = conn.execute(
        "SELECT user_id, first_name, username FROM members WHERE chat_id=?",
        (chat_id,)
    ).fetchall()
    conn.close()
    return rows


def remove_member(chat_id, user_id):
    conn = db()
    conn.execute("DELETE FROM members WHERE chat_id=? AND user_id=?",
                 (chat_id, user_id))
    conn.commit()
    conn.close()


def save_user(user_id, first_name, username):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?,?,?)",
        (user_id, first_name, username)
    )
    conn.execute(
        "UPDATE users SET first_name=?, username=? WHERE user_id=?",
        (first_name, username, user_id)
    )
    conn.commit()
    conn.close()


def set_verified(user_id, phone):
    conn = db()
    conn.execute("UPDATE users SET phone=?, verified=1 WHERE user_id=?",
                 (phone, user_id))
    conn.commit()
    conn.close()


def is_verified(user_id):
    conn = db()
    row = conn.execute("SELECT verified FROM users WHERE user_id=?",
                       (user_id,)).fetchone()
    conn.close()
    return row and row[0] == 1


def get_user(user_id):
    conn = db()
    row = conn.execute(
        "SELECT first_name, username, phone FROM users WHERE user_id=?",
        (user_id,)).fetchone()
    conn.close()
    return row


def all_user_ids():
    conn = db()
    rows = conn.execute("SELECT user_id FROM users WHERE verified=1").fetchall()
    conn.close()
    return [r[0] for r in rows]


def user_count():
    conn = db()
    n = conn.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0]
    conn.close()
    return n


# ═══════════ /START ═══════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.first_name or "", user.username or "")

    if is_verified(user.id):
        await update.message.reply_text(
            f"👋 Salom, {user.first_name}!\n\n"
            "✍️ Savol yoki murojaatingizni yozing — adminlarga yetkazamiz.\n"
            "ℹ️ Bot haqida to'liq ma'lumot: /yordam",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Kontakt so'rash tugmasi
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Kontaktni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        f"👋 Salom, {user.first_name}!\n\n"
        "🤖 Siz bot emasligingizni tasdiqlash uchun telefon raqamingizni yuboring.\n\n"
        "👇 Pastdagi tugmani bosing (faqat 🇺🇿 O'zbekiston raqamlari qabul qilinadi):",
        reply_markup=kb
    )


# ═══════════ /YORDAM — BOT HAQIDA MA'LUMOT ═══════════
async def yordam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(BOT_INFO, parse_mode="Markdown")


# ═══════════ KONTAKT QABUL QILISH ═══════════
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact

    # O'zganing kontaktini yuborsa — rad etish
    if contact.user_id != user.id:
        await update.message.reply_text(
            "❌ Iltimos, o'zingizning raqamingizni yuboring (birovnikini emas).\n"
            "👇 Tugmani bosing:"
        )
        return

    phone = contact.phone_number.replace(" ", "").replace("+", "")

    # Faqat O'zbekiston (998) raqamlari
    if not phone.startswith("998"):
        await update.message.reply_text(
            "❌ Kechirasiz, faqat 🇺🇿 O'zbekiston (+998) raqamlari qabul qilinadi.\n\n"
            "Boshqa davlat raqami bilan ro'yxatdan o'tolmaysiz."
        )
        return

    set_verified(user.id, phone)
    await update.message.reply_text(
        "✅ Tasdiqlandi! Rahmat.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✍️ Endi savol yoki murojaatingizni yozing — "
        "adminlarga yetkazamiz. Tez orada javob olasiz!",
        reply_markup=ReplyKeyboardRemove()
    )

    # Adminlarga xabar
    uname = f"@{user.username}" if user.username else "username yo'q"
    for admin_id in ADMINS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🆕 Yangi foydalanuvchi ro'yxatdan o'tdi:\n"
                f"👤 {user.first_name} ({uname})\n"
                f"🆔 {user.id}\n"
                f"📱 +{phone}"
            )
        except Exception:
            pass


# ═══════════ GURUH: A'ZOLARNI ESLAB QOLISH ═══════════
async def group_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhda kim yozsa, bazaga saqlaymiz (keyin teg qilish uchun)."""
    if not update.message or not update.effective_user:
        return
    user = update.effective_user
    if user.is_bot:
        return
    save_member(
        update.effective_chat.id,
        user.id,
        user.first_name or "",
        user.username or ""
    )


async def is_group_admin(update, context):
    member = await context.bot.get_chat_member(
        update.effective_chat.id, update.effective_user.id
    )
    return member.status in ("administrator", "creator")


# ═══════════ /ALL — HAMMANI CHAQIRISH ═══════════
async def all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("Bu buyruq faqat guruhda ishlaydi!")
        return
    # Faqat guruh adminlari chaqira olsin
    if not await is_group_admin(update, context):
        await update.message.reply_text("❌ Faqat guruh adminlari hammani chaqira oladi!")
        return

    chat_id = update.effective_chat.id
    members = get_members(chat_id)
    # Buyruq yozgan odamni ham qo'shib qo'yamiz
    u = update.effective_user
    save_member(chat_id, u.id, u.first_name or "", u.username or "")
    members = get_members(chat_id)

    if not members:
        await update.message.reply_text(
            "Hali hech kim eslab qolinmagan.\n"
            "A'zolar guruhda yozgani sari ro'yxatga qo'shiladi."
        )
        return

    # Qo'shimcha matn bo'lsa (masalan /all yig'ilish bor)
    extra = " ".join(context.args) if context.args else "📢 Diqqat!"

    # Har a'zoga: teg + tasodifiy hazil matn, alohida qatorda
    lines = []
    for uid, fname, uname in members:
        if uname:
            mention = f"@{uname}"
        else:
            safe = (fname or "user").replace("<", "").replace(">", "")
            mention = f'<a href="tg://user?id={uid}">{safe}</a>'
        joke = random.choice(ALL_JOKES)
        lines.append(f"{mention} {joke}")

    for i in range(0, len(lines), 25):
        chunk = lines[i:i + 25]
        header = extra + "\n\n" if i == 0 else ""
        await context.bot.send_message(
            chat_id,
            header + "\n".join(chunk),
            parse_mode="HTML"
        )


# ═══════════ /USERS — ADMIN UCHUN: BAZADAGI HAMMA USER ═══════════
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    # Bazadagi BARCHA foydalanuvchi (shaxsiy chatga /start bosganlar)
    conn = db()
    rows = conn.execute(
        "SELECT user_id, first_name, username, phone, verified FROM users "
        "ORDER BY verified DESC, user_id"
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 Hali hech kim bazada yo'q.")
        return

    verified = [r for r in rows if r[4] == 1]
    lines = [f"👥 Bazadagi foydalanuvchilar: {len(rows)} ta "
             f"(tasdiqlangan: {len(verified)} ta)\n"]
    for i, (uid, fname, uname, phone, ver) in enumerate(rows, 1):
        u = f"@{uname}" if uname else "username yo'q"
        mark = "✅" if ver else "⏳"
        tel = f" | 📱+{phone}" if phone else ""
        lines.append(f"{i}. {mark} {fname} — {u} (ID: {uid}){tel}")

    text = "\n".join(lines)
    # Uzun bo'lsa bo'laklarga bo'lib yuboramiz (Telegram limiti ~4096)
    for i in range(0, len(text), 3500):
        await update.message.reply_text(text[i:i + 3500])


# ═══════════ /GURUH — SHU GURUHNING FAOL A'ZOLARI ═══════════
async def guruh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "Bu buyruqni guruh ichida yozing — o'sha guruhning faol a'zolarini ko'rsataman.\n"
            "Bazadagi hamma foydalanuvchi uchun: /users"
        )
        return
    members = get_members(update.effective_chat.id)
    if not members:
        await update.message.reply_text("Hali bu guruhda hech kim eslab qolinmagan.")
        return
    lines = [f"👥 Bu guruhning faol a'zolari ({len(members)} ta):\n"]
    for i, (uid, fname, uname) in enumerate(members, 1):
        u = f"@{uname}" if uname else "username yo'q"
        lines.append(f"{i}. {fname} — {u} (ID: {uid})")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await update.message.reply_text(text[i:i + 3500])


# ═══════════ FOYDALANUVCHI XABARI → ADMINLARGA ═══════════
async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Guruhda — bu funksiya ishlamaydi (faqat shaxsiy murojaat)
    if update.effective_chat.type != "private":
        return

    # Admin yozsa — bu funksiya emas (adminlar /send ishlatadi)
    if user.id in ADMINS:
        await update.message.reply_text(
            "ℹ️ Foydalanuvchiga javob berish uchun:\n"
            "/send ID matn\n\n"
            "Masalan: /send 123456789 Salom, savolingiz bo'yicha...\n\n"
            "Hammaga xabar: /hammaga matn"
        )
        return

    # Tasdiqlanmagan bo'lsa — start'ga qaytar
    if not is_verified(user.id):
        await update.message.reply_text(
            "⚠️ Avval telefon raqamingizni yuboring.\n/start bosing."
        )
        return

    uname = f"@{user.username}" if user.username else "username yo'q"
    text = update.message.text or "[matnsiz xabar]"

    # Barcha adminlarga yuborish (javob berish uchun ID bilan)
    header = (
        f"💬 Yangi xabar:\n"
        f"👤 {user.first_name} ({uname})\n"
        f"🆔 {user.id}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"↩️ Javob: /send {user.id} javobingiz"
    )
    sent = False
    for admin_id in ADMINS:
        try:
            await context.bot.send_message(admin_id, header)
            sent = True
        except Exception:
            pass

    if sent:
        await update.message.reply_text(
            "✅ Xabaringiz adminlarga yuborildi!\n"
            "⏳ Tez orada javob olasiz."
        )
    else:
        await update.message.reply_text(
            "❌ Xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."
        )


# ═══════════ /SEND — ADMIN JAVOBI ═══════════
async def send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format: /send ID matn\n\n"
            "Masalan: /send 123456789 Salom, savolingizga javob..."
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID raqam bo'lishi kerak.")
        return

    matn = " ".join(args[1:])
    try:
        await context.bot.send_message(
            target_id,
            f"📩 Admindan javob:\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"{matn}"
        )
        await update.message.reply_text(f"✅ Yuborildi (ID: {target_id})")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Yuborilmadi. Foydalanuvchi botni bloklagan bo'lishi mumkin.\n{e}"
        )


# ═══════════ /HAMMAGA — HAMMAGA XABAR ═══════════
async def hammaga_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    if not context.args:
        await update.message.reply_text("❌ Format: /hammaga xabar matni")
        return

    matn = " ".join(context.args)
    ids = all_user_ids()
    ok, fail = 0, 0
    await update.message.reply_text(f"📤 {len(ids)} ta foydalanuvchiga yuborilmoqda...")

    for uid in ids:
        try:
            await context.bot.send_message(
                uid,
                f"📢 E'lon:\n━━━━━━━━━━━━━━━━━━\n\n{matn}"
            )
            ok += 1
        except Exception:
            fail += 1

    await update.message.reply_text(
        f"✅ Yuborildi: {ok} ta\n❌ Yuborilmadi: {fail} ta"
    )


# ═══════════ /STAT — ADMIN ═══════════
async def stat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    await update.message.reply_text(
        f"📊 Statistika:\n👥 Tasdiqlangan foydalanuvchilar: {user_count()} ta"
    )


# ═══════════ MAIN ═══════════
def main():
    init_db()
    app = (Application.builder()
           .token(BOT_TOKEN)
           .connect_timeout(30).read_timeout(30).write_timeout(30)
           .build())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("yordam", yordam_cmd))
    app.add_handler(CommandHandler("help", yordam_cmd))
    app.add_handler(CommandHandler("send", send_cmd))
    app.add_handler(CommandHandler("hammaga", hammaga_cmd))
    app.add_handler(CommandHandler("stat", stat_cmd))
    app.add_handler(CommandHandler("all", all_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("guruh", guruh_cmd))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    # Shaxsiy chatdagi matn → adminga murojaat
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, user_message))
    # Guruhdagi har xabar → a'zoni eslab qolish (teg uchun)
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND, group_track))

    print("✅ Support bot ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()
