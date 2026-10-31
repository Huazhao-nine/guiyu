import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from runtime_policy import GIB,choose_policy


class RuntimePolicyTests(unittest.TestCase):
    def test_same_standard_budget_on_16_and_32gb_for_daily_model(self):
        a=choose_policy(6_000_000_000,16*GIB)
        self.assertEqual(a,choose_policy(6_000_000_000,32*GIB))
        self.assertEqual(a.name,'standard-16gb')
        self.assertLess(a.memory_bytes,10*GIB)
        self.assertLess(a.cache_bytes,GIB)

    def test_large_model_refused_before_loading_on_16gb(self):
        with self.assertRaisesRegex(ValueError,'至少 32 GB'):choose_policy(12_000_000_000,16*GIB)
        with self.assertRaisesRegex(ValueError,'至少 32 GB'):choose_policy(12_000_000_000,24*GIB)
        self.assertEqual(choose_policy(12_000_000_000,32*GIB).name,'extended-32gb')

    def test_unknown_or_small_device_cannot_opt_into_large_model(self):
        with self.assertRaises(ValueError):choose_policy(2_000_000_000,8*GIB)
        with self.assertRaises(ValueError):choose_policy(12_000_000_000,0)
