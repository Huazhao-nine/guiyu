"""Freeze fictional workbook variants before the first v0.22 model evaluation."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
from zoneinfo import ZoneInfo
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'fixtures/workbook_variants_v22'
assert not folder.exists(), 'Never regenerate a frozen input in place.'
workspace=folder/'workspace';workspace.mkdir(parents=True)
rng=random.Random(731902)

def book(name, headers, rows, header_row=3):
    wb=Workbook();ws=wb.active;ws.title='原始记录'
    ws.cell(1,1,'虚构验收资料 仅用于本地软件测试')
    for i,value in enumerate(headers,1):
        c=ws.cell(header_row,i,value);c.font=Font(bold=True);c.fill=PatternFill('solid',fgColor='DAE7DE')
        ws.column_dimensions[c.column_letter].width=24
    for row in rows:ws.append(row)
    ws.freeze_panes='A'+str(header_row+1)
    wb.save(workspace/name)
    actual=load_workbook(workspace/name,read_only=True,data_only=False)
    assert list(actual.active.values)[header_row-1]==tuple(headers)
    actual.close()

mass=[]
for i in range(9):
    gross=Decimal(rng.choice([1400,1800,2200,2900,3500]))
    tare=Decimal(rng.choice([150,300,650,900]))
    status='验收通过' if i%4!=0 else '待复核'
    mass.append([f'P{i+31}',str(gross/1000),str(tare),status])
book('包件核重.xlsx',['批次','毛重（kg）','皮重（g）','验收'],mass,4)
mass_ok=[(r[0],Decimal(r[1])*1000-Decimal(r[2])) for r in mass if r[3]=='验收通过' and Decimal(r[1])*1000-Decimal(r[2])>=750]
mass_rows=[[name,str(v/1000).rstrip('0').rstrip('.')] for name,v in sorted(mass_ok)]
mass_total=sum(v for _,v in mass_ok)/1000

headers=['票号','应收(kCNY)','实收(CNY)','状态','截止日期','可延后']
invoices=[]
for i in range(12):
    cap=Decimal(rng.choice([2000,3200,4800,5600,7200]));paid=Decimal(rng.choice([0,400,1200,2400]))
    status=['已开票','待开票','作废'][i%3];delay='是' if i%2 else '否'
    date=['2027-01-31','2027-02-01','2027-02-12','2027-02-28','2027-03-01'][i%5]
    invoices.append([f'Z{i+51}',str(cap/1000),str(paid),status,date,delay])
invoices.append(list(invoices[1][:1])+['9','0','已开票','2027-02-20','是'])
book('东站票据.xlsx',headers,invoices[:6],2)
book('西站票据.xlsx',headers,invoices[6:],5)
seen=set();unique=[]
for row in invoices:
    if row[0] not in seen:unique.append(row);seen.add(row[0])
def invoice_rows(floor):
    selected=[]
    for r in unique:
        if not ('2027-02-01'<=r[4]<='2027-02-28') or not (r[3]=='已开票' or r[3]=='待开票' and r[5]=='是'):continue
        remaining=Decimal(r[1])*1000-Decimal(r[2])
        if remaining>=floor:selected.append([r[0],str(remaining)])
    return sorted(selected,key=lambda r:Decimal(r[1]),reverse=True)
invoice=invoice_rows(800);revised=invoice_rows(1500)
def total(rows):return str(sum((Decimal(r[1]) for r in rows),Decimal(0)))

hours=[['R1','丙组','完成','2027-02-01','90','内部'],['R2','丁组','复核通过','2027-02-28','1.5小时','内部'],
       ['R3','丙组','复核通过','2027-02-15','45','外包'],['R4','丁组','取消','2027-02-05','300','内部'],
       ['R5','丙组','完成','2027-03-01','120','内部'],['R6','丁组','完成','2027-02-17','60','外包'],
       ['R7','丙组','复核通过','2027-02-11','120','内部']]
book('服务月记.xlsx',['记录号','小组','状态','登记日期','工时（分钟）','来源'],hours,3)

cases=[
 {'id':'package_net_kg','prompt':'包件核重里，只看验收通过的。净重按毛重减皮重计算，只保留净重不少于750克的，净重以kg显示；按批次升序，只要批次和净重。保留每条明细，再给净重合计和条数，写简短说明并导出Word。',
  'rows':mass_rows,'summary_rows':[[str(mass_total),str(len(mass_rows))]],'word':True},
 {'id':'invoice_complex_union','prompt':'把东站票据和西站票据纵向合并，先按票号保留原表首次记录，不排序后再去重。之后只看截止日期在2027-02-01到2027-02-28含两端，且状态为已开票、或者状态为待开票并且可延后为是的记录。未收按应收减实收计算，只要未收不少于800元。按未收降序，仅留票号和未收。每条明细保留，再给合计及条数，导出Word说明，不添加审批结论。',
  'rows':invoice,'summary_rows':[[total(invoice),str(len(invoice))]],'word':True},
 {'id':'invoice_brief','parent':'invoice_complex_union','prompt':'门槛改成不少于1500元，其他要求不变。这次只要表格，不要Word。',
  'rows':revised,'summary_rows':[[total(revised),str(len(revised))]],'word':False},
 {'id':'service_or_group','prompt':'服务月记中，只看2027年2月含首尾日期。保留状态是完成的，或者状态是复核通过且来源为内部的记录。按小组汇总记录条数和工时合计，工时用小时显示。按工时合计降序，只要小组、条数、工时合计三列，不写文稿。',
  'rows':[['丙组','2','3.5'],['丁组','2','2.5']],'word':False},
]
assert mass_rows and invoice and revised
(folder/'tasks.json').write_text(json.dumps({'cases':cases},ensure_ascii=False,indent=2)+'\n')
files=[folder/'tasks.json',*workspace.glob('*.xlsx')]
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
q=ROOT/'qa/v0.22';q.mkdir(exist_ok=True)
(q/'new-input-freeze.json').write_text(json.dumps({'created_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
 'seed':731902,'model_runs':0,'case_count':4,'input_hashes':hashes,
 'scope':'Developer-authored fictional variations, fixed before any v22 model run. Expected rows computed with Decimal from generated source records; no external human or user study.',
 'no_backend_tuning_after_new_input_model_results':True},ensure_ascii=False,indent=2)+'\n')
print('Frozen four goals over four fictional XLSX files; no model used.')
