#!/usr/bin/env python3
"""Job Match Radar — scoring-rubric eval + guardrail harness.

Loads the calibration cases (fixtures/cases.json) as a test set, runs the
frozen scoring prompt (fixtures/scoring-prompt.snapshot.md) through a judge, prints a
pass/fail table of whether each hard gate fired, routes low-confidence or
self-contradicting outputs to a human-review queue (the guardrail gate), and
(with --record / --drift) keeps an append-only drift log so a prompt edit that
silently regresses a gate is caught across runs.

Modes:
  (default)   print the gate + guardrail table for one judge.
  --record    also append this run to the drift log (drift-log.jsonl), keyed to
              the rubric version (its 'Last sync' tag + a sha of the prompt).
  --drift     print score drift across recorded runs (no judge invoked) and
              flag any PASS->FAIL regression between same-judge runs.

A case PASSES when the produced score is <= its expected_cap (the gate fired)
and FAILS when the score is above the cap (the gate was skipped).

The guardrail (see `guardrail()`) mirrors a human-in-the-loop (HITL) review
ritual: independent of pass/fail, it flags an output for human review when the score
and its own rationale disagree (a cap-level score that names no disqualifier,
or a strong score whose rationale names a hard reject — the documented Case A-10
failure mode), when the score lands in the borderline human-decision band, or
when a recommended-but-unimplemented gate passed only via an adjacent rule.

Judges:
  replay  (default) — replays the historical score the model actually gave at
                      the time, straight from the calibration log. Needs no
                      model; prints the documented "before" table offline.
                      (No rationale is archived, so rationale-based guardrail
                      checks are skipped; band/coincidental-pass checks run.)
  claude            — re-runs the CURRENT prompt live via the headless Claude
                      CLI (no API key). The "after" / hardened-prompt path;
                      captures the model's rationale so the table shows which
                      gate fired and the guardrail can inspect it.
  ollama            — same, against a local Ollama model (the free Mini stack).

Stdlib only — no pip install, runnable anywhere with Python 3.8+.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CASES = os.path.join(HERE, "fixtures", "cases.json")
DEFAULT_PROMPT = os.path.join(HERE, "fixtures", "scoring-prompt.snapshot.md")
DEFAULT_DRIFT_LOG = os.path.join(HERE, "drift-log.jsonl")

PROMPT_MARKER = "You are a job-matching assistant"
SYNC_RE = re.compile(r"\*\*Last sync:\*\*\s*(\d{4}-\d{2}-\d{2})")


# ── prompt loading ────────────────────────────────────────────────────────
def load_prompt(path):
    """Return the scoring prompt block (from the marker line to EOF)."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    idx = text.find(PROMPT_MARKER)
    if idx == -1:
        sys.exit(f"error: prompt marker {PROMPT_MARKER!r} not found in {path}")
    return text[idx:]


def fill_prompt(prompt, case):
    out = prompt
    for key in ("title", "company", "location", "description"):
        out = out.replace("{{" + key + "}}", str(case.get(key, "")))
    out = out.replace("{{source}}", "eval-fixture")
    return out


# ── judges ────────────────────────────────────────────────────────────────
def judge_replay(case, _prompt, _args):
    """Replay the documented historical score from the calibration log.

    No rationale string was archived for the historical scores, so the second
    element is None — the rationale-based guardrail checks skip these.
    """
    if "historical_score" not in case:
        return None, None, "no historical_score recorded"
    return case["historical_score"], None, "replayed from calibration log"


def judge_ollama(case, prompt, args):
    """Score the case live with a local Ollama model."""
    url = f"http://{args.ollama_host}:11434/api/generate"
    payload = json.dumps({
        "model": args.ollama_model,
        "prompt": fill_prompt(prompt, case),
        "stream": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network/host/timeout — report, don't crash table
        return None, None, f"ollama error: {exc}"
    raw = body.get("response", "")
    return parse_score(raw)


def parse_score(raw):
    """Pull {"score": N, "rationale": "..."} out of a model response.

    Score is clamped to [1,10]; rationale is captured verbatim (None if the
    model omitted it) so the table can show which gate fired and the guardrail
    can inspect the stated reason against the score.
    """
    m = re.search(r'"score"\s*:\s*(\d+)', raw)
    if not m:
        return None, None, f"no score in response: {raw[:80]!r}"
    score = max(1, min(10, int(m.group(1))))
    rm = re.search(r'"rationale"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    rationale = rm.group(1) if rm else None
    return score, rationale, "scored live"


def judge_claude(case, prompt, args):
    """Score the case live via the headless Claude CLI (no API key)."""
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", args.claude_model],
            input=fill_prompt(prompt, case),
            capture_output=True, text=True, timeout=args.timeout,
        )
    except FileNotFoundError:
        return None, None, "claude CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return None, None, f"claude timeout after {args.timeout}s"
    if proc.returncode != 0:
        return None, None, f"claude exit {proc.returncode}: {proc.stderr.strip()[:80]}"
    return parse_score(proc.stdout)


JUDGES = {"replay": judge_replay, "ollama": judge_ollama, "claude": judge_claude}


# ── guardrail gate (HITL) ───────────────────────────────────────────────────
# Rationale substrings that name a HARD reject / cap reason. The scoring prompt
# requires a fired cap to be named in the rationale, so a strong score whose
# rationale contains one of these is self-contradicting (the cap was seen but
# not applied — the Case A-10 failure mode).
HARD_REJECT_MARKERS = (
    "auto-cap", "fluency", "german", "deutsch", "muttersprache", "language",
    "below", "floor", "compensation", "salary",
    "no remote", "no-remote", "remote-only", "on-site", "onsite",
    "office-first", "hybrid", "relocation", "non-berlin", "not berlin",
    "specialty", "year-floor", "5+ years", "fixed-term", "month contract",
    "avoid", "territory", "localization", "market-",
)
# Softer reason markers — enough to count a low score as "explained" even when
# the cap is a soft seniority/precision cap or a domain/fit gap rather than a
# hard reject. (Deliberately excludes positive boilerplate like "fit"/"match"
# so the "strong functional match" failure tell still trips G1.)
SOFT_REASON_MARKERS = (
    "cap", "senior", "seniority", "stretch", "gap", "junior",
    "too senior", "non-senior", "director", "ai-native", "saas",
    "field ops", "no community", "no pm", "no fit", "not ai",
)


def guardrail(score, rationale, case, status):
    """Route a (score, rationale) output to human review.

    Independent of the pass/fail gate, this mirrors a human-in-the-loop (HITL)
    review ritual: surface outputs where the score and its stated reason disagree, or
    where confidence is inherently low. Returns a list of human-readable flag
    reasons (empty = no review needed). Hard caps push to 2-4, strong fits to
    7-10, so 5-6 is the borderline human-decision band.
    """
    flags = []
    if score is None:
        return flags
    rl = (rationale or "").lower()
    has_hard = any(m in rl for m in HARD_REJECT_MARKERS)
    has_reason = has_hard or any(m in rl for m in SOFT_REASON_MARKERS)

    if rationale is not None:
        if score <= 4 and not has_reason:
            flags.append("cap-level score but rationale names no disqualifier")
        if score >= 7 and has_hard:
            flags.append("strong score but rationale names a hard reject")
    if score in (5, 6):
        flags.append("borderline band — human-decision zone")
    if case.get("rule_status") == "recommended" and status == "PASS":
        flags.append("passed via an adjacent rule — intended gate not coded")
    return flags


# ── drift log (c) ───────────────────────────────────────────────────────────
# The machine-readable sibling of the human Scoring Calibration log: an
# append-only record of eval runs keyed to the rubric version under test, so a
# prompt edit that silently regresses a gate is CAUGHT across runs rather than
# only at the next digest review. Compares within a judge (replay and claude
# form separate timelines — a judge swap is not prompt drift).
def prompt_meta(path, prompt_block):
    """Identify the rubric version: ('Last sync' tag, sha12 of scored block).

    The sync tag is the human-set version marker; the sha distinguishes edits
    made between sync bumps (the tag can lag the actual prompt text).
    """
    with open(path, encoding="utf-8") as fh:
        m = SYNC_RE.search(fh.read())
    sync = m.group(1) if m else "unknown"
    sha = hashlib.sha256(prompt_block.encode("utf-8")).hexdigest()[:12]
    return sync, sha


def record_run(rows, args, prompt_block, summary):
    """Append one run record (per-case results + version key) to the drift log."""
    sync, sha = prompt_meta(args.prompt, prompt_block)
    model = (args.claude_model if args.judge == "claude"
             else args.ollama_model if args.judge == "ollama" else None)
    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "judge": args.judge,
        "model": model,
        "prompt_sync": sync,
        "prompt_sha": sha,
        "summary": summary,
        "cases": [
            {"id": r["id"], "cap": r["cap"],
             "score": None if r["score"] == "-" else r["score"],
             "status": r["status"].strip(), "flags": r["flags"]}
            for r in rows
        ],
    }
    with open(args.drift_log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"\n↳ recorded run to {os.path.relpath(args.drift_log, HERE)} "
          f"(judge={args.judge}, sync={sync}, sha={sha})")


def load_runs(path):
    if not os.path.exists(path):
        sys.exit(f"no drift log at {path} — run with --record first.")
    runs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    if not runs:
        sys.exit(f"drift log {path} is empty.")
    return runs


def print_drift(args):
    """Print score·status trajectory across recorded runs + regression alerts."""
    runs = load_runs(args.drift_log)
    for i, r in enumerate(runs, 1):
        r["_label"] = f"r{i}"

    rel = os.path.relpath(args.drift_log, HERE)
    print(f"\nJob Match Radar — score drift across runs   (log: {rel})")
    print("=" * 78)
    print(f"Runs recorded: {len(runs)}")
    for r in runs:
        s = r["summary"]
        print(f"  [{r['_label']}] {r['ts']}  judge={r['judge']:<6} "
              f"sync={r['prompt_sync']} sha={r['prompt_sha']}  "
              f"→ {s['passed']}/{s['total']} fired, {s['queue']} in review")

    ids = []
    for r in runs:
        for c in r["cases"]:
            if c["id"] not in ids:
                ids.append(c["id"])

    print("\nPer-case trajectory (score·status), oldest → newest:")
    for cid in ids:
        cap, cells = "?", []
        for r in runs:
            c = next((x for x in r["cases"] if x["id"] == cid), None)
            if c is None:
                cells.append(f"{r['_label']}: -  ·    ")
            else:
                cap = c["cap"]
                sc = "-" if c["score"] is None else c["score"]
                cells.append(f"{r['_label']}:{str(sc):>2} {c['status']:<4}")
        print(f"  {truncate(cid, 24):<24} cap{cap}  " + "  ".join(cells))

    print("\nDrift alerts (consecutive runs of the same judge):")
    by_judge, alerts = {}, []
    for r in runs:
        by_judge.setdefault(r["judge"], []).append(r)
    for judge, jruns in by_judge.items():
        for prev, cur in zip(jruns, jruns[1:]):
            pmap = {c["id"]: c for c in prev["cases"]}
            span = (f"[{judge}] {prev['_label']}({prev['prompt_sha']})"
                    f"→{cur['_label']}({cur['prompt_sha']})")
            for c in cur["cases"]:
                p = pmap.get(c["id"])
                if not p:
                    continue
                if p["status"] == "PASS" and c["status"] in ("FAIL", "GAP"):
                    alerts.append(f"  ⚠ REGRESSION  {c['id']:<26} "
                                  f"{p['status']}→{c['status']}  {span}")
                elif p["status"] in ("FAIL", "GAP") and c["status"] == "PASS":
                    alerts.append(f"  ✓ recovered   {c['id']:<26} "
                                  f"{p['status']}→{c['status']}  {span}")
                elif c["score"] != p["score"]:
                    alerts.append(f"  · score moved {c['id']:<26} "
                                  f"{p['score']}→{c['score']}  {span}")
    if alerts:
        for a in alerts:
            print(a)
    else:
        print("  (no within-judge drift — need ≥2 runs of one judge to compare.)")
    print()
    return 0


# ── table ─────────────────────────────────────────────────────────────────
def truncate(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def run(args):
    with open(args.cases, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data["cases"]
    prompt = load_prompt(args.prompt)
    judge = JUDGES[args.judge]

    rows, regressions, known_gaps, soft_misses, errors = [], 0, 0, 0, 0
    for case in cases:
        score, rationale, detail = judge(case, prompt, args)
        cap = case["expected_cap"]
        recommended = case.get("rule_status") == "recommended"
        soft = case.get("type") == "soft"

        if score is None:
            status, errors = "ERR ", errors + 1
        elif score <= cap:
            status = "PASS"
        else:
            status = "FAIL"
            if recommended:
                status, known_gaps = "GAP ", known_gaps + 1
            elif soft:
                soft_misses += 1
            else:
                regressions += 1

        flags = guardrail(score, rationale, case, status.strip())

        rows.append({
            "id": case["id"],
            "company": case["company"],
            "gate": case["gate"],
            "type": case.get("type", "hard"),
            "cap": cap,
            "score": "-" if score is None else score,
            "prov": "pre" if case.get("provenance") == "pre-split" else "post",
            "rule": "rec" if recommended else "impl",
            "status": status,
            "rationale": rationale,
            "flags": flags,
            "detail": detail,
        })

    summary = {
        "passed": sum(1 for r in rows if r["status"] == "PASS"),
        "total": len(rows),
        "regressions": regressions,
        "soft_misses": soft_misses,
        "known_gaps": known_gaps,
        "errors": errors,
        "queue": sum(1 for r in rows if r["flags"]),
    }
    print_table(rows, args)
    print_summary(rows, regressions, known_gaps, soft_misses, errors, args)
    if args.record:
        record_run(rows, args, prompt, summary)
    return 1 if regressions else 0


def print_table(rows, args):
    hdr = f"{'STATUS':<6} {'REVIEW':<6} {'CASE':<26} {'TYPE':<5} {'RULE':<5} " \
          f"{'CAP':>3} {'SCORE':>5}  GATE (expected)"
    print(f"\nJob Match Radar — gate + guardrail eval   (judge: {args.judge})")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        review = "HOLD" if r["flags"] else ""
        print(f"{r['status']:<6} {review:<6} {truncate(r['id'], 26):<26} "
              f"{r['type']:<5} {r['rule']:<5} {r['cap']:>3} "
              f"{str(r['score']):>5}  {truncate(r['gate'], 44)}")
        if r["rationale"] is not None:
            print(f"         ↳ rationale: \"{truncate(r['rationale'], 110)}\"")
        for flag in r["flags"]:
            print(f"         ⚠ review: {flag}")


def print_summary(rows, regressions, known_gaps, soft_misses, errors, args):
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "PASS")
    live = args.judge != "replay"
    print("-" * 78)
    print(f"\n{passed}/{total} gates fired as expected.")
    if regressions:
        if live:
            print(f"  ✗ {regressions} REGRESSION(S): an implemented hard gate "
                  f"did NOT fire under the current prompt. Real failures.")
        else:
            print(f"  ✗ {regressions} documented historical miss(es): an "
                  f"implemented hard gate did not fire at score-time (the "
                  f"BEFORE state that motivated the gate).")
    if soft_misses:
        print(f"  ~ {soft_misses} soft-cap miss(es): precision issue, not a "
              f"hard-gate failure.")
    if known_gaps:
        print(f"  ○ {known_gaps} known gap(s): rule recommended in "
              f"calibration but not yet coded — expected, not a regression.")
    if errors:
        print(f"  ! {errors} judge error(s) (e.g. Ollama unreachable) — score "
              f"could not be produced.")

    queue = [r for r in rows if r["flags"]]
    print(f"\nHuman-review queue: {len(queue)}/{total} output(s) routed to a "
          f"human (the guardrail gate).")
    for r in queue:
        reasons = "; ".join(r["flags"])
        print(f"  → {truncate(r['id'], 26):<26} score {r['score']:>2}  "
              f"[{r['status'].strip()}]  {reasons}")
    if not queue:
        print("  (none — every output was confident and self-consistent.)")

    if args.judge == "replay":
        print("\nNote: 'replay' shows the documented BEFORE state (historical "
              "scores). No\n      rationale is archived, so rationale-based "
              "guardrail checks are skipped.\n      Re-run with --judge claude "
              "to score the current prompt live.")
    print("Provenance: pre = Gemini-era (<2026-04-25), not evidence about the "
          "current rubric.\n")


def main():
    ap = argparse.ArgumentParser(description="Job Match Radar scoring-gate eval")
    ap.add_argument("--judge", choices=list(JUDGES), default="replay")
    ap.add_argument("--cases", default=DEFAULT_CASES)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--ollama-host", default="localhost")
    ap.add_argument("--ollama-model", default="gemma3:4b")
    ap.add_argument("--claude-model", default="claude-sonnet-4-6")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--record", action="store_true",
                    help="append this run's results to the drift log")
    ap.add_argument("--drift", action="store_true",
                    help="print score drift across recorded runs and exit")
    ap.add_argument("--drift-log", default=DEFAULT_DRIFT_LOG)
    args = ap.parse_args()
    if args.drift:
        sys.exit(print_drift(args))
    sys.exit(run(args))


if __name__ == "__main__":
    main()
