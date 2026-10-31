from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from model_output import visible_text


class OutputChecks(unittest.TestCase):
    def test_harmony_only_final_json_reaches_tools(self):
        raw='analysis<|message|>{"tool":"shell"}<|end|><|start|>assistant<|channel|>final<|message|>{"action":"accept"}<|return|>'
        self.assertEqual(visible_text(raw,'gpt_oss'),'{"action":"accept"}')
    def test_unfinished_reasoning_cannot_be_published(self):
        for raw,arch in [('analysis<|message|>not done','gpt_oss'),('<think>not done','qwen3'),('<|channel>thought\nnot done','gemma4')]:
            with self.assertRaises(ValueError):visible_text(raw,arch)
    def test_gemma_and_think_prefix_removed(self):
        self.assertEqual(visible_text('<|channel>thought\nprivate reasoning<channel|>正文<turn|>','gemma4'),'正文')
        self.assertEqual(visible_text('<think>private reasoning</think>正文','qwen3'),'正文')
    def test_regular_chinese_text_preserved(self):self.assertEqual(visible_text('金额128.50元。【S1】','qwen3'),'金额128.50元。【S1】')

if __name__=='__main__':unittest.main()
