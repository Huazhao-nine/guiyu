import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('guiyu_worker', ROOT/'backend/worker.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.selected = self.root/'selected'
        self.selected.mkdir()
        self.a = self.selected/'原始材料.txt'
        self.a.write_text('这是原始资料。',encoding='utf-8')
        self.outside = self.root/'未授权.txt'
        self.outside.write_text('不应读取',encoding='utf-8')
        self.scope = w.Scope([str(self.selected)])
        self.tx = w.Transactions(self.root/'transactions')
        self.docs, _ = w.collect(self.scope)

    def tearDown(self): self.temp.cleanup()

    def plan(self):
        return self.tx.prepare(self.docs, {'moves':[{'source_id':'S1','category':'活动材料','new_name':'整理后.txt'}]})

    def test_scope_excludes_outside_and_symlink(self):
        (self.selected/'绕过.txt').symlink_to(self.outside)
        self.assertFalse(self.scope.permits(self.outside))
        self.assertFalse(self.scope.permits(self.selected/'绕过.txt'))
        self.assertEqual(self.scope.files(),[self.a.resolve()])

    def test_source_modification_stops_rename(self):
        tx = self.plan()
        self.a.write_text('修改后的资料')
        with self.assertRaises(ValueError): self.tx.apply(tx['id'],self.scope)
        self.assertTrue(self.a.exists())

    def test_existing_destination_is_never_overwritten(self):
        tx = self.plan()
        target = Path(tx['moves'][0]['destination'])
        target.parent.mkdir()
        target.write_text('请保留')
        with self.assertRaises(ValueError): self.tx.apply(tx['id'],self.scope)
        self.assertEqual(target.read_text(),'请保留')
        self.assertTrue(self.a.exists())

    def test_round_trip_preserves_bytes(self):
        before = self.a.read_bytes()
        tx = self.plan()
        self.tx.apply(tx['id'],self.scope)
        self.assertFalse(self.a.exists())
        self.tx.undo(tx['id'])
        self.assertEqual(self.a.read_bytes(),before)
        self.assertEqual(self.tx.get(tx['id'])['state'],'undone')

    def test_changed_result_prevents_undo(self):
        tx = self.plan()
        applied = self.tx.apply(tx['id'],self.scope)
        target = Path(applied['moves'][0]['destination'])
        target.write_text('用户后来修改过的资料')
        with self.assertRaises(ValueError): self.tx.undo(tx['id'])
        self.assertEqual(target.read_text(),'用户后来修改过的资料')

    def test_duplicate_source_plan_rejected(self):
        with self.assertRaises(ValueError):
            self.tx.prepare(self.docs,{'moves':[{'source_id':'S1','new_name':'一.txt'},{'source_id':'S1','new_name':'二.txt'}]})

    def test_unknown_source_plan_rejected(self):
        with self.assertRaises(ValueError): self.tx.prepare(self.docs,{'moves':[{'source_id':'S999'}]})

    def test_scope_change_prevents_apply(self):
        tx = self.plan()
        with self.assertRaises(ValueError): self.tx.apply(tx['id'],w.Scope([str(self.outside)]))

    def test_atomic_rename_no_overwrite(self):
        target = self.selected/'存在.txt'
        target.write_text('已有文件')
        with self.assertRaises(OSError): w.rename_exclusive(self.a,target)
        self.assertEqual(target.read_text(),'已有文件')

    def test_destination_symlink_prevents_apply(self):
        tx = self.plan()
        Path(tx['moves'][0]['destination']).parent.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError): self.tx.apply(tx['id'],self.scope)

    def test_spreadsheet_formulas_are_text(self):
        for text in ['=WEBSERVICE("https://invalid")','  =1+1','@SUM(1)','-1','+cmd']:
            self.assertTrue(w.spreadsheet_value(text).startswith("'"))
        self.assertEqual(w.spreadsheet_value('普通中文'),'普通中文')

    def test_archive_expansion_limit(self):
        path = self.selected/'膨胀.docx'
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('large.xml',b'x'*(33*1024*1024))
        with self.assertRaisesRegex(ValueError,'展开后过大'): w.read_document(path)

    def test_excess_scope_is_explicit(self):
        with self.assertRaises(ValueError): w.Scope([str(self.a)]*41)

    def test_invalid_transaction_identifier(self):
        with self.assertRaises(ValueError): self.tx.get('../../outside')


if __name__ == '__main__': unittest.main()
