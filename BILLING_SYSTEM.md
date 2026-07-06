# VADG Billing, Credits & Admin Dashboard

Credit-based pricing with automatic report-limit enforcement, a purchase flow,
and an admin management dashboard.

## Pricing model

| Tier | Price | Reports | Notes |
|------|-------|---------|-------|
| Free | ₹0 | **1 / day** per registered user | Resets daily. Configurable via `FREE_REPORTS_PER_DAY`. |
| Pay As You Go (`payg`) | ₹29 | 1 credit | For an extra report after the daily free one. |
| Standard Pack (`pack12`) | ₹399 | 15 credits | Featured. |
| Premium Pack (`pack25`) | ₹599 | 25 credits | Best value. |

- **Credits never expire** and stack on top of the daily free report.
- **Admins get unlimited reports.**
- Plans live in the `pricing_plans` collection (seeded on startup) and are fully
  editable from the admin dashboard — the model scales to new tiers with no code
  changes.

## Enforcement

Two independent gates, checked at two different points in the flow:

1. **`POST /symptom`** (start of a NEW diagnosis) — anonymous-only gate. An
   anonymous device (`X-Anon-Id` header) gets **exactly one free diagnosis,
   ever** — not a 24-hour or daily window. `billing.anon_entitlements.has_used_free_report(x_anon_id)`
   is checked here, *before* a session is created, so a second anonymous
   attempt never gets past the patient-details step and the first diagnosis
   is never interrupted mid-flow. Once used, that device must log in for any
   further diagnosis — clearing the browser's local storage (which regenerates
   the anon device id) is the only way to get another anonymous free report.
   Logged-in users (`current_user` present) skip this gate entirely and fall
   through to their per-day free-report allowance below.
2. **`GET /generate_report/{session_id}`** (end of a diagnosis) — the
   credit/report gate for everyone else, via `billing.entitlements.check_and_consume`.
   Consumption order: **free daily → paid credit → 402**. It is **idempotent
   per `session_id`** (keyed by the `report_usage` collection), so re-fetching,
   exporting to PDF, or switching the report language for the same diagnosis
   is never charged twice.

Responses the frontend handles:
- **401** (`code: "login_required"` at `/symptom`, or `code: "anon_free_report_used"`
  at `/generate_report` for an anon session started before this gate order
  existed) → redirect to `/login?next=…`
- **402** (`code: "no_reports_remaining"`) → redirect to `/pricing` / show "Buy Credits"

Entitlement state on each `auth_users` doc: `report_credits` (never expire),
`free_report_date` (`YYYY-MM-DD`, UTC — **resets at UTC midnight, not on a
rolling 24-hour timer**), `free_report_count` (resets to 0 whenever
`free_report_date` != today), `total_reports`, `subscription`.

**Anonymous free-report state** lives in its own `anon_report_usage`
collection (`anon_id`, `used`, `session_id`, `used_at`) — a one-time flag per
device, not tied to any date/time field at all.

## Endpoints

### User — `/api/billing`
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/plans` | Public plan catalogue + free/day + per-report price |
| GET | `/balance` | Signed-in user's entitlement snapshot |
| GET | `/history` | User's payment history |
| POST | `/purchase` | Create an order for a plan (`plan_code`/`plan_id`) |
| POST | `/confirm` | Settle the order → credits granted |

### Admin — `/api/admin/billing` (admin token)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/overview` | KPIs: users, revenue, reports, plans |
| GET | `/users` | Users + balances (search, paginate) |
| GET | `/users/{id}` | One user + their payments |
| PATCH | `/users/{id}/status` | Activate / deactivate |
| PATCH | `/users/{id}/role` | Change role |
| POST | `/users/{id}/credits` | Add/remove credits (`delta`) |
| GET | `/payments` | Payments ledger + revenue |
| GET | `/usage` | Report-usage stats + recent activity |
| GET/POST/PATCH/DELETE | `/plans[/{id}]` | Manage pricing plans |

The permanent admin (`m87.krishna@gmail.com`) cannot be modified.

## Payments

Current mode is **manual/dev**: an order is created then confirmed directly (no
external charge), and every purchase is recorded in the `payments` collection so
revenue and history are auditable. The design is **pluggable** — set
`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` and switch on the marked hooks in
`billing/payments.py` (`_razorpay_create_order` / `_razorpay_verify`) to charge
real payments; callers and the frontend flow don't change.

## Collections & config

- Collections: `pricing_plans`, `payments`, `report_usage`, `anon_report_usage`
  (indexes in `database/connection.py`). `report_usage.session_id` is unique
  (idempotency); `anon_report_usage.anon_id` is unique.
- Env: `FREE_REPORTS_PER_DAY`, `PAY_PER_REPORT_PRICE_INR`, `RAZORPAY_*` — see
  `env.example`.

## Frontend

- `services/billingApi.ts` — user billing calls (shared axios/user token).
- `admin/adminApi.ts` — admin billing/user-management calls (admin session token).
- `pages/Price.tsx` — modern plan comparison, live balance, purchase modal.
- `pages/Profile.tsx` — "Reports & billing" balance card.
- `utils/reportFetch.ts` — auth-attached report fetch + 401/402 gate handling
  (used by `DiagnosisReport`, `DiagnosisReportPreview`, `ReportGenerator`).
- Admin pages: `admin/pages/Users`, `Payments`, `ReportUsage`, `Plans` (routes
  `/admin/users`, `/admin/payments`, `/admin/report-usage`, `/admin/plans`;
  linked in `AdminLayout`).

## Verified (2026-07-06, E2E)

The full flow was driven end-to-end against the real API (not mocked): first
anonymous free report succeeds and is idempotent on re-fetch; a second
anonymous diagnosis attempt is blocked with 401 at `/symptom` itself; a
logged-in user with zero free-reports-today and zero credits gets 402 with a
"Buy Credits" message; granting credits and generating a report deducts
exactly 1 credit and increments `total_reports` by exactly 1; re-fetching the
same report afterward does not charge a second time; a second new session for
the same user correctly draws down a second credit. All checks passed.
