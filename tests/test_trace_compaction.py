import unittest,json
from synthetic_mind.stores import state_patch
class TraceCompactionTests(unittest.TestCase):
    def test_rolling_history_lossless_and_compact(self):
        before=[{'id':i,'payload':'x'*500} for i in range(128)]
        after=before[1:]+[{'id':128,'payload':'new'}]
        patch=state_patch(before,after);replayed=list(before)
        for op in patch:
            index=op['path'][0]
            if op.get('remove'):del replayed[index]
            elif index==len(replayed):replayed.append(op['value'])
            else:replayed[index]=op['value']
        self.assertEqual(replayed,after);self.assertLess(len(json.dumps(patch)),200)
