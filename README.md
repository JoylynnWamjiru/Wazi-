# Wazi

> Built during the **Democracy & AI Hackathon** — July 4th, 2026
> Hosted by **Mozilla Foundation** & **KamiLimu**

---

## Team

| Name | Role | GitHub |
|------|------|--------|
| Chris Waweru Gichohi | Frontend Engineer and Solutions Architect | [@chriswawerusc](https://github.com/chriswawerusc) |
| Joyline Njeri Wanjiru | Backend and AI Engineer | [@JoylynnWamjiru](https://github.com/JoylynnWamjiru) |

**Team Name:** WAZIRI
**University:** Dedan Kimathi University Of Technology, University of Nairobi

---

## Problem & User

### Problem Statement

> Youth advocates and community members in rural Kenyan counties face significant barriers in tracking local government spending and demanding accountability for public projects, evidenced by the Ethics and Anti-Corruption Commission's 2023 survey finding that 60% of service seekers are dissatisfied with transparency. This problem is primarily caused by the absence of lightweight, mobile-native tools capable of translating lengthy, technical English fiscal PDFs into accessible, local-language summaries.

### Target User

| Dimension | Detail |
|-----------|--------|
| **Primary user** | Youth advocates and members of community-based organisations in rural Kenyan counties |
| **Tech comfort** | Comfortable with WhatsApp text and voice notes; not desktop/web-fluent |
| **Language** | Swahili, Sheng — not formal English |
| **Current workflow** | Relies on word of mouth or local radio for project updates; no way to verify against official records |

### The Specific Gap

1. **What's already there:** International Budget Partnership Kenya's County Budget Transparency Survey, Auditor-General county audit reports, civic tech platforms like Mzalendo and BudgIT
2. **Why it falls short:** published as lengthy, technical English PDFs on desktop-optimised websites — a last-mile delivery and comprehension barrier
3. **The gap we fill:** real-time, grounded Swahili/Sheng summaries delivered conversationally, with source citations, plus a community verification signal for disputed project claims

### Why It Matters

> When rural citizens can't track county spending in a language and channel they actually use, projects stall and funds get diverted without scrutiny. Closing this last-mile gap restores a basic democratic feedback loop between citizen and government.

---

## Run Instructions

### Prerequisites

- Python 3.10+
- An Anthropic API key

### Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/[org]/[repo].git
cd [repo]

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
cp .env.example .env
# Edit .env with your API keys

# 5. Run the project
streamlit run src/app/streamlit_app.py
```

---

## 📁 Project Structure

```
.
├── README.md                       ← You are here
├── docs/
│   └── problem-statement.md        ← Detailed problem breakdown
├── src/
│   ├── main.py                     ← Entry point
│   ├── ingestion/                  ← PDF extraction, embedding & indexing pipeline
│   │   ├── __init__.py
│   │   ├── extract.py
│   │   ├── embed.py
│   │   └── pipeline.py
│   ├── app/                        ← Streamlit chat UI
│   │   ├── __init__.py
│   │   └── streamlit_app.py
│   └── shared/                     ← Config & pipeline contracts
│       ├── __init__.py
│       ├── config.py
│       ├── pipeline_interface.py
│       └── mock_pipeline.py
├── notebooks/
│   └── exploration.ipynb           ← Experiments & prototyping
├── data/
│   └── .gitkeep                    ← Sample / reference data
├── requirements.txt
├── .env.example
├── .gitignore
└── LICENSE
```

---

## Approach & Architecture

```
[Citizen on WhatsApp-style chat] → [Retrieval engine (RAG over county PDFs)] → [Grounded LLM generator, Swahili/Sheng] → [Reply with citation]
```

---

## License

MIT © WAZIRI, 2026
