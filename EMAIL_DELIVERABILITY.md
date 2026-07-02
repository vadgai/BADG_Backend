# Fixing "emails go to spam"

## Why it happens (root cause)

VADG currently sends from **`vadg.office@gmail.com`** (a free Gmail account) with
**"VADG" branding and links to `vadg.in`**. Gmail treats "generic gmail sender +
different brand/link domain" as a phishing signal, and a personal Gmail account
has no transactional sending reputation. **No code or message-content change can
overcome this** — the fix is to send from your own authenticated domain.

The application code is already ready for this: it reads standard SMTP env vars,
so switching providers is only a matter of setting environment variables +
adding DNS records. No code changes needed.

---

## The fix: send from `no-reply@vadg.in` via an email provider (ESP)

Pick one provider (all have free tiers big enough for VADG):

| Provider | Free tier | Setup effort |
|----------|-----------|--------------|
| **Resend** (recommended for devs) | 3,000/mo | Lowest |
| **Brevo** (formerly Sendinblue) | 300/day | Low |
| **Amazon SES** | 3,000/mo (in free tier) | Medium |

### Step 1 — Create the account and add your domain
Sign up, choose "Add domain", enter **`vadg.in`**. The provider shows you a set
of DNS records to add.

### Step 2 — Add the DNS records at your domain registrar
You will add three kinds of records (the provider gives exact values):

- **SPF** (TXT on `vadg.in`), e.g. `v=spf1 include:<provider-spf> ~all`
- **DKIM** (TXT/CNAME the provider gives, e.g. `resend._domainkey`)
- **DMARC** (TXT on `_dmarc.vadg.in`), start with:
  `v=DMARC1; p=none; rua=mailto:dmarc@vadg.in`

Wait for the provider dashboard to show the domain as **Verified** (minutes to a
few hours for DNS propagation).

### Step 3 — Set these environment variables on the backend (Cloud Run)
Once the domain is verified, the provider gives you an SMTP host / username /
password (or API key used as the SMTP password). Set:

```
SMTP_HOST=<provider smtp host>          # e.g. smtp.resend.com
SMTP_PORT=587
SMTP_USER=<provider smtp username>      # e.g. "resend"
SMTP_PASSWORD=<provider smtp password/api key>
MAIL_FROM=no-reply@vadg.in
MAIL_FROM_NAME=VADG
SUPPORT_EMAIL=support@vadg.in           # or keep vadg.office@gmail.com
FRONTEND_URL=https://www.vadg.in
ENVIRONMENT=production
```

That's it. The code already reads these; `SMTP_PASSWORD` takes priority over the
legacy `SENDER_PASSWORD`, so the ESP takes over automatically. On startup the
service logs `Email service ready (...)` confirming the config.

---

## Why this works
Sending from `no-reply@vadg.in` means the sender domain, the brand, and the
links all match `vadg.in`, and SPF/DKIM/DMARC prove you own it. That is exactly
the alignment Gmail looks for, and it moves mail from Spam to Inbox.

## Interim mitigations (do NOT rely on these long-term)
- In Gmail, open the message → "Report not spam", and add the sender to Contacts.
  This trains the filter per-recipient but does not scale to new users.
- Keep sending volume low and steady while reputation builds.

## Already done in code
- Proper transactional headers (Date, Message-ID, Reply-To, List-Unsubscribe,
  Auto-Submitted).
- Removed emojis from subjects/bodies.
- Production-safe `FRONTEND_URL` and startup config validation.
These help but are secondary to domain authentication above.
