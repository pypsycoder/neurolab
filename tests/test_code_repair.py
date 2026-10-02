import unittest
from neurolab.code_repair import CodeRepair, apply_line_repair


class CodeRepairTests(unittest.TestCase):
    def test_model_replacement_preserves_every_other_line(self):
        proposal=CodeRepair.model_validate({'self_score':.5,'line_edits':[{'line':2,'replacement':'    return [failed]'}]})
        self.assertEqual(apply_line_repair('def affected_nodes(edges, failed):\n    return Edges\n',proposal),'def affected_nodes(edges, failed):\n    return [failed]\n')

    def test_out_of_range_duplicate_and_multiline_edits_fail(self):
        for edits in ([{'line':3,'replacement':''}], [{'line':1,'replacement':'x'},{'line':1,'replacement':'y'}], [{'line':1,'replacement':'a\nb'}]):
            proposal=CodeRepair.model_validate({'self_score':.5,'line_edits':edits})
            with self.assertRaises(ValueError):
                apply_line_repair('a\nb\n',proposal)
