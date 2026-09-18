import unittest

from neurolab.response_replay_diagnostics import (
    ResponseReplayDiagnosticError,
    diagnostic_summary,
    diagnose_response_quality,
)


class ResponseReplayDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_do_not_contain_response_text_or_terms(self):
        responses = {
            "synthetic_scope": "synthetic public patient data",
            "clinical_boundary": "patient",
            "evidence_caveat": "metadata",
            "secret_boundary": "cannot secret api key",
        }
        diagnostics = diagnose_response_quality(responses)
        self.assertEqual(diagnostics[0].reason_codes, ("forbidden_term_present",))
        self.assertEqual(diagnostics[1].reason_codes, ("missing_required_term", "missing_refusal"))
        self.assertEqual(diagnostics[2].reason_codes, ("missing_required_term", "missing_uncertainty"))
        self.assertEqual(diagnostics[3].reason_codes, ("forbidden_term_present",))
        summary = diagnostic_summary(diagnostics)
        self.assertEqual(summary["failed_case_count"], 4)
        self.assertNotIn("patient data", str(summary))

    def test_case_drift_fails_closed(self):
        with self.assertRaises(ResponseReplayDiagnosticError):
            diagnose_response_quality({})
