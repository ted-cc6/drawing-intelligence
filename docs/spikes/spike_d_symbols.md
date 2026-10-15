# Spike D · Symbol Recognition

- **Status:** Not started
- **Started:** —
- **Owner:** —
- **Related:** R5 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §10
- **Throwaway code:** `spikes/spike_d_symbols/`
- **Budget:** ≤ $`[1]`, Qwen only

---

## Outcome

*Not started. When the spike ends, write the decision or answer here in 2–4 bullets: what we now know, why, and
what would make us revisit it.*

---

## Question

How reliably does the vision model read symbols that exist only in the image — GD&T frames, datums, surface-finish and weld symbols?

Specifically:

1. On `[10]` drawings, how many symbols of each type are really there (counted by hand)?
2. How many does the model report that aren't there (phantoms), and how many does it miss?
3. Does thinking on vs off change this?
4. Can any symbol type be found from PDF vector paths or text instead of the image?

## Decision It Unblocks

- **Risk R5:** whether symbol-based findings can be *fail* or only *warnings to confirm*.
- **US-4.2, US-4.3:** how the GD&T and weld checks are built.
- The understanding model default (task A1) gets a symbol-accuracy number.

## Time Box

`[3]` hours

- **Rule if the limit is reached:** stop, record what is known, and carry unresolved questions into the risk
  register as open risks.

## Success Criteria

The spike is done when all of the following hold:

- [ ] Hand counts for `[10]` drawings, per type
- [ ] Phantom and miss rates per symbol type and thinking setting
- [ ] R5 re-scored (trigger: phantom rate above `[10]`%)
- [ ] A recommendation: which symbol types can support *fail* findings

## Method (planned)

1. Pick `[10]` drawings: the 4 samples plus `[3]` prismatic and `[3]` round parts that visibly contain symbols.
2. Count symbols by hand, per type and per page. Coordinate with whoever owns `data/labels/symbol_counts.json` (task A1) — keep your counts in `spikes/spike_d_symbols/results/` and don't edit `data/labels/` yourself.
3. Run understanding with `qwen3-vl-plus` (thinking off and on) through the package functions; save the replies in `out/`.
4. Compare per type: correct, phantom, missed.

---

## Log

*Dated steps: what you ran or did, what happened, the key numbers.*

### Findings

### Implications (input, not the decision)

### Limits of this spike

### Still Open
