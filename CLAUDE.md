# Campus Lost & Found — Project Context for Claude

## What This Project Is
A web app for students to post lost and found items with photos. Key features:
- No forced login — anyone can browse, post, and message without an account
- Every item has a public message thread (like a comment section) for open communication
- Found items show a **drop-off location** field so people can go collect without messaging
- AI image matching (CLIP) auto-suggests when a lost item photo matches a found item photo
- Registered accounts are optional — they unlock a personal dashboard and AI match alerts

## Tech Stack
- **Frontend:** HTML5 + CSS3 + Bootstrap 5 (CDN) + Vanilla JS
- **Backend:** Python 3.11 + FastAPI
- **Database:** SQLite via SQLAlchemy
- **Auth:** JWT (python-jose + passlib/bcrypt) — optional, only needed for dashboard
- **AI Matching:** CLIP ViT-B/32 via `transformers` + `torch`
- **Image Storage:** Local filesystem at `backend/uploads/`

## Project Structure
```
campus-lost-found/
├── backend/
│   ├── main.py                  # FastAPI app entry point, CORS, startup
│   ├── config.py                # Settings: DB URL, secret key, upload path, CLIP threshold
│   ├── database.py              # SQLAlchemy engine + SessionLocal + Base
│   ├── models.py                # ORM models: User, Item, Message, Match
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── dependencies.py          # get_db(), get_current_user(), get_optional_user()
│   ├── routers/
│   │   ├── auth.py              # POST /auth/register, POST /auth/login
│   │   ├── items.py             # POST/GET/DELETE items (guest + registered)
│   │   ├── messages.py          # GET/POST message threads on items
│   │   ├── matches.py           # GET AI match suggestions for an item
│   │   └── admin.py             # Admin-only routes
│   ├── services/
│   │   ├── auth_service.py      # Password hashing, JWT create/decode
│   │   └── matching_service.py  # CLIP model, get_embedding(), find_matches()
│   └── uploads/                 # Saved item photos (gitignored)
├── frontend/
│   ├── index.html               # Landing page — no login wall
│   ├── browse.html              # Browse all items + search + filters
│   ├── item-detail.html         # Item info + drop-off location + message thread + AI matches
│   ├── post-item.html           # Post form (works for guest and logged-in)
│   ├── login.html               # Login page
│   ├── register.html            # Register page
│   ├── dashboard.html           # Registered user dashboard
│   ├── admin.html               # Admin panel
│   ├── css/style.css            # All custom styles
│   └── js/
│       ├── api.js               # Fetch wrapper — sends token only if present
│       ├── auth.js              # login(), register(), logout()
│       ├── items.js             # postItem(), getItems(), getItem()
│       ├── messages.js          # getMessages(), postMessage()
│       ├── matches.js           # getMatches(), render match cards
│       └── dashboard.js         # Dashboard page logic
├── requirements.txt
├── .env                         # Secret values — NOT committed
└── CLAUDE.md                    # This file
```

## Database Models
```
User     id, name, email, student_id, password_hash, is_admin, created_at

Item     id, user_id(nullable), poster_name, poster_contact,
         type(lost|found), title, description, category,
         location, date_occurred, drop_off_location(nullable),
         image_path, embedding(JSON), status(open|resolved), created_at

Message  id, item_id(FK), user_id(nullable), sender_name, body, created_at

Match    id, lost_item_id(FK), found_item_id(FK), similarity_score, created_at
```

## Guest vs Registered Access
| Action | Guest | Registered |
|---|---|---|
| Browse + search items | Yes | Yes |
| Post lost/found item | Yes (name + contact required) | Yes |
| Message on any post | Yes (name required) | Yes (name pre-filled) |
| Personal dashboard | No | Yes |
| AI match notifications | No (sees on item page) | Yes (in dashboard) |
| Edit/delete own posts | No | Yes |

## Build Phases & Status
| Phase | Description | Status |
|---|---|---|
| 1 | Project skeleton: folder structure, DB models, server health check | ✅ Done |
| 2 | Authentication: register, login, JWT (optional for users) | ⬜ Not started |
| 3 | Item posting: form with photo upload, guest + registered | ⬜ Not started |
| 4 | Browse & search: item cards, filters, item detail page | ⬜ Not started |
| 5 | Message threads: public comment section on every item | ⬜ Not started |
| 6 | AI image matching: CLIP embeddings, auto-match suggestions | ⬜ Not started |
| 7 | User dashboard: my posts, match alerts | ⬜ Not started |
| 8 | Polish & admin panel | ⬜ Not started |

## Key Decisions
- Communication is public (message threads on item pages) — no private inbox needed
- No login required to post or message — lowers barrier for casual users
- Drop-off location on found items lets people collect without any interaction
- CLIP embeddings stored in DB so AI never re-processes old photos
- `get_optional_user()` used on all public routes so they work with or without a token

## How to Run
```bash
# Install dependencies
pip install -r requirements.txt

# Start backend (from project root)
uvicorn backend.main:app --reload

# Frontend: open frontend/index.html directly in browser
# or use a simple static server
```

## Environment Variables (.env)
```
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///./campus_lostfound.db
UPLOAD_DIR=backend/uploads
CLIP_THRESHOLD=0.70
```
