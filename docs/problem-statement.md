# Problem Statement — Wazi

> Revised: 2026-08-04 — narrowed to verification-at-point-of-need,
> reframed Nakuru rationale, fixed 5 Whys cascade.

## The Problem

Youth advocates who attend county budget forums on behalf of their communities
cannot independently verify the claims made by county officials against official
audit and budget records — not because the records don't exist, but because they
are locked inside 200-page technical English PDFs published on desktop websites.
The Auditor-General and Controller of Budget document project costs, payment
status, and irregularities in detail, but at the moment a youth advocate needs
that information — standing at a baraza, on a phone, with a community expecting
answers — it is inaccessible. The Ethics and Anti-Corruption Commission's 2023
survey found that 60% of service seekers are dissatisfied with transparency.
This gap is one reason why.

## Root Cause — 5 Whys

1. **Why** can't youth advocates verify county officials' claims against official
   records at community accountability forums?
   → Because they cannot access and comprehend the official budget and audit
     documents that contain the verification evidence.

2. **Why** can't they access and comprehend those documents?
   → Because the documents are published as 200-page technical English PDFs on
     desktop-optimised websites — a format that is unsearchable on a phone,
     incomprehensible to non-accountants, and unavailable in Swahili or Sheng.

3. **Why** are they published in that format, with no citizen-accessible version?
   → Because Kenya's Public Finance Management Act (2012) and County Governments
     Public Finance Management Regulations mandate publication but do not specify
     format, language, summarisation, or accessibility standards.  The legal
     obligation is met by uploading the raw technical PDF.

4. **Why** has this regulatory gap persisted?
   → Because the existing accountability ecosystem — Auditor-General audits,
     Controller of Budget reports, IBP Kenya's County Budget Transparency
     Survey — is designed for oversight institutions and civil society
     organisations, not for direct citizen consumption.  The assumption is
     that intermediaries (journalists, CSOs) will translate for the public.
     Those intermediaries are under-resourced and cannot scale.

5. **Why** has no tool filled the direct-to-citizen verification gap?
   → Because existing civic-tech platforms (Mzalendo, BudgIT) focus on
     digitising and publishing documents rather than transforming them into
     answers — grounded, cited, in the user's language and register — on a
     channel citizens already use at the moment they need them.

**Root cause:** Kenya's fiscal transparency framework stops at document
publication.  There is no last-mile mechanism — regulatory or technological —
that transforms published budget documents into verifiable, conversational,
local-language answers available on a mobile channel at the point of need.

## Why Nakuru County for the MVP

Nakuru County is our starting county — not because its residents have low
literacy (they do not; Nakuru has city status and ~84% adult literacy), but
because the accessibility problem we are solving is about *format and channel*,
not reading ability.  A 200-page technical PDF is inaccessible to a university
graduate standing at a baraza with a phone, just as it is to a farmer with
limited English.  Nakuru offers:

1. **Reliable document corpus.** Nakuru's audit reports and BIRRs are
   consistently published and available on OAG and CoB websites — a
   prerequisite for building and testing a retrieval pipeline.

2. **Active civic ecosystem.** Nakuru has organised youth advocacy groups and
   community-based organisations — the primary users identified below —
   providing a test bed for user feedback and early adoption.

3. **Representative accountability challenges.** Nakuru's audit reports
   document the same accountability issues found across all 47 counties:
   stalled projects, pending bills, procurement irregularities, and
   unsupported expenditure.  Solving for Nakuru solves the pattern, not
   the exception.

4. **Scalable by design.** The source registry uses a county-agnostic URL
   template.  Adding a second county is a configuration change, not an
   architecture change.

## Target User

| Dimension | Detail |
|-----------|--------|
| **Primary user** | Youth advocates (aged 20–35) and members of community-based organisations who serve as information intermediaries between their communities and county government |
| **Context** | Attends county budget forums (barazas), pre-election accountability events, and community meetings on behalf of constituents who cannot attend |
| **Tech comfort** | WhatsApp-native — uses text and voice notes daily; may not own a laptop or have reliable desktop internet |
| **Language** | Conversational Swahili and Sheng in daily communication; can read basic English but struggles with technical fiscal terminology (accounting language, budget classifications) regardless of the language it appears in |
| **Current workflow** | Attends a forum, hears an official claim about a project, cannot verify it in real time, reports back to the community with what was said — not what is true. If the claim is wrong, neither the advocate nor the community finds out until the next Auditor-General's report is published, if at all. |

## The Specific Gap

1. **What's already there:** Auditor-General county audit reports document
   project costs, payment status, pending bills, and irregularities for every
   county.  The Controller of Budget's quarterly BIRRs track actual spending
   against approved budgets.  IBP Kenya's County Budget Transparency Survey
   rates all 47 counties on document publication.  Civic-tech platforms
   (Mzalendo, BudgIT) publish and aggregate these documents.

2. **Why it falls short:** these documents are published as lengthy technical
   English PDFs on desktop websites.  At the moment a youth advocate needs to
   verify a claim — standing at a baraza, on a phone — they are unsearchable,
   incomprehensible, and in the wrong language.  The existing ecosystem stops
   at publication; it does not answer questions.

3. **The gap we fill:** real-time verification of official claims against
   grounded fiscal evidence, delivered conversationally in Swahili or Sheng
   on WhatsApp, with source citations (document name, page number) that the
   advocate can show at the forum.  A community verification signal allows
   citizens to flag disputed answers for human review, creating a feedback
   loop that improves accuracy and builds trust.

## Why It Matters

When a county official tells a baraza that a Kshs 17 million project is
"complete," and the Auditor-General's report shows it was paid for but never
finished, the gap between those two statements is a democratic failure.  It
means public money was spent and the public never found out.  Closing this
verification gap — giving the youth advocate the evidence before they leave
the meeting — restores a basic accountability loop between what officials
claim and what records show.

## Responsible Computing Considerations

- **No PII collected or stored.** Phone numbers are HMAC-SHA256 hashed with
  a secret salt on receipt and never stored.  The database contains only
  cryptographic hashes — a copy of the database cannot identify citizens.
- **Identity separated from content.** Dispute records and chat history live
  in separate database tables with no join path.  The system cannot produce
  a list of who reported what, eliminating the risk of retaliatory
  identification.
- **Human review for disputes.** Community-submitted dispute claims require
  human moderator review before they affect other users.  Unverified claims
  are never surfaced as fact.
- **Curated corpus only.** The retrieval corpus is limited to official sources
  (Auditor-General reports, Controller of Budget BIRRs, county budget
  documents).  The generator answers only from these grounded sources and
  cites them, reducing hallucination and misinformation risk.
- **The trade-off: breadth for trust.** Wazi deliberately answers less than
  a general chatbot.  If the answer is not in the curated corpus, it says
  "sina taarifa za kutosha" rather than guessing.  A wrong number about
  public money is worse than no number at all.

## Sources

- **EACC 2023** — Ethics and Anti-Corruption Commission, *National Ethics and
  Corruption Survey 2023* (60% of service seekers dissatisfied with
  transparency).
- **IBP Kenya / Bajeti Hub, 2019–2025** — *County Budget Transparency Survey*,
  annual assessments of all 47 counties against 10 budget documents.
- **OAG Kenya, ongoing** — Annual county audit reports (Nakuru FY 2023/24,
  FY 2024/25).
- **Controller of Budget, ongoing** — County Budget Implementation Review
  Reports (quarterly).
- **D'Arcy, M. & Cornell, A. (2016)** — "Devolution and corruption in Kenya:
  Everyone's turn to eat?" *African Affairs*, 115(459), 246–273.
- **Gikonyo, W. (2020)** — "Citizen Participation in County Budget Processes:
  A Review of Legal Frameworks and Practice in Kenya." KIPPRA / IBP.
- **KNBS (2019)** — *Kenya Population and Housing Census* (county-level
  literacy data).
- **CIPESA 2025** — Collaboration on International ICT Policy for East and
  Southern Africa.
