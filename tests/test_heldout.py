"""Held-out selection: reproducible, and never a drawing development looked at."""

from __future__ import annotations

from pathlib import Path

from drawing_intelligence.eval.heldout import development_sample, select_heldout


def client_set(tmp_path: Path, n: int = 450) -> tuple[Path, Path]:
    client, raw = tmp_path / "client", tmp_path / "raw"
    (client / "Generic Prismatic Parts").mkdir(parents=True)
    raw.mkdir()
    for i in range(n):
        (client / "Generic Prismatic Parts" / f"P{i:04d}.PDF").write_bytes(b"")
    (client / "10K_CAM PLATE.pdf").write_bytes(b"")  # a copy of a sample drawing
    (client / "WP Specific Guidelines").mkdir()
    for i in range(60):
        (client / "WP Specific Guidelines" / f"G{i}.pdf").write_bytes(b"")  # documents, not drawings
    (raw / "10K_CAM PLATE.pdf").write_bytes(b"")
    return client, raw


def test_selection_is_reproducible_and_unseen(tmp_path: Path):
    client, raw = client_set(tmp_path)
    first = select_heldout(client, 25, seed=7, samples_dir=raw)
    assert first == select_heldout(client, 25, seed=7, samples_dir=raw) and len(first) == 25
    assert not set(first) & development_sample(client)
    assert all(p.stem != "10K_CAM PLATE" and "Guidelines" not in str(p) for p in first)
    assert first != select_heldout(client, 25, seed=8, samples_dir=raw)
