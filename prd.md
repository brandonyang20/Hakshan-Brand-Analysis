# BrandPulse — Product Requirements Document

**Version:** 1.0  
**Date:** May 2026  
**Status:** Active  

> This is the authoritative product spec. It supersedes and consolidates `06-saas-design-doc.md`, `07-scope-review.md`, and `08-eng-review.md`. All open questions from those documents have been resolved or marked as decisions pending.

---

## 1. Vision

**BrandPulse** is an F&B brand intelligence platform for multi-branch restaurant operators in Southeast Asia.

The one-line pitch: *"The weekly brand report your marketing manager would send — without the marketing manager."*

Delivered via WhatsApp. Zero login. Priced for Malaysian SMEs.

---

## 2. Problem

Multi-branch F&B owners (3–10 outlets) are managing brand health manually across:
- 3–10 Google Business profiles
- 1–2 Instagram / Facebook accounts
- Competitors they monitor inconsistently or not at all

No affordable tool exists that aggregates this into one view, is priced for the mid-market, and works without an IT team or a dedicated marketer.

The result: owners react to problems instead of preventing them. A branch drops to 4.1 stars — they notice weeks later. A competitor gains 1,000 followers — they never know.

**Why now:**
- Hakshan (5-branch Hakka chain, Klang Valley) is the founder's own restaurant. This tool was built for them first — founder-market fit is real.
- The data layer and dashboard UI are proven for one brand. SaaS infrastructure (auth, billing, multi-tenancy, report delivery) is greenfield.
- No FPX-native, WhatsApp-first, Malaysian-priced F&B monitoring tool exists. The closest competitor (Momos) targets APAC enterprise restaurant groups — the gap is pricing and payment localisation for independent Malaysian operators.

---

## 3. Ideal Customer Profile

| Attribute | Description |
|-----------|-------------|
| Business type | F&B chain (any cuisine) — owner controls their own Google Business profiles and social accounts |
| Outlet count | 3–10 branches |
| Geography | Klang Valley (MY) → expand to SG, Penang, Johor Bahru |
| Team size | No dedicated marketing person |
| Decision maker | Founder or ops director |
| Pain level | High — manually checks Google Maps across branches weekly |
| Budget | RM200–500/month without needing a business case |
| Communication style | WhatsApp-first; checks phone before laptop |

**Counter-ICP (do not target):**
- Single-outlet F&B — not enough data to make the product useful
- Chains where head office manages digital presence centrally — the local operator has no pain and no control
- Non-F&B businesses — different review platforms, different vocabulary

**Prerequisite note:** The branch-config mechanism (allowing dynamic addition of branch data per tenant) must be built before any customer can be onboarded. Currently all branch data is hardcoded for Hakshan.

---

## 4. Product Strategy

### 4.1 The Wedge: Weekly Brand Pulse Report

The smallest thing we can charge for today.

**What it is:** A weekly WhatsApp/email message summarising how each branch performed last week. No login required. No dashboard. Just a digest.

**Why this is the wedge:**
- Zero onboarding friction — owner doesn't have to "learn" anything
- Delivery channel (WhatsApp) is where Malaysian F&B owners already live
- The first report they receive IS the demo — no sales call needed
- Creates a weekly habit before upselling the dashboard

**Report format (v1):**

```
客善 Hakshan — Week of 12–18 May 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⭐ REVIEWS THIS WEEK
Kepong       ▲ 18 new reviews  (4.7 ⭐)
Subang       ▲ 12 new reviews  (4.5 ⭐)
Puchong      ▲  9 new reviews  (4.4 ⭐)
Cheras       ▲  7 new reviews  (4.5 ⭐)
Sri Petaling ▲  5 new reviews  (4.3 ⭐)

📱 SOCIAL PULSE
Instagram    2,812 followers  (+41 this week)
Facebook     6,290 likes      (+33 this week)

⚠️  ACTION NEEDED
• 3 unanswered 1-star reviews (Kepong, Subang)
• Subang dropped 0.1 stars — review reasons attached

View full dashboard → [link]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Powered by BrandPulse  |  Reply STOP to unsubscribe
```

**Technical prerequisite:** The weekly review delta ("▲ 18 new reviews") requires a time-series review snapshot service — a weekly cron job that fetches and stores review counts per branch. This does not currently exist and is a Phase 1B build requirement.

### 4.2 Upsell 1: Multi-Branch Dashboard

The existing Hakshan app, made multi-tenant. Owners can:
- See all branches on one screen
- Drill into a branch for review themes and sentiment breakdown
- Compare week-over-week trends
- View the last 6 months of review velocity per branch

Included from day 1 on all paid tiers. Pulse gets a summary view; Insight gets full drill-down with the competitor module.

### 4.3 Upsell 2: Competitor Tracking Module

Already built for Hakshan. Track for any brand:
- Competitor follower counts (IG, FB)
- Competitor review score and review velocity
- Side-by-side gap analysis

Included in Insight tier. Available as an RM100/month add-on on Pulse.

---

## 5. What Is Not in v1

| Out of Scope | Reason |
|---|---|
| TikTok / Xiaohongshu API integration | Gated API access; not required for wedge |
| AI-generated review responses | LLM cost + quality risk; Phase 2 |
| POS / delivery platform integration (Grab, Foodpanda) | High per-platform integration cost |
| Mobile app | Web-first; WhatsApp report removes need for native app in v1 |
| Multi-language dashboard UI | English-first; Mandarin/BM in v2 after ICP validation |
| Influencer tracking | Different buyer (agencies, not operators) |
| Automated Google review request campaigns | Legal risk; Phase 2 |

**Phase 2 (Month 3):**
- Self-serve onboarding — concierge flow is used for first 10 customers; self-serve ships in Month 3 alongside Phase 2 multi-tenancy

---

## 6. Pricing

### Decision: Per-brand flat rate (not per-branch)

Per-branch pricing creates friction ("should I add that new outlet?"). Flat-rate per brand aligns incentives — more branches = more value delivered, same price.

| Tier | Monthly | Annual | Saving | Includes |
|---|---|---|---|---|
| **Pulse** | RM199/month | RM1,990/year *(RM166/month)* | RM398 (2 months free) | Weekly WhatsApp/email report + summary dashboard (branch totals, social counts, alerts) |
| **Insight** | RM399/month | RM3,990/year *(RM332/month)* | RM798 (2 months free) | Everything in Pulse + full drill-down dashboard, competitor tracking, AI-drafted monthly strategy summary (founder-reviewed before sending) |
| **Custom** | RM800+/month | Quote | — | Insight + concierge setup, custom report cadence, Mandarin/BM reports |

**Pulse vs Insight dashboard boundary:** Pulse gets a read-only summary (totals and alerts only). Insight gets full drill-down per branch, sentiment breakdown, 6-month trend charts, and competitor side-by-side comparison.

**Monthly strategy summary (Insight):** AI-generated draft, reviewed and edited by the founder before sending. Cap Insight at 15 customers until the AI draft quality is validated and the review workflow is under 30 minutes/week.

**No free trial.** The sales demo IS the first manual report — the founder sends it via WhatsApp before the customer pays. Once they see value, they subscribe. Payment starts on day one.

---

## 7. Billing Architecture

### Dual payment gateway: Stripe + Billplz

Malaysian F&B operators split between two payment behaviours. A card-only checkout loses ~40% of Malaysian SME customers.

| Gateway | Use case | Renewal model |
|---|---|---|
| **Stripe** | Card payers (younger founders, startup-adjacent) | Fully automatic, silent charge on cycle date |
| **Billplz** | FPX / online banking (traditional SME operators) | Customer must manually approve each cycle in their banking app |

⚠️ **Billplz churn risk:** Monthly FPX customers must consciously approve each renewal. One missed notification = lapsed subscription. **Mitigation: default FPX customers to annual billing** (one approval per year). Offer the annual plan as the recommended default in the checkout flow.

### Subscription states

```
CREATED → ACTIVE → PAST_DUE → CANCELLED
                 ↘ CANCELLED (voluntary)
```

- Day 0: payment fails → WhatsApp alert to customer
- Day 7: access restricted (reports paused, dashboard read-only)
- Day 14: subscription cancelled, tenant deactivated

Every state transition emits a `payment_events` row for full audit trail.

### Database schema

```sql
tenants (
  id          uuid PRIMARY KEY,
  slug        text UNIQUE NOT NULL,
  name        text NOT NULL,
  email       text NOT NULL,
  phone       text,                  -- WhatsApp delivery number
  status      text NOT NULL DEFAULT 'active',
  consent_given_at  timestamptz,     -- PDPA requirement
  created_at  timestamptz DEFAULT now()
)

subscriptions (
  id                    uuid PRIMARY KEY,
  tenant_id             uuid REFERENCES tenants(id),
  plan                  text NOT NULL,      -- pulse | insight | custom
  billing_period        text NOT NULL,      -- monthly | annual
  status                text NOT NULL,      -- active | past_due | cancelled
  current_period_start  date NOT NULL,
  current_period_end    date NOT NULL,
  amount_myr            numeric(10,2) NOT NULL,
  payment_method        text NOT NULL,      -- stripe | billplz
  stripe_customer_id       text,
  stripe_subscription_id   text,
  billplz_collection_id    text,
  billplz_active_bill_id   text,            -- updated each cycle; history in payment_events
  created_at            timestamptz DEFAULT now(),
  updated_at            timestamptz DEFAULT now()
)

payment_events (
  id                uuid PRIMARY KEY,
  tenant_id         uuid REFERENCES tenants(id),
  subscription_id   uuid REFERENCES subscriptions(id),
  event_type        text NOT NULL,
  amount_myr        numeric(10,2),
  payment_method    text,
  gateway_reference text,            -- Stripe invoice ID or Billplz bill ID
  status            text,
  created_at        timestamptz DEFAULT now()
)

review_snapshots (
  id            uuid PRIMARY KEY,
  tenant_id     uuid REFERENCES tenants(id),
  branch_id     text NOT NULL,
  rating        numeric(2,1),
  review_count  int,
  snapshot_date date NOT NULL,
  UNIQUE (tenant_id, branch_id, snapshot_date)
)
```

### Webhook endpoints (to build)

| Route | Gateway | Action |
|---|---|---|
| `POST /webhooks/stripe` | Stripe | Verify `stripe-signature`; handle `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.updated/deleted` |
| `POST /webhooks/billplz` | Billplz | Verify HMAC-SHA256 `x_signature`; handle `paid` IPN; activate/renew tenant |

Both endpoints must be idempotent — check `gateway_reference` against `payment_events` before processing.

**Invoice generation:** Stripe auto-generates PDF invoices. For Billplz customers, the platform must generate and email a receipt after each successful IPN. This is a customer support obligation.

---

## 8. Technical Architecture

### Current state (as-is)

Single-tenant Flask app, hardcoded to Hakshan. All data lives in `STATIC_DATA` dict in `data_fetcher.py`. No auth, no billing, no multi-tenancy, no report delivery.

### Target architecture

- **Single Flask app** with path-based tenant routing: `/t/<slug>/dashboard`
- **Supabase** for tenant data, config, subscription state, and snapshot history
- **APScheduler** for scheduled jobs (snapshot, report dispatch)
- **Supabase Auth** (magic link) for customer login
- **Supabase RLS** for tenant data isolation

### Tenant routing

```
GET /t/hakshan/dashboard
  → extract slug → validate (^[a-z0-9-]{3,50}$)
  → SELECT tenant WHERE slug = ?
  → check subscription active
  → check session (redirect to /login?next=... if none)
  → verify session.tenant_id == tenant.id (403 if mismatch)
  → load tenant config, render dashboard
```

**ADR — Path routing over subdomains:** Path routing (`/t/<slug>/`) requires zero DNS changes. Subdomain routing requires a wildcard DNS record and paid SSL add-on. Deferred to Phase 3.

### Review snapshot service

Weekly cron (Sunday 03:00 MYT). One APScheduler job iterates active tenants sequentially with a 30-second delay between tenants.

**Data source:** Serpapi Google Maps API.

**Request volume and unit economics:**
```
10 tenants × 5 branches × 1 request/week = 50 requests/week = ~200/month
Serpapi: $50/500 requests → ~$20/month at 10 tenants ($2/tenant/month COGS)
```
Snapshot weekly, not daily. Daily polling = 350 requests/day = $245/month = 56% COGS on a RM199 subscription.

**Exception:** if a branch rating drops >0.2 stars, trigger an immediate re-fetch.

### Token encryption

**ADR — Fernet (Option B):** Supabase Vault requires Pro plan (~$25/month). Fernet is free, ~30 lines, and sufficient for v1 at 10 tenants.

Per-tenant Instagram/Facebook tokens stored as Fernet-encrypted text in Supabase. Encryption key in env var (`TENANT_SECRET_KEY`), never in DB, never logged.

### Auth

Magic link via Supabase Auth. No password to manage. Session cookies: `Secure`, `HttpOnly`, `SameSite=Lax`, 30-day lifetime.

---

## 9. Feature Requirements by Phase

### Phase 1A — Foundation (Weeks 1–2)

**Goal:** Multi-tenant auth and routing. No customer can be onboarded without this.

| Requirement | Acceptance criteria |
|---|---|
| Supabase schema created | Tables: `tenants`, `subscriptions`, `payment_events`, `review_snapshots`, `tenant_config` with RLS policies |
| Supabase Auth magic link | Customer can receive magic link, click it, and land on their dashboard |
| `@require_auth` Flask decorator | Any unauthenticated request to `/t/<slug>/` routes redirects to `/login?next=<path>` |
| Tenant routing | `GET /t/hakshan/dashboard` resolves correctly; unknown slug returns 404; wrong tenant session returns 403 |
| RLS policies | Tenant A cannot query Tenant B's data even with a valid session |

**RLS implementation note:** Use `auth.uid()` joined to `tenant_users`, not `auth.jwt() ->> 'tenant_id'` — Supabase default JWTs have no `tenant_id` claim and will silently return zero rows.

### Phase 1B — Config & Data (Weeks 3–4)

**Goal:** Real data pipeline. Wedge report becomes technically possible.

| Requirement | Acceptance criteria |
|---|---|
| Branch config extraction | `STATIC_DATA` extracted to per-tenant JSON config; `data_fetcher.py` reads from tenant config based on slug |
| Review snapshot service | Serpapi cron runs Sunday 03:00 MYT; inserts rows into `review_snapshots`; handles Serpapi outage gracefully (skip branch, log, continue) |
| Weekly delta calculation | `delta_reviews(tenant_id, branch_id)` returns `this_week.count - last_week.count`; returns `None` if no prior snapshot |
| Social delta | IG/FB follower counts snapshotted weekly alongside reviews |
| Cache isolation | Per-tenant cache files (`cache/{slug}/...`); Tenant A cannot read Tenant B's cache |

### Phase 2A — Billing (Weeks 5–6)

**Goal:** Customers can pay. Access is gated on subscription status.

| Requirement | Acceptance criteria |
|---|---|
| Billplz checkout | `POST /checkout/billplz` creates a bill and redirects to Billplz payment page |
| Billplz IPN handler | `POST /webhooks/billplz` verifies HMAC, is idempotent, activates tenant on `paid=true` |
| Billplz receipt generation | PDF receipt emailed to customer after each successful Billplz IPN |
| Stripe checkout | `POST /checkout/stripe` creates Stripe Checkout session and redirects |
| Stripe webhook handler | `POST /webhooks/stripe` verifies signature, is idempotent, handles `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.deleted` |
| Access control | Dashboard gated on `subscriptions.status`; past_due gets 7-day grace period |
| Tier gating | Pulse tier cannot access Insight-only features (competitor module, full drill-down) |

**v1 billing note:** For first 10 customers (Month 1–2), billing is handled manually by the founder via Billplz bill link. Stripe Checkout goes live in Month 3. Track subscriptions in Supabase from day one regardless of manual/automated flow.

### Phase 2B — Report Delivery (Weeks 7–8)

**Goal:** Reports are generated and dispatched automatically.

| Requirement | Acceptance criteria |
|---|---|
| Report generator | `generate_report(tenant_id)` renders correct template with real delta data; gracefully handles missing snapshot ("data unavailable this week") |
| Weekly dispatch cron | Monday 08:00 MYT; skips inactive tenants; per-tenant try/except (one tenant failure does not cancel others) |
| WhatsApp delivery (Twilio) | Primary delivery channel; retry up to 2× on failure |
| Email fallback (Sendgrid) | Triggered if WhatsApp delivery fails after retries |
| Permanent failure handling | Log `PERMANENTLY_FAILED` in `payment_events`; alert founder; do not retry current cycle |
| UTM-tagged dashboard links | Every report contains a UTM-tagged link; click-through rate measurable via analytics |
| Report delivery state machine | States: `PENDING → GENERATING → SENDING → DELIVERED / FAILED_GENERATE / EMAIL_FALLBACK / PERMANENTLY_FAILED` |

### Phase 3 — Self-Serve & Polish (Weeks 9–12)

**Goal:** New customers can onboard without founder involvement.

| Requirement | Acceptance criteria |
|---|---|
| Onboarding form | Tenant can enter brand name, branch details, IG/FB tokens, select plan, and complete checkout without contacting founder |
| Token health monitoring | Weekly cron checks `token_expires_at`; WhatsApp alert to tenant 7 days before expiry; dashboard shows clear reconnect prompt on token error |
| Admin dashboard | Founder can manually activate/deactivate tenants, view subscription status, trigger report resend |
| Unanswered review alerts | Report includes count of unanswered 1-star reviews per branch (requires Google review content access — manual or Serpapi-provided) |
| Rating drop alerts | Alert in report if any branch drops >0.1 stars week-over-week |

---

## 10. Security Requirements

All of the following are required before any paying customer is onboarded:

| Requirement | Detail |
|---|---|
| Supabase RLS on all tables | Physically prevents cross-tenant data access even if application code is buggy |
| Webhook signature verification | Stripe: `stripe.Webhook.construct_event()`. Billplz: HMAC-SHA256 `compare_digest()`. Return 400 on failure. |
| Fernet token encryption | All Instagram/Facebook tokens stored encrypted in Supabase. Never logged, never in cache files. |
| Flask session hardening | `SECRET_KEY` from env, `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"` |
| CSRF protection | Flask-WTF or manual CSRF token on all POST routes that modify state |
| Rate limiting | Flask-Limiter: 5 req/min per IP on all auth-required endpoints |
| Slug validation | `^[a-z0-9-]{3,50}$` — reject anything else with 400. Prevents path traversal. |
| SQL parameterisation | All Supabase queries parameterised. No f-string SQL. |
| PDPA compliance | Privacy policy at `/privacy`, consent checkbox at signup, `consent_given_at` stored in `tenants`, data deletion mechanism for PDPA §30 |

---

## 11. 90-Day Go-To-Market Plan

### Month 1 — First 3 Paying Customers

**Goal:** Validate the weekly report format and pricing before building.

| Week | Action |
|---|---|
| 1 | Send a free sample report (manually written by founder) to 3 F&B contacts via WhatsApp |
| 2 | Close payment before sending a second report. Create Billplz bill (RM199 or RM1,990 annual). Report #2 is sent only after payment clears. |
| 3 | Deliver manually written report to 3 paying customers. Collect testimonials. Build report generation script in parallel. |
| 4 | Onboard 3 more customers from referrals. Repeat: sample report → payment → manual delivery. |

**Founder bandwidth constraint:** Hakshan operations and BrandPulse sales compete for the same hours. Weeks 1–4 must be scoped to tasks executable in ~5 hours/week.

**Target contacts:** F&B operators in Klang Valley known through Hakshan's network — suppliers, fellow association members, nearby chain operators.

**Channels:** Direct WhatsApp from founder; Hakshan social media; F&B operator Facebook groups.

### Month 2 — Dashboard + 6 Customers

**Goal:** Ship multi-tenant dashboard. Upsell existing customers to Insight tier.

| Week | Action |
|---|---|
| 5–6 | Build Phase 1A + 1B (auth, routing, snapshot service) |
| 7 | Give Pulse customers dashboard access. Pitch Insight tier upgrade. |
| 8 | First inbound from referrals. Target 6 paying customers total. |

### Month 3 — 10 Customers + First Press

**Goal:** Hit RM2,000 MRR. Get one earned media mention.

| Week | Action |
|---|---|
| 9–12 | Phase 2A + 2B (billing webhooks, report delivery) — 4-week sprint, not 2 |
| 11 | Pitch story to Says.com / Vulcan Post: "The restaurant that built its own brand radar" |
| 12 | Self-serve onboarding form ships. 10 paying customers target. |

### MRR Targets

| Month | Customers | Avg. Revenue | MRR |
|---|---|---|---|
| 1 | 3 | RM199 | RM597 |
| 2 | 6 | RM280 | RM1,680 |
| 3 | 10 | RM320 | RM3,200 |
| 6 | 25 | RM350 | RM8,750 |
| 12 | 60 | RM380 | RM22,800 |

---

## 12. Success Metrics

### v1 Validation (Month 1–2)
- [ ] 3 paying customers before dashboard is built
- [ ] Dashboard link click-through rate > 40% per weekly report (UTM-tracked)
- [ ] 0 customers cancel after their first report
- [ ] At least 1 customer says "I didn't know that — that's really useful"

### Product-Market Fit Signal (Month 3–6)
- [ ] NPS > 50
- [ ] >30% of new customers come from referrals
- [ ] Churn < 5%/month
- [ ] At least 1 customer upgrades from Pulse → Insight

### Scale Signal (Month 6–12)
- [ ] RM10,000 MRR
- [ ] Inbound leads without founder outreach
- [ ] At least 3 customers in Singapore or Penang

---

## 13. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Founder bandwidth** — running 5 branches + building SaaS | **Very High** | Cap GTM at 5 hrs/week; hire ops support for Hakshan before scaling BrandPulse past 10 customers |
| **PDPA compliance** — collecting phone, email, payment data | **High** | Engage a Malaysian lawyer before first customer signs up; publish privacy policy, consent checkbox, data retention policy |
| Google review data hard to automate | High | Serpapi at weekly polling ($2/tenant/month COGS) for v1; manual fallback for first 5 customers |
| WhatsApp Business API requires approval | Medium | Use personal WhatsApp for first 10 customers; apply for Twilio API concurrently |
| Instagram token expiry disrupts reports | Medium | Token health monitoring; alert 7 days before expiry; re-auth flow |
| Instagram Business Account requirement | Medium | Personal accounts cannot use Graph API; include "Convert to Business Account" in onboarding checklist |
| Google Maps ToS / Serpapi legality | Medium | Serpapi is acceptable v1 workaround; target Google Business Profile API (official) for Phase 2 |
| Billplz monthly churn — manual approval each cycle | Medium | Default FPX customers to annual billing |
| Customers don't pay after seeing demo report | Low | Demo must include one "action needed" callout that costs them money if ignored |
| Competitor copies the product | Low | Moat is founder-operator trust and SEA localisation, not technology |

---

## 14. Open Decisions

| # | Question | Decision deadline |
|---|---|---|
| 1 | **Google review data source** — Serpapi vs DataForSEO vs Google Business API. Evaluate cost and reliability for 10 branches × 10 tenants. | Before Phase 1B build |
| 2 | **WhatsApp delivery** — Personal WhatsApp (manual, immediate) vs Twilio WhatsApp Business API (automated, requires approval). Start manual; automate at 5+ customers. | Month 2 |
| 3 | **Brand name** — "BrandPulse" is a working title. Check trademark availability in MY/SG. | Before public launch |
| 4 | **Pricing test** — Is RM199 too cheap? Test by anchoring at RM299 with new customers in Month 2. | Month 2 |
| 5 | **Billplz Direct Debit** — Confirm whether Billplz auto-debit (no customer approval per cycle) is available for business accounts. | Before Phase 2A |
| 6 | **Annual refund policy** — Recommended: no refunds after 30 days, prorated refund within first 30 days. | Before first annual sale |
| 7 | **SST / tax** — Is the subscription subject to Malaysia Service Tax? Consult an accountant before first invoice. | Month 1 |

---

## 15. Existing Codebase Assets

The Hakshan app already has the following, which should be extended rather than rewritten:

| Feature | Status | Notes |
|---|---|---|
| Flask web server | Production | Deployed via Procfile on Railway |
| Instagram Graph API | Live | Needs per-tenant token management |
| Facebook Graph API | Live | Needs per-tenant token management |
| Competitor social tracking | Live | Admin-only POST endpoint |
| Google RSS news feed | Live | Per-brand query strings |
| 24h data caching | Production | Per-file cache; needs per-tenant isolation |
| APScheduler | Production | Runs every 6h for social, daily for news |
| Multi-branch review data | Static | Needs Serpapi integration for live data |
| Admin token auth | Basic | Upgrade to Supabase Auth in Phase 1A |

**Reuse strategy:** Don't rewrite. Extract `STATIC_DATA` into tenant config files and add a tenant-routing layer on top. The core data fetching, caching, and API integration is solid.

**Dependencies to add (`requirements.txt`):**

```
supabase>=2.0.0
PyJWT>=2.8.0
stripe>=7.0.0
twilio>=8.0.0
sendgrid>=6.11.0
flask-limiter>=3.5.0
cryptography>=42.0.0
```

---

## 16. Reference Documents

| Document | Purpose |
|---|---|
| `06-saas-design-doc.md` | Original product design doc (superseded by this PRD) |
| `07-scope-review.md` | Critical review of the design doc — all issues resolved in this PRD |
| `08-eng-review.md` | Engineering review — data flows, state machines, error paths, security, test matrix |
| `01-brand-overview.md` | Hakshan brand context — the pilot customer |
| `05-recommendations.md` | Hakshan marketing strategy — context for the product's value proposition |
