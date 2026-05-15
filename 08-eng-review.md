# 08 — Engineering Review
**BrandPulse: Data Flow, State Machines, Error Paths, Test Matrix, Failure Modes, Security**

*Against design doc v1 — May 2026*

---

## 1. Current Architecture (As-Is)

Before diagramming the target, this is the actual runtime topology:

```
                          ┌─────────────────────────────────────┐
                          │  Single Heroku/Railway Dyno         │
                          │                                     │
 Browser ──GET /──────────►  Flask (app.py)                    │
                          │    │                                │
                          │    ├── GET /api/data                │
                          │    │     └── data_fetcher.get_data()│
                          │    │           ├── STATIC_DATA (dict)│
                          │    │           ├── cache/data.json  │
                          │    │           ├── Instagram API ◄──┼── meta servers
                          │    │           ├── Facebook API  ◄──┼── meta servers
                          │    │           └── Google RSS    ◄──┼── news.google.com
                          │    │                                │
                          │    ├── POST /api/competitors/social │
                          │    │     └── cache/competitor_social.json
                          │    │                                │
                          │    └── APScheduler (background)     │
                          │          ├── 03:00 daily_refresh    │
                          │          └── 03:30/09:00/15:00/21:00│
                          │              social_refresh         │
                          │                                     │
                          │  Filesystem (no DB)                 │
                          │    cache/data.json       (24h TTL)  │
                          │    cache/social_live.json (6h TTL)  │
                          │    cache/competitor_social.json     │
                          └─────────────────────────────────────┘

Authentication: NONE (all routes public except /api/competitors/social)
Multi-tenancy:  NONE (hardcoded to Hakshan)
Billing:        NONE
Report delivery: NONE
```

---

## 2. Target Architecture (To-Build)

```
                   ┌──────────────────────────────────────────────────────────┐
                   │                    Supabase                              │
                   │  tenants  tenant_users  tenant_config  billplz_bills     │
                   │  review_snapshots  [Auth + Row-Level Security]           │
                   └────────────────────┬─────────────────────────────────────┘
                                        │ postgres
               ┌────────────────────────┼────────────────────────┐
               │                        │                        │
     ┌─────────▼──────────┐   ┌────────▼───────────┐   ┌───────▼──────────┐
     │  Flask Web App     │   │  Scheduler Worker  │   │  Webhook Handler │
     │  (multi-tenant)    │   │  (APScheduler)     │   │  (Flask routes)  │
     │                    │   │                    │   │                  │
     │  /t/<slug>/        │   │  Sun 03:00 snap    │   │  /webhooks/billplz
     │  session auth      │   │  Mon 08:00 report  │   │  (Stripe deferred│
     │  tier-gated views  │   │  6h social sync    │   │   to Month 2-3)  │
     └─────────┬──────────┘   └────────┬───────────┘   └───────┬──────────┘
               │                       │                        │
       ┌───────┼───────────────────────┼───────┐               │
       │       │        External APIs  │       │               │
       ▼       ▼                       ▼       ▼               ▼
    Meta    Serpapi             Meta       Twilio/         Billplz
    Graph   (review            Graph      WhatsApp        IPN
    API     snapshots)         API        Business
```

---

## 3. Data Flow: Weekly Report Pipeline

```
  Monday 08:00 MYT
        │
        ▼
  ┌─────────────────────────────────────────────────┐
  │  for each tenant in supabase.tenants            │
  └─────────────────────────────────────────────────┘
        │
        ▼
  tenant_is_active(tenant_id)?
        │
   No ──┴── Yes
   │         │
  SKIP       ▼
        ┌────────────────────────────────────────────┐
        │  PHASE A: Snapshot Fetch (already done     │
        │  at 03:00 by snapshot cron)                │
        │                                            │
        │  this_week = snapshots.latest(tenant_id)   │
        │  last_week = snapshots.one_week_ago(...)   │
        │                                            │
        │  delta_reviews[branch] =                  │
        │    this_week.count - last_week.count       │
        └───────────────────┬────────────────────────┘
                            │
                            ▼
        ┌────────────────────────────────────────────┐
        │  PHASE B: Social Fetch (from 6h cache)     │
        │                                            │
        │  ig_now      = social_live.instagram       │
        │  ig_last_wk  = snapshots.ig_one_week_ago() │
        │  delta_ig    = ig_now - ig_last_wk         │
        └───────────────────┬────────────────────────┘
                            │
                            ▼
        ┌────────────────────────────────────────────┐
        │  PHASE C: Alert Generation                 │
        │                                            │
        │  unanswered_1star = reviews with           │
        │    rating == 1 AND reply == null           │
        │    AND date > 7 days ago                   │
        │                                            │
        │  dropped_branches = branches where         │
        │    this_week.rating < last_week.rating     │
        │    - 0.1                                   │
        └───────────────────┬────────────────────────┘
                            │
                            ▼
        ┌────────────────────────────────────────────┐
        │  PHASE D: Report Render                    │
        │                                            │
        │  template.render(                          │
        │    brand=tenant.name,                      │
        │    week_range="12–18 May 2026",            │
        │    branches=delta_reviews,                 │
        │    social=delta_ig,                        │
        │    alerts=unanswered_1star,                │
        │    dashboard_url=utm_link(tenant)          │
        │  )                                         │
        └───────────────────┬────────────────────────┘
                            │
                            ▼
        ┌────────────────────────────────────────────┐
        │  PHASE E: Delivery                         │
        │                                            │
        │  Primary:   Twilio → tenant.phone          │
        │  Fallback:  Sendgrid → tenant.email        │
        │  Log:       payment_events row (delivered) │
        └────────────────────────────────────────────┘
```

---

## 4. Data Flow: Review Snapshot Service (Critical Missing Piece)

This pipeline does not exist yet. It is the prerequisite for any weekly delta.

**ADR — Scheduler approach: one iterating job, sequential per tenant.**
Register a single APScheduler cron job (Sunday 03:00 MYT). The job fetches
the live tenant list from Supabase at runtime, then processes each tenant
sequentially with a 30-second delay between tenants. This avoids index-shifting
bugs (tenant deletion renumbers remaining slots) and automatically includes
tenants added after the app started, at the cost of slight head-of-line latency
if the first tenant's Serpapi call is slow.

```
  Weekly Sunday 03:00 MYT (one APScheduler cron job)
        │
        ▼
  tenants = supabase.from("tenants").select("*").eq("status","active").execute()
        │
        ▼
  for each tenant in tenants:           ← live list fetched each run
    sleep(30s between tenants)          ← rate-limit buffer
    for each branch in tenant.config.branches:
        │
        ▼
     Serpapi request:
     GET /search?engine=google_maps
       &q={branch.maps_query}
       &api_key={SERPAPI_KEY}
        │
   ┌────┴────┐
 200 OK    Error
   │         │
   │    log error, skip branch
   │    (partial snapshot ok)
   ▼
  parse:
    rating     = result.place_results.rating
    review_cnt = result.place_results.reviews

        │
        ▼
  INSERT INTO review_snapshots (
    tenant_id, branch_id,
    rating, review_count,
    snapshot_date  -- today's date, not timestamp
  )
  ON CONFLICT (tenant_id, branch_id, snapshot_date)
  DO UPDATE SET rating=..., review_count=...

  -- snapshot_date uniqueness prevents duplicate
  -- entries if cron runs twice in a day
```

**Request volume math:**
```
  Tenants × Branches × Weekly snapshots
  = 10 × 5 × 7 = 350 requests/week     ← EXPENSIVE (if daily)
  = 10 × 5 × 1 = 50  requests/week     ← USE THIS (weekly)

  Serpapi: $50 / 500 req → $5/week = $20/month at 10 tenants
  Per-tenant COGS: $2/month ← acceptable on RM199 subscription

  Action: snapshot WEEKLY (Sunday night), not daily.
  Exception: if rating drops > 0.2, trigger immediate re-fetch.
```

---

## 5. Data Flow: Stripe Subscription

> **NOT IN v1 SCOPE — DEFERRED to Month 2-3.**
> v1 billing is Billplz only (Section 6). Stripe is for international expansion
> (Singapore, Australia). Do not implement this section in Week 6.

```
  Customer on /pricing
        │
  [select plan + monthly/annual]
  [select "Pay by Card"]
        │
        ▼
  POST /checkout/stripe
    creates Stripe Checkout Session
    metadata: {tenant_slug, plan, period}
        │
        ▼
  Redirect → Stripe Checkout (hosted)
        │
   ┌────┴──────────────────────────┐
   │  Customer fills card details  │
   └────────────────┬──────────────┘
                    │
          ┌─────────┴────────┐
       Success            Cancel
          │                  │
          │            /pricing (no state change)
          ▼
  Stripe fires webhook:
  POST /webhooks/stripe
  event: invoice.payment_succeeded
          │
          ▼
  1. verify stripe-signature header
     ── fail → 400, log, discard
          │
  2. extract metadata.tenant_slug, plan, period
          │
  3. upsert subscriptions:
     status            = 'active'
     current_period_end = event.period_end
     stripe_customer_id = event.customer
     stripe_subscription_id = event.subscription
          │
  4. upsert tenants.status = 'active'
          │
  5. send welcome WhatsApp to tenant.phone
          │
  6. log payment_events row
          │
  7. return 200 (Stripe retries on non-2xx)
```

---

## 6. Data Flow: Billplz (FPX) Subscription

```
  Customer on /pricing
        │
  [select plan + annual]   ← default annual for FPX
  [select "Pay by FPX / Online Banking"]
        │
        ▼
  POST /checkout/billplz
    creates Billplz Bill via API:
      collection_id = BILLPLZ_COLLECTION_{PLAN}
      name          = tenant.name
      email         = tenant.email
      amount        = tier_price_sen (e.g. 199000)
      callback_url  = /webhooks/billplz
      redirect_url  = /payment/success
    INSERT INTO billplz_bills (tenant_id, billplz_bill_id, amount_sen, status)
        │
        ▼
  Redirect → Billplz payment page
        │
   ┌────┴──────────────────────────────────┐
   │  Customer selects bank, pays via FPX  │
   └────────────────┬──────────────────────┘
                    │
          ┌─────────┴────────┐
       Paid              Unpaid / Abandoned
          │                  │
          │             bill expires (due_at)
          │             send reminder at T-3 days
          ▼
  Billplz fires IPN:
  POST /webhooks/billplz (form-encoded)
  paid=true, id=bill_id, x_signature=...
          │
          ▼
  1. verify x_signature:
     HMAC-SHA256(billplz_secret, "bill_id|paid")
     ── fail → 400, log, discard
          │
  2. check billplz_bills.status for bill_id
     ── already 'paid' → 200, discard (idempotent)
          │
  3. UPDATE billplz_bills SET status = 'paid' WHERE billplz_bill_id = $1
  4. UPDATE tenants SET status = 'active' WHERE id = $tenant_id
  5. send welcome WhatsApp to tenant.phone (founder notified)
  6. return 200

  Monthly renewal:
    Cron on billing anniversary:
      create new Billplz Bill → customer gets payment link
      send WhatsApp: "Your BrandPulse subscription renews. Pay here: [link]"
      wait up to 7 days → if not paid → PAST_DUE
```

---

## 7. Data Flow: Multi-Tenant Request Routing

**ADR — Routing: URL-path routing chosen over subdomain routing.**
Path routing (`/t/<slug>/`) requires zero DNS changes and uses Heroku's existing
TLS certificate. Subdomain routing (`<slug>.brandpulse.my`) requires a DNS wildcard
record and Heroku ACM (paid add-on) for wildcard SSL — out of scope for v1.

```
  GET https://brandpulse.my/t/hakshan/dashboard
        │
        ▼
  extract slug from URL path
    slug = "hakshan"
        │
        ▼
  validate slug: ^[a-z0-9-]{3,50}$ → reject 400 if invalid
        │
        ▼
  SELECT * FROM tenants WHERE slug = $1
        │
   ┌────┴─────────────────────┐
   │                          │
Not found                 Found
   │                          │
  404                         ▼
                    tenant_is_active(tenant.id)
                              │
                    ┌─────────┴──────────────┐
                 No │  (cancelled/past_due   │ Yes
                    │   > grace period)       │
                    ▼                         ▼
            /subscription-lapsed      check session cookie
                                              │
                                    ┌─────────┴──────────────┐
                                    │ No session             │ Valid session
                                    ▼                         │
                             /login?next=/dashboard           │
                             [magic link flow]                 ▼
                                                     verify session.tenant_id
                                                       == tenant.id
                                                              │
                                                    ┌─────────┴──────────────┐
                                                    │ Mismatch               │ Match
                                                    │ (wrong tenant)         │
                                                    ▼                         ▼
                                             403 Forbidden           load tenant config
                                                                      fetch tenant data
                                                                      render dashboard
```

---

## 8. State Machine: Subscription Lifecycle

```
                     ┌─────────┐
                     │ CREATED │  (row inserted, payment not yet confirmed)
                     └────┬────┘
                          │
              payment succeeds (webhook)
                          │
                          ▼
                     ┌─────────┐◄──────────────────────────────────────────┐
                     │ ACTIVE  │                                            │
                     └────┬────┘                                            │
                          │                                                 │
         ┌────────────────┼───────────────────┐             renewal succeeds│
         │                │                   │                             │
   payment          voluntary cancel    billing period ends                 │
   fails            (WhatsApp/email     (manual renewal in v1)              │
     │              support request)        │                               │
     ▼                    │                  ▼                               │
┌──────────┐              │          ┌─────────────┐                        │
│ PAST_DUE │              │          │  CANCELLED  │                        │
└────┬─────┘              │          │  (access    │                        │
     │                    │          │   until EOP)│                        │
     │          ┌─────────┤          └─────────────┘                        │
     │          │         │                                                 │
  day 0:     access       │                                                 │
  WhatsApp   continues    │                                                 │
  alert      until EOP    │                                                 │
     │                    │                                                 │
  day 7:                  │                                                 │
  access                  │                                                 │
  restricted              │                                                 │
     │                    │                                                 │
  day 14:                 │                                                 │
  CANCELLED               ▼                                                 │
     │             ┌─────────────┐                                          │
     └────────────►│  CANCELLED  │                                          │
                   └──────┬──────┘                                          │
                          │                                                 │
                    re-subscribe ──────────────────────────────────────────►┘
                    (new checkout)

State transitions that MUST emit a payment_events row:
  CREATED → ACTIVE        (payment_succeeded)
  ACTIVE → PAST_DUE       (payment_failed)
  PAST_DUE → ACTIVE       (retry_succeeded)
  PAST_DUE → CANCELLED    (grace_expired)
  ACTIVE → CANCELLED      (voluntary)
  * → ACTIVE              (resubscribed)
```

---

## 9. State Machine: Report Delivery

```
                     ┌──────────┐
                     │ PENDING  │  (created by weekly cron)
                     └────┬─────┘
                          │
                   start generation
                          │
                          ▼
                  ┌──────────────┐
                  │  GENERATING  │
                  └──────┬───────┘
                         │
             ┌───────────┴───────────┐
             │                       │
          success                 error
             │                       │
             ▼                       ▼
        ┌─────────┐         ┌─────────────────┐
        │ SENDING │         │ FAILED_GENERATE │
        └────┬────┘         └────────┬────────┘
             │                       │
     ┌───────┴──────┐           retry ≤ 3?
   OK │           Fail│               │
     ▼              ▼         ┌──────┴──────┐
┌───────────┐ ┌────────────┐  Yes          No
│ DELIVERED │ │ RETRY_Q    │   │             │
│ (primary) │ └──────┬─────┘   │         alert founder
└───────────┘        │         └──► GENERATING
                     │
               retry 1–2 (WhatsApp)
                     │
             ┌───────┴──────┐
           OK │           Fail│
             ▼              ▼
        ┌───────────┐  ┌────────────────┐
        │ DELIVERED │  │ EMAIL_FALLBACK  │  ← Sendgrid
        │ (retry)   │  └───────┬────────┘
        └───────────┘          │
                       ┌───────┴──────┐
                     OK │           Fail│
                        ▼              ▼
                   ┌───────────┐ ┌──────────────────┐
                   │ DELIVERED │ │ PERMANENTLY_FAILED│
                   │ (email)   │ └────────┬──────────┘
                   └───────────┘          │
                                   alert founder
                                   log in payment_events
                                   do NOT retry this cycle
```

---

## 10. Error Paths

### 10A. Instagram Token Expiry

```
  APScheduler: social_refresh (every 6h)
        │
        ▼
  fetch_instagram_data(token)
        │
  Instagram API responds:
  {"error": {"code": 190, "type": "OAuthException"}}
        │
        ▼
  fetch_instagram_data() returns None
        │
        ▼
  get_live_social_data() returns {} (no instagram key)
        │
        ▼
  get_data() overlays nothing — stale cached followers shown
  social_live_fetched_at is NOT updated
        │
        ▼
  Dashboard shows: "Live" badge → gone (fetched_at stale)
  Report shows: last known follower count, NO delta

  Mitigation path (to build):
  ├─ On error code 190: set token_health = 'expired' in Supabase
  ├─ Send WhatsApp to tenant: "Your Instagram connection has expired. Reconnect: [link]"
  └─ Weekly health cron: check token_expires_at — alert 7 days before expiry
```

### 10B. Serpapi Outage During Snapshot

```
  Snapshot cron: 03:00
        │
        ▼
  for branch in tenant.branches:
    GET serpapi.com/search?...
        │
  ┌─────┴──────────────────────────────────┐
  │ Timeout / 5xx / rate limit             │
  └─────┬──────────────────────────────────┘
        │
        ▼
  log: "Snapshot failed: {tenant_slug}/{branch_id} at {ts}"
  SKIP this branch — do NOT crash the loop
        │
        ▼
  When report generator runs at 08:00:
    delta_reviews[branch] = None  ← missing snapshot
        │
        ▼
  Report renders:
  "Kepong   — review data unavailable this week"
  NOT: "Kepong ▲ 18 new reviews"

  Do NOT send empty or broken data — be explicit about gaps.
  If ALL branches fail: defer report 24h, retry snapshot, resend.
  If > 50% fail: send partial report with explicit warning.
```

### 10C. Stripe Webhook Duplicate or Out-of-Order

```
  Stripe may deliver the same webhook event more than once.
  Stripe may deliver events out of chronological order.

  Correct handler:

  POST /webhooks/stripe
        │
  1. verify stripe-signature → fail: 400
        │
  2. event_id = event["id"]
     SELECT id FROM payment_events WHERE gateway_reference = event_id
     ── found: return 200 immediately (idempotent)
        │
  3. event_type = event["type"]
     ── "invoice.payment_succeeded":
          check current subscription status
          if already ACTIVE with period_end >= event.period_end:
            return 200 (stale event, ignore)
          else:
            activate/renew subscription
     ── "customer.subscription.deleted":
          check if subscription status is already CANCELLED:
            return 200
          else:
            cancel subscription

  Never rely on event delivery order.
  Always derive state from current DB record + event, not event alone.
```

### 10D. Billplz IPN Replay

```
  Billplz may fire IPN multiple times for the same payment.

  POST /webhooks/billplz (form-encoded)
        │
  1. verify x_signature → fail: 400
        │
  2. bill_id = request.form["id"]
     SELECT id FROM payment_events
       WHERE gateway_reference = bill_id
         AND event_type = 'payment_succeeded'
     ── found: return 200 (idempotent)
        │
  3. paid = request.form["paid"] == "true"
     ── false: log declined event, return 200
        │
  4. activate subscription (normal path)
  5. INSERT payment_events with gateway_reference = bill_id
  6. return 200
```

### 10E. Auth Session Expired Mid-Request

```
  User on /dashboard — session cookie expires
        │
        ▼
  Flask: session.get("user_id") → None
        │
        ▼
  @require_auth decorator triggers:
    return redirect(f"/login?next={request.path}")
        │
        ▼
  Login page: "Your session expired. Enter your email to continue."
        │
        ▼
  Magic link sent → user clicks → new session issued
        │
        ▼
  Redirect to /dashboard (original destination preserved via ?next=)

  Do NOT: clear form data on redirect
  Do NOT: send to /login without preserving next= parameter
  Do NOT: issue sessions longer than 30 days without re-auth
```

---

## 11. Test Matrix

### 11A. Unit Tests

| Module | Function | Test cases |
|---|---|---|
| `data_fetcher` | `fetch_instagram_data()` | Valid token → parses followers/posts; expired token (code 190) → returns None; timeout → returns None; missing `media_url` field → uses `thumbnail_url` |
| `data_fetcher` | `fetch_facebook_data()` | Valid → parses fan_count; error in response → None; page_id not found → None |
| `data_fetcher` | `is_cache_stale()` | Age < 24h → False; age > 24h → True; missing fetched_at → True; malformed ISO string → True |
| `snapshots` | `delta_reviews()` | Normal week → positive delta; first week (no last_week row) → None; branch missing from last_week → None; review count decreased → negative delta (legitimate) |
| `report` | `render_report()` | All branches present → full report; one branch missing snapshot → "data unavailable"; zero delta → "▶ 0 new reviews"; no alerts → alert section omitted |
| `billing` | `tenant_is_active()` | status=active → True; status=past_due, day 3 → True; status=past_due, day 8 → False; status=cancelled → False |
| `billing` | `verify_stripe_signature()` | Valid sig → passes; wrong secret → raises; missing header → raises |
| `billing` | `verify_billplz_hmac()` | Valid sig → passes; tampered body → raises; missing x_signature → raises |

### 11B. Integration Tests

| Flow | Test cases |
|---|---|
| Stripe payment happy path | POST /checkout/stripe → redirects to Stripe URL; simulate webhook invoice.payment_succeeded → tenant status becomes 'active' in DB |
| Stripe payment failure | Simulate invoice.payment_failed webhook → subscription becomes 'past_due'; day 8 simulation → access blocked |
| Stripe idempotency | Fire same invoice.payment_succeeded twice → subscription row updated once; payment_events has one row |
| Billplz payment happy path | POST /checkout/billplz → bill created; simulate IPN paid=true → tenant activated |
| Billplz IPN replay | Fire same IPN twice → idempotency check returns 200, no duplicate payment_events row |
| Billplz HMAC failure | Fire IPN with wrong x_signature → 400 returned, no DB changes |
| Tenant routing | GET brandpulse.my/t/hakshan/dashboard → resolves to Hakshan tenant; GET brandpulse.my/t/unknown/dashboard → 404 |
| Auth gate | Unauthenticated GET /dashboard → redirect to /login?next=/dashboard; authenticated → page renders |
| Tenant isolation | User authenticated as Tenant A; attempt GET Tenant B's slug → 403 |
| Session expiry | Session older than 30 days → redirect to /login; re-auth → redirect to original page |
| Report delivery | generate_report(tenant) → renders correct template; mock Twilio → delivery logged; Twilio failure → email fallback triggered |

### 11C. Security Tests

| Test | Expected behaviour |
|---|---|
| Slug traversal: `../../etc/passwd` | 404 — slug validation: alphanumeric + hyphen only |
| Slug traversal: `../admin` | 404 — no slug matches |
| Unauthenticated `/api/data` | For multi-tenant version: 401. (Current version: public — must be gated in Phase 1) |
| Authenticated user requests another tenant's `/api/data` | 403 — session.tenant_id must match slug's tenant.id |
| POST `/webhooks/stripe` without `stripe-signature` | 400 |
| POST `/webhooks/stripe` with forged signature | 400 |
| POST `/webhooks/billplz` with wrong HMAC | 400 |
| POST `/api/competitors/social` without `ADMIN_TOKEN` | 401 |
| POST `/api/competitors/social` with wrong token | 401 |
| Session cookie without Secure + HttpOnly flags | Must fail security scan — set both flags in Flask config |
| SQL injection in slug param | SELECT with parameterized query, not f-string — must not execute arbitrary SQL |
| XSS in tenant name rendered in HTML | Jinja2 auto-escaping on; any tenant.name in template must be `{{ name }}` not `{{ name \| safe }}` |

### 11D. Failure Mode Tests

| Failure | How to simulate | Expected system behaviour |
|---|---|---|
| Instagram API down | Return 503 from mock server | Dashboard shows stale count, no "Live" badge, no crash |
| Serpapi timeout | Mock 30s response delay | Snapshot for that branch skipped; report shows "unavailable"; loop continues to next branch |
| Stripe webhook replay | Send identical event_id twice | Second delivery returns 200; DB shows single payment_events row |
| APScheduler crash | Kill scheduler thread | Flask app continues serving requests; no reports sent; restart recovers |
| Supabase connection lost | Drop DB connection mid-request | Request fails with 500; error logged; no data corruption |
| Twilio delivery failure | Mock 400 from Twilio | System retries 2×; falls back to email; logs PERMANENTLY_FAILED if email also fails |
| OOM (out of memory) | Large tenant dataset | Report generation per-tenant uses < 50MB peak; measured, not assumed |

---

## 12. Failure Modes (FMEA)

| Component | Failure Mode | Detected By | Customer Impact | MTTR Target | Mitigation |
|---|---|---|---|---|---|
| Instagram API | Token expires | Health cron + API 190 error | Stale social data in report | < 1h | Alert owner 7 days before expiry; re-auth flow |
| Facebook API | Token expires | Same as IG | Stale like count | < 1h | Same token (shared with IG) |
| Serpapi | Outage / rate limit | HTTP 5xx in snapshot cron | Missing review delta this week | < 24h | Partial report with "unavailable" message; retry next day |
| Stripe | Webhook delivery failure | Stripe dashboard, missing activation | Customer paid but not activated | < 4h | Stripe retries 3 days; manual reconciliation job |
| Billplz IPN | IPN not received | Bill not marked paid; customer calls | Customer paid but not activated | < 4h | Customer support: manual activate via admin; Billplz has IPN logs |
| Twilio | WhatsApp API down | Delivery failure event | Report not received | < 2h | Email fallback; Twilio SLA 99.95% |
| Supabase | Database down | 503 on all routes | Dashboard + reports down | < 1h | Supabase SLA 99.9%; fallback: serve cached static data for dashboard |
| APScheduler | Crash | No report delivered; no snapshot | Reports not sent; review delta gaps | < 2h | Supervisor restart; health check endpoint `/health/scheduler` |
| Report generator | Exception for one tenant | Log entry | That tenant misses one report | < 1h | Per-tenant try/except; alert founder; manual resend |
| Flask app | OOM or crash | Railway/Heroku health check | All customers: dashboard down | < 5min | Auto-restart on crash; memory profiling before launch |

---

## 13. Security Concerns

### 13.1 Tenant Data Isolation (Highest Priority)

The current app has zero tenant isolation — it's single-tenant. In the multi-tenant target:

```
Risk: Tenant A reads Tenant B's data by guessing slugs or manipulating session.

Attack vectors:
  1. Slug guessing: GET competitor-brand.brandpulse.my/api/data
  2. Session token theft: reuse Tenant A's cookie to access Tenant B's routes
  3. Forced browsing: directly access /api/data without auth

Mitigations required:
  1. Supabase Row-Level Security (RLS) on ALL tables:
       CREATE POLICY tenant_isolation ON review_snapshots
         USING (tenant_id = (
           SELECT tenant_id FROM tenant_users WHERE id = auth.uid()
         ));
     -- Uses auth.uid() (from the JWT sub claim — always present in Supabase Auth)
     -- joined to tenant_users. Do NOT use auth.jwt() ->> 'tenant_id': Supabase
     -- default JWTs have no tenant_id claim, causing every query to return zero
     -- rows silently (blank dashboard, no error).
     -- This makes it physically impossible to query across tenant boundaries
     -- even if application code is buggy

  2. Slug → tenant_id binding in session:
       session["tenant_id"] = tenant.id  (UUID, not slug)
     All API queries use session["tenant_id"], not URL slug

  3. Slug validation: ^[a-z0-9-]{3,50}$ — reject anything else with 400
```

### 13.2 Webhook Signature Verification

```
Risk: Attacker sends fake webhook to activate a subscription without paying.

Stripe:
  stripe.Webhook.construct_event(
    payload=request.data,
    sig_header=request.headers["Stripe-Signature"],
    secret=STRIPE_WEBHOOK_SECRET
  )
  -- If this throws, return 400. Never process unsigned events.

Billplz:
  expected = hmac.new(
    BILLPLZ_SECRET.encode(),
    f"{bill_id}|{paid}".encode(),
    hashlib.sha256
  ).hexdigest()
  if not hmac.compare_digest(expected, request.form["x_signature"]):
    return "", 400
  -- Use compare_digest (constant-time) to prevent timing attacks
```

### 13.3 Secret Storage

**ADR — Token encryption: Fernet (Option B chosen).**
Supabase Vault requires Pro plan (~$25/month), adding cost before the first paying customer.
Fernet is free, ~30 lines, and sufficient for v1 at 10 tenants. Schema columns rename from
`instagram_token text` → `instagram_token_enc text` (Fernet output is base64 text).

```
Current:   Single ADMIN_TOKEN in env var — acceptable for single tenant
Target:    Per-tenant Instagram/Facebook tokens

Wrong:
  tenant_config.instagram_token text = "EAAB..."  -- plaintext; never store like this

CHOSEN: Fernet encryption before insert
  Schema:  instagram_token_enc text, facebook_token_enc text  (Fernet base64 output)
  Env var: TENANT_SECRET_KEY (Heroku config var; never in DB; never logged)
  Write:
    from cryptography.fernet import Fernet
    f = Fernet(os.getenv("TENANT_SECRET_KEY").encode())
    encrypted = f.encrypt(raw_token.encode()).decode()   # base64 str → store in DB
  Read:
    decrypted = f.decrypt(row.instagram_token_enc.encode()).decode()

  Key rotation: script re-encrypts all tenant rows with new key.
                Run before rotating the env var. Takes < 1 minute at 10 tenants.

Deferred: Supabase Vault (Option A) — revisit at Month 2-3 if moving to Pro plan.

Never: log tokens, include in error responses, or store in cache files
```

### 13.4 Current Admin Endpoint Vulnerability

```python
# Current app.py line 74–76:
auth = request.headers.get("Authorization", "")
if not ADMIN_TOKEN or auth != f"Bearer {ADMIN_TOKEN}":
    return jsonify({"error": "Unauthorized"}), 401
```

```
Vulnerability 1: if ADMIN_TOKEN is empty string (""), the condition
  `not ADMIN_TOKEN` is True → returns 401 (correct).
  But if env var is unset, os.getenv returns "" → admin endpoint
  always returns 401, effectively disabling it silently.
  Fix: raise startup error if ADMIN_TOKEN is not set in production.

Vulnerability 2: No rate limiting on this endpoint.
  An attacker can brute-force the token.
  Fix: add Flask-Limiter (5 req/min per IP on auth-required endpoints).

Vulnerability 3: In multi-tenant, a single ADMIN_TOKEN grants access
  to ALL tenants' competitor data.
  Fix: per-tenant admin scoping or Supabase service role with RLS.
```

### 13.5 Flask Session Security

```python
# Required Flask config before launch:
app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],  # must be set; 32+ random bytes
    SESSION_COOKIE_SECURE=True,        # HTTPS only
    SESSION_COOKIE_HTTPONLY=True,      # no JS access
    SESSION_COOKIE_SAMESITE="Lax",    # CSRF protection
    PERMANENT_SESSION_LIFETIME=2592000, # 30 days
)
```

```
Additional CSRF protection needed for any POST route that modifies state
(subscription changes, admin updates). Flask-WTF or manual CSRF token.

Current state: no CSRF protection, no secure cookie flags.
Risk level: Medium — exploitable if an attacker can get a tenant to click
a link while logged in (CSRF on /api/refresh, /api/competitors/social).
```

### 13.6 PDPA Compliance Checklist

```
Required before first customer signs up:

[ ] Privacy Policy published at /privacy
    - What data is collected (name, email, phone, payment)
    - How it is used (service delivery, billing)
    - How long it is retained (active subscription + 7 years for tax)
    - How to request deletion (PDPA §30)

[ ] Consent checkbox at signup:
    "I agree to BrandPulse's Privacy Policy and consent to receiving
     weekly WhatsApp reports."
    Store: consent_given_at timestamp in tenants table

[ ] Data deletion endpoint (internal admin):
    Soft-delete tenant → anonymise PII in tenants table
    Hard-delete after 7 years (retain payment_events for tax)

[ ] Data breach notification:
    If Supabase is breached: notify affected tenants within 72 hours
    (PDPA §12A if amended; current PDPA has no mandatory timeline,
    but best practice)

[ ] Subprocessor list in privacy policy:
    Supabase (US), Stripe (US), Billplz (MY), Twilio (US),
    Meta Graph API (US), Serpapi (US)
```

---

## 14. Missing Dependencies (Requirements to Add)

Before any of this can ship, `requirements.txt` needs:

```
# Billing
stripe>=7.0.0
# (Billplz has no official Python SDK — use requests directly)

# Database
supabase>=2.0.0          # Supabase Python client
psycopg2-binary>=2.9     # direct PostgreSQL if needed

# Auth
PyJWT>=2.8.0             # JWT session verification
itsdangerous>=2.1.0      # signed tokens for magic links (already in Flask)

# Report delivery
twilio>=8.0.0            # WhatsApp Business API
sendgrid>=6.11.0         # email fallback

# Security
flask-limiter>=3.5.0     # rate limiting
cryptography>=42.0.0     # Fernet for token encryption

# Review data
# Serpapi: use requests directly (no official Python SDK needed)

# Utilities
python-dotenv>=1.0.0     # already present
celery>=5.3.0            # optional: replace APScheduler for distributed task queue
redis>=5.0.0             # optional: Celery broker + rate limit backend
```

---

## 15. Recommended Build Order

Based on dependency graph — each phase unblocks the next:

```
Phase 1A (Week 1–2): Foundation
  ├── Supabase schema: tenants, tenant_users, tenant_config, billplz_bills, review_snapshots
  ├── Supabase Auth: magic link setup
  ├── Flask: auth middleware (@require_auth decorator)
  ├── Flask: tenant routing (slug → tenant_id → session)
  └── Flask: Supabase RLS policies

Phase 1B (Week 3–4): Config & Data
  ├── Branch config: extract STATIC_DATA into tenant JSON configs
  ├── Review snapshot service: Serpapi → review_snapshots table
  └── Social delta: snapshot IG/FB counts weekly alongside reviews

Phase 2A (Week 5–6): Billing
  ├── Stripe: Checkout, webhook handler, Customer Portal
  ├── Billplz: Bill creation, IPN handler, monthly renewal cron
  └── Access control: gate dashboard on subscription status

Phase 2B (Week 7–8): Report Delivery
  ├── Report generator: diff calculator + template renderer
  ├── Twilio: WhatsApp delivery
  ├── Sendgrid: email fallback
  └── Weekly report cron: per-tenant dispatch

Phase 3 (Week 9–12): Self-Serve & Polish
  ├── Onboarding form: tenant signup → auto-config → checkout
  ├── Admin dashboard: manual tenant management (for concierge cases)
  ├── Token health monitoring: expiry alerts
  └── Alerts: unanswered 1-star reviews, rating drops
```
