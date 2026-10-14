# Spike F · Planted-Error Realism

- **Status:** Not started
- **Started:** —
- **Owner:** —
- **Related:** R8 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §10
- **Throwaway code:** none (manual)
- **Budget:** $0

---

## Outcome

*Not started. When the spike ends, write the decision or answer here in 2–4 bullets: what we now know, why, and
what would make us revisit it.*

---

## Question

Do the planted errors in the evaluation set look like errors a real checker would catch?

Specifically:

1. For each planted case, would a PARI checker plausibly see this error in a real drawing?
2. Is each one too easy or too hard compared with real errors?
3. Which kinds of real errors are missing from the set?

## Decision It Unblocks

- **Risk R8:** whether M1 on the planted set can be trusted.
- Which cases to replace or add before the review evaluation (task A5b).

## Time Box

`[1]` hour

- **Rule if the limit is reached:** stop, record what is known, and carry unresolved questions into the risk
  register as open risks.

## Success Criteria

The spike is done when all of the following hold:

- [ ] Every planted case rated, with a reason
- [ ] A list of cases to replace and kinds of error to add
- [ ] R8 re-scored

## Method (planned)

1. Wait until the first planted-error cases exist (task A5a, `data/eval/seeded/`).
2. As the PARI proxy, rate each case *realistic*, *unrealistic* or *too obvious*, with one line of reason.
3. Compare with the issues you found in Spike A: list real kinds of error the set doesn't cover.

---

## Log

*Dated steps: what you ran or did, what happened, the key numbers.*

### Findings

### Implications (input, not the decision)

### Limits of this spike

### Still Open
