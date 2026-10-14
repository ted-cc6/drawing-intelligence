"""Spike A: Monte Carlo estimate of manual vs assisted check time per drawing (stdlib only, $0).

Run: uv run python spikes/spike_a_user_validation/time_model.py
Every unit time is a triangular distribution (min, mode, max) in seconds unless noted; see
docs/spikes/spike_a_user_validation.md for where each value comes from.
"""

import random
import statistics

RUNS = 100_000
SEED = 13
TITLE_BLOCK_FIELDS = 14
LOOKUPS = 3

# Manual check
OVERHEAD_MIN = (1, 2, 4)  # minutes: open files, orient, read the title block once
PER_DIMENSION = (8, 15, 40)
PER_TB_FIELD = (3, 8, 20)
PER_NOTE = (4, 10, 30)
PER_LOOKUP = (30, 60, 180)
HOLISTIC_MIN = (2, 4, 10)  # minutes: views, GD&T, datums, manufacturability, design intent
FINDINGS = (1, 3, 6)  # real issues on a drawing
PER_WRITE_UP = (30, 45, 90)
CHECKER_SPEED = (0.75, 1.0, 1.5)  # multiplier shared by every step: one checker is uniformly faster or slower

# Assisted check (with the tool's report)
RECALL, PRECISION = 0.8, 0.7  # discovery M1 and M2 targets
READ_SUMMARY_MIN = (0.5, 1, 2)
PER_REPORTED_FINDING = (15, 30, 90)  # go to the marked location, confirm or reject
SPOT_CHECK_MIN = (2, 5, 10)  # glance over what the review did not cover
PER_ACCEPTED_EDIT = (10, 20, 40)  # adjust the comment or correction in the report row

SCENARIOS = {  # name: (dimensions, notes), medians from results/item_counts.csv
    "Cam Plate": (21, 16),
    "Sample median": (20, 17),
    "Round-part median": (16, 32),
    "Prismatic median": (25, 39),
    "Prismatic p75": (35, 53),
}


def tri(rng: random.Random, spec: tuple[float, float, float]) -> float:
    low, mode, high = spec
    return rng.triangular(low, high, mode)


def one_run(rng: random.Random, dims: int, notes: int) -> tuple[float, float]:
    k = tri(rng, CHECKER_SPEED)
    findings = tri(rng, FINDINGS)
    manual = (
        tri(rng, OVERHEAD_MIN) * 60
        + dims * tri(rng, PER_DIMENSION)
        + TITLE_BLOCK_FIELDS * tri(rng, PER_TB_FIELD)
        + notes * tri(rng, PER_NOTE)
        + LOOKUPS * tri(rng, PER_LOOKUP)
        + tri(rng, HOLISTIC_MIN) * 60
        + findings * tri(rng, PER_WRITE_UP)
    )
    reported = findings * RECALL / PRECISION
    assisted = (
        tri(rng, OVERHEAD_MIN) * 60
        + tri(rng, READ_SUMMARY_MIN) * 60
        + reported * tri(rng, PER_REPORTED_FINDING)
        + tri(rng, SPOT_CHECK_MIN) * 60
        + findings * RECALL * tri(rng, PER_ACCEPTED_EDIT)
    )
    return k * manual / 60, k * assisted / 60


def pct(xs: list[float], p: float) -> float:
    return statistics.quantiles(xs, n=100)[int(p) - 1]


def main() -> None:
    rng = random.Random(SEED)
    header = ["manual min p5/p50/p95", "assisted p5/p50/p95", "ratio p5/p50/p95"]
    print(f"{'scenario':18s} {header[0]:>24s} {header[1]:>22s} {header[2]:>20s} P(ratio<=0.5)")
    for name, (dims, notes) in SCENARIOS.items():
        runs = [one_run(rng, dims, notes) for _ in range(RUNS)]
        manual = [m for m, _ in runs]
        assisted = [a for _, a in runs]
        ratio = [a / m for m, a in runs]

        def fmt(xs: list[float], digits: int = 1) -> str:
            return "/".join(f"{pct(xs, p):.{digits}f}" for p in (5, 50, 95))

        share = sum(r <= 0.5 for r in ratio) / RUNS
        print(f"{name:18s} {fmt(manual):>24s} {fmt(assisted):>22s} {fmt(ratio, 2):>20s} {share:.2f}")
        means = f"manual mean {statistics.fmean(manual):.1f}, assisted mean {statistics.fmean(assisted):.1f}"
        print(f"{'':18s} {means}")


if __name__ == "__main__":
    main()
