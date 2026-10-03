import unittest
from types import SimpleNamespace
from neurolab.code_repair import CodeRepair, apply_line_repair, parse_repair_response, repair_output_diagnostics


class CodeRepairTests(unittest.TestCase):
    def test_model_replacement_preserves_every_other_line(self):
        proposal=CodeRepair.model_validate({'self_score':.5,'line_edits':[{'line':2,'replacement':'    return [failed]'}]})
        self.assertEqual(apply_line_repair('def affected_nodes(edges, failed):\n    return Edges\n',proposal),'def affected_nodes(edges, failed):\n    return [failed]\n')

    def test_out_of_range_duplicate_and_multiline_edits_fail(self):
        for edits in ([{'line':3,'replacement':''}], [{'line':1,'replacement':'x'},{'line':1,'replacement':'y'}], [{'line':1,'replacement':'a\nb'}]):
            proposal=CodeRepair.model_validate({'self_score':.5,'line_edits':edits})
            with self.assertRaises(ValueError):
                apply_line_repair('a\nb\n',proposal)

    def test_complete_json_required_and_length_flag_never_ignored(self):
        content='{"self_score":0.5,"line_edits":[{"line":2,"replacement":"    return [failed]"}]}'
        response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=content))])
        self.assertEqual(parse_repair_response(response).line_edits[0].line,2)
        response.choices[0].finish_reason='length'
        with self.assertRaises(ValueError):
            parse_repair_response(response)

    def test_only_whole_json_fence_is_allowed_and_diagnostics_are_redacted(self):
        content='{"self_score":0.5,"line_edits":[{"line":2,"replacement":"    return [failed]"}]}'
        response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='```json\n'+content+'\n```'))])
        self.assertEqual(parse_repair_response(response).line_edits[0].line,2)
        self.assertEqual(repair_output_diagnostics(response)['known_fields'],['line_edits','self_score'])
        self.assertNotIn('replacement',str(repair_output_diagnostics(response)))
        response.choices[0].message.content='untrusted preface\n```json\n'+content+'\n```'
        with self.assertRaises(ValueError):
            parse_repair_response(response)
        response.choices[0].finish_reason='stop'
        response.choices[0].message.content=content[:-1]
        with self.assertRaises(ValueError):
            parse_repair_response(response)
