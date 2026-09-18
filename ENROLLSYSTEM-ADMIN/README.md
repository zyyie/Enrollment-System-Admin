# EMS — Admin Portal

Standalone **Admin / Faculty** application. No student pages or routes.

## Run

```bash
cd ENROLLSYSTEM-ADMIN
python main.py
```

Open: **http://localhost:8001/login.html**

Default admin ( **`admins`** table): `FAC-2026-0001` / `admin123` 
Run `supabase/admin-table.sql` once on existing Supabase projects.

## Setup

1. Copy `.env.example` → `.env`
2. Add Supabase **Secret Key** (required for admission review + scheduling apply)
3. Add Gmail App Password (approval emails)
4. Add Groq API key for AI Auto-Schedule (free at console.groq.com/keys)
5. Run SQL migrations in `supabase/` (especially `fix-approve-review.sql`, `apply-auto-schedule.sql`)

## Directory Tree

```
ENROLLSYSTEM-ADMIN/
├── main.py # Entry point (port 8001)
├── server.py # Admin API only
├── login.html # Faculty login
├── index.html # Redirect → login
├── admin/ # Dashboard, review, auto-schedule pages
├── scheduling/ # AI + conflict-free scheduler
├── enrollment_curriculum.py (SHS curriculum — same file as project root after sync)
├── supabase/ # SQL migrations
├── js/ # Supabase client, icons
├── assets/
├── uploads/admissions/
└── data/
```

## API Routes (Admin only)

| Method | Path |
|--------|------|
| POST | `/api/auth/admin` |
| GET | `/api/admission/pending`, `/history`, `/detail` |
| POST | `/api/admission/review` |
| GET | `/api/faculty/dashboard` |
| GET/POST | `/api/scheduling/*` |
| GET | `/api/health` |

## Packages

**Python 3.10+** — no pip packages required (stdlib only).

Optional: none.

## Standalone

This folder runs alone: `python server.py` → port **8001**. Student portal is a separate folder (`ENROLLSYSTEM`, port **8000**); only Supabase config is shared via `.env`.
