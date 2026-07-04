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

`GET /generate_report/{session_id}` now requires authentication and calls
`billing.entitlements.check_and_consume`. Consumption order: **free daily →
paid credit → 402**. It is **idempotent per `session_id`** (keyed by the
`report_usage` collection), so re-fetching, exporting to PDF, or switching the
report language for the same diagnosis is never charged twice.

Responses the frontend handles:
- **401** → user not signed in → redirect to `/login?next=…`
- **402** → out of reports → redirect to `/pricing`

Entitlement state on each `auth_users` doc: `report_credits`,
`free_report_date`, `free_report_count`, `total_reports`, `subscription`.

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

- Collections: `pricing_plans`, `payments`, `report_usage` (indexes in
  `database/connection.py`). `report_usage.session_id` is unique (idempotency).
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

## Follow-up note

Report generation is gated at report time (not at diagnosis start), so an
anonymous user completing a diagnosis is redirected to login when they request
the report. If you prefer a login wall before starting a diagnosis, guard the
diagnosis entry route with `RoleProtectedRoute`.
