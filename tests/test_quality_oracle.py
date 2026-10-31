from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_models import grade


class IndependentOracleChecks(unittest.TestCase):
    def test_comparison_subject_is_not_confused_with_comparison_object(self):
        good='预算优先选青禾客厅（450元）比梧桐空间（600元）更便宜【S1】【S2】。需要投影仪可选梧桐空间。梧桐空间提前48小时免费取消；青禾客厅确认预订后取消收100元。'
        self.assertTrue(all(grade({'oracle':'chinese_repair'},good).values()))
        bad='梧桐空间费用更低，600元；青禾客厅450元。梧桐空间提前48小时免费取消；青禾客厅确认预订后取消收100元。【S1】【S2】'
        self.assertFalse(grade({'oracle':'chinese_repair'},bad)['correct_price_direction'])
    def test_cancel_condition_cannot_be_credited_to_both_options(self):
        bad='预算优先选青禾客厅450元；梧桐空间600元，两场地均需提前48小时取消，青禾客厅确认后收费100元，梧桐空间免费取消。【S1】【S2】'
        self.assertFalse(grade({'oracle':'chinese_repair'},bad)['condition_not_assigned_to_both_venues'])

if __name__=='__main__':unittest.main()
