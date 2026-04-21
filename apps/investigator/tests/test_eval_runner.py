"""End-to-end eval runner test against the seeded golden.jsonl."""

import os

from eval.runner import run


def test_golden_dataset_runs():
    dataset = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "eval",
        "dataset",
        "golden.jsonl",
    )
    summary, scores = run(dataset, backend="scripted")
    assert summary["n"] >= 7
    # Scripted backend should match the 7 straightforward cases; tricky cases
    # intentionally fail the default prior. Assert the baseline is non-trivial.
    assert summary["root_cause_accuracy"] >= 0.5
    assert len(scores) == summary["n"]
