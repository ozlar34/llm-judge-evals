#!/usr/bin/env python3
"""Negative-control tests for the guardrail gate (eval.py :: guardrail()).

The guardrail's rationale-based checks (G1, G2) stay correctly SILENT on a
hardened prompt: every cap names its disqualifier, and no strong score names a
hard reject. That silence is the right behavior — but it means a broken marker
list would never fire and nobody would notice (the "armed but unproven" risk).
These tests feed synthetic conflicting outputs straight into guardrail() to
prove each flag FIRES when it should AND stays QUIET when it shouldn't — the
unit-level proof the live eval can't give us on a clean prompt.

Regression note: an earlier marker list contained the bare substring "comp",
which matched "company" — so G2 (the Case A-10 detector) false-fired on any
strong score whose rationale mentioned the company. test_g2_silent_on_company
pins that fix.

Stdlib unittest. Run from this dir: python3 test_guardrail.py
"""
import unittest

from eval import guardrail

CASE = {"id": "synthetic", "rule_status": "implemented"}
REC_CASE = {"id": "synthetic-rec", "rule_status": "recommended"}

G1 = "cap-level score but rationale names no disqualifier"
G2 = "strong score but rationale names a hard reject"
BAND = "borderline band — human-decision zone"
ADJ = "passed via an adjacent rule — intended gate not coded"


class TestGuardrail(unittest.TestCase):
    # ── G1: a cap-level score whose rationale names no disqualifier ──────────
    def test_g1_fires_when_low_score_unexplained(self):
        # the failure mode: a 2 justified only by positive boilerplate
        flags = guardrail(2, "Strong functional match, great team.", CASE, "FAIL")
        self.assertIn(G1, flags)

    def test_g1_silent_when_hard_disqualifier_named(self):
        flags = guardrail(2, "German fluency required — auto-cap.", CASE, "PASS")
        self.assertNotIn(G1, flags)

    def test_g1_silent_when_soft_reason_named(self):
        flags = guardrail(4, "Non-senior title — capped at the band.", CASE, "PASS")
        self.assertNotIn(G1, flags)

    # ── G2: a strong score whose rationale names a hard reject (Case A-10) ───
    def test_g2_fires_on_strong_fit_hard_reject(self):
        # the literal hero failure: 9/10 on a role that requires German
        flags = guardrail(9, "Ideal Track B fit, but German fluency required.",
                          CASE, "FAIL")
        self.assertIn(G2, flags)

    def test_g2_silent_when_strong_score_clean(self):
        flags = guardrail(9, "Track B core PM at an AI-native firm, ideal axis.",
                          CASE, "PASS")
        self.assertNotIn(G2, flags)

    def test_g2_silent_on_company(self):
        # regression: bare "comp" used to match "company" and false-fire G2
        flags = guardrail(9, "Strong fit at this AI-native company.", CASE, "PASS")
        self.assertNotIn(G2, flags)

    def test_g2_still_catches_compensation(self):
        # the fix must not lose real comp-reject coverage
        flags = guardrail(8, "Great role but compensation is below target.",
                          CASE, "FAIL")
        self.assertIn(G2, flags)

    # ── band: 5-6 is the human-decision zone ────────────────────────────────
    def test_band_fires_on_5_and_6(self):
        self.assertIn(BAND, guardrail(5, "Right role, real seniority stretch.",
                                      CASE, "PASS"))
        self.assertIn(BAND, guardrail(6, "Non-senior title floor.", CASE, "PASS"))

    def test_band_silent_outside_5_6(self):
        self.assertNotIn(BAND, guardrail(4, "auto-cap fired.", CASE, "PASS"))
        self.assertNotIn(BAND, guardrail(7, "strong on-strand fit.", CASE, "PASS"))

    # ── coincidental-pass: a recommended (uncoded) gate that PASSed anyway ───
    def test_adjacent_rule_flag_on_recommended_pass(self):
        flags = guardrail(3, "Non-Berlin location cap fires.", REC_CASE, "PASS")
        self.assertIn(ADJ, flags)

    def test_adjacent_rule_silent_on_implemented_pass(self):
        flags = guardrail(3, "Non-Berlin location cap fires.", CASE, "PASS")
        self.assertNotIn(ADJ, flags)

    def test_adjacent_rule_silent_when_recommended_fails(self):
        flags = guardrail(6, "Surfaced too high.", REC_CASE, "FAIL")
        self.assertNotIn(ADJ, flags)

    # ── null guard: no score → no flags ─────────────────────────────────────
    def test_no_score_no_flags(self):
        self.assertEqual(guardrail(None, None, CASE, "ERR"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
