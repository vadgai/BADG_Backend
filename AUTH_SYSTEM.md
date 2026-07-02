# VADG Authentication & User Management

Complete, production-oriented auth system: registration, email verification,
login/logout, password reset, profile management, JWT sessions with refresh
rotation, and role-based access control (RBAC).

Backend: FastAPI + MongoDB (`auth_users` collection, with in-memory fallback).
Frontend: React + `AuthContext` + axios interceptors.

## Permanent admin

`m87.krishna@gmail.com` is seeded on startup as a verified `admin` with
`is_permanent_admin=true`. It **cannot be demoted or deactivated** via the API.
It can sign in through the normal user login *and* the admin dashboard login.

Set its initial password with `PERMANENT_ADMIN_PASSWORD` (or `ADMIN_PASSWORD`).
If neither is set, a random password is generated and logged as a warning — use
the "forgot password" flow to set one.

## Endpoints (`/api/auth`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/register` | – | Create account, send verification email |
| POST | `/verify-email` | – | Confirm email with token |
| POST | `/resend-verification` | – | Resend verification email (generic response) |
| POST | `/login` | – | Authenticate → access + refresh tokens |
| POST | `/refresh` | refresh token + (expired) access header | Rotate tokens |
| POST | `/logout` | access | Revoke current session (or all devices) |
| GET | `/me` | access | Current user profile |
| PATCH | `/profile` | access | Update name/phone/avatar |
| POST | `/change-password` | access | Change password (revokes all sessions) |
| POST | `/forgot-password` | – | Send reset link (generic response) |
| POST | `/reset-password` | – | Reset password with single-use token |
| GET | `/users` | **admin** | List/search users (paginated) |
| PATCH | `/users/{id}/role` | **admin** | Change a user's role |
| PATCH | `/users/{id}/status` | **admin** | Activate/deactivate a user |

The admin dashboard login (`POST /api/admin/login`) accepts either the legacy
env admin **or** any `admin`-role user in `auth_users`.

## Security properties

- **Passwords**: bcrypt (passlib). Policy: ≥8 chars, upper + lower + digit.
- **Access tokens**: short-lived JWT (default 60 min), signed with `JWT_SECRET_KEY`
  / `ADMIN_JWT_SECRET`. Carry `sub`, `email`, `role`, `type=access`.
- **Refresh tokens**: opaque, high-entropy; only a SHA-256 hash is stored. Rotated
  on every refresh; capped at 10 concurrent sessions; revoked on password change
  and on account deactivation.
- **RBAC**: `require_role(...)` / `require_admin`. `get_current_admin` now enforces
  `role == "admin"` (previously any valid token passed — hardened).
- **Enumeration resistance**: forgot-password and resend-verification always return
  a generic message.
- **Rate limiting**: per-IP, per-action, in-process (login 10/5min, register/forgot/
  resend 5/hour). Move to Redis for multi-instance deployments.
- **Single-use reset**: a `jti` stored on the user is consumed on reset.
- **Email verification** required to log in when `REQUIRE_EMAIL_VERIFICATION=true`.

## Email (SMTP)

Transactional email is sent from `vadg.office@gmail.com` via Gmail SMTP.
Configure `SMTP_PASSWORD` with a Gmail **App Password**
(https://myaccount.google.com/apppasswords). If unset, email bodies are logged
instead of sent (dev-friendly). Links are built from `FRONTEND_URL`.

## Required environment variables

See `env.example`. Minimum for production:

```
JWT_SECRET_KEY / ADMIN_JWT_SECRET   # long random string (shared signing secret)
MONGO_URI                           # MongoDB connection
SMTP_USER=vadg.office@gmail.com
SMTP_PASSWORD=<gmail app password>
FRONTEND_URL=https://<your-frontend>
PERMANENT_ADMIN_PASSWORD=<strong password>   # first-run seed
```

## Frontend

- `context/AuthContext.tsx` — `useAuth()` exposes `user`, `isAuthenticated`,
  `isAdmin`, `login`, `register`, `logout`, `refreshUser`.
- `services/authApi.ts` — typed API client.
- `utils/axiosConfig.ts` — auto-attaches the access token and transparently
  refreshes on 401 (rotates the refresh token, retries the request).
- `components/RoleProtectedRoute.tsx` — guards routes by auth + role + verified.
- Pages: `auth/login`, `auth/registration`, `auth/ForgotPassword`,
  `auth/ResetPassword`, `auth/VerifyEmail`, `pages/Profile`.
- Routes: `/login`, `/register`, `/forgot-password`, `/reset-password`,
  `/verify-email`, `/profile` (protected), `/dashboard` (protected).
