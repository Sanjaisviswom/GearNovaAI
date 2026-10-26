# 🔧 WhatsApp AI Spare Parts Assistant

A production-ready WhatsApp bot that diagnoses machine faults using **Google Gemini AI**, recommends the exact spare parts needed, and sends **YouTube repair tutorial videos** — all within a single WhatsApp conversation.

```
User (WhatsApp)  →  FastAPI Webhook  →  Gemini AI  →  Parts Catalogue (PostgreSQL)
                                                    ↘  YouTube API
                                     ←  WhatsApp Reply (Parts + Videos)
```

---

## ✨ Features

- 🤖 **AI Fault Diagnosis** — Describe a fault in plain language or send a photo
- 📦 **Spare Parts Recommendations** — Enriched with your own parts catalogue
- 🎥 **YouTube Tutorial Videos** — Auto-searched and cached to save quota
- 💬 **Multi-turn Conversations** — Remembers context across messages
- 🖼️ **Image Analysis** — Send a photo of a broken part for instant identification
- ⚠️ **Safety Warnings** — AI flags high-risk situations automatically
- 🗄️ **Full Admin API** — Manage your parts catalogue via REST endpoints
- 📊 **Usage Statistics** — Track users, conversations, and messages

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker Desktop (for PostgreSQL)
- [ngrok](https://ngrok.com) (for WhatsApp webhook testing)
- Meta Developer Account with WhatsApp Cloud API access

### 1. Clone & Setup Environment

```bash
cd "spare parts"
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
copy .env.example .env
```

Edit `.env` and fill in your API keys:

| Variable | Where to get it |
|---|---|
| `WHATSAPP_VERIFY_TOKEN` | Any random string you choose |
| `WHATSAPP_ACCESS_TOKEN` | Meta Developer Console → WhatsApp → API Setup |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta Developer Console → WhatsApp → API Setup |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com) → YouTube Data API v3 |

### 3. Start PostgreSQL with Docker

```bash
docker-compose up -d postgres redis
```

### 4. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Database tables are created automatically on first startup.

### 5. Seed the Parts Catalogue

```bash
python scripts/seed_parts.py
```

This loads 20 sample spare parts (bearings, belts, seals, electrical components).
You can also import your own CSV:

```bash
python scripts/seed_parts.py --csv path/to/your_parts.csv
```

### 6. Expose Webhook with ngrok

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL.

### 7. Configure Meta Webhook

1. Go to [Meta Developer Console](https://developers.facebook.com) → Your App → WhatsApp → Configuration
2. Set **Callback URL** to: `https://xxxx.ngrok-free.app/webhook`
3. Set **Verify Token** to the value of `WHATSAPP_VERIFY_TOKEN` in your `.env`
4. Subscribe to **messages** events
5. Click **Verify and Save**

### 8. Send a WhatsApp Message!

Text your WhatsApp Business number:
> *"My air compressor is making a grinding noise and the pressure drops"*

The bot will respond with a fault analysis, spare parts list, and YouTube videos. 🎉

---

## 📁 Project Structure

```
spare-parts/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Settings (pydantic-settings)
│   ├── database.py              # SQLAlchemy async engine + session
│   ├── models/
│   │   ├── user.py              # WhatsApp user model
│   │   ├── conversation.py      # Conversation + Message models
│   │   └── spare_part.py        # Parts catalogue + YouTube cache
│   ├── routers/
│   │   ├── webhook.py           # WhatsApp webhook (GET verify + POST messages)
│   │   └── admin.py             # Admin REST API
│   ├── services/
│   │   ├── whatsapp.py          # WhatsApp Cloud API client
│   │   ├── ai_engine.py         # Gemini fault analysis engine
│   │   ├── youtube.py           # YouTube search + caching
│   │   └── parts_lookup.py      # DB parts enrichment
│   └── utils/
│       └── message_parser.py    # Webhook payload parser
├── data/
│   └── spare_parts_seed.csv     # Sample parts catalogue
├── migrations/                  # Alembic DB migrations
├── scripts/
│   └── seed_parts.py            # DB seeder script
├── tests/
│   ├── conftest.py              # Pytest fixtures
│   ├── test_webhook.py          # Webhook endpoint tests
│   ├── test_message_parser.py   # Parser unit tests
│   └── test_admin.py            # Admin API tests
├── .env.example                 # Environment variable template
├── docker-compose.yml           # PostgreSQL + Redis
├── requirements.txt
├── pytest.ini
└── alembic.ini
```

---

## 🔌 API Endpoints

### Webhook
| Method | Path | Description |
|---|---|---|
| GET | `/webhook` | Meta verification handshake |
| POST | `/webhook` | Receive WhatsApp messages |

### Admin
| Method | Path | Description |
|---|---|---|
| GET | `/admin/parts` | List parts (paginated) |
| POST | `/admin/parts` | Create a part |
| GET | `/admin/parts/search?q=bearing` | Keyword search |
| GET | `/admin/parts/{id}` | Get single part |
| PUT | `/admin/parts/{id}` | Update part |
| DELETE | `/admin/parts/{id}` | Delete part |
| POST | `/admin/parts/bulk-import` | Import CSV |
| GET | `/admin/conversations` | List conversations |
| GET | `/admin/conversations/{id}` | Conversation detail |
| GET | `/admin/stats` | Usage statistics |

### Monitoring
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe |
| GET | `/docs` | Swagger UI (dev only) |

---

## 🧪 Running Tests

```bash
pip install aiosqlite  # Needed for in-memory SQLite tests
pytest tests/ -v --cov=app
```

---

## 📦 Parts Catalogue CSV Format

The CSV importer accepts these columns (only `name` is required):

```csv
part_number,name,description,category,brand,compatible_with,fault_keywords,price_min,price_max,currency,in_stock,stock_qty
SKF-6205,Ball Bearing SKF 6205,Deep groove ball bearing,Bearings,SKF,"compressor,motor","grinding noise,vibration",350,650,INR,true,50
```

---

## 🗺️ Conversation Flow

```
1. User sends message → Webhook receives it
2. Mark as read (blue ticks)
3. New user? → Send welcome message
4. AI analyses fault (text or image)
5. AI needs clarification? → Ask follow-up question
6. Safety warning present? → Send warning first
7. Enrich AI parts with DB catalogue (prices, stock status)
8. Search YouTube for repair tutorials (cached for 7 days)
9. Send interactive parts list + video links to user
10. Save full conversation to PostgreSQL
```

---

## 🔑 Getting Your API Keys

### WhatsApp Cloud API
1. Create a Meta Developer account at [developers.facebook.com](https://developers.facebook.com)
2. Create a new app → Select **Business** type
3. Add **WhatsApp** product
4. Under **API Setup**, note your **Phone Number ID** and **Access Token**

### Google Gemini API
1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click **Create API Key**
3. Free tier: 15 requests/minute, 1M tokens/day

### YouTube Data API v3
1. Visit [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. Create **API Key** credentials
4. Free quota: 10,000 units/day (~100 searches)

---

## 📄 License

MIT License — feel free to use, modify, and distribute.
