"""CPU-only OfficeAgent replay of the saved fictional native export failure.

Only editorial fact-ID selection is stubbed. Any data-planning model call fails
the check. This validates the saved result, XLSX and Word, not native UI clicks.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import worker as core
from office_agent import OfficeAgent
from workbook_export import read_cells
from openpyxl import load_workbook
from docx import Document


def main():
    fixture = json.loads((ROOT / "fixtures/submission_v27/delivery-reuse-predecessors.json").read_text())
    with tempfile.TemporaryDirectory(prefix="guiyu-delivery-replay-") as directory:
        run = Path(directory)
        workspace = run / "fictional-workspace"
        workspace.mkdir()
        for file in (ROOT / "fixtures/submission_v27/workspace").iterdir():
            if file.is_file():
                shutil.copy2(file, workspace / file.name)
        plans = json.loads(json.dumps(fixture["plans"], ensure_ascii=False).replace("$WORKSPACE", str(workspace)))
        parent = next(plan for plan in plans if plan["id"] == fixture["source_parent_id"])

        class EditorialStub:
            info = {"name": parent["model_name"], "key": "cpu-export-replay"}
            calls = 0

            def generate(self, system, user, **kwargs):
                if not system.startswith("你是中文办公文稿编辑。"):
                    raise AssertionError("Unexpected data replanning instead of checked result reuse")
                self.calls += 1
                return '{"facts":["COUNT"]}', {}

        model = EditorialStub()
        office = OfficeAgent(core.Agent(model, run / "data"), core)
        for plan in plans:
            (office.root / (plan["id"] + ".json")).write_text(json.dumps(plan, ensure_ascii=False))
        request = {"id": str(uuid.uuid4()),
                   "prompt": "回到刚才的支持汇总，给第一名的结果再导出一份Word，其他口径和列不变。",
                   "kind": "auto", "adaptive": True, "workbook_mode": "flow", "paths": parent["paths"],
                   "workspace_root": str(workspace), "parent_id": parent["id"],
                   "conversation_parent_id": fixture["conversation_parent_id"], "thread_id": parent["thread_id"]}
        with redirect_stdout(io.StringIO()):
            plan = office.draft(request)
            result = office.execute({"plan_id": plan["id"], "paths": plan["paths"], "workspace_root": str(workspace)})
        xlsx = next(a["path"] for a in result["artifacts"] if a["type"] == "xlsx")
        book = load_workbook(xlsx, read_only=True, data_only=False)
        try:
            cells = read_cells(book, "处理结果")
        finally:
            book.close()
        assert cells[1:] == fixture["expected_rows"], cells
        assert result["plan"]["workbook"]["flow"]["contract"]["delivery_revision"]["data_unchanged"]
        word = Document(next(a["path"] for a in result["artifacts"] if a["type"] == "docx"))
        rows = [[" | ".join(c.text for c in row.cells) for row in table.rows] for table in word.tables]
        assert any("白组 | 3 | 0.033 | 2" == value for table in rows for value in table), rows
        assert all(core.digest(Path(path)) == value for path, value in parent["snapshot"].items())
        report = {"passed": True, "scope": "Portable CPU-only full OfficeAgent replay of sanitized actual fictional native predecessor; editorial selection stubbed. Not a native UI or model test.",
                  "actual_rows": cells[1:], "word_table_rows": rows, "editorial_fact_selection_calls": model.calls,
                  "originals_unchanged": True,
                  "backend_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "backend").glob("*.py")}}
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
