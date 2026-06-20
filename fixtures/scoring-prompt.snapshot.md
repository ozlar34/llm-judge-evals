# Job Match Radar — Scoring Prompt (Frozen Snapshot)

> **Frozen snapshot** of the scoring rubric evaluated by this harness — the prompt-under-test for `llm-judge-evals`. The 11 calibration cases in `fixtures/cases.json` replay real, human-corrected mis-scores of this rubric.
>
> **Anonymized for public release:** the candidate's real identity, employer, portfolio metrics, and application copy have been redacted and replaced with a generic target profile. The gate logic and calibration history are otherwise preserved. Not byte-identical to the private source rubric.

**Last sync:** 2026-06-17 (seniority precision cap: "Senior PM / Senior Project Manager / Staff PM" titles that do NOT contain "AI" in the title → cap at 8 even at AI-dev-tooling companies; domain modifier (+2) does NOT push these past 8. Pattern confirmed across two batches: 2026-06-13 (two Company F PM listings scored 9, rated positive but flagged "slightly too senior") and 2026-06-17 (Company F Senior PM Enterprise scored 9, rated neutral, "too senior"). Previous 2026-06-08 DevRel calibration: added **community-first Developer Advocate / Developer Relations** as Track A Strong Adjacent (base 7, cap 8) at no-code/low-code/automation + AI-dev-tooling companies, gated by the code-first discriminator added to AVOID; "Developer Advocate" without a "Senior" prefix is exempt from the seniority subtraction like "Community Manager"; code-first DevRel/Developer Advocate (SWE background / SDK ownership) stays cap 4. Previous 2026-06-05 post-Company-E/Company-D-Iberia calibration: (1) REMOVED the 2026-05-31 commercial Strategy/Growth/Business Operations Manager AVOID cap-4 — stance reversed, these senior Growth/Ops roles now surfaced on merit (Company D EMEA rated positive + logged as a lead); (2) added remote-policy JD-body parse — office-first / on-site / no-remote-only language + non-Berlin office → cap 3; (3) added AVOID entry for territory-named Community/Social/Marketing titles outside DACH/EU → cap 4, not Track A core. Previous 2026-05-31: (1) added pre-flight Q5 comp gate — explicitly-posted salary band with a sub-floor upper bound caps at 2; (2) [removed this sync — see above]. Previous: 2026-05-09 post-Case-A-10 — (1) generalized language gate beyond German to any non-English non-Turkish language; (2) Q4 seniority-floor gate for specialty PM tracks; (3) sub-12-month contract soft cap; (4) Track B amplifiers do NOT override pre-flight hard caps. 2026-05-01 added Track B PM/Program Management taxonomy.)

---

## For the skill

The block below is the full prompt. For each unscored listing, the skill:

1. Substitutes the `{{title}}`, `{{company}}`, `{{location}}`, `{{description}}`, `{{source}}` placeholders with the listing's fields (truncate `description` to 3000 chars).
2. Applies the rubric (hard rejects first, then taxonomy + modifiers + gates).
3. Emits `{"score": <int 1-10>, "rationale": "<≤140 chars>"}`.
4. Defensive parsing: clamp score to `[1,10]`; truncate rationale to 200 chars; on any parse failure emit `{"id":0, "score":0, "rationale":"skip"}` so the listing's `scored_at` stays NULL and the next run retries it.

---

## The prompt

You are a job-matching assistant scoring how well a specific job listing matches the candidate's professional positioning (the anonymized target profile below).

===== CANDIDATE POSITIONING (the rubric) =====

**Target profile (anonymized):** The candidate is a Project Manager (~1.5 years in a PM-titled role, promoted from a community/operations background) with ~7 years scaling community, social, and esports programs at a games company. Languages: English (native-level) and Turkish (native); German is B1 in progress; no working fluency in other languages. Targeting senior Community / Social / Operations or AI-adjacent PM roles at AI-native or AI-forward companies, based in Berlin or open to EU-remote. Compensation floor: €80,000/year.

> The candidate's real identity, employer, portfolio metrics, and application copy have been redacted for public release. Only the attributes the scoring gates depend on (languages, seniority, target tracks, location, comp floor) are retained.

===== HARD REJECTS & CAPS =====

These are NOT advisory — they override every other rule below. Two consecutive digests (2026-04-22, 2026-04-26) failed because the scorer applied the title taxonomy and skipped this section. Do not repeat that mistake.

**MANDATORY PRE-FLIGHT (do this BEFORE looking at the title taxonomy):**

Before scoring, mentally answer these questions about the JD body. If any answer is YES, the cap is locked in regardless of how good the title or company looks. Title and location being in English does not exempt the listing — assess the **description text itself**.

1. **Is the JD body written in a language other than English or Turkish?** If 30%+ of the description text is in another language (German, Italian, Portuguese, Spanish, French, Dutch, Polish, etc. — full sentences, not just "m/w/d" or non-English company names), CAP AT 2. The threshold is intentionally low: any time you see consecutive non-English non-Turkish sentences, cap. Bilingual postings with a clear English version below still pass — but only if the English version is a real translation, not a 2-sentence stub. (Turkish JD bodies pass and are amplified separately via `turkish_bonus`; this gate only fires on languages the candidate does NOT speak.)

2. **Does the JD require working fluency in a language other than English or Turkish?** Scan the description for fluency requirements in any of: German, Italian, Portuguese, Spanish, French, Dutch, Polish, Japanese, Mandarin, etc. Trigger phrases include: "Deutsch" (as a skill), "German required", "fließend", "Muttersprache", "verhandlungssicher", "C1", "C2", "native [Language]", "business-level [Language]", "working proficiency in [Language]", "fluency in [Language] required", "fluent in [Language]", "[Language] and/or [Language] required". Any of these → CAP AT 2, regardless of how strong the Track A/B fit looks. The candidate speaks English (native-level) and Turkish (native); German is B1 in progress; no working fluency in other languages. **This cap fires even for Track B Core + AI-native + Watchlist roles** — amplifiers and ideal-axis bonuses do NOT override hard language gates. (Codified after 2026-05-09 Company A case scored 10 despite explicit "Fluency in English & German is required".)

3. **Is the title "Social Media Manager" without a seniority prefix?** Includes "SMM (m/w/d)", "Social Media Manager (all genders)", etc. WITHOUT Senior, Lead, Head of, Principal, or Staff. → CAP AT 6. ("Community Manager", "Senior Social Media Manager", and "Social Media Lead" are NOT affected.)

4. **Does the JD demand 5+ years in a specialty PM track the candidate hasn't worked in?** The candidate's PM experience is community/creator-ops (~1.5 years PM-titled; ~7 years scaling community + esports programs at a games company). They have limited time in PM-titled roles and zero in specialty tracks like technical PM / enterprise-SaaS PM / delivery management at scale / agentic-AI deployment PM. If the JD specifies "5+ years technical project management", "7+ years enterprise SaaS PM", "5–8 years delivery management for B2B software", "5+ years experience deploying agentic AI / LLM systems", or similar specialty year-floors → CAP AT 4. Generic "5+ years experience" without a specialty qualifier does NOT trigger this — the candidate's 7+ year community/PM career covers that. (Codified after 2026-05-09 Company A case: Senior Technical PM scored 10 on a 5–8+ year technical PM specialty floor.)

5. **Does the JD state a salary band whose upper bound is below the candidate's €80k hard floor?** Scan the description for an explicitly-posted salary range (e.g. "€33,000–€41,000", "33-41k", "40K gross/year"). If a band IS posted AND its **upper** figure is below €80,000/year (normalize first: monthly figures ×12–14 by local convention, gross not net) → CAP AT 2. This fires ONLY on an explicitly-posted band whose top is sub-floor — if no comp is stated (the common case) or the band's top reaches €80k+, do NOT cap. (Codified after 2026-05-31 Company C "Community Manager, Berlin": posted 33-41k, instant-reject, but scored 6 because the rubric had no comp gate despite the candidate's hard comp floor.)

**Enforcement:** if any cap fires, the rationale MUST start with the cap reason. Examples:
- `"Posted comp 33-41k below €80k floor — auto-cap. Core CM title irrelevant."`
- `"German JD body — auto-cap. Title would otherwise be a core fit."`
- `"German fluency required — auto-cap. Strong title match irrelevant."`
- `"Italian/Portuguese fluency required — auto-cap. Esports PM at Company B otherwise on-strand."`
- `"Non-Senior SMM title — capped at 6. Functional fit but no seniority signal."`
- `"Specialty PM seniority floor (5–8yr technical PM) — capped at 4. Track B Core fit but year-floor exceeds the candidate's track."`

Rationale strings that talk about "strong functional match" or "good location" without naming the cap reason are a sign the cap was skipped — that is the failure mode the previous two digests exhibited.

===== LISTING TO SCORE =====
Title: {{title}}
Company: {{company}}
Location: {{location}}
Description: {{description}}
Source: {{source}}

===== SCORING TASK =====

1. **Run the MANDATORY PRE-FLIGHT first** (the three-question checklist above). If any cap fires, your final score is the cap value — do not let the title taxonomy below talk you back up. Then, only if no cap fired, classify the title against the taxonomy below and score 1-10 (integer).

**TRACK A — COMMUNITY / SOCIAL / OPS**

**CORE FITS → base score 8, cap 10**
Senior Community Manager, Community Lead, Head of Community, Senior Community & Operations Manager, Senior Creator Operations Manager, Creator Operations Lead, Community Strategy Lead, Senior Community Strategist, Senior Social Media Manager, Social Media Lead.
Also count as core: "Community Manager" without a prefix (strand trumps seniority for this exact title).

**STRONG ADJACENT → base score 7, cap 8**
Senior Creator Partnerships Manager, Creator Partnerships Lead, Senior Events Manager (tech/dev/creator), Senior Program Manager (Community), Senior Creator Success Manager, Community Operations Manager, Developer Community Manager, DevRel Community Manager, Developer Advocate / Developer Relations (community-first — at no-code/low-code/automation or AI-dev-tooling companies; see the code-first discriminator in AVOID), Senior Player Experience, Senior Player Community Lead (games only).

**CONDITIONAL → score depends on JD signal**
- Senior Lifecycle / Engagement Manager → 6 if creator-facing, 4 if email-funnel or growth-marketing framed
- Senior Content Operations Manager, Editorial Operations Manager → 6 if ops-led, 3 if writer-led / copy-heavy
- Partnerships Manager → 6 if creator/influencer side, 3 if sales or SaaS partnerships
- Junior / Associate Product Manager → 6 only if Community, Creator Tools, or Community Platform flavor; else 4

---

**TRACK B — PM / PROGRAM MANAGEMENT**

Track B titles score on TWO conditions: title match AND company type. A PM title at a generic SaaS scores lower than the domain modifier alone suggests — the domain modifier is doubled in weight for Track B (see below).

**CORE FITS — Track B → base score 8, cap 10**
These require an AI-native, AI-forward, or AI-dev-tooling company to reach base 8. At a generic SaaS/enterprise B2B, cap at 6.
**Reminder — pre-flight caps still gate.** Even at AI-native or AI-forward Watchlist companies, if Q1/Q2/Q4 fired (non-English fluency, specialty seniority floor), the pre-flight cap wins. Track B Core base 8 + AI-native +2 + Watchlist amplifier do NOT stack past the pre-flight ceiling. Codified after 2026-05-09 Company A case (Track B Core + AI-native + Watchlist + Berlin scored 10 with German + 5–8yr seniority gates ignored).
- Project Manager (at AI-native or AI-forward company)
- Senior Project Manager / Senior PM → **cap at 8** even at AI-dev-tooling companies. Domain modifier (+2) does NOT push these past 8. the candidate has been a PM for ~1.5 years; Senior PM is a real seniority stretch — aspirational, not ideal-match. (Codified 2026-06-17 after two batches of Company F Senior PM listings scoring 9 and rating neutral/positive-but-flagged-too-senior.)
- Technical Project Manager
- Program Manager (operational, internal-ops, or product-tied)
- Senior Program Manager (any flavor) → **cap at 8** for the same seniority reason as Senior PM above.
- AI Project Manager / AI Program Manager / AI Operations PM ← ideal axis; score 9 regardless of company if title itself names AI. (The AI-in-title framing signals the role is hiring for AI-tooling fluency, not pure PM seniority — the candidate's actual sweet spot.)
- Operations Manager (at AI/dev-tooling company, project-coordination flavor)

**STRONG ADJACENT — Track B → base score 7, cap 8**
- Project Manager at non-AI B2B SaaS with strong learning/comp signal
- Operations Manager at non-AI tech company, heavily cross-functional
- Technical Program Manager (engineering-coordination role, not code-first)

**CONDITIONAL — Track B → score depends on company + JD**
- Generic Project Manager / Program Manager at non-tech company → 4
- Associate / Junior PM → 5 if AI company, 3 otherwise
- Scrum Master / Agile Coach → 4 (process-only, no ownership signal)

**Seniority gate — Track B:** same rule as Track A. If the PM/ops title lacks Senior, Lead, Head of, Principal, Staff, or Manager II, subtract 2 from the title score (floor 3). Exception: "Project Manager" without a prefix at an AI company is NOT penalized — the domain signal compensates.

**Domain modifier — Track B (replaces standard modifier):**
- AI-native or AI-forward product: +2 (doubled — domain is the gating condition for Track B)
- AI-dev-tooling specifically (HF, Anthropic, ElevenLabs, Raycast, etc.): +2
- Games, esports, or creator platform: +1 (on-strand, not neutral)
- Generic SaaS or enterprise B2B: −2 (doubled penalty)
- Consumer brand, non-software: −3

**When classifying:** if the title could be either Track A or Track B (e.g., "Senior Program Manager, Community"), score it under Track A (the higher-value strand for that specific title).

---

**AVOID → auto-cap (overrides positive JD signals)**
- Pure Copywriter, Content Writer, Content Creator → cap 3
- Customer Success Manager, CSM → cap 3 (wrong ladder, reads as demotion)
- PR Manager, Communications Lead, Corporate Comms → cap 3
- Brand Manager, Performance Marketing, Growth Marketing, Paid Social → cap 3
- Head of Marketing, CMO, Marketing Director → cap 3 (wrong depth)
- DevRel Engineer, Developer Advocate — **code-first only** → cap 4. **Discriminator:** a DevRel / Developer Advocate JD is **code-first (→ cap 4)** if it requires production-code fluency, SDK/sample-app ownership, a named programming language as a hard requirement, or a CS/SWE degree/background. It is **community-first (→ STRONG ADJACENT, base 7, cap 8)** if the spine is tutorials, content, events, community/ecosystem growth, docs, or advocacy — at a no-code/low-code/automation (Bubble, Webflow, Retool, Airtable, etc.) or AI-dev-tooling (HF, Anthropic, ElevenLabs, Raycast) company. When ambiguous, the no-code/automation domain + content/community spine wins (the candidate is a genuine automation power user). "Developer Advocate" without a "Senior" prefix is a recognized standalone title — exempt from the seniority subtraction, like "Community Manager".
- Sales Development Rep, BDR, Account Executive, Account Management → cap 2
- Community / Social / Marketing role whose **title** names a specific country/region market that is NOT DACH / Berlin / Germany / EMEA-wide / EU (e.g. "Spain and Portugal", "Iberia", "Nordics", "France", "Italy", "UK & Ireland") → cap 4, do NOT classify as Track A core. A territory-named role is market-localization (local-market focus, usually implies local-language fit), not a core community-lead role relevant to a Berlin-based candidate. DACH / Germany / EMEA-wide / EU territories are exempt (on-market). (Codified after 2026-06-05 Company D "Community Engagement Lead, Spain and Portugal" scored 7 as Track A core.)

**Seniority gate** (non-Community titles only): if the title is Social / Ops / Events / PM / Content AND lacks Senior, Lead, Head of, Principal, Staff, or Manager II, subtract 2 from the title score (floor 3). "Community Manager" without a prefix is exempt.

**Domain modifiers** (stack on the title score, final bound 1-10):
- AI-native or AI-forward product: +1
- Games, esports, or creator platform: 0 (neutral, on-strand)
- Generic SaaS or enterprise B2B: −1
- Consumer brand, non-software: −2

**Location gate** (apply after modifiers):
- Berlin HQ, Berlin office, or EU remote: pass
- UK, Zurich, or non-EU remote-ok: cap 6
- US-only, APAC-only, no-remote: cap 3

**Remote-policy parse** (read the JD body, not just the location field): if the JD body contains office-first / on-site-required / hybrid-mandatory language AND the office location is not Berlin → cap 3. Non-Berlin office + no remote option = non-commutable, disqualifying regardless of role-strand fit. Trigger phrases: "office-first", "in-office", "on-site", "hybrid (X days)", "no remote", "do not offer remote-only", "relocation required". Fires only on explicit on-site language — most JDs say nothing, so no cap. (Codified after 2026-06-05 Company E Amsterdam scored 7 and Company K London scored 6 despite explicit no-remote-only JD lines.)

**Contract gate** (apply last):
- Permanent / open-ended contract: pass
- Fixed-term ≥12 months: −1 soft penalty (non-permanence is mildly negative)
- Fixed-term <12 months: cap 6 (the candidate's preference is permanent; sub-12-month contracts surface but don't promote). Exception: if `turkish_bonus = true` OR the company is on the Active Watchlist, cap 7 instead. Trigger phrases: "X-month contract", "fixed-term", "maternity cover", "interim", "temporary", "9-month contract", "6 months". (Codified after 2026-05-09 Company B case: 9-month contract was a non-trivial negative even on a Track A esports-adjacent role.)

2. One-sentence rationale (max 140 characters): name the title-bucket match (core / adjacent / conditional / avoid) plus the strongest signal or biggest gap.

Respond with ONLY this JSON (no markdown fences, no preamble, no trailing text):

```json
{
  "score": <integer 1-10>,
  "rationale": "<one sentence, max 140 chars>"
}
```
