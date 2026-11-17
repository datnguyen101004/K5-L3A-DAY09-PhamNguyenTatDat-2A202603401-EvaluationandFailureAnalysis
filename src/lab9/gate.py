"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    # 1. Any metric value in pr["metrics"] that is NaN or inf
    for k, v in pr.get("metrics", {}).items():
        if isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is NaN or inf")

    # 2. Row count matches manifest items x seeds
    m_items = pr.get("manifest", {}).get("items", 0)
    m_seeds = len(pr.get("manifest", {}).get("seeds", []))
    expected_rows = m_items * m_seeds
    if len(pr.get("rows", [])) != expected_rows:
        problems.append(f"row count {len(pr.get('rows', []))} != manifest {m_items} items x {m_seeds} seeds ({expected_rows})")

    # 3. Duplicate rows check
    row_pairs = [(r.get("item_id"), r.get("seed")) for r in pr.get("rows", [])]
    if len(row_pairs) != len(set(row_pairs)):
        problems.append("duplicate (item_id, seed) rows detected")

    # 4. The (item_id, seed) set of PR differs from the baseline's
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base.get("rows", [])}
    if set(row_pairs) != base_pairs:
        problems.append("(item_id, seed) set differs from baseline")

    # 5. pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is None
    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures is non-empty: {len(pr['evaluator_failures'])} failure(s)")
    graded_spec_metrics = {m["id"] for m in spec.get("metrics", [])}
    for r in pr.get("rows", []):
        for m in graded_spec_metrics:
            if m in r and r[m] is None:
                problems.append(f"row {r.get('item_id')} seed {r.get('seed')} has None for graded metric {m}")
                break
        else:
            continue
        break

    # 6. An item's slice tags in PR rows differ from the baseline's
    base_slices = {r["item_id"]: tuple(sorted(r.get("slices") or [])) for r in base.get("rows", [])}
    pr_slices = {r["item_id"]: tuple(sorted(r.get("slices") or [])) for r in pr.get("rows", [])}
    if base_slices != pr_slices:
        problems.append("item slice tags differ from baseline")

    # 7. Ratchet: base_spec given and a threshold in spec is LOOSER than in base_spec for the same eval-set version
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        base_m_map = {m["id"]: m for m in base_spec.get("metrics", [])}
        curr_m_map = {m["id"]: m for m in spec.get("metrics", [])}
        for mid, bm in base_m_map.items():
            if mid not in curr_m_map:
                problems.append(f"metric {mid} disappeared in new spec")
                continue
            cm = curr_m_map[mid]
            if bm.get("blocking") and not cm.get("blocking"):
                problems.append(f"metric {mid} became non-blocking")
            bth = bm.get("threshold", {})
            cth = cm.get("threshold", {})
            if "max" in bth:
                if "max" not in cth or cth["max"] > bth["max"]:
                    problems.append(f"threshold max for {mid} loosened: {cth.get('max')} > {bth['max']}")
            if "min" in bth:
                if "min" not in cth or cth["min"] < bth["min"]:
                    problems.append(f"threshold min for {mid} loosened: {cth.get('min')} < {bth['min']}")
            if bth.get("no_significant_drop") and not cth.get("no_significant_drop"):
                problems.append(f"no_significant_drop dropped for {mid}")
            if "max_increase" in bth:
                if "max_increase" not in cth or cth["max_increase"] > bth["max_increase"]:
                    problems.append(f"threshold max_increase for {mid} loosened")

        base_s_map = {s["name"]: s for s in base_spec.get("slices", [])}
        curr_s_map = {s["name"]: s for s in spec.get("slices", [])}
        for sname, bs in base_s_map.items():
            if sname not in curr_s_map:
                problems.append(f"slice {sname} disappeared in new spec")
                continue
            cs = curr_s_map[sname]
            if bs.get("blocking") and not cs.get("blocking"):
                problems.append(f"slice {sname} became non-blocking")
            if "min" in bs:
                if "min" not in cs or cs["min"] < bs["min"]:
                    problems.append(f"slice {sname} min loosened: {cs.get('min')} < {bs['min']}")
            if bs.get("no_significant_drop") and not cs.get("no_significant_drop"):
                problems.append(f"slice {sname} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})

    for s in spec.get("slices", []):
        name = s["name"]
        metric = s["metric"]
        blocking = s.get("blocking", False)
        val_dict = per_item(pr, metric, slice_name=name)
        val = round(sum(val_dict.values()) / len(val_dict), 4) if val_dict else None

        verdict = "ok"
        note = ""
        if val is None:
            verdict = "missing"
        elif "min" in s and val < s["min"]:
            verdict = "fail"

        if s.get("no_significant_drop") and val is not None:
            base_dict = per_item(base, metric, slice_name=name)
            keys = sorted(set(val_dict) & set(base_dict))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [val_dict[k] for k in keys],
                    [base_dict[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        slice_id = f"slice:{name}/{metric}"
        if verdict != "ok" and blocking:
            blocked.append(slice_id)

        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if blocking else "warn")
        lines.append(f"  {slice_id:<22} {val!s:<8} min: {s.get('min')} {note:<28} {label}")

    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
