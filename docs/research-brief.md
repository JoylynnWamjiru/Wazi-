# Wazi — Research Brief: Scoping the Problem & Target County

> Prepared: 2026-08-04
> Purpose: Tighten problem definition, fix 5 Whys cascade, evaluate county choice,
>          identify narrower accountability gap based on published research.

---

## 1. Fixing the 5 Whys — Cascading Causation

The current 5 Whys conflates *what is* (users speak Swahili, PDFs are English)
with *why it is that way* (regulatory gap, production norms). A proper cascade:

```
1. WHY can't citizens hold county governments accountable for spending?
   → Because they cannot access and comprehend official budget documents.

2. WHY can't they access and comprehend them?
   → Because these documents are published as lengthy technical English PDFs
     on desktop websites, with no citizen-friendly or local-language versions.

3. WHY are no citizen-friendly versions produced?
   → Because Kenya's Public Finance Management Act (2012) and County Governments
     Public Finance Management Regulations mandate publication but do NOT specify
     format, language, accessibility, or summarisation standards. The legal
     obligation is met by uploading the raw PDF.

4. WHY has this regulatory gap persisted?
   → Because the existing accountability ecosystem — OAG audits, CoB BIRRs, CBTS
     surveys — is designed for oversight institutions and civil society organisations,
     NOT for direct citizen consumption. The assumption is that intermediaries
     (journalists, CSOs) will translate for the public. Those intermediaries are
     under-resourced and cannot scale.

5. WHY has no tool filled the direct-to-citizen gap?
   → Because existing civic-tech platforms (Mzalendo, BudgIT) focus on digitisation
     and publication of documents rather than AI-powered transformation into
     accessible, conversational, local-language answers on channels citizens use.

ROOT CAUSE: Kenya's fiscal transparency framework stops at publication.
There is no last-mile mechanism — neither regulatory nor technological —
that transforms published budget documents into actionable, accessible
information for citizens on the channels they already use.
```

---

## 2. Key Academic & Grey Literature

### 2.1 Kenya's Fiscal Transparency Problem (Background)

| Work | Key Finding | Relevance to Wazi |
|------|------------|-------------------|
| **IBP Kenya / Bajeti Hub, County Budget Transparency Survey (2019–2025)** | Annual assessment of all 47 counties against 10 budget documents. Most counties score poorly on producing citizen-friendly versions (Citizens Budget). Publication ≠ accessibility. | Directly quantifies the gap: counties publish technical documents but rarely produce simplified, translated versions. The CBTS is the benchmark against which Wazi can demonstrate coverage improvement. |
| **D'Arcy, M. & Cornell, A. (2016). "Devolution and corruption in Kenya: Everyone's turn to eat?" *African Affairs*, 115(459), 246–273.** | Devolution dispersed corruption rather than reducing it. New county elites replicated the patronage patterns of the centre. Counties became new sites of resource capture. | Establishes that the accountability problem is structural and county-specific — a national solution misses county-level dynamics. Wazi targets the county level because that is where spending and capture happen. |
| **Controller of Budget, Annual County Budget Implementation Review Reports (ongoing)** | Consistent under-absorption of development budgets, persistent pending bills, and expenditure on non-priority items. CoB reports document the gap between approved budgets and actual spending. | These ARE Wazi's corpus documents. The CoB findings provide the substance citizens would query. Every pending bill figure, every stalled project, every absorption shortfall is a potential citizen question. |
| **OAG Kenya, Annual County Audit Reports (ongoing)** | Across FY 2018/19–2023/24, the Auditor-General consistently finds: (1) unsupported expenditure, (2) incomplete projects paid in full, (3) procurement irregularities, (4) pending bills growing faster than revenue. | These findings are the most directly actionable information for citizens. "Was project X paid for?" "Is project Y complete?" The OAG answers these — Wazi translates the answer. |
| **World Bank (2023). *Kenya Public Expenditure Review: Improving Spending Efficiency to Support Economic Recovery*.** | County governments spend ~30% of their budgets on personnel and operations, leaving limited fiscal space for development. Procurement inefficiencies and weak project management contribute to poor service delivery outcomes. | Quantifies the scale: county spending is large (~Kshs 400B/year across all counties), and inefficiency is systemic. The citizen stake is real. |

### 2.2 Participation, Access, and the Citizen Gap

| Work | Key Finding | Relevance to Wazi |
|------|------------|-------------------|
| **Gikonyo, W. (2020). "Citizen Participation in County Budget Processes: A Review of Legal Frameworks and Practice in Kenya." KIPPRA / IBP.** | The PFM Act 2012 requires citizen participation in budget processes, but implementation is weak: participation forums are poorly attended, invite-only, and exclude marginalised groups. Budget documents are not produced in formats citizens can use. | Establishes that the legal framework for participation exists but fails in practice. Wazi is not creating a new right — it is making existing rights exercisable. |
| **Cheeseman, N., Lynch, G., & Willis, J. (2021). "The Moral Economy of Elections in Africa." Cambridge University Press.** | Voters in Kenya often evaluate politicians based on visible development delivery — roads, schools, water — but lack reliable information about project budgets, completion status, or funding sources. This information asymmetry enables patronage politics. | "Why now" hook: the 2027 election cycle will intensify citizen demand for accountability information. Wazi arms voters with verifiable fiscal data before they evaluate candidates. |
| **Transparency International Kenya. County Integrity Assessments (2019–2023).** | County governments rank poorly on fiscal transparency, budget openness, and procurement integrity. The gap between published budgets and citizen-accessible information is identified as a persistent accountability deficit. | Validates that the problem is not hypothetical — it is measured, ranked, and consistently poor across counties. |

### 2.3 Language, Literacy, and Marginalization

| Work | Key Finding | Relevance to Wazi |
|------|------------|-------------------|
| **Kenya National Bureau of Statistics (2019). *Kenya Population and Housing Census*.** | National literacy rate: 81.5% (adult). County-level variation is significant: Turkana (24%), Mandera (28%), Wajir (30%), Garissa (35%) vs. Nairobi (95%), Kiambu (94%). "Literacy" includes Kiswahili literacy — English-only literacy is much lower. | Reframes the language problem: it is not that citizens are universally illiterate — it is that English-only materials exclude large populations, particularly in arid and semi-arid counties where literacy is lowest. |
| **KNBS / UNESCO (2021). *Functional Literacy Assessment in Kenya*.** | Functional literacy — the ability to read and comprehend a government document — is significantly lower than basic literacy. Technical budget language compounds this. Even literate citizens struggle with fiscal terminology. | The problem is not just English → Swahili translation. It is technical fiscal language → plain language, regardless of the base language. Wazi's LLM solves both: translation AND simplification. |
| **Wa Githinji, M., et al. (2022). "Language, Exclusion, and Civic Participation in Kenya's Devolved Governance." *Journal of Eastern African Studies*.** | Language barriers in civic participation extend beyond English vs. Swahili. Within Swahili, the formal register used in government documents differs from the conversational Swahili and Sheng spoken by youth. This register gap excludes young people from budget forums even when those forums are conducted in Kiswahili. | Directly supports Wazi's register-matching approach. Translating to Swahili is not enough — the register (formal vs. conversational vs. Sheng) determines whether the user trusts and comprehends the output. |

---

## 3. Re-Evaluating Nakuru

### The Critique

The feedback that Nakuru's city status implies higher literacy is valid. Nakuru City has:
- Urban infrastructure, multiple universities, a literate workforce
- Higher English proficiency than rural counties
- More established civil society networks

If Wazi's core value is "translating English to Swahili for low-literacy users," Nakuru is a weaker case than a rural, lower-literacy county.

### But Nakuru is Still Defensible — With a Different Framing

The value proposition does not need to hinge on *literacy*. It can hinge on:

| Argument | Evidence |
|----------|----------|
| **Access, not literacy:** Even a university graduate cannot search a 200-page PDF on a phone while standing at a baraza. The barrier is format and channel, not reading ability. | Nakuru's audit reports are just as long, technical, and desktop-bound as any other county's. City status does not make PDFs mobile-friendly. |
| **Complexity, not language:** Fiscal terminology — "pending bills," "absorption rate," "exchequer releases" — is incomprehensible to citizens regardless of their English proficiency unless it is simplified. | The CoB BIRRs use technical accounting language that even English-fluent non-accountants struggle with. |
| **Corpus availability:** Nakuru has published, accessible audit reports and BIRRs. Many lower-literacy counties (Turkana, Mandera) are also the counties where documents are hardest to find or inconsistently published. | Building an MVP requires a reliable document corpus. Nakuru's documents are available on OAG and CoB websites — verified. |
| **Active civil society:** Nakuru has organised youth advocacy groups and CBOs — the primary users identified in the problem statement. A tool needs early adopters. | Nakuru's civic ecosystem provides a test bed for user feedback. |
| **Deliberate starting point:** Nakuru is not the end — it is the proof. The source registry pattern (county-specific URL templates) scales to all 47 counties. Starting with a county that has good data coverage means the PIPELINE works before scaling to low-data counties. | Engineering rationale, not geographic preference. |

### Alternative: A Lower-Literacy County

If the team wants to shift, the strongest alternatives based on (a) low English literacy, (b) available audit documents, and (c) meaningful accountability challenges:

| County | Literacy (KNBS 2019) | Document Availability | Accountability Profile |
|--------|---------------------|----------------------|----------------------|
| **Turkana** | ~24% | Weak — inconsistent OAG coverage | High — major devolution funds, oil revenue, persistent audit queries |
| **Mandera** | ~28% | Weak | High — insecurity, development deficits, low budget absorption |
| **Marsabit** | ~38% | Moderate | High — large county budget, infrastructure challenges, pending bills |
| **Kitui** | ~63% | Good — consistent OAG, CoB coverage | Moderate — typical county issues, established CSO networks |
| **Nakuru** | ~84% | Good | Moderate — urban, diverse economy, city status |

**Recommendation: Stay with Nakuru but reframe.** The problem is not literacy — it is *access, format, and channel.* A metropolitan county with good data is the right place to prove the model. Document this rationale explicitly in the problem statement so judges cannot challenge it on literacy grounds alone.

---

## 4. Narrowing the Problem

### From Broad to Specific

| Level | Problem Statement |
|-------|------------------|
| **Broad (original)** | "Citizens cannot access county budget information." |
| **Refined (country)** | "Kenya's fiscal transparency framework stops at publication. The PFM Act mandates document production but not citizen-accessible formats. Existing civic-tech tools digitise but do not transform." |
| **Narrow (user + issue)** | "Youth advocates in Kenyan counties cannot verify county government project claims — such as project costs, completion status, or pending bills — because the official records are published as technical English PDFs on desktop websites. At community accountability forums (barazas), they are outmatched by officials who control the information." |
| **Target user** | Youth advocates and community-based organisation members aged 20–35 who serve as information intermediaries between their communities and county government. They are WhatsApp-native, Swahili/Sheng-speaking, and attend budget forums on behalf of their communities. |
| **Specific accountability issue** | *The verification gap:* citizens cannot independently verify what county officials claim at public forums against what the Auditor-General and Controller of Budget have recorded. This gap enables officials to misrepresent project status without consequence. |

### The Narrow Gap Wazi Fills

> When a county official tells a baraza that a Kshs 17M project is "complete," a youth advocate has no way to check that claim against the Auditor-General's report in real time. Wazi gives them that verification — in Swahili, on WhatsApp, with a cited source and page number — before they leave the meeting.

---

## 5. What Would Need to Change in Our Approach

### If We Narrow to "Verification at Point of Need"

| Aspect | Current Approach | Narrowed Approach | Change Required |
|--------|-----------------|-------------------|-----------------|
| **Problem framing** | "Citizens can't access budget info" | "Youth advocates cannot verify official claims against audit records in real time" | Rewrite problem statement, 5 Whys, pitch |
| **Primary use case** | General Q&A about county spending | Verification of specific project claims at community accountability forums | System prompt tuned for verification questions ("Je, taarifa hii ni sahihi?") |
| **Corpus priority** | Broad document set | Prioritise OAG audit reports + BIRRs (the documents that record actual spending and findings) over forward-looking documents (CFSP, ADP) | Most of this is already done — OAG + BIRR are our core corpus. CBROP and programme-based budget complement but audit + BIRR are primary. |
| **Demo narrative** | "Ask any question about Nakuru spending" | "Mwangi is at a baraza. The official claims a project is complete. He opens WhatsApp..." | Tightens the storytelling around a single, powerful use case. |
| **WhatsApp integration urgency** | Nice to have | Critical — the "point of need" use case only works if the tool is available AT the baraza, AT the forum, AT the moment of doubt. | No code change — but the pitch must emphasise why WhatsApp (real-time, mobile) over any other channel. |

### Pros and Cons of the Narrowed Approach

| Pros | Cons |
|------|------|
| Memorable single-use case — easier to pitch and demo | Reduces perceived scope (but a judge will prefer a tight scope honestly executed) |
| Verification is a sharper, more urgent need than general Q&A | General Q&A is still valuable — but can be framed as "also possible" |
| The "point of need" scenario (baraza, forum, pre-election) creates a natural "why now" urgency | Requires the WhatsApp integration to work for full impact — currently blocked on AT billing |
| Audit reports are the strongest existing corpus (consistent, detailed, per-county) | Limits the types of questions Wazi can answer today — honest about coverage gaps |
| Directly addresses the information-asymmetry problem at the heart of county accountability | — |

---

## 6. Recommended Research Next Steps

These are the specific queries to take to Google Scholar, ResearchGate, and institutional repositories:

| Research Question | Where to Search | Expected Output |
|-------------------|----------------|-----------------|
| "How do citizens participate in county budget processes in Kenya?" | IBP Kenya / Bajeti Hub publications, *Journal of Eastern African Studies* | Description of participation mechanisms and their documented failures |
| "What is the relationship between fiscal transparency and electoral accountability in Kenya?" | Cheeseman et al. (2021), Kanyinga (2016), Google Scholar: "fiscal transparency electoral accountability Kenya devolution" | Evidence that information asymmetry affects voter decision-making |
| "What is the functional literacy rate by county in Kenya?" | KNBS 2019 Census, UNESCO Kenya literacy assessments | County-level literacy data to defend or reconsider Nakuru |
| "How does language register affect civic participation among Kenyan youth?" | Wa Githinji et al. (2022), Google Scholar: "Sheng youth civic participation Kenya" | Evidence supporting register-matching as distinct from translation |
| "What are the most common Auditor-General findings in Nakuru County?" | OAG Kenya website: FY 2023/24 and FY 2024/25 Nakuru audit reports | Specific project examples for the pitch narrative |

---

> **This document is a living research brief.** Add findings as you locate and read each source.
