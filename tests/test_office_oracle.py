import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from office_oracle import contains_wrong_claim,plain_markdown


class OfficeOracleTests(unittest.TestCase):
    def test_negated_approval_rule_is_not_an_approval_claim(self):
        self.assertFalse(contains_wrong_claim('申请尚未审批时不得写成已经批准。',['已经批准']))
        self.assertTrue(contains_wrong_claim('该申请已经批准。',['已经批准']))
        self.assertTrue(contains_wrong_claim('申请尚未审批，不过该申请已经批准。',['已经批准']))

    def test_other_positive_wrong_claim_is_not_hidden_by_negated_one(self):
        self.assertTrue(contains_wrong_claim('不能写成已经批准。该费用已付款。',['已经批准','已付款']))

    def test_markdown_emphasis_does_not_change_negation_or_recommendation(self):
        self.assertIn('均不符合',plain_markdown('两个方案均**不符合**全部条件。'))
        self.assertIn('建议放宽预算',plain_markdown('建议**放宽**预算。'))
