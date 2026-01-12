import os, asyncio, sqlite3, yt_dlp
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
SKIP_VOTE_PERCENT = int(os.getenv("SKIP_VOTE_PERCENT", "60"))
FORCE_VOTE_PERCENT = int(os.getenv("FORCE_VOTE_PERCENT", "60"))

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ================= INIT =================
app = Client("vc_music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
call = PyTgCalls(app)

queues = {}      # {chat_id: [(file, title)]}
paused = set()   # paused chat_ids
votes = {}       # {chat_id: {"skip": set(), "force": set()}}

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS group_admins (chat_id INTEGER, user_id INTEGER)")
db.commit()

def add_admin(chat_id, user_id):
    cur.execute("INSERT INTO group_admins VALUES (?,?)", (chat_id, user_id))
    db.commit()

def del_admin(chat_id, user_id):
    cur.execute("DELETE FROM group_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    db.commit()

def get_admins(chat_id):
    cur.execute("SELECT user_id FROM group_admins WHERE chat_id=?", (chat_id,))
    return {r[0] for r in cur.fetchall()}

# ================= HELPERS =================
def is_owner(uid): return uid == OWNER_ID

async def is_group_admin(client, chat_id, uid):
    if is_owner(uid): return True
    if uid in get_admins(chat_id): return True
    m = await client.get_chat_member(chat_id, uid)
    return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)

def need_votes(chat_id, percent):
    members = max(3, len(votes.get(chat_id, {}).get("members", set())))
    return max(2, members * percent // 100)

def download_audio(q):
    ydl_opts = {"format":"bestaudio","outtmpl":f"{DOWNLOAD_DIR}/%(id)s.%(ext)s","quiet":True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{q}", download=True)
        v = info["entries"][0]
        for e in ["mp3","m4a","webm","opus"]:
            p = f"{DOWNLOAD_DIR}/{v['id']}.{e}"
            if os.path.exists(p): return p, v["title"]
    raise Exception("download failed")

async def play_next(chat_id):
    if not queues.get(chat_id):
        await call.leave_group_call(chat_id)
        return
    f,_ = queues[chat_id].pop(0)
    await call.change_stream(chat_id, AudioPiped(f))

# ================= MUSIC =================
@app.on_message(filters.command("play") & filters.group)
async def play(_, m):
    q = " ".join(m.command[1:])
    if not q: return await m.reply("Use: /play song")
    f,t = download_audio(q)
    queues.setdefault(m.chat.id, []).append((f,t))
    votes[m.chat.id] = {"skip":set(),"force":set(),"members":set()}
    if len(queues[m.chat.id]) == 1:
        await call.join_group_call(m.chat.id, AudioPiped(f))
        await m.reply(f"🎵 Now Playing: {t}")
    else:
        await m.reply(f"➕ Queued: {t}")

@app.on_message(filters.command("pause") & filters.group)
async def pause(_, m):
    if m.chat.id not in paused:
        paused.add(m.chat.id)
        await call.pause_stream(m.chat.id)
        await m.reply("⏸ Paused")

@app.on_message(filters.command("resume") & filters.group)
async def resume(_, m):
    if m.chat.id in paused:
        paused.remove(m.chat.id)
        await call.resume_stream(m.chat.id)
        await m.reply("▶️ Resumed")

@app.on_message(filters.command("skip") & filters.group)
async def skip(_, m):
    if await is_group_admin(app, m.chat.id, m.from_user.id):
        await play_next(m.chat.id)
        return await m.reply("⏭ Skipped by admin")

    v = votes.setdefault(m.chat.id, {"skip":set(),"force":set(),"members":set()})
    v["skip"].add(m.from_user.id)
    v["members"].add(m.from_user.id)
    if len(v["skip"]) >= need_votes(m.chat.id, SKIP_VOTE_PERCENT):
        await play_next(m.chat.id)
        await m.reply("⏭ Skip vote passed")
    else:
        await m.reply("🗳 Skip vote added")

@app.on_message(filters.command("forceplay") & filters.group)
async def force(_, m):
    q = " ".join(m.command[1:])
    if not q: return await m.reply("Use: /forceplay song")
    f,t = download_audio(q)

    if await is_group_admin(app, m.chat.id, m.from_user.id):
        queues[m.chat.id] = [(f,t)]
        await call.change_stream(m.chat.id, AudioPiped(f))
        return await m.reply(f"🔥 Force play by admin: {t}")

    v = votes.setdefault(m.chat.id, {"skip":set(),"force":set(),"members":set()})
    v["force"].add(m.from_user.id)
    v["members"].add(m.from_user.id)
    if len(v["force"]) >= need_votes(m.chat.id, FORCE_VOTE_PERCENT):
        queues[m.chat.id] = [(f,t)]
        await call.change_stream(m.chat.id, AudioPiped(f))
        await m.reply("🔥 Force play vote passed")
    else:
        await m.reply("🗳 Force vote added")

@app.on_message(filters.command("stop") & filters.group)
async def stop(_, m):
    queues.pop(m.chat.id, None)
    await call.leave_group_call(m.chat.id)
    await m.reply("🛑 VC stopped")

@app.on_message(filters.command("queue") & filters.group)
async def qlist(_, m):
    q = queues.get(m.chat.id, [])
    if not q: return await m.reply("Queue empty")
    txt="Queue:\n"+"\n".join(f"{i+1}. {t}" for i,(_,t) in enumerate(q))
    await m.reply(txt)

# ================= ADMINS =================
@app.on_message(filters.command("addadmin") & filters.group)
async def addadm(_, m):
    if not is_owner(m.from_user.id): return
    if not m.reply_to_message: return await m.reply("Reply user + /addadmin")
    add_admin(m.chat.id, m.reply_to_message.from_user.id)
    await m.reply("✅ Group admin added")

@app.on_message(filters.command("deladmin") & filters.group)
async def deladm(_, m):
    if not is_owner(m.from_user.id): return
    if not m.reply_to_message: return await m.reply("Reply user + /deladmin")
    del_admin(m.chat.id, m.reply_to_message.from_user.id)
    await m.reply("❌ Group admin removed")

# ================= START =================
async def main():
    await app.start()
    await call.start()
    print("VC MUSIC BOT ULTIMATE RUNNING")
    await asyncio.Event().wait()

asyncio.run(main())
