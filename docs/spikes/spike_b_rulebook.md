# Spike B · Rulebook Extraction

- **Status:** Not started
- **Started:** —
- **Owner:** —
- **Related:** R2 · A3 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §10
- **Throwaway code:** `spikes/spike_b_rulebook/`
- **Budget:** $0 (an LLM may help draft, Qwen only, ≤ $`[1]`)

---

## Outcome

*Not started. When the spike ends, write the decision or answer here in 2–4 bullets: what we now know, why, and
what would make us revisit it.*

---

## Question

How much of the client's checklist and WP guidelines can become checkable rules, and of which kind?

Specifically:

1. Which rules can be extracted from `Check List.docx` and each file in `WP Specific Guidelines/`?
2. For each rule: is it a **code** check, a **lookup** in a table, or an **LLM** judgement?
3. What parameters does each rule need (e.g. an approved-materials list, a tolerance table, a stock-size table)?
4. Which checklist categories have no source material at all?

## Decision It Unblocks

- **The `Rule` data contract** (task A2): which fields the rules actually need.
- **The standards reviewer's design:** how much is lookup versus LLM.
- **Open item O3:** a first draft for PARI to correct.
- Validates assumption A3.

## Time Box

`[4]` hours

- **Rule if the limit is reached:** stop, record what is known, and carry unresolved questions into the risk
  register as open risks.

## Success Criteria

The spike is done when all of the following hold:

- [ ] `[20]` draft rules in the `Rule` format, each with check type and source
- [ ] Counts per category and per check type
- [ ] Each guideline table loaded by a script, or the reason it can't be
- [ ] A list of checklist categories with no source material
- [ ] A list of fields the `Rule` contract is missing

## Method (planned)

1. Read the checklist and each guideline file; list candidate rules with the document and section they come from.
2. Write `[20]` of them as YAML in the `Rule` shape (use the A2 shape if merged, otherwise the proposal in the Oct 06 update; record any field that doesn't fit).
3. Where a guideline is a table (raw-material sizes, US–India equivalents), write a small loader in `spikes/spike_b_rulebook/` to prove the table can be read reliably.
4. Count rules per category and per check type.

---

## Log

*Dated steps: what you ran or did, what happened, the key numbers.*

### Findings

### Implications (input, not the decision)

### Limits of this spike

### Still Open
