"""Recompute the frozen synthetic answers from files without any Agent tools."""
import csv
from datetime import datetime
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fmt(value):
    value = format(value, 'f') if isinstance(value, D) else str(value)
    return value.rstrip('0').rstrip('.') if '.' in value else value


def main():
    from openpyxl import load_workbook
    folder = ROOT / 'fixtures/workbook_model_search_v24'
    freeze = json.loads((ROOT / 'qa/v0.24/new-input-freeze.json').read_text())
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in freeze['hashes'].items())
    cases = {c['id']: c for c in json.loads((folder / 'tasks.json').read_text())['cases']}
    recomputed = {}
    book = load_workbook(folder / 'workspace/差旅报销.xlsx', data_only=False, read_only=True)
    seen, totals = set(), {}
    try:
        for sheet, header_row, scale in [('纸质', 3, D(1)), ('线上', 4, D(1000))]:
            rows = list(book[sheet].values)
            headers = rows[header_row - 1]
            for values in rows[header_row:]:
                row = dict(zip(headers, values))
                if row['ReportID'] in seen:
                    continue
                seen.add(row['ReportID'])
                requested = D(str(next(v for k, v in row.items() if k.startswith('报销额')))) * scale
                balance = requested - D(str(row['已付额（元）']))
                day = row['BookedOn'].strftime('%Y-%m-%d')
                state_ok = row['状态'] == '已核准' or (row['状态'] == '待补票' and row['允许预支'] == '是')
                if '2027-07-01' <= day <= '2027-07-31' and state_ok and balance >= 600:
                    amount, count = totals.get(row['Department'], (D(0), 0))
                    totals[row['Department']] = amount + balance, count + 1
    finally:
        book.close()
    recomputed['travel_union_word'] = [[name, fmt(amount), str(count)] for name, (amount, count)
                                     in sorted(totals.items(), key=lambda p: (-p[1][0], p[0]))]
    recomputed['travel_short_followup'] = [r for r in recomputed['travel_union_word'] if r[0] == '技术支持部']
    totals = {}
    with (folder / 'workspace/服务登记.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.reader(handle))
    for row in rows[3:]:
        group, day, stage, channel, duration = row
        if '2027-08-01' <= day <= '2027-08-31' and (stage == '完成' or stage == '复核通过' and channel == '推荐'):
            unit = '分钟' if duration.endswith('分钟') else '小时'
            hours = D(duration.removesuffix(unit)) / (60 if unit == '分钟' else 1)
            amount, count = totals.get(group, (D(0), 0))
            totals[group] = amount + hours, count + 1
    recomputed['english_monthly_duration'] = [[name, str(count), fmt(hours)] for name, (hours, count)
                                            in sorted(totals.items(), key=lambda p: (-p[1][0], p[0]))]
    book = load_workbook(folder / 'workspace/办公室库存.xlsx', data_only=False, read_only=True)
    selected = []
    try:
        for code, enabled, planned, current, price in list(book['库存'].values)[3:]:
            if enabled is True and price is not None and planned > current:
                gap = D(str(planned)) - D(str(current))
                cost = gap * D(str(price))
                if cost >= 75:
                    selected.append([code, gap, cost])
    finally:
        book.close()
    selected.sort(key=lambda r: (-r[2], r[0]))
    recomputed['office_stock_detail_word'] = [[r[0], fmt(r[1]), fmt(r[2])] for r in selected]
    checks = {key: rows == cases[key]['rows'] for key, rows in recomputed.items()}
    checks['stock_summary'] = cases['office_stock_detail_word']['summary_values'] == [fmt(sum((r[2] for r in selected), D(0))), str(len(selected))]
    assert all(checks.values()), checks
    target = ROOT / 'qa/v0.24/gold-audit.json'
    assert not target.exists()
    target.write_text(json.dumps({'time': datetime.now().astimezone().isoformat(), 'checks': checks,
                                 'recomputed_rows': recomputed, 'all_passed': True,
                                 'method': 'Read the actual frozen XLSX and CSV independently with openpyxl/csv/Decimal; no production planning, unit, filter, group or export tools used.'},
                                ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(checks))


if __name__ == '__main__':
    main()
