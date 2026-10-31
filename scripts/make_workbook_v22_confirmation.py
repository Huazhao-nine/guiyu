"""Freeze a second, different set of fictional workbooks before model runs."""
import csv
from datetime import date,datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
from zoneinfo import ZoneInfo
from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'fixtures/workbook_confirmation_v22'
SEED=2026103017
D=Decimal


def number(value):
    value=format(value,'f') if isinstance(value,D) else str(value)
    return value.rstrip('0').rstrip('.') if '.' in value else value


def main():
    assert not DEST.exists(),'Preserving frozen confirmation inputs and expected cells.'
    folder=DEST/'workspace';folder.mkdir(parents=True);rng=random.Random(SEED)
    # ClaimID, Team, Requested CNY, Settled CNY, date, status, advance flag.
    second=[['P41','设备支持',1800,300,'2027-04-01','已核准','否'],['P42','行政协调',2400,400,'2027-04-10','补交中','是'],
            ['P43','算力运维',3200,1000,'2027-04-30','补交中','否'],['P44','设备支持',5000,0,'2027-03-31','已核准','否']]
    first=[['P41','设备支持',9000,0,'2027-04-05','已核准','是'],['P44','设备支持',8000,0,'2027-04-06','已核准','是'],
           ['P45','行政协调',4800,1800,'2027-04-20','补交中','是'],['P46','设备支持',3600,1000,'2027-04-30','已核准','否'],
           ['P47','算力运维',2900,2200,'2027-04-15','已核准','是'],['P48','算力运维',4400,1200,'2027-04-01','补交中','是'],
           ['P49','行政协调',1800,0,'2027-05-01','已核准','否'],['P50','设备支持',3700,2000,'2027-04-02','拒绝','是']]
    rng.shuffle(first);rng.shuffle(second)
    def claims(name,rows,scale,order,padding):
        book=Workbook();sheet=book.active;sheet.title='登记'
        for _ in range(padding):sheet.append(['采购支付登记 附件为虚构数据'] if sheet.max_row==1 else [])
        headers=['ClaimID','Team','申请额（'+('千元' if scale==1000 else '元')+'）','Settled（元）','BookedOn','状态','可预付']
        sheet.append([headers[i] for i in order])
        for row in rows:
            cells=[row[0],row[1],float(D(row[2])/D(scale)),row[3],datetime.fromisoformat(row[4]),row[5],row[6]]
            sheet.append([cells[i] for i in order])
        sheet.freeze_panes='A'+str(padding+2);book.save(folder/name)
    claims('采购一部.xlsx',first,1000,[0,1,2,3,4,5,6],2)
    claims('采购二部.xlsx',second,1,[5,0,6,4,3,1,2],0)
    retained=[];seen=set()
    for row in second+first:  # User explicitly names department two before one.
        if row[0] in seen:continue
        seen.add(row[0]);balance=D(row[2])-D(row[3])
        if date(2027,4,1)<=date.fromisoformat(row[4])<=date(2027,4,30) and (row[5]=='已核准' or (row[5]=='补交中' and row[6]=='是')) and balance>=900:
            retained.append((row,balance))
    def grouped(records):
        sums={}
        for row,balance in records:
            total,count=sums.get(row[1],(D(0),0));sums[row[1]]=(total+balance,count+1)
        return [[key,number(total),str(count)] for key,(total,count) in sorted(sums.items(),key=lambda x:(-x[1][0],x[0]))]
    rows=grouped(retained);short=grouped([(row,b) for row,b in retained if D(row[2])>=2500])
    assert len(rows)==3 and len(short)==3 and rows!=short
    cases=[{'id':'claims_first_scope','prompt':'合并采购二部和采购一部的登记表，保持这个合并顺序。先按ClaimID保留原表首次记录，之后只看BookedOn在2027-04-01至2027-04-30且含两端的记录，状态为已核准，或者状态为补交中并且可预付为是。待付按申请额减Settled计算，只看待付不少于900元的。按Team汇总待付合计和票数，按待付合计降序；只要Team、待付合计、票数三列，写Word说明，不添加审批结论。',
            'rows':rows,'word':True,'word_numbers':[r[1] for r in rows]},
           {'id':'claims_record_followup','parent':'claims_first_scope','prompt':'只统计单笔申请额不少于2500元的原始登记，仍按Team汇总，其余条件和输出列不变。这次只要表格，不要Word。','rows':short,'word':False}]
    masses=[['B81','可寄送','1.65','250','甲'],['B82','暂停','2.1','100','乙'],['B83','可寄送','.95','150','甲'],
            ['B84','可寄送','2.4','700','丙'],['B85','可寄送','1.1','100','乙'],['B86','待核','3.2','300','甲'],['B87','可寄送','1.28','80','丙']]
    rng.shuffle(masses);book=Workbook();sheet=book.active;sheet.title='称量';sheet.append(['样品称量 虚构记录']);sheet.append([])
    for cell,value in [('A3','Batch'),('B3','处理标记'),('C3','称量'),('E3','委托组'),('C4','GrossMass（kg）'),('D4','TareMass（g）')]:sheet[cell]=value
    for area in ['A3:A4','B3:B4','C3:D3','E3:E4']:sheet.merge_cells(area)
    for batch,state,gross,tare,team in masses:sheet.append([batch,state,float(D(gross)),float(D(tare)),team])
    book.save(folder/'样品称量.xlsx')
    selected=[(r[0],D(r[2])*1000-D(r[3])) for r in masses if r[1]=='可寄送' and D(r[2])*1000-D(r[3])>=1000]
    mass_rows=[[batch,number(net/1000)] for batch,net in sorted(selected)];mass_total=number(sum((net for _,net in selected),D(0))/1000)
    cases.append({'id':'samples_multilevel_mass','prompt':'只处理样品称量.xlsx的称量表，处理标记必须为可寄送。净寄重按GrossMass减TareMass计算，只保留净寄重不少于1千克的，按Batch升序；只留Batch和净寄重两列，净寄重以kg显示。每条明细保留，另外给净寄重合计和条数，再写一段寄送说明并导出Word。',
                  'rows':mass_rows,'summary_values':[mass_total,str(len(selected))],'word':True,'word_numbers':[mass_total]})
    followups=[['项目支持','2027-05-01','已完成','外部','45分钟'],['项目支持','2027-05-10','复核通过','转介','1.5小时'],['项目支持','2027-05-20','复核通过','其他','60分钟'],
               ['行政联络','2027-05-31','已完成','其他','2小时'],['行政联络','2027-05-03','复核通过','转介','30分钟'],['行政联络','2027-05-14','草稿','转介','100分钟'],
               ['技术协作','2027-05-20','已完成','外部','75分钟'],['技术协作','2027-05-31','复核通过','转介','45分钟'],['技术协作','2027-04-30','已完成','外部','300分钟'],['项目支持','2027-06-01','已完成','外部','15分钟']]
    rng.shuffle(followups)
    with (folder/'跟进记录.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['跟进记录 虚构资料']);writer.writerow([]);writer.writerow(['组别','登记日','跟进状态','来源','用时']);writer.writerows(followups)
    sums={}
    for team,day,state,origin,duration in followups:
        if not (date(2027,5,1)<=date.fromisoformat(day)<=date(2027,5,31) and (state=='已完成' or (state=='复核通过' and origin=='转介'))):continue
        value=D(duration.removesuffix('分钟').removesuffix('小时'))*(60 if duration.endswith('小时') else 1)
        total,count=sums.get(team,(D(0),0));sums[team]=(total+value,count+1)
    hours=[[team,str(count),number(total/60)] for team,(total,count) in sorted(sums.items(),key=lambda x:(-x[1][0],x[0]))]
    cases.append({'id':'followup_implicit_or_hours','prompt':'把跟进记录.csv中2027年5月的记录按组别统计，包含月初和月底。只算已完成的，或复核通过并且来源为转介的记录。每组给记录数和用时合计，用小时显示，按用时合计从多到少；只要组别、记录数、用时合计三列，不生成文稿。','rows':hours,'word':False})
    (DEST/'tasks.json').write_text(json.dumps({'seed':SEED,'scope':'Second-phase developer-authored fictional inputs; no model-generated expectations.','cases':cases},ensure_ascii=False,indent=2)+'\n')
    paths=[p for p in DEST.rglob('*') if p.is_file()]
    frozen={'created_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'seed':SEED,'model_runs_at_creation':0,'case_count':len(cases),
            'input_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'scope':'Different bilingual money/order, multilevel mass and implicit-category duration tasks. Developer synthesis, not independent user research. First-phase0/4 retained separately; no tuning on these model outcomes.'}
    (ROOT/'qa/v0.22/confirmation-input-freeze.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    print('Frozen second4-goal confirmation inputs; no model execution.')


if __name__=='__main__':main()
