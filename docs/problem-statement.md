# Problem Statement — Wazi

## The Problem

Youth advocates and community members in rural Kenyan counties face significant
barriers in tracking local government spending and demanding accountability for
public projects, evidenced by the Ethics and Anti-Corruption Commission's 2023
survey finding that 60% of service seekers are dissatisfied with transparency.
This problem is primarily caused by the absence of lightweight, mobile-native
tools capable of translating lengthy, technical English fiscal PDFs into
accessible, local-language summaries.

## Root Cause — 5 Whys

1. **Why** can't rural citizens track county spending?
   Because the information they need lives in lengthy, technical English fiscal PDFs.

2. **Why** don't they read those PDFs?
   Because the documents are published on desktop-optimised websites and require
   advanced English literacy, stable internet, and a large screen.

3. **Why** is that a barrier?
   Because the target users are WhatsApp-reliant and speak Swahili/Sheng rather
   than formal English, so the content is effectively inaccessible to them.

4. **Why** hasn't the gap been closed already?
   Because existing civic-tech tools (Mzalendo, BudgIT, IBP surveys) still assume
   a desktop, English-literate reader and stop at publishing raw documents.

5. **Why** does no accessible alternative exist?
   Because there is no lightweight, mobile-native pipeline that digests county
   budget PDFs and returns grounded local-language summaries on a channel citizens
   already use.

**Root cause:** There is no lightweight AI-powered WhatsApp tool that digests
county budget PDFs into Swahili/Sheng summaries for rural citizens.

## Target User

| Dimension | Detail |
|-----------|--------|
| **Primary user** | Youth advocates and members of community-based organisations in rural Kenyan counties |
| **Tech comfort** | Comfortable with WhatsApp text and voice notes; not desktop/web-fluent |
| **Language** | Swahili, Sheng — not formal English |
| **Current workflow** | Relies on word of mouth or local radio for project updates; no way to verify against official records |

## The Specific Gap

1. **What's already there:** International Budget Partnership Kenya's County Budget
   Transparency Survey, Auditor-General county audit reports, civic tech platforms
   like Mzalendo and BudgIT.
2. **Why it falls short:** published as lengthy, technical English PDFs on
   desktop-optimised websites — a last-mile delivery and comprehension barrier.
3. **The gap we fill:** real-time, grounded Swahili/Sheng summaries delivered
   conversationally, with source citations, plus a community verification signal
   for disputed project claims.

## Why It Matters

When rural citizens can't track county spending in a language and channel they
actually use, projects stall and funds get diverted without scrutiny. Closing
this last-mile gap restores a basic democratic feedback loop between citizen and
government.

## Responsible Computing Considerations

- **No PII collected or stored.** The tool does not collect or persist any
  personally identifiable information about the citizens who use it.
- **Human review for disputes.** Any community-submitted dispute claim about a
  project requires human review before it is shown to other users; unverified
  claims are never surfaced as fact.
- **Curated corpus only.** The retrieval corpus is limited to curated official
  sources (e.g. Auditor-General reports, county budget documents). The generator
  answers only from these grounded sources and cites them, reducing hallucination
  and misinformation risk.

## Sources

- **EACC 2023** — Ethics and Anti-Corruption Commission, National Ethics and
  Corruption Survey 2023 (60% of service seekers dissatisfied with transparency).
- **IBP Kenya 2023** — International Budget Partnership Kenya, County Budget
  Transparency Survey 2023.
- **CIPESA 2025** — Collaboration on International ICT Policy for East and
  Southern Africa, 2025.
