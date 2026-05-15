# 06 — SaaS Product Design Document
**BrandPulse: F&B Brand Intelligence for Multi-Branch Operators**

*Draft v1 — May 2026*

---

## TL;DR

Turn the existing Hakshan brand analysis app into a multi-tenant SaaS serving multi-branch F&B operators in Southeast Asia. The wedge is an automated weekly brand pulse report delivered to the owner's phone — zero login, zero friction. The dashboard and competitor tracking become the upsell. Target RM200–500/month per brand. First 10 paying customers come from direct founder outreach to F&B operators in Klang Valley.

---

## 1. Problem

Multi-branch F&B owners (3–10 outlets) are managing brand data across:
- 3–10 Google Business profiles
- 1–2 Instagram/Facebook accounts
- Competitors they can't systematically monitor

They do this manually, inconsistently, or not at all. There is no tool that:
1. Aggregates all of this into one view
2. Is priced for the mid-market (not RM10,000/month enterprise)
3. Works without an IT team or a dedicated marketer

The result: owners react to problems instead of preventing them. A branch drops to 4.1 stars — they notice weeks later. A competitor gains 1,000 followers — they never notice.

---

## 2. Why This, Why Now

| Signal | Evidence |
|--------|----------|
| Founder-market fit | Hakshan is a 5-branch F&B operator. We built this tool for ourselves. |
| Working prototype | Flask app with IG API, Facebook API, competitor tracking, review aggregation — deployed and running. |
| Market gap | Birdeye/ReviewTrackers: $200–400/month, US-centric, no SEA localisation, no WhatsApp delivery. |
| Timing | Post-COVID F&B expansion wave in Malaysia — more multi-branch independents than ever. |
| Zero SEA competition | No F&B-specialized brand monitoring tool with Malay/Chinese language support exists in MY/SG. |

---

## 3. Who We're Building For

**Ideal Customer Profile (ICP) — v1**

| Attribute | Description |
|-----------|-------------|
| Business type | F&B chain, non-franchise, Chinese or multi-ethnic cuisine |
| Outlet count | 3–10 branches |
| Location | Klang Valley (MY) → expand to SG, Penang, Johor Bahru |
| Team size | No dedicated marketing person |
| Decision maker | Founder or ops director |
| Pain level | High — manually checks Google Maps across branches weekly |
| Budget | RM200–500/month without needing a business case |
| Communication | WhatsApp-first; checks phone before laptop |

**Counter-ICP (don't target):**
- Single-outlet F&B (not enough data to make the product useful)
- Franchise chains with 20+ outlets (need enterprise contract, different sales motion)
- Non-F&B businesses (different review platforms, different competitors, different vocabulary)

---

## 4. Product Strategy

### 4.1 The Wedge: Weekly Brand Pulse Report

The smallest thing we can charge for today.

**What it is:** A weekly WhatsApp/email message to the owner summarising how each branch performed last week. No login. No dashboard. Just a digest.

**Why this is the wedge:**
- Zero onboarding friction — owner doesn't have to "learn" anything
- Delivery channel (WhatsApp) is where Malaysian F&B owners already live
- The first report they receive IS the demo — no sales call needed
- Works even if the dashboard UI is unpolished
- Creates weekly habit before upselling the dashboard

**Report contents (v1):**
```
客善 Hakshan — Week of 12–18 May 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⭐ REVIEWS THIS WEEK
Kepong      ▲ 18 new reviews  (4.7 ⭐)
Subang      ▲ 12 new reviews  (4.5 ⭐)
Puchong     ▲ 9 new reviews   (4.4 ⭐)
Cheras      ▲ 7 new reviews   (4.5 ⭐)
Sri Petaling ▲ 5 new reviews   (4.3 ⭐)

📱 SOCIAL PULSE
Instagram   2,812 followers  (+41 this week)
Facebook    6,290 likes      (+33 this week)

⚠️  ACTION NEEDED
• 3 unanswered 1-star reviews (Kepong, Subang)
• Subang dropped 0.1 stars — review reasons attached

View full dashboard → [link]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Powered by BrandPulse  |  Reply STOP to unsubscribe
```

### 4.2 Upsell 1: Multi-Branch Dashboard

The existing Hakshan app, made multi-tenant. Owners can:
- See all branches on one screen
- Drill into a branch for review themes, sentiment breakdown
- Compare week-over-week trends
- See the last 6 months of review velocity per branch

**Unlock condition:** After 4 weeks of receiving the report, owner gets a link to the dashboard. Priced separately or included in a higher tier.

### 4.3 Upsell 2: Competitor Tracking Module

Already built for Hakshan. For any brand, track:
- Competitor follower counts (IG, FB, TikTok)
- Competitor review score and review velocity
- Side-by-side gap analysis

**Unlock condition:** Top-tier plan or add-on at RM100/month.

---

## 5. What We Are NOT Building in v1

| Out of Scope | Why |
|---|---|
| TikTok / Xiaohongshu API integration | Gated API access; complex; not required for wedge |
| AI-generated review responses | Requires LLM cost + quality review; phase 2 |
| POS / delivery platform integration (Grab, Foodpanda) | Different API per platform, high integration cost |
| Mobile app | Web-first; WhatsApp report removes need for app in v1 |
| Multi-language dashboard UI | English-first; Mandarin/Malay in v2 after ICP validation |
| Influencer tracking | Out of scope; different buyer (agencies, not operators) |
| Automated Google review request campaigns | Legal risk; phase 2 feature |
| Self-serve onboarding | Concierge onboarding for first 20 customers — manual is fine |

---

## 6. Architecture Plan

### Current state
Single-tenant Flask app hardcoded for Hakshan. All data lives in `STATIC_DATA` dict in `data_fetcher.py`. Instagram/Facebook API credentials are single-account env vars.

### Migration path to multi-tenant

**Phase 1 — Config-driven multi-tenancy (no DB required)**
- Extract `STATIC_DATA` into a per-tenant JSON config file
- `data_fetcher.py` reads the config for the active tenant based on a URL slug or subdomain
- Each tenant gets their own Instagram/Facebook API tokens in env vars or a secrets store
- Deployment: one Heroku app per tenant (naive but works for first 10 customers)
- **Effort: ~2 days**

**Phase 2 — Database-backed multi-tenancy**
- Supabase (already available via MCP) for tenant data, config, subscription status
- One app instance, subdomain routing (`hakshan.brandpulse.my`, `nasi-lemak-abc.brandpulse.my`)
- Scheduled jobs (APScheduler, already wired) run per-tenant
- **Effort: ~1 week**

**Phase 3 — Report delivery pipeline**
- Twilio/WhatsApp Business API for WhatsApp delivery
- Sendgrid for email fallback
- Weekly cron job generates and dispatches reports per tenant
- **Effort: ~3 days**

### Data sources map

| Data type | Source | Status |
|---|---|---|
| Instagram followers + posts | Instagram Graph API | Live ✓ |
| Facebook likes | Facebook Graph API | Live ✓ |
| Google review count + rating | Google Business API (or scrape) | Static (manual update) |
| Competitor social | Admin API (manual POST) | Live ✓ |
| Industry news | Google RSS | Live ✓ |
| Review themes / sentiment | Static analysis text | Manual |

**Critical gap:** Google Business API requires OAuth per-location verification. Alternatives:
1. Serpapi / DataForSEO (paid, ~$50/month for 500 requests) — recommended for v1
2. Manual input via admin dashboard — acceptable for first 5 tenants
3. Google Business Profile API — implement in phase 2 when volume justifies verification effort

---

## 7. Pricing Model

### Decision: Per-brand flat rate (not per-branch)

**Rationale:** Per-branch pricing creates friction ("should I add that new outlet?"). Flat-rate per brand aligns incentives — more branches = more value delivered, same price. Owners think in terms of "my brand" not "my branches."

### Tiers

| Tier | Price | Includes | Target |
|---|---|---|---|
| **Pulse** | RM199/month | Weekly WhatsApp report (all branches), basic dashboard | First-time buyers, 3–5 branches |
| **Insight** | RM399/month | Everything in Pulse + competitor tracking module, monthly strategy summary | 5–10 branches, growth-focused operators |
| **Custom** | RM800+/month | Insight + concierge setup, custom report cadence, Mandarin/BM reports | Groups with 10+ branches or franchisors |

**Annual discount:** 2 months free (pay 10, get 12).

**Why RM199:** Below the psychological RM200 barrier. Cheaper than one hour of a marketing consultant. Cheaper than any Western competitor after currency conversion. Owners can expense it without approval.

---

## 8. 90-Day Go-To-Market Plan

### Month 1 — First 3 Paying Customers

**Goal:** Validate the weekly report format and pricing. Get paid before building anything else.

| Week | Action |
|---|---|
| 1 | Generate manual weekly report for 3 F&B contacts (WhatsApp message, no code). Get feedback on format. |
| 2 | Ask the 3 to pay RM199 for next month. Build the report generator script. |
| 3 | Deliver automated report to 3 paying customers. Collect testimonials. |
| 4 | Onboard 3 more customers from referrals. |

**Target contacts:** F&B operators in Klang Valley known through Hakshan's network — suppliers, fellow association members, nearby chain operators.

**Channels:**
- Direct WhatsApp from founder
- Hakshan social media ("we built the tool we wished existed")
- F&B operator Facebook groups (Malaysia Restaurant & Café Owners)

### Month 2 — Dashboard + 6 Customers

**Goal:** Ship the multi-tenant dashboard. Upsell existing 3 customers to Insight tier.

| Week | Action |
|---|---|
| 5–6 | Build Phase 1 multi-tenancy (config-driven, one app per tenant). |
| 7 | Give Pulse customers dashboard access. Pitch Insight tier upgrade. |
| 8 | First inbound from referrals. Target 6 paying customers total. |

### Month 3 — 10 Customers + First Press

**Goal:** Hit RM2,000 MRR. Get one earned media mention in a Malaysian F&B publication.

| Week | Action |
|---|---|
| 9–10 | Phase 2 multi-tenancy (Supabase). Self-serve onboarding form. |
| 11 | Pitch story to Says.com / Vulcan Post: "The restaurant that built its own brand radar" |
| 12 | 10 paying customers, RM2,000–4,000 MRR. Product-market fit signal: are customers referring others? |

### MRR Targets

| Month | Customers | Avg. Revenue | MRR |
|---|---|---|---|
| 1 | 3 | RM199 | RM597 |
| 2 | 6 | RM280 | RM1,680 |
| 3 | 10 | RM320 | RM3,200 |
| 6 | 25 | RM350 | RM8,750 |
| 12 | 60 | RM380 | RM22,800 |

---

## 9. Success Metrics

### v1 Validation (Month 1–2)
- [ ] 3 paying customers before dashboard is built
- [ ] Weekly report open/engagement rate > 80%
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

## 10. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Google review data hard to automate | High | Use Serpapi/DataForSEO for v1; manual fallback for first customers |
| WhatsApp Business API requires approval | Medium | Use personal WhatsApp for first 10 customers; apply for API concurrently |
| Instagram API token expiry disrupts reports | Medium | Already handled in codebase; add token health monitoring |
| Customers don't see enough value in report alone | Low | Offer first 2 weeks free; report includes one "action needed" callout per week |
| Competitor copies the product | Low | Moat is founder-operator trust and SEA localisation, not technology |

---

## 11. Open Questions (to resolve by end of Month 1)

1. **Google review data source:** Serpapi vs DataForSEO vs Google Business API — evaluate cost and reliability for 10 branches × 10 tenants.
2. **WhatsApp delivery:** Personal WhatsApp (manual, immediate) vs Twilio WhatsApp Business API (requires approval, automated) — start manual, automate at 5+ customers.
3. **Brand name:** "BrandPulse" is a working title. Check trademark availability in MY/SG.
4. **Legal:** Does scraping competitor follower counts violate any platform ToS? Clarify before public launch.
5. **Pricing:** Is RM199 too cheap? Test by anchoring at RM299 in month 2 with new customers.

---

## Appendix: Existing Codebase Assets

The Hakshan app (`app.py`, `data_fetcher.py`) already has:

| Feature | Status | Notes |
|---|---|---|
| Flask web server | ✓ Production | Deployed via Procfile |
| Instagram Graph API | ✓ Live | Needs per-tenant token management |
| Facebook Graph API | ✓ Live | Needs per-tenant token management |
| Competitor social tracking | ✓ Live | Admin-only POST endpoint |
| Google RSS news feed | ✓ Live | Per-brand query strings |
| 24h data caching | ✓ Production | Per-file cache; needs per-tenant isolation |
| Scheduled refresh (APScheduler) | ✓ Production | Runs every 6h for social, daily for news |
| Multi-branch review data | ✓ Static | Needs Google Business API for live data |
| Competitor analysis | ✓ Static | Good enough for v1 |
| Analysis markdown files | ✓ Manual | Phase 2: AI-generated |
| Admin token auth | ✓ Basic | Upgrade to proper auth in phase 2 |

**Reuse strategy:** Don't rewrite. Extract `STATIC_DATA` into tenant config files and add a tenant-routing layer on top. The core data fetching, caching, and API integration is solid.
