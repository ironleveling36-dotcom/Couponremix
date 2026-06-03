# 🛒 Advanced Telegram Shop Bot

> Feature-complete, production-ready Telegram shop bot built with **aiogram v3** + **aiosqlite**.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🛒 Shop | Categories with live stock counters |
| 🎟 Coupons | Bulk upload, auto-deliver on purchase |
| 💳 UPI Payment | QR code + UPI ID display |
| 💰 Wallet | Top-up, pay from wallet instantly |
| 🎁 Referral | Unique links, wallet bonus on signup |
| 📢 Channel Gate | Force-join before bot access |
| 👑 Admin Panel | Full CRUD, broadcast, stats |
| 📊 Statistics | Revenue, orders by category |
| 🔄 Self-Healing | Supervisor loop + admin crash alerts |
| 🚀 Railway Ready | One-click deploy |

---

## 🚀 Quick Deploy to Railway

### 1. Push to GitHub

```bash
cd telebot/
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Create Railway Project

1. Go to [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo**
3. Select your repo
4. Click **Add Variables** and set:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | Your bot token from @BotFather |
| `ADMIN_IDS` | Your Telegram user ID (comma-separated for multiple) |
| `BOT_USERNAME` | Your bot's username (without @) |
| `REQUIRED_CHANNEL` | `@yourchannel` or leave empty |
| `REFERRAL_BONUS` | `10` (₹10 per referral) |
| `DB_PATH` | `/app/data/shop.db` |

### 3. Add Persistent Volume (important!)

In Railway dashboard:
- **Volumes → Add Volume**
- Mount path: `/app/data`
- This ensures your database survives redeploys

### 4. Deploy

Railway auto-deploys on every push. Done! 🎉

---

## 🏃 Run Locally

```bash
# 1. Clone / copy bot files
cd telebot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
nano .env   # Fill in BOT_TOKEN, ADMIN_IDS, etc.

# 4. Run
python main.py
```

---

## 📁 Project Structure

```
telebot/
├── main.py                # Entry point + self-healing supervisor
├── config.py              # Env var loader
├── requirements.txt
├── Procfile               # Railway/Heroku process file
├── railway.toml           # Railway deploy config
├── .env.example           # Config template
│
├── database/
│   └── db.py              # All SQLite queries (aiosqlite)
│
├── handlers/
│   ├── admin.py           # Admin panel (categories, coupons, orders, broadcast…)
│   ├── user.py            # /start, shop, my orders
│   ├── payment.py         # UPI "I have paid" + wallet payment
│   ├── wallet.py          # Wallet top-up flow
│   └── referral.py        # Referral link + stats
│
└── utils/
    ├── keyboards.py       # All InlineKeyboardMarkup builders
    ├── helpers.py         # Channel check, admin guard, formatters
    └── states.py          # FSM state groups
```

---

## 👑 Admin Commands

| Command | Description |
|---|---|
| `/admin` | Open admin panel |
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/userinfo <user_id>` | View user details + wallet |

---

## 🛒 Admin Panel Features

- **Categories**: Add / Edit / Delete — set name, price, description
- **Coupons**: Paste codes (one per line) per category
- **Stock View**: Live stock count per category
- **Orders**: Filter by pending / approved / rejected
- **Approve Payment**: Delivers coupons + deducts stock automatically
- **Reject Payment**: Notifies user; refunds wallet if paid from wallet
- **Broadcast**: Send message/photo/video to all users
- **Statistics**: Total orders, revenue, breakdown by category
- **Settings**:
  - UPI ID
  - QR Code image
  - Required channel
  - Referral bonus amount

---

## 💰 Wallet System

- Users can top up wallet via UPI
- Admin approves top-up → wallet credited
- Users can pay for purchases directly from wallet (instant, no admin approval needed)
- Wallet balance shown on main menu

---

## 🎁 Referral System

- Each user gets a unique referral code
- Share link: `https://t.me/BOTUSERNAME?start=ref_CODE`
- When a new user joins via the link → referrer gets wallet bonus
- Double-counting prevented (one bonus per referred user)
- Bonus amount configurable from admin panel

---

## 🔄 Self-Healing / Auto-Bug-Fix

The bot has a **supervisor loop** in `main.py`:

- If bot crashes → auto-restarts after a short delay
- Delay increases with each consecutive crash (backoff)
- Admin gets a Telegram notification with the full traceback on every crash
- After 10 consecutive crashes → gives up and exits (Railway will restart the container)
- All errors logged to `bot.log`

---

## 🔐 Security Notes

- Admin commands are protected by `ADMIN_IDS` list
- Users can only see their own orders
- Wallet deduction is atomic (race-condition safe with SQLite WAL mode)
- Coupon delivery is atomic — won't double-deliver on retry

---

## 📝 License

MIT — use freely, no attribution required.
