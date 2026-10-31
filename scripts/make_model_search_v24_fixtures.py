"""Freeze new fictional office inputs before candidate selection or inference."""
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
from zoneinfo import ZoneInfo
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'fixtures/workbook_model_search_v24'
SEED = 2026103024
D = Decimal


def text(value):
    value = format(value, 'f') if isinstance(value, D) else str(value)
    return value.rstrip('0').rstrip('.') if '.' in value else value


def main():
    assert not DEST.exists(), 'Preserving the first fixed confirmation inputs.'
    folder = DEST / 'workspace'
    folder.mkdir(parents=True)
    rng = random.Random(SEED)
    # ID, department, requested CNY, paid CNY, date, status, advance flag.
    paper = [['TR31', '技术支持部', 2400, 600, '2027-07-01', '已核准', '否'],
             ['TR32', '行政协作部', 1500, 300, '2027-07-20', '待补票', '是'],
             ['TR33', '人力运营部', 3600, 400, '2027-06-30', '已核准', '是'],
             ['TR34', '技术支持部', 980, 500, '2027-07-08', '已核准', '否'],
             ['TR35', '行政协作部', 2800, 900, '2027-07-31', '待补票', '否']]
    online = [['TR31', '技术支持部', 9000, 0, '2027-07-10', '已核准', '是'],
              ['TR33', '人力运营部', 15000, 0, '2027-07-08', '已核准', '是'],
              ['TR36', '技术支持部', 4200, 1200, '2027-07-31', '待补票', '是'],
              ['TR37', '人力运营部', 1800, 800, '2027-07-12', '已核准', '否'],
              ['TR38', '行政协作部', 2100, 600, '2027-07-01', '已核准', '是'],
              ['TR39', '人力运营部', 900, 200, '2027-08-01', '已核准', '否'],
              ['TR40', '技术支持部', 5000, 0, '2027-07-05', '驳回', '是']]
    rng.shuffle(paper)
    rng.shuffle(online)
    book = Workbook()
    book.remove(book.active)
    for title, records, scale, order, header_row in [
            ('纸质', paper, 1, [0, 1, 2, 3, 4, 5, 6], 3),
            ('线上', online, 1000, [5, 4, 0, 6, 3, 1, 2], 4)]:
        sheet = book.create_sheet(title)
        sheet.append(['差旅报销登记 虚构资料'])
        while sheet.max_row < header_row - 1:
            sheet.append([''])
        headers = ['ReportID', 'Department', '报销额（' + ('千元' if scale == 1000 else '元') + '）',
                   '已付额（元）', 'BookedOn', '状态', '允许预支']
        sheet.append([headers[i] for i in order])
        for row in records:
            values = [row[0], row[1], float(D(row[2]) / scale), row[3], datetime.fromisoformat(row[4]), row[5], row[6]]
            sheet.append([values[i] for i in order])
        sheet.freeze_panes = 'A' + str(header_row + 1)
    book.save(folder / '差旅报销.xlsx')
    seen, sums = set(), {}
    for row in paper + online:
        if row[0] in seen:
            continue
        seen.add(row[0])
        balance = D(row[2]) - D(row[3])
        if ('2027-07-01' <= row[4] <= '2027-07-31'
                and (row[5] == '已核准' or row[5] == '待补票' and row[6] == '是')
                and balance >= 600):
            total, count = sums.get(row[1], (D(0), 0))
            sums[row[1]] = total + balance, count + 1
    expense_rows = [[name, text(amount), str(count)] for name, (amount, count)
                    in sorted(sums.items(), key=lambda pair: (-pair[1][0], pair[0]))]
    cases = [{'id': 'travel_union_word',
              'prompt': '汇总差旅报销.xlsx中“纸质”和“线上”的记录，按这个顺序合并。先按ReportID保留首次记录，之后仅纳入2027年7月整月且包含月初月底，状态为已核准，或者状态为待补票且允许预支为是。未付按报销额减已付额计算，只纳入未付不少于600元的，按Department汇总未付合计和单数，未付合计降序；只要Department、未付合计、单数三列。生成Word，标题“七月差旅待付说明”，不新增审核意见。',
              'rows': expense_rows, 'word': True, 'word_numbers': [r[1] for r in expense_rows]},
             {'id': 'travel_short_followup', 'parent': 'travel_union_word',
              'prompt': '那技术支持部呢？其他口径不变，这次只要表格。',
              'rows': [r for r in expense_rows if r[0] == '技术支持部'], 'word': False}]

    services = [['A组', '2027-08-01', '完成', '自助', '45分钟'],
                ['A组', '2027-08-16', '复核通过', '推荐', '1.5小时'],
                ['A组', '2027-08-20', '复核通过', '其他', '60分钟'],
                ['B组', '2027-08-31', '完成', '其他', '2小时'],
                ['B组', '2027-08-04', '复核通过', '推荐', '30分钟'],
                ['B组', '2027-08-22', '草稿', '推荐', '120分钟'],
                ['C组', '2027-08-10', '完成', '推荐', '90分钟'],
                ['C组', '2027-08-31', '复核通过', '推荐', '45分钟'],
                ['C组', '2027-07-31', '完成', '自助', '500分钟'],
                ['A组', '2027-09-01', '完成', '自助', '60分钟']]
    rng.shuffle(services)
    with (folder / '服务登记.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['服务处理登记 虚构资料'])
        writer.writerow([])
        writer.writerow(['Group', 'HandledOn', 'Stage', 'Channel', 'Duration'])
        writer.writerows(services)
    sums = {}
    for group, day, state, channel, duration in services:
        if not ('2027-08-01' <= day <= '2027-08-31'
                and (state == '完成' or state == '复核通过' and channel == '推荐')):
            continue
        amount = D(duration.removesuffix('分钟').removesuffix('小时')) * (60 if duration.endswith('小时') else 1)
        total, count = sums.get(group, (D(0), 0))
        sums[group] = total + amount, count + 1
    service_rows = [[group, str(count), text(amount / 60)] for group, (amount, count)
                    in sorted(sums.items(), key=lambda pair: (-pair[1][0], pair[0]))]
    cases.append({'id': 'english_monthly_duration',
                  'prompt': '从服务登记.csv中选取HandledOn在2027年8月整月的记录，包含两端。Stage为完成，或者Stage为复核通过且Channel为推荐。按Group统计记录数与时长合计，用小时显示；时长合计降序，同小时按Group升序。只要Group、记录数、时长合计三列，不生成文稿。',
                  'rows': service_rows, 'word': False})

    inventory = [['OF81', True, 7, 4, 50], ['OF82', False, 20, 0, 100],
                 ['OF83', True, 9, 9, 40], ['OF84', True, 10, 3, 25],
                 ['OF85', True, 6, 4, 20], ['OF86', True, 5, 1, None],
                 ['OF87', True, 5, 2, 40], ['OF88', True, 4, 8, 100]]
    rng.shuffle(inventory)
    book = Workbook()
    sheet = book.active
    sheet.title = '库存'
    sheet.append(['办公物料库存 虚构资料'])
    for cell, value in [('A2', 'ItemCode'), ('B2', '启用'), ('C2', '数量'), ('E2', 'UnitPrice（元）'),
                        ('C3', '计划数量'), ('D3', '现有数量')]:
        sheet[cell] = value
    for area in ['A2:A3', 'B2:B3', 'C2:D2', 'E2:E3']:
        sheet.merge_cells(area)
    for row in inventory:
        sheet.append(row)
    book.save(folder / '办公室库存.xlsx')
    chosen = []
    for code, enabled, planned, current, price in inventory:
        if enabled and price is not None and planned > current:
            gap = D(planned) - D(current)
            amount = gap * D(price)
            if amount >= 75:
                chosen.append([code, gap, amount])
    chosen.sort(key=lambda row: (-row[2], row[0]))
    amount = sum((row[2] for row in chosen), D(0))
    cases.append({'id': 'office_stock_detail_word',
                  'prompt': '处理办公室库存.xlsx的库存页，只看启用为是且单价非空、计划数量大于现有数量的物料。缺口按计划数量减现有数量，预计金额按缺口乘UnitPrice计算，只纳入预计金额不少于75元的。按预计金额降序，同金额按ItemCode升序，只保留ItemCode、缺口、预计金额，保留逐条明细并附加预计金额合计和条数。生成Word，标题“办公补充计划”，不添加采购日期或供应商。',
                  'rows': [[r[0], text(r[1]), text(r[2])] for r in chosen],
                  'summary_values': [text(amount), str(len(chosen))], 'word_numbers': [text(amount)], 'word': True})
    (DEST / 'tasks.json').write_text(json.dumps({'seed': SEED, 'scope': 'New developer-synthesized confirmation, fixed before candidate inference; expected values use independent Decimal logic.', 'cases': cases}, ensure_ascii=False, indent=2) + '\n')
    frozen = {'created_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'seed': SEED,
              'candidate_task_runs_at_creation': 0, 'goals': len(cases),
              'hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in DEST.rglob('*') if p.is_file()},
              'limits': 'Synthetic office variation, not independent user research. No retuning on confirmation outputs.'}
    (ROOT / 'qa/v0.24/new-input-freeze.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'new_goals': len(cases), 'travel': expense_rows, 'service': service_rows,
                      'stock': cases[-1]['rows'], 'stock_total': text(amount)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
