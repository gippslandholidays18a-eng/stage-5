# STR Booking Source Analytics & CRM — PRD

## Original problem statement (verbatim)
Build a booking-source analytics and CRM tool for a short-term rental (STR)
accommodation business managing ~15 properties across multiple complexes,
receiving bookings from direct channels and OTAs (Airbnb, Booking.com, Stayz,
VRBO, Expedia). Final deployment target: Supabase (DB) + Vercel (frontend).
This codebase is Stage 1; further stages add segmentation, scoring, campaigns,
reporting.

## Stage 1 goal
Clean booking data import, accurate source classification, solid database
foundation, and a summary dashboard.

## User decisions (gathered at kickoff)
- **Stack**: FastAPI (Python) + MongoDB + React. Original spec asked for
  Node.js + PostgreSQL + Supabase — user agreed to use the Emergent default
  stack; an external developer can later port to Supabase/Postgres at handoff.
- **Auth**: None for Stage 1 (open admin access).
- **Sample data**: User will upload their own CSVs.
- **Properties**: User-managed list (UI module included), plus property names
  are also auto-captured from CSV imports.
- **GitHub**: User pushes via Emergent's "Save to GitHub" UI.

## User personas
- **STR operations manager** — uploads OTA/PMS exports, reviews booking-source
  mix, corrects misclassifications, exports reports.
- **Marketing / growth analyst** — tracks Direct vs OTA share and revenue
  attribution to inform channel investment.

## Architecture (Stage 1)
- **Backend** (`/app/backend/server.py`)
  - FastAPI app with `/api` prefix, MongoDB via Motor.
  - Endpoints:
    - `GET /api/` — health
    - `GET /api/sources` — list of 11 standard source categories
    - `POST /api/import/preview` — multipart CSV → parsed/normalised rows,
      column mapping, validation
    - `POST /api/import/confirm` — JSON `{filename, rows[]}` → upsert by
      `reservation_id`, write `import_log`
    - `GET /api/reservations` — filter by `source`, `property_name`
    - `PATCH /api/reservations/{id}/source` — manual classification override
    - `GET /api/imports` — import history log
    - `GET /api/analytics/summary` — KPIs + by_source + OTA/Direct split
    - `GET|POST|DELETE /api/properties` — manage property list
  - Classification engine: case-insensitive substring matching with priority
    order (named OTAs → phone → email → repeat → direct → other-OTA fallback
    → Unknown). Column header alias detection for ~13 canonical fields.
- **Frontend** (`/app/frontend/src/`)
  - React 19 + react-router 7 + shadcn/ui + recharts + sonner + tailwind.
  - Routes: `/` (Dashboard), `/reservations`, `/import`, `/properties`,
    `/history`.
  - Dark luxury analytics aesthetic (Aman × Bloomberg). No purple gradients;
    obsidian background, brand-accent gold (#D9A05B), Satoshi/Manrope fonts.

## Database collections (MongoDB)
- `reservations` — id, reservation_id (unique upsert key), guest_*,
  property_name, dates, nights, guest_count, booking_value,
  raw_booking_source, classified_source, booking_date, is_cancelled,
  imported_at, manually_overridden.
- `import_logs` — id, filename, imported_at, total_rows, successful_rows,
  failed_rows, status (completed | partial | failed).
- `properties` — id, name (unique), notes, created_at.

## What's implemented (2026-02 — Stage 1 complete)
- CSV upload UI with drag-and-drop, preview of first 10 rows, validation
  panel, confirm/cancel.
- Automatic header-alias detection (e.g. `guests` → `guest_count`,
  `booking_source` → `raw_booking_source`).
- Source classification engine with all 11 categories + manual override.
- Dashboard with 4 KPI cards (Total reservations, Total revenue, Direct
  share %, OTA share %), bookings-by-source bar chart, OTA-vs-Direct donut,
  revenue-by-source bar chart, source-performance breakdown table.
- Reservations table with source filter, free-text search, sortable columns,
  inline classification override (pencil → Select dropdown).
- Properties management (add / list / delete with placeholder images).
- Import history log with status badges (Completed / Partial / Failed).
- Append-safe imports (upsert by reservation_id — no duplicates on re-upload).

## Verified by testing agent (iteration_1)
- Backend: 10/10 pytest tests pass — classification matrix, preview, confirm,
  filter, override, append safety, analytics summary, properties CRUD.
- Frontend: dashboard renders KPIs/charts after import, /import flow works
  end-to-end and redirects to /reservations, override persists with checkmark
  indicator, history shows correct status.

## Stage 2+ backlog (priority order)
- **P0** Guest segmentation engine (new vs repeat, OTA-acquired vs Direct,
  high-value, by-property cohorts).
- **P0** Guest scoring algorithm (LTV proxy, repeat-likelihood, channel
  switch propensity).
- **P1** Campaign tools (segment → email/SMS export, suppression lists).
- **P1** Advanced reporting (period-over-period, channel ROI, commission
  estimation).
- **P1** PMS integrations (direct sync — Guesty, Hospitable, Hostaway).
- **P2** Authentication & multi-user roles.
- **P2** Property complex grouping, property photos upload, occupancy view.
- **P2** Port to Supabase/Postgres + Vercel for external developer handoff
  (write SQL schema mirroring current MongoDB collections; the FastAPI
  layer can be re-implemented in Node.js with the same endpoint surface).

## Handoff notes (Vercel + Supabase port)
- All endpoints prefixed `/api`. Schema in this PRD maps 1:1 to Postgres
  tables (`reservations`, `import_logs`, `properties`). Use Supabase Row
  Level Security off for Stage 1 (no auth), enable in Stage 2 with admin
  role check.
- Classification logic is pure Python in
  `backend/server.py::classify_source` — easy to port to a Postgres
  function or a Node service.
- Frontend uses `process.env.REACT_APP_BACKEND_URL`; for Vercel, set this
  env var to the deployed API origin (could be a Vercel serverless route or
  separate Supabase Edge Function).
