# STR Booking Source Analytics & CRM — PRD

## Original problem statement (verbatim)
Build a booking-source analytics and CRM tool for a short-term rental (STR)
accommodation business managing ~15 properties across multiple complexes,
receiving bookings from direct channels and OTAs (Airbnb, Booking.com, Stayz,
VRBO, Expedia). Final deployment target: Supabase (DB) + Vercel (frontend).
Multi-stage build: Stage 1 = booking source classification, Stage 2 = guest
segmentation + cancellation system, Stages 3-7 = scoring, campaigns,
analytics, tasks, calendar.

## Tech stack (locked at kickoff)
FastAPI (Python) + MongoDB + React. Original spec asked for Node + Postgres +
Supabase; user agreed to use the Emergent default stack with an explicit
porting plan documented at handoff.

## User personas
- **STR operations manager** — uploads OTA/PMS exports, reviews booking-source
  mix, manages cancellation recoveries.
- **Marketing / growth analyst** — segments guests, exports remarketing
  audiences, tracks Direct-vs-OTA revenue attribution.

## Stages shipped
| Stage | Status | Scope |
|---|---|---|
| 1 | ✅ 2026-02 | CSV import, source classification, dashboard, reservations, properties, history |
| 2 | ✅ 2026-02 | Guest profile consolidation, 12 segments, remarketing priority score, cancellation analytics, audience CSV export |
| 3 | ✅ 2026-02 | 4-score engine (direct conversion, LTV, rebooking, revenue opportunity), OTA commission tracking, configurable commission rates |
| 4 | ✅ 2026-02 | Full analytics dashboard (5 sections), 7 exportable reports, date+property filters |
| 4.5 | ✅ 2026-02 | Weekly digest via Resend — webhook-triggered, configurable recipients/schedule, trend notes, click-through links, "no new data" skip |
| 5 | Backlog | Campaign tools (segment → email/SMS export, suppression lists, audience builder) |
| 6 | Backlog | Tasks system (cancellation recovery workflows) |
| 7 | Backlog | Staff calendar |
| ∞ | Backlog | Auth + multi-user, PMS sync (Guesty/Hospitable/Hostaway), Postgres/Vercel port |

## Architecture
### Backend (`/app/backend/`)
- `server.py` — FastAPI app, `/api` prefix, MongoDB via Motor.
- `segmentation_service.py` — pure functions for profile build, segment rules
  (`SEGMENT_RULES` list = single source of truth), priority score,
  `recompute_all_guests(db)`.
- `cancellation_service.py` — read-only analytics + audience CSV export.

#### Endpoints
**Stage 1**: `GET /api/`, `GET /api/sources`, `POST /api/import/preview`,
`POST /api/import/confirm`, `GET /api/reservations`,
`PATCH /api/reservations/{id}/source`, `GET /api/imports`,
`GET /api/analytics/summary`, `GET|POST|DELETE /api/properties`.

**Stage 2**: `POST /api/guests/recompute`, `GET /api/guests`,
`GET /api/guests/{email}`, `GET /api/segments`,
`GET /api/cancellations/summary`, `GET /api/cancellations`,
`GET /api/cancellations/export.csv`.

**Stage 3**: `POST /api/scores/recalculate`, `GET /api/scores/summary`,
`GET /api/scores/guests`, `GET /api/scores/guests/export.csv`,
`GET /api/commissions/summary`, `GET|PUT /api/settings/commissions`.

**Stage 4**: `GET /api/analytics/{revenue|bookings|guests|conversion|clv}`
(supports `?preset`, `?start_date`, `?end_date`, `?property_name`),
`GET /api/reports` (list), `GET /api/reports/{key}/count`,
`GET /api/reports/{key}.csv`. Reports include: full guest database, OTA
commission period, cancellation period, revenue by source period, top
conversion opportunities, guests at risk of churning, high-intent
cancellations.

Auto-recompute hooks fire after every `/api/import/confirm` and every
`PATCH /api/reservations/{id}/source` → both `recompute_all_guests` AND
`recalculate_all_scores` chained.

### Frontend (`/app/frontend/src/`)
React 19 + react-router 7 + shadcn/ui + recharts + sonner + tailwind.
Dark luxury analytics theme. Pages: `/` Analytics Dashboard (5 tabs:
Revenue, Bookings, Guests, Conversion, Lifetime value) · `/reservations` ·
`/segments` · `/scores` · `/cancellations` · `/reports` · `/import` ·
`/properties` · `/history` · `/guests/:id` · `/settings/commissions`.

## Database collections (MongoDB)
- **reservations** — id, reservation_id (unique upsert key), guest_*,
  property_name, dates, nights, guest_count, booking_value,
  raw_booking_source, classified_source, booking_date, is_cancelled,
  imported_at, manually_overridden.
- **import_logs** — id, filename, imported_at, total_rows, successful_rows,
  failed_rows, status.
- **properties** — id, name (unique), notes, created_at.
- **guests** *(Stage 2)* — id (= lowercase email), email, first_name,
  last_name, initials, total_stays, lifetime_spend, first_stay_date,
  last_stay_date, most_used_source, primary_channel (Direct|OTA|Unknown),
  properties[], cancellation_count, cancellation_rate, avg_booking_value,
  avg_length_of_stay, recovered, remarketing_priority_score (0-100),
  segments[], updated_at.

## Segment rules (Stage 2 — `segmentation_service.SEGMENT_RULES`)
**Standard (8)**: Direct Loyal Guest · OTA Loyal Guest · OTA First-Time Guest
· OTA Repeat Guest · High Value Direct Guest · High Value OTA Guest · OTA
Guest Most Likely to Convert · Direct Guest at Risk of Churning.
**Cancellation (4)**: Cancelled — High Intent · Cancelled — Repeat Canceller
· Cancelled — Recovered Guest · Cancelled — OTA Winback Target.

A guest can hold zero-to-many segments. All rules use cross-cohort context
(lifetime spend p75, avg booking value median, cancelled value median).
Edit a predicate in `SEGMENT_RULES` to retune without touching engine code.

## Remarketing priority score (Stage 2)
Integer 0-100. Zero if no cancellations. Otherwise:
- Cancelled value vs median: up to 30 pts (linear: 0 → 2× median → 30 pts).
- Recency of last cancellation: up to 25 pts (≤90d full, sliding to 0 at
  24mo+).
- Recovery bonus: +20 if cancelled then later completed.
- OTA cancellation bonus: +15.
- Repeat-canceller penalty: −20 if 2+ cancels & zero completed.

## Verified (testing agent)
- Iteration 1 (Stage 1): 10/10 tests pass.
- Iteration 2 (Stage 2): 22/22 tests pass + Stage 1 regression. Frontend
  /segments, /guests/:email, /cancellations all render and function
  correctly. Auto-recompute triggers on import & override verified.

## Handoff notes (Vercel + Supabase port)
- Endpoints map 1:1 to Postgres tables. The `guests` table becomes a
  materialised view (or scheduled recompute job) since it's derived state.
- Classification + segmentation are pure Python — easy to port to a
  Postgres function, Node service, or Supabase Edge Function.
- Frontend uses `process.env.REACT_APP_BACKEND_URL`; set for the deployed
  API origin on Vercel.

## Known by-design behaviour
- A guest whose sole cancellation value equals the cancelled-value median
  exactly is not assigned `Cancelled — High Intent` (spec says "above
  overall median"; strict `>`). Once two or more cancellers exist this
  resolves naturally.
