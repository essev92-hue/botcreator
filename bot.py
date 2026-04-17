"""
bot.py — Twitter Thread Generator Bot (Pro Edition)
Alur: URL → Twitter handle → Bahasa → Generate
"""

import os
import re
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
    ConversationHandler,
)
from telegram.constants import ParseMode
from dotenv import load_dotenv
from thread_generator import ThreadGenerator
from ai_providers import get_available_providers, get_provider_status, PROVIDERS

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

generator = ThreadGenerator()

# ── Conversation states ──────────────────────────────────────────
WAITING_TWITTER = 1
WAITING_PROVIDER = 2

def build_welcome() -> str:
    from ai_providers import get_provider_status
    status = get_provider_status()
    provider_lines = []
    for pid, info in status.items():
        mark = "✅" if info["available"] else "❌"
        provider_lines.append(f"{mark} {info['label']}")
    providers_text = "\n".join(provider_lines)
    return f"""
🧵 *Twitter Thread Generator — Multi-AI Pro*

Riset mendalam *website + Twitter/X*, ditulis oleh AI pilihan kamu.

*AI Providers:*
{providers_text}

*Cara pakai:*
1️⃣ Kirim URL website project
2️⃣ Masukkan Twitter/X handle project
3️⃣ Pilih AI provider
4️⃣ Pilih bahasa
5️⃣ Thread siap! 🔥

Mulai dengan kirim URL project kamu 👇
"""

WELCOME_MSG = build_welcome()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(build_welcome(), parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
📖 *Panduan Bot Pro*

*Commands:*
/start — Mulai dari awal
/help  — Panduan ini
/cancel — Batalkan proses

*Alur penggunaan:*
1. Kirim URL website project
2. Bot auto-detect akun Twitter dari website
3. Konfirmasi atau input manual Twitter handle
4. Pilih bahasa thread
5. Tunggu 45-90 detik
6. Thread siap posting!

*Kenapa perlu Twitter?*
Akun Twitter project mengandung:
• Tone & voice asli project
• Announcements & milestone
• Community signals
• Quotes yang bisa dijadikan bukti

*Tips:*
• Selalu sertakan Twitter handle untuk hasil terbaik
• Gunakan URL resmi bukan artikel berita
• Coba URL /docs atau /whitepaper jika website minim info
""", parse_mode=ParseMode.MARKDOWN)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Proses dibatalkan. Kirim URL baru untuk mulai lagi.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationHandler.END

# ── Step 1: Terima URL ───────────────────────────────────────────
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ URL tidak valid. Pastikan dimulai dengan `http://` atau `https://`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    context.user_data["url"] = url
    context.user_data["twitter_handle"] = ""

    # Coba auto-detect Twitter dari URL domain name dulu
    domain = url.replace("https://","").replace("http://","").replace("www.","").split("/")[0].split(".")[0]

    keyboard = [
        [InlineKeyboardButton(f"✅ Ya, lanjut ke bahasa", callback_data="twitter:skip")],
        [InlineKeyboardButton("📝 Input Twitter manual", callback_data="twitter:manual")],
    ]

    await update.message.reply_text(
        f"✅ URL diterima!\n`{url}`\n\n"
        f"🐦 *Apakah kamu punya akun Twitter/X project ini?*\n\n"
        f"Dengan Twitter, thread jauh lebih kaya:\n"
        f"• Tone asli project\n"
        f"• Announcements & proof points\n"
        f"• Community signals\n\n"
        f"Ketik handle Twitter-nya (contoh: `@UniswapProtocol`) atau pilih skip:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAITING_TWITTER

# ── Step 2a: User ketik Twitter handle manual ────────────────────
async def receive_twitter_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Validasi: harus terlihat seperti Twitter handle atau URL
    handle_match = re.search(r"@?([A-Za-z0-9_]{1,50})", text)
    if not handle_match:
        await update.message.reply_text(
            "❌ Handle tidak valid. Contoh: `@UniswapProtocol` atau `UniswapProtocol`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_TWITTER

    handle = handle_match.group(1)
    context.user_data["twitter_handle"] = handle

    await _ask_provider(update.message, context, handle)
    return ConversationHandler.END

# ── Step 2b: Callback dari tombol ────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Twitter pilihan ──────────────────────────────────────────
    if data == "twitter:skip":
        context.user_data["twitter_handle"] = ""
        await _ask_provider(query.message, context, "")
        return ConversationHandler.END

    elif data == "twitter:manual":
        await query.message.reply_text(
            "📝 Ketik akun Twitter/X project:\n\n"
            "Contoh: `@UniswapProtocol` atau `UniswapProtocol`\n"
            "Atau paste URL: `https://x.com/UniswapProtocol`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return WAITING_TWITTER

    # ── Pilihan provider ─────────────────────────────────────────
    elif data.startswith("provider:"):
        provider = data.split(":")[1]
        context.user_data["provider"] = provider
        handle = context.user_data.get("twitter_handle", "")
        await _ask_language(query.message, context, handle)

    # ── Pilihan bahasa ───────────────────────────────────────────
    elif data.startswith("lang:"):
        lang = data.split(":")[1]
        url = context.user_data.get("url", "")
        twitter = context.user_data.get("twitter_handle", "")
        provider = context.user_data.get("provider", "groq")
        if not url:
            await query.message.reply_text("❌ URL hilang. Kirim ulang URL project.")
            return ConversationHandler.END
        await _run_generation(query.message, url, twitter, lang, provider)

    # ── Regenerate ───────────────────────────────────────────────
    elif data.startswith("regen:"):
        parts = data.split(":", 4)
        # format: regen:lang:provider:twitter:url
        _, lang, provider, twitter, url = parts
        await _run_generation(query.message, url, twitter, lang, provider)

    # ── Ganti Provider (dari footer) ─────────────────────────────
    elif data.startswith("switch_provider:"):
        _, twitter, url = data.split(":", 2)
        context.user_data["url"] = url
        context.user_data["twitter_handle"] = twitter if twitter != "_" else ""
        await _ask_provider(query.message, context, twitter if twitter != "_" else "")

async def _ask_provider(message, context, handle: str):
    """Step 2b: tanya pilihan AI provider"""
    available = get_available_providers()
    status = get_provider_status()

    keyboard = []
    for pid in ["groq", "deepseek", "openai"]:
        info = status[pid]
        if info["available"]:
            keyboard.append([InlineKeyboardButton(
                info["label"],
                callback_data=f"provider:{pid}"
            )])

    if not keyboard:
        # Tidak ada provider tersedia — tidak mungkin tapi handle saja
        await message.reply_text("❌ Tidak ada API key yang dikonfigurasi.")
        return

    handle_info = f"@{handle}" if handle else "Website only"
    await message.reply_text(
        f"🤖 *Pilih AI Provider:*\n\n"
        f"🌐 URL: `{context.user_data.get('url','')}`\n"
        f"🐦 Twitter: `{handle_info}`\n\n"
        f"Setiap model punya karakter berbeda:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def _ask_language(message, context, handle: str):
    handle_info = f"Twitter: @{handle}" if handle else "Twitter: skip (website only)"
    keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang:english"),
         InlineKeyboardButton("🇮🇩 Bahasa Indonesia", callback_data="lang:indonesia")]
    ]
    await message.reply_text(
        f"🌐 *Pilih bahasa thread:*\n\n"
        f"Provider: {PROVIDERS.get(context.user_data.get('provider','groq'),{}).get('label','—')}\n"
        f"Twitter: {handle_info}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ── Step 3: Generate thread ──────────────────────────────────────
async def _run_generation(message, url: str, twitter_handle: str, lang: str, provider: str = "groq"):
    lang_label = "🇬🇧 English" if lang == "english" else "🇮🇩 Bahasa Indonesia"
    tw_label = f"@{twitter_handle}" if twitter_handle else "Website only"
    provider_cfg = PROVIDERS.get(provider, PROVIDERS["groq"])
    provider_label = provider_cfg["label"]

    steps = [
        "🌐 Scraping website & sub-pages...",
        "🐦 Riset akun Twitter/X project...",
        "🎨 Menganalisis brand DNA & visual identity...",
        "🧠 AI menulis thread sesuai karakter merek...",
    ]

    loading = await message.reply_text(
        f"🔍 *Riset mendalam dimulai!*\n\n"
        f"📎 `{url}`\n"
        f"🐦 `{tw_label}`\n"
        f"🌐 {lang_label}\n"
        f"🤖 {provider_label}\n\n"
        f"⏳ {steps[0]}\n"
        f"⏳ {steps[1]}\n"
        f"⏳ {steps[2]}\n"
        f"⏳ {steps[3]}\n\n"
        f"_Mohon tunggu 45–90 detik..._",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Update status scraping
    async def update_status(step_idx: int):
        status_lines = []
        for i, step in enumerate(steps):
            if i < step_idx:
                status_lines.append(f"✅ {step}")
            elif i == step_idx:
                status_lines.append(f"🔄 {step}")
            else:
                status_lines.append(f"⏳ {step}")

        try:
            await loading.edit_text(
                f"🔍 *Riset mendalam dimulai!*\n\n"
                f"📎 `{url}`\n"
                f"🐦 `{tw_label}`\n"
                f"🌐 {lang_label}\n"
                f"🤖 {provider_label}\n\n"
                + "\n".join(status_lines) +
                "\n\n_Mohon tunggu..._",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass

    try:
        # Jalankan dengan status update
        await update_status(0)
        await asyncio.sleep(1)

        # Generate (ini yang paling lama)
        # Kita jalankan dengan progress update manual
        gen_task = asyncio.create_task(
            generator.generate_thread(url, twitter_handle, lang, provider)
        )

        # Update status sementara menunggu
        await asyncio.sleep(6)
        if not gen_task.done():
            await update_status(1)
        await asyncio.sleep(10)
        if not gen_task.done():
            await update_status(2)
        await asyncio.sleep(8)
        if not gen_task.done():
            await update_status(3)

        result = await gen_task

        await loading.delete()

        if not result["success"]:
            await message.reply_text(
                f"❌ *Gagal generate thread*\n\n`{result['error']}`\n\n"
                "Tips:\n"
                "• Coba URL halaman /docs atau /whitepaper\n"
                "• Pastikan website bisa diakses\n"
                "• Coba lagi beberapa saat",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # ── Kirim header info ────────────────────────────────────
        tw_status = ""
        if result.get("twitter_handle"):
            if result.get("twitter_success"):
                source_label = {
                    "nitter": "via Nitter ✅",
                    "xcom": "via x.com ✅",
                    "websearch": "via Web Search ⚠️",
                }.get(result.get("twitter_source",""), "✅")
                tw_status = f"🐦 @{result['twitter_handle']}: {source_label}\n"
            else:
                tw_status = f"🐦 @{result['twitter_handle']}: ⚠️ Tidak tersedia\n"

        used_emoji = result.get("provider_emoji", "🤖")
        used_name  = result.get("provider_name", provider)
        used_model = result.get("provider_model", "")
        brand_tag  = "🎨 Brand DNA analyzed" if result.get("brand_analyzed") else ""

        await message.reply_text(
            f"✅ *Thread selesai!*\n\n"
            f"📌 *{result['project_name']}*\n"
            f"🧵 {result['tweet_count']} tweets · {lang_label}\n"
            f"{tw_status}"
            f"{used_emoji} *{used_name}* (`{used_model}`)\n"
            f"{brand_tag}\n\n"
            f"⬇️ Thread lengkap:",
            parse_mode=ParseMode.MARKDOWN,
        )

        # ── Kirim tiap tweet ─────────────────────────────────────
        for tweet in result["tweets"]:
            safe = _safe_markdown(tweet)
            try:
                await message.reply_text(safe, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                # Fallback tanpa markdown
                await message.reply_text(tweet)
            await asyncio.sleep(0.7)

        # ── Footer ───────────────────────────────────────────────
        tw_handle = result.get("twitter_handle", "")
        regen_twitter = tw_handle or "_"
        used_provider = result.get("provider_used", provider)
        keyboard = [
            [
                InlineKeyboardButton("🔄 EN", callback_data=f"regen:english:{used_provider}:{regen_twitter}:{url}"),
                InlineKeyboardButton("🔄 ID", callback_data=f"regen:indonesia:{used_provider}:{regen_twitter}:{url}"),
            ],
            [
                InlineKeyboardButton("🔁 Ganti Provider", callback_data=f"switch_provider:{regen_twitter}:{url}"),
            ]
        ]
        await message.reply_text(
            "✨ *Thread siap diposting!*\n\n"
            "💡 _Post satu tweet per 1-2 menit untuk engagement terbaik._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception as e:
        logger.error(f"Generation error: {e}", exc_info=True)
        try:
            await loading.delete()
        except Exception:
            pass
        await message.reply_text(
            f"❌ *Terjadi kesalahan*\n\n`{str(e)}`\n\nCoba kirim URL lagi.",
            parse_mode=ParseMode.MARKDOWN,
        )

def _safe_markdown(text: str) -> str:
    """Sanitize teks agar aman untuk Telegram Markdown"""
    # Escape backtick dan bracket
    text = text.replace("`", "'")
    text = text.replace("[", "(").replace("]", ")")
    # Pastikan bold/italic tidak broken
    text = re.sub(r"\*{3,}", "**", text)
    return text

async def handle_non_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cek apakah sedang dalam state waiting twitter
    await update.message.reply_text(
        "👋 Kirimkan URL website project untuk mulai!\n\n"
        "Contoh: `https://uniswap.org`",
        parse_mode=ParseMode.MARKDOWN,
    )

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN tidak ditemukan di .env")

    app = Application.builder().token(token).build()

    # ConversationHandler untuk alur URL → Twitter → Bahasa
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & filters.Regex(r"https?://\S+"), handle_url)
        ],
        states={
            WAITING_TWITTER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"https?://\S+"),
                    receive_twitter_handle,
                ),
                CallbackQueryHandler(handle_callback, pattern="^twitter:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_callback))  # untuk lang: dan regen: di luar conv
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"https?://\S+"),
            handle_non_url,
        )
    )

    logger.info("🤖 Bot Pro started — Website + Twitter Research Mode")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
