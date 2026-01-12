# vc-music-

# 🎧 Telegram VC Music Bot

A powerful Telegram **Voice Chat Music Bot** with public play, admin override, force play, voting system, and permanent admin storage.

Built using **Pyrogram + PyTgCalls**.  
Tested on Replit. Recommended for VPS deployment.

---

## 🚀 Features

### 🎵 Music Playback
- `/play <song>` – Play music in voice chat (any member)
- `/pause` – Pause music
- `/resume` – Resume music
- `/queue` – Show current queue
- `/stop` – Stop music & leave VC

### 🔥 Force Play
- `/forceplay <song>`
- Admin: instant force play
- Members: vote-based force play

### 🗳 Voting System
- Vote-based `/skip`
- Vote-based `/forceplay`
- Vote percentage configurable via ENV
- **Admin actions bypass voting**

### 👑 Permissions
- **Owner** (global control)
- **Per-group admins** (stored permanently in DB)
- Telegram group admins auto-recognized

### 🧹 Smart Behavior
- Auto leave VC when queue is empty
- Auto reset votes on new song
- Permanent admin storage (SQLite)

---

## 🔐 Environment Variables

Set these in **Replit Secrets / VPS ENV**:
