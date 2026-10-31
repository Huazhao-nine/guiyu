from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from money_subtotals import verified_subtotals


class SubtotalTests(unittest.TestCase):
    def facts(self,*values):return [{'value':Decimal(str(v)),'unit':'元'} for v in values]
    def test_quantity_times_unit_price_can_authorize_a_real_subtotal(self):
        result=verified_subtotals('1200+35*24+480',self.facts(1200,35,480))
        self.assertIn({'expression':'35*24','value':'840','unit':'元'},result)
        self.assertIn({'expression':'1200+35*24+480','value':'2520','unit':'元'},result)
    def test_counts_and_ratios_are_not_currency(self):
        result=verified_subtotals('1200/(3+9)',self.facts(1200))
        self.assertFalse(any(r['value']=='12' for r in result));self.assertEqual(result[-1]['value'],'100')
        self.assertEqual(verified_subtotals('1200/480',self.facts(1200,480)),[])
    def test_mixed_currency_and_squared_money_do_not_authorize_amounts(self):
        self.assertEqual(verified_subtotals('35*24',self.facts(35,24)),[])
        self.assertEqual(verified_subtotals('35+24',self.facts(35)+[{'value':Decimal(24),'unit':'USD'}]),[])
    def test_no_code_or_rounded_intermediate_is_accepted(self):
        self.assertEqual(verified_subtotals('__import__("os")',self.facts(35)),[])
        self.assertEqual(verified_subtotals('35/3',self.facts(35)),[])


if __name__=='__main__':unittest.main()
