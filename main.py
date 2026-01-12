import os
import asyncio
import sqlite3
from pyrogram import Client, filters
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
import yt_dlp

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))  # bot owner (super admin)

if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
    print("❌ Missing ENV variables")
    exit(1)

# ================= CLIENT =================
app = Client(
    "vc-music-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)
call = PyTgCalls(app)

# ================= STORAGE =================
queues = {}      # chat_id -> [(file, title)]
paused = set()
users = set()

# ================= DATABASE =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS group_admins (
    chat_id INTEGER,
    user_id INTEGER
)
""")
db.commit()

def add_group_admin(chat_id, user_id):
    cur.execute(
        "INSERT INTO group_admins (chat_id, user_id) VALUES (?, ?)",
        (chat_id, user_id),
    )
    db.commit()

def remove_group_admin(chat_id, user_id):
    cur.execute(
        "DELETE FROM group_admins WHERE chat_id=? AND user_id=?",
        (chat_id, user_id),
    )
    db.commit()

def get_group_admins(chat_id):
    cur.execute(
        "SELECT user_id FROM group_admins WHERE chat_id=?",
        (chat_id,),
    )
    return {row[0] for row in cur.fetchall()}

# ================= HELPERS =================
def is_owner(uid: int) -> bool:
    return uid == OWNER_ID

def is_group_admin(chat_id: int, uid: int) -> bool:
    if uid == OWNER_ID:
        return True
    return uid in get_group_admins(chat_id)

def is_global_admin(uid: int) -> bool:
    return uid == OWNER_ID

# ================= YTDLP =================
os.makedirs("downloads", exist_ok=True)
ydl_opts = {
    "format": "bestaudio/best",
    "outtmpl": "downloads/%(id)s.%(ext)s",
    "quiet": True,
}

def download_song(song):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{song}", download=True)
        v = info["entries"][0]
        return f"downloads/{v['id']}.webm", v["title"]

# ================= MUSIC COMMANDS (PUBLIC) =================
@app.on_message(filters.command("play") & filters.group)
async def play(_, m):
    users.add(m.from_user.id)

    if len(m.command) < 2:
        return await m.reply("Use: /play song name")

    q = " ".join(m.command[1:])
    msg = await m.reply("🔍 Downloading...")

    try:
        file, title = await asyncio.get_event_loop().run_in_executor(
            None, download_song, q
        )
    except:
        return await msg.edit("❌ Song nahi mila")

    queues.setdefault(m.chat.id, []).append((file, title))

    if len(queues[m.chat.id]) == 1:
        await call.play(m.chat.id, MediaStream(file, audio_only=True))
        await msg.edit(f"🎵 Now Playing:\n{title}")
    else:
        await msg.edit(f"➕ Queued:\n{title}")

@app.on_message(filters.command("forceplay") & filters.group)
async def forceplay(_, m):
    users.add(m.from_user.id)

    if len(m.command) < 2:
        return await m.reply("Use: /forceplay song name")

    q = " ".join(m.command[1:])
    msg = await m.reply("🔥 Force playing...")

    try:
        file, title = await asyncio.get_event_loop().run_in_executor(
            None, download_song, q
        )
    except:
        return await msg.edit("❌ Song nahi mila")

    queues[m.chat.id] = [(file, title)]
    await call.play(m.chat.id, MediaStream(file, audio_only=True))
    await msg.edit(f"🔥 Force Playing:\n{title}")

@app.on_message(filters.command("pause") & filters.group)
async def pause(_, m):
    await call.pause(m.chat.id)
    paused.add(m.chat.id)
    await m.reply("⏸ Paused")

@app.on_message(filters.command("resume") & filters.group)
async def resume(_, m):
    await call.resume(m.chat.id)
    paused.discard(m.chat.id)
    await m.reply("▶️ Resumed")

@app.on_message(filters.command("skip") & filters.group)
async def skip(_, m):
    if not queues.get(m.chat.id):
        return await m.reply("❌ Queue empty")

    queues[m.chat.id].pop(0)

    if not queues[m.chat.id]:
        await call.leave_call(m.chat.id)
        return await m.reply("🛑 Music ended")

    file, title = queues[m.chat.id][0]
    await call.play(m.chat.id, MediaStream(file, audio_only=True))
    await m.reply(f"⏭ Skipped\nNow Playing:\n{title}")

@app.on_message(filters.command("stop") & filters.group)
async def stop(_, m):
    queues.pop(m.chat.id, None)
    await call.leave_call(m.chat.id)
    await m.reply("🛑 Music stopped")

@app.on_message(filters.command("queue") & filters.group)
async def queue(_, m):
    if not queues.get(m.chat.id):
        return await m.reply("📭 Queue empty")

    text = "📜 Queue:\n\n"
    for i, (_, title) in enumerate(queues[m.chat.id], 1):
        text += f"{i}. {title}\n"

    await m.reply(text)

# ================= PER-GROUP ADMIN COMMANDS =================
@app.on_message(filters.command("addadmin") & filters.group)
async def addadmin(_, m):
    if not is_owner(m.from_user.id):
        return await m.reply("❌ Sirf owner admin add kar sakta hai")

    if not m.reply_to_message:
        return await m.reply("Reply user + /addadmin")

    uid = m.reply_to_message.from_user.id
    add_group_admin(m.chat.id, uid)
    await m.reply("✅ Group admin added")

@app.on_message(filters.command("deladmin") & filters.group)
async def deladmin(_, m):
    if not is_owner(m.from_user.id):
        return await m.reply("❌ Sirf owner admin remove kar sakta hai")

    if not m.reply_to_message:
        return await m.reply("Reply user + /deladmin")

    uid = m.reply_to_message.from_user.id
    remove_group_admin(m.chat.id, uid)
    await m.reply("❌ Group admin removed")

# ================= GLOBAL ADMIN =================
@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast(_, m):
    if not is_global_admin(m.from_user.id):
        return await m.reply("❌ Owner only")

    if len(m.command) < 2:
        return await m.reply("Use: /broadcast message")

    text = " ".join(m.command[1:])
    sent = 0

    for uid in users:
        try:
            await app.send_message(uid, f"📢 {text}")
            sent += 1
        except:
            pass

    await m.reply(f"✅ Broadcast sent to {sent} users")

@app.on_message(filters.command("status") & filters.private)
async def status(_, m):
    if not is_global_admin(m.from_user.id):
        return await m.reply("❌ Owner only")

    await m.reply(
        f"📊 Bot Status\n\n"
        f"👥 Users: {len(users)}\n"
        f"🎧 Active VC: {len(queues)}"
    )

# ================= START =================
async def main():
    await app.start()
    await call.start()
    print("✅ VC Music Bot Running (Per-Group Admin Enabled)")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
