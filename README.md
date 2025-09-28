# Internship Tracker

If you’re a student trying to juggle classes, clubs, and job apps, this repo is for you. The app scrapes a bunch of company career pages every few minutes, keeps only internship-friendly roles in the United States, and blasts updates straight to a live React dashboard. 

## What you get
- **Real-time feed**: new listings appear in the UI the moment the backend ingests them.
- **Push notifications**: browser tab stays open, toaster pops whenever a fresh role drops.
- **Source coverage**: Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee (the open APIs companies actually expose). Everything is filtered to internships in the U.S. only, so no more “Senior Internal Communications” false positives.
- **Dockerized**: spin up the full stack with a single command during office hours or from your dorm Wi-Fi.

## TL;DR setup
```bash
# Clone repo, then from repo root:
docker-compose up -d --build
```
- Frontend → http://localhost:5173
- Backend API → http://localhost:8000 (REST + `/ws` WebSocket)
- Postgres → localhost:5433 (user `internship_user`, pass `internship_pass`, db `internship_db`)

Everything auto-migrates; the poller kicks off as soon as the backend boots. You’ll see internship cards fill the UI within a minute.

## How the sausage is made
- **Backend**: FastAPI + SQLAlchemy + httpx. Poller runs every ~2–4 minutes (configurable) on each ATS.
- **Database**: PostgreSQL with a unique constraint to stop duplicates when companies “refresh” roles.
- **Frontend**: React (TypeScript) + Vite + Tailwind. Uses a WebSocket hook for live updates and radix toasts so you don’t miss hot drops during lecture.

## Customize the company list
All the knobs live in `docker-compose.yml` under the `backend` service:

| Env Var | What it expects | Where to find the values |
| --- | --- | --- |
| `GREENHOUSE_BOARDS` | comma-separated slugs | `https://boards.greenhouse.io/<slug>` |
| `LEVER_COMPANIES` | company slugs | `https://jobs.lever.co/<slug>` |
| `ASHBY_ORGANIZATIONS` | hosted jobs page names | `https://jobs.ashbyhq.com/<name>` |
| `SMARTRECRUITERS_COMPANIES` | company IDs | `https://careers.smartrecruiters.com/<id>` |
| `RECRUITEE_COMPANIES` | subdomains | `https://<subdomain>.recruitee.com` |

Update the list, redeploy the backend (`docker-compose up -d --force-recreate backend`), and the poller will pick them up.

## Dev mode (for night-owls)
```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload

# Frontend
cd frontend
npm install
npm run dev -- --host
```

Hit http://localhost:5173 and http://localhost:8000 like normal. The frontend points to the local backend out of the box.

## Where the data comes from
The site only touches the public career-site APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee). Big names on Workday/Taleo/etc. don’t expose anonymous JSON feeds, so they’ll only appear if we add a compliant connector. If a company edits a posting, the timestamp will jump—no way around that unless the provider sends historical metadata.

## Quick roadmap ideas
- Slack/Discord bot for “internship just dropped” alerts.
- UI filters by company, role, tech stack.
- CSV/RSS export for the spreadsheet crowd.
- Optional caching or asynchronous workers so 300+ boards don’t hammer your Wi‑Fi.
