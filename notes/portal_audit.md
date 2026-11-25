# Moss Portal UX Audit (`portal.usemoss.dev/inference`)

> **Capture Source:** Onboarding flow screenshots (`notes/portal_onboarding_ux.pdf` / `notes/portal_onboarding_ux.png`)

## Onboarding Flow Walkthrough (5 Steps Observed)

1. **Step 1 — Use-Case Selection ("What are you building with Moss?")**
   - Options: *Voice AI*, *AI Agents & Copilots*, *In-App Search*, *Edge / On-Device AI*, *Something else*.
   - Includes a skip escape hatch: *"Just exploring? See Moss in action ->"*.
2. **Step 2 — Attribution ("How did you hear about us?")**
   - Marked optional with 8 radio/card choices (*AI assistant*, *Google search*, *Friend or colleague*, *LinkedIn or X*, *Event or hackathon*, *Moss newsletter*, *Moss webinar*, *Moss blog*).
3. **Step 3 — Runtime/SDK Selection ("Let's set up retrieval for your voice agent")**
   - Tailored headline based on Step 1 selection.
   - Pre-creates a sample index before asking the user to upload data.
   - Options: *TypeScript / Node*, *Python*, *Other (REST API and other SDKs)*.
4. **Step 4 — Instant Playground ("Your Moss setup is ready")**
   - Provisions `voice-agent-context` with 50 sample documents.
   - Live browser-side search demo: query `"customer wants a refund"` returned 3 ranked hits (`0.94`, `0.79`, `0.71`) in **`1.0 ms`** (*"Searched 50 documents, right in your browser."*).
   - CTA: *"Use my own data ->"*.
5. **Step 5 — Data Ingestion ("Ready to use your own data?")**
   - Two ingestion paths: **Website / URLs** (crawl & build index) or **Documents** (PDF & DOCX, drag & drop, up to 20 files, 50 MB each).
   - Editable index name (`my-documents`), plus *"Keep sample data for now"* fallback.
6. **Step 6 — Connect SDK ("You're ready to connect Moss — Voice AI + Python")**
   - Displays `pip install moss`, `MOSS_PROJECT_ID`, and a one-time `MOSS_PROJECT_KEY` (*"Save this key now. You won't see it again."*).
   - Shows a copy-paste `search.py` snippet using `MossClient` (`await client.load_index("Company factuals")` + `await client.query(...)`) with a note that `"Company factuals is still building"`.
   - CTA: *"Go to dashboard"*.

## Initial UX Observations (for One-Pager Section 1)

### What Works Well
- **Immediate "Aha" moment in Step 4:** Instead of dropping new users onto an empty dashboard with API keys and a blank index, Moss seeds 50 domain-relevant sample docs and runs an interactive `1.0 ms` in-browser semantic search right inside onboarding.
- **Tailored copy & personalized snippet:** Step 1 (*Voice AI*) and Step 3 (*Python*) carry all the way into Step 6's ready-to-run `search.py` snippet populated with your exact project ID/key and your newly created index name (`"Company factuals"`).
- **Low-friction document ingestion:** Supporting direct PDF/DOCX drag-and-drop (up to 20 files x 50 MB) and URL crawling in Step 5 eliminates boilerplate ETL before trying retrieval.
- **Good security hygiene:** One-time display of `MOSS_PROJECT_KEY` with an explicit warning (*"Save this key now. You won't see it again."*) and a TypeScript/Python toggle right above the snippet.

### Friction / Areas to Probe & Improve
- **Inference & Tasks APIs are invisible in the onboarding flow:** Even when signing up specifically through `portal.usemoss.dev/inference`, all 6 onboarding steps focus exclusively on `MossClient` retrieval (`load_index` / `query`). There is no mention of `MossInference`, `responses.create`, `tasks.run`, available models, or the `$10` credit balance until after clicking *Go to dashboard*.
- **No explicit skip-all button at Step 1 for returning/API-first engineers:** Power users who already have scripts in mind still step through attribution (Step 2) and language choice (Step 3) unless they click *"Just exploring? See Moss in action"*, which isn't clearly labeled as "Skip to dashboard".
- **Index build status & chunking transparency:** Step 5 lacks chunk-size/OCR/metadata options, and Step 6 only says `"is still building... usually within a few minutes"` without a live progress indicator or webhook/ready state before running `search.py`.
- **OS-neutral env snippet:** Step 6 outputs `export VAR=...` (bash/zsh only), which fails copy-paste on Windows PowerShell (`$env:VAR=...`).
- **2FA phone number validation bug (Auth / UX):**
  - **Observed:** During 2FA setup/verification, entering a malformed phone number still displays `"OTP sent"` instead of rejecting the invalid format upfront.
  - **Likely impact (inferred):** Users who mistype a number may never receive an OTP and get stuck, and invalid numbers could trigger wasted SMS carrier attempts.
