import json
import unittest
from neurolab.agent_event_metadata import observe_line


class AgentMetadataTests(unittest.TestCase):
    def test_no_text_commands_or_unknown_labels_persist(self):
        counts = {}
        observe_line(json.dumps({'kind':'ActionEvent','tool_name':'terminal','command':'private prompt','content':'secret token'}).encode(),counts)
        observe_line(json.dumps({'kind':'secret credential','tool_name':'unknown private tool'}).encode(),counts)
        self.assertEqual(counts,{'json_events':2,'ActionEvent':1,'tool:terminal':1,'non_executable_action':1})
        self.assertNotIn('private',json.dumps(counts))

    def test_required_risk_failure_has_fixed_label(self):
        counts = {}
        observe_line(json.dumps({'kind':'AgentErrorEvent','error':"Error validating tool: Failed to provide security_risk field; private"}).encode(),counts)
        self.assertEqual(counts['missing_security_risk'],1)
        self.assertNotIn('private',json.dumps(counts))

    def test_schema_error_classification_does_not_keep_error_text(self):
        counts = {}
        observe_line(json.dumps({'kind':'AgentErrorEvent','error':'1 validation error: Field required; private input'}).encode(),counts)
        self.assertEqual(counts['action_schema_validation'],1)
        self.assertEqual(counts['action_missing_field'],1)
        self.assertNotIn('private',json.dumps(counts))

    def test_error_marker_and_huge_event_are_bounded(self):
        counts = {}
        observe_line(b'ReadTimeout private provider body',counts)
        observe_line(b'x'*65537,counts)
        self.assertEqual(counts,{'ReadTimeout':1,'oversized_event':1})

    def test_editor_command_and_error_are_metadata_only(self):
        counts={}
        observe_line(json.dumps({'kind':'ActionEvent','action':{'command':'view','path':'private path'}}).encode(),counts)
        observe_line(json.dumps({'kind':'ObservationEvent','observation':{'is_error':True,'content':'Permission denied private prompt'}}).encode(),counts)
        self.assertEqual(counts['editor:view'],1)
        self.assertEqual(counts['permission_denied'],1)
        self.assertEqual(counts['tool_errors'],1)
        self.assertNotIn('private',json.dumps(counts))
