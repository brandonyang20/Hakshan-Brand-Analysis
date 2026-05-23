# 07 — Scope Review: Design Doc Challenge
**10-Section Critical Review of `06-saas-design-doc.md`**

*Reviewed May 2026 — against actual codebase state*

---

## How to Read This Document

Each section follows the format:

> **Challenge** — What assumption or claim is being questioned
> **Finding** — What the codebase or logic actually shows
> **Fix** — What was changed in `06-saas-design-doc.md`

This document exists to catch problems in the design doc *before* they become bugs in production or promises to customers that can't be kept.

---

## §1 · TL;DR + Problem Statement

**Challenge:** The TL;DR describes a "working prototype" with billing via Stripe and Billplz, implying a near-shippable product. Is this accurate?

**Finding:** The codebase tells a different story:

| Claimed | Actual |
|---|---|
| "Working prototype" | Single-tenant proof-of-concept, hardcoded to Hakshan only |
| "Billed via Stripe and Billplz" | Neither `stripe` nor `billplz` appear in `requirements.txt` |
| Multi-tenant SaaS | Zero tenant routing, zero auth, zero DB — fully single-tenant |
| "Subscription platform" | No subscription logic of any kind exists |

The problem statement itself is accurate (multi-branch operators do have this pain), but the solution framing overstates readiness. Anyone reading the doc at face value would assume billing and multi-tenancy are already built.

**Fix:** TL;DR updated to "single-tenant proof-of-concept; auth, billing, and delivery are greenfield." Subscription billing description qualified as "to be built."

---

## §2 · Why This, Why Now

**Challenge:** Two of the five "Why Now" signals are overstated.

**Finding:**

**Signal 1 — "Working prototype":** As established in §1, the current app is a demo for one brand, not a prototype of the SaaS product. A prototype would have multi-tenancy, auth, and at minimum a report delivery mechanism. The accurate signal is: "The data layer and dashboard UI are proven for one brand; the SaaS infrastructure layers are greenfield."

**Signal 2 — "Zero SEA competition":** Momos (identified in competitive research) explicitly targets multi-location F&B operators in APAC, including Singapore and Malaysia. The original claim is falsifiable. The accurate gap is narrower: no tool exists in the region that is FPX-native, WhatsApp-first, and priced for operators spending RM200–500/month.

**Fix:** Both signals revised with accurate scope. "Zero SEA competition" replaced with "No FPX-native, WhatsApp-first, Malaysian-priced F&B monitoring tool."

---

## §3 · Who We're Building For (ICP)

**Challenge:** Three ICP constraints are either too narrow, inconsistent with the product, or presuppose a capability that doesn't exist.

**Finding:**

**Constraint 1 — "3–10 branches":** The app has no mechanism to add branches dynamically. All branch data (names, addresses, ratings, review counts, map queries) is hardcoded in `STATIC_DATA`. To serve a 7-branch customer, you'd need to manually add 7 branch entries to a config file. This constraint implies a configurability that has not been built.

**Constraint 2 — "Non-franchise":** This exclusion is too blunt. The real distinction is whether the owner controls their own digital brand. A ZUS Coffee franchisee who runs their own Google Business profile has exactly the same problem as an independent chain operator. The relevant exclusion is "corporate-managed digital presence" (i.e., head office runs all socials and reviews centrally), not "franchise" as a legal structure.

**Constraint 3 — "Chinese or multi-ethnic cuisine":** This is a Hakshan-as-customer bias. The platform works identically for a Malay nasi campur chain or an Indian banana-leaf chain. Cuisine type is irrelevant to whether the product delivers value. This constraint should be removed entirely.

**Fix:** Cuisine type constraint removed. Franchise exclusion rewritten to "corporate-managed digital presence." Note added that the branch-config mechanism must exist before serving the 3–10 branch ICP.

---

## §4 · Product Strategy — The Wedge Report

**Challenge:** The flagship product feature — "▲ 18 new reviews this week" — is technically impossible with current architecture.

**Finding:** This is the most critical gap in the document.

To show a weekly review delta, you need:
1. A snapshot of total review count per branch, taken at a fixed time each week
2. A stored history of those snapshots
3. A diff calculation: `this_week_count − last_week_count`

None of this exists:
- There is no nightly or weekly cron job that fetches review counts
- There is no time-series table or file storing historical counts
- Review counts in `STATIC_DATA` are manually hardcoded and never updated programmatically
- There is no Google Business API integration (all review data is static)

The report format shown in the design doc is a mockup of a product that doesn't yet have its most fundamental data pipeline.

**Secondary finding:** Section 4.2 states "After 4 weeks of receiving the report, owner gets a link to the dashboard" — but Section 7 defines the Pulse tier as including the "basic dashboard" from day 1. These two sections directly contradict each other.

**Fix:** Time-series review snapshot service added to Section 6 as a Phase 1 requirement (prerequisite for the wedge). The "4 weeks before dashboard access" gate removed from Section 4.2 — it contradicted Pulse tier definition and introduced unnecessary friction.

---

## §5 · What We Are NOT Building in v1

**Challenge:** Two items in the Out of Scope table are contradicted by other sections of the same document.

**Finding:**

**Contradiction 1:** "Self-serve onboarding — concierge for first 20 customers" is listed as Out of Scope. But Section 9 (Month 3, Week 9–10) explicitly schedules "Self-serve onboarding form" for a 2-week sprint. If self-serve onboarding is being built in Month 3, it is in scope for v1.

**Contradiction 2 (omission):** Authentication is not mentioned anywhere in the Out of Scope table or in the "must build" sections. A multi-tenant SaaS with private customer dashboards and billing state cannot function without customer login. The current app has zero authentication on any route — all endpoints are public. This is not a stretch goal; it is a prerequisite.

**Fix:** Self-serve onboarding moved from Out of Scope to "Phase 2 (Month 3)." Customer auth added explicitly to Section 6 architecture as a Phase 1 requirement with options (magic link, email+password, Supabase Auth).

---

## §6 · Architecture Plan

**Challenge:** Four structural gaps make the architecture plan incomplete as a build guide.

**Finding:**

**Gap 1 — No auth architecture:** The doc describes a SaaS where customers log in to see their brand dashboard. There is no discussion of how login works, what session mechanism is used, or where customer credentials are stored. This is the first thing that needs to be designed before any multi-tenancy work begins.

**Gap 2 — Phase 1 "one app per tenant" is operationally untenable:** 10 customers = 10 separate Heroku/Railway app instances, 10 separate deployment pipelines, 10 sets of env vars to manage, and 10 APScheduler processes running in parallel. At RM199/month revenue, 10 Heroku dynos at ~$7/month each = $70/month COGS before any other infrastructure. This is a bad tradeoff when a single-app config-routing approach (reading tenant config from a JSON file or DB row) is achievable from customer 1 with only marginally more upfront work.

**Gap 3 — Time-series review tracking absent from all three phases:** None of the three phases mentions storing historical review counts. This data pipeline is a prerequisite for the report (§4), yet it doesn't appear in the architecture at all.

**Gap 4 — Serpapi unit economics understated:** The doc presents Serpapi as "~$50/month for 500 requests" without working through the actual request volume. At 10 tenants × 5 branches × 7 daily snapshots = 350 requests/day = 2,450/week. At $50/500 requests, that's ~$245/month at 10 tenants — $24.50/tenant/month COGS. On a RM199/month subscription (~$44 USD), that's 56% COGS just for review data. This is not a viable unit economics model at daily polling frequency; weekly snapshots (7× cheaper) should be the default.

**Fix:** Auth layer added to Phase 1 as required. Phase 1 deployment model revised from "one app per tenant" to "single app with config-driven tenant routing." Review snapshot service added as Phase 1 component. Serpapi unit economics corrected and weekly polling recommended.

---

## §7 · Pricing Model

**Challenge:** The Pulse tier definition contradicts the product strategy, and the Insight tier includes an undefined deliverable.

**Finding:**

**Contradiction:** Section 4.2 implies dashboard access is an upsell that unlocks after 4 weeks of report delivery ("priced separately or included in a higher tier"). Section 7 defines Pulse as explicitly including the "basic dashboard" from day 1. One of these must be wrong. Since the removal of the 4-week gate (fixed in §4), Pulse correctly includes the dashboard — but the tier boundary between Pulse and Insight needs sharper definition.

**Undefined deliverable:** Insight includes a "monthly strategy summary." Who produces this? The doc does not specify. If AI-generated (LLM), there's a per-tenant cost and a quality/hallucination risk. If founder-written, it cannot scale beyond ~10–15 customers before becoming a weekly obligation. This must be defined before Insight is sold.

**Fix:** Pulse vs Insight boundary clarified (Pulse = summary view, Insight = full drill-down + competitor module). "Monthly strategy summary" defined as AI-generated draft with founder review — capped at Insight-tier customers until automation is validated.

---

## §8 · Subscription Billing Architecture

**Challenge:** Three issues that could cause structural churn or introduce a schema bug.

**Finding:**

**Issue 1 — Billplz monthly = manual approval = structural churn risk:** Every month, FPX subscribers must consciously open their banking app and approve the new Billplz bill. This is not a silent auto-charge. A customer who is travelling, ill, or simply missed the notification will lapse. The doc acknowledges this is "not truly silent-auto like Stripe" but does not identify it as a churn risk or propose a mitigation. At scale, this will produce a measurable delta in monthly churn rate between Stripe and Billplz customers. Recommended: default monthly FPX customers toward annual billing (one approval per year) or offer a small discount as incentive.

**Issue 2 — `billplz_bill_id` schema is wrong for monthly billing:** The current schema stores one `billplz_bill_id` per subscription row. But for monthly Billplz billing, each renewal cycle creates a new Bill with a new ID. The field as designed can only ever store the most recently created bill — not the full history, and it gets overwritten each month. Correct approach: store only `billplz_active_bill_id` (updated each cycle) and log full bill history in `payment_events`.

**Issue 3 — No invoice/receipt generation:** Malaysian SMEs require proper tax invoices for accounting and SST compliance. Stripe auto-generates invoices (PDF, email). Billplz does not. For Billplz customers, the platform must generate and email a receipt after each successful payment — either via a custom template or an integration with accounting software. This is a customer support burden if ignored; it will be the first support ticket after the first payment.

**Fix:** Billplz monthly churn risk noted with mitigation (annual default). Schema field renamed to `billplz_active_bill_id` with clarifying note. Invoice generation requirement added for Billplz customers.

---

## §9 · 90-Day Go-To-Market Plan

**Challenge:** Two timeline commitments are unrealistic; one metric is misleading; one critical constraint is entirely absent.

**Finding:**

**Misleading metric — Week 3 "automated report":** The plan states "Deliver automated report to 3 paying customers." There is no automation code. APScheduler is wired for data cache refresh, not report delivery. No WhatsApp API client exists. No report generation script exists. This week's deliverable is a manually written WhatsApp message sent by the founder — calling it "automated" will cause confusion when someone reads this plan in Month 2 and tries to hand it off.

**Unrealistic timeline — Month 3 Phase 2 in 2 weeks:** "Phase 2 multi-tenancy (Supabase). Self-serve onboarding form." requires: Supabase schema design and migration, auth layer (signup, login, session), tenant isolation (each customer can only see their own data), billing webhook handlers for both Stripe and Billplz, and a self-serve onboarding form. Realistically 4–6 engineering weeks minimum, not 2. Compressing this creates half-finished infrastructure that will cause security and data isolation bugs.

**Missing constraint — Founder bandwidth:** The GTM plan is written as if the founder is full-time on the SaaS. Hakshan has 5 restaurant branches, each requiring operational oversight. Running founder outreach (WhatsApp, F&B groups), manually delivering weekly reports, onboarding customers, and shipping Phase 2 code simultaneously is not survivable without dedicated engineering and ops support — none of which is budgeted or mentioned.

**Fix:** Week 3 label changed to "manually delivered report." Month 3 Phase 2 expanded to 4-week sprint, GTM milestone pushed accordingly. Founder bandwidth added as the highest-priority risk in §11.

---

## §10 · Success Metrics + Risks

**Challenge:** One metric is unmeasurable; four significant risks are absent.

**Finding:**

**Unmeasurable metric:** "Weekly report open/engagement rate > 80%." WhatsApp does not expose read receipts programmatically. For personal WhatsApp, you have no signal at all. For WhatsApp Business API (Twilio), you can track message delivery status but not reads. This metric cannot be measured. A measurable proxy: click-through rate on the dashboard link included in each report (requires UTM-tagged links and basic analytics).

**Missing risk 1 — Founder bandwidth (HIGH):** Already described in §9. This is the highest-likelihood risk in the entire plan. An operator running 5 restaurant branches who is also building a SaaS and doing sales will hit a wall, and the SaaS will lose.

**Missing risk 2 — PDPA compliance (HIGH):** The Personal Data Protection Act 2010 (Malaysia) applies to any business collecting personal data (names, phone numbers, email addresses, payment information). The platform will collect all of these. PDPA requires: a published privacy policy, explicit consent at data collection, a data subject access/deletion mechanism, and data breach notification procedures. Non-compliance is not just a fine risk — it can shut down a SaaS business entirely. This must be addressed before the first customer signs up.

**Missing risk 3 — Instagram Business Account requirement (MEDIUM):** The Instagram Graph API (v19.0) only works with Business or Creator accounts. If a tenant's Instagram is a Personal account, their API token will fail silently or return an error. This is a real onboarding blocker that will affect a portion of the ICP. Mitigation: include "Convert to Business Account" in the onboarding checklist; surface a clear error message if the token returns a personal-account error.

**Missing risk 4 — Google Maps scraping legality (MEDIUM):** Using Serpapi or DataForSEO to pull Google Maps review data is in a legal grey area. Google's ToS prohibits scraping their services. These third-party services use various techniques to extract data, some of which Google actively tries to block. This is a technical and legal risk. Mitigation: Google Business Profile API (official, rate-limited, requires per-location OAuth) should be the Phase 2 target; Serpapi is an acceptable v1 workaround with documented risk.

**Fix:** WhatsApp open rate metric replaced with dashboard link click-through rate. Four risks added to §11 risk table. "Founder bandwidth" placed as the first and highest-likelihood row.

---

## Summary: Issues by Severity

| Severity | Issue | Section |
|---|---|---|
| 🔴 Critical | No time-series review tracking — wedge report is unbuildable without it | §4, §6 |
| 🔴 Critical | No auth architecture — SaaS cannot function without customer login | §5, §6 |
| 🟠 High | PDPA compliance not mentioned — legal risk before first customer | §10 |
| 🟠 High | Founder bandwidth not in risk table — highest execution risk | §9, §10 |
| 🟠 High | §4.2 ↔ §7 contradiction: dashboard gate vs Pulse tier definition | §4, §7 |
| 🟡 Medium | Serpapi unit economics broken at daily polling — 56% COGS | §6 |
| 🟡 Medium | Billplz monthly = manual approval = structural churn risk | §8 |
| 🟡 Medium | `billplz_bill_id` schema wrong for monthly billing cycles | §8 |
| 🟡 Medium | "Automated report" in Week 3 is misleading — still manual | §9 |
| 🟡 Medium | Phase 2 in 2 weeks is unrealistic — realistically 4–6 weeks | §9 |
| 🟡 Medium | "Zero SEA competition" overstated — Momos is in APAC | §2 |
| 🔵 Low | Cuisine type ICP constraint is irrelevant — remove | §3 |
| 🔵 Low | "Monthly strategy summary" undefined deliverable | §7 |
| 🔵 Low | WhatsApp open rate is unmeasurable | §10 |
