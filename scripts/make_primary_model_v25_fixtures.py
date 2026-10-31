"""Freeze different office files and conversational goals before primary-model work."""
import csv
from datetime import datetime
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import random
from openpyxl import Workbook

ROOT=Path(__file__).resolve().parents[1]


def fmt(n):
    s=format(n,'f') if isinstance(n,D) else str(n)
    return s.rstrip('0').rstrip('.') if '.' in s else s


def main():
    dest=ROOT/'fixtures/primary_model_v25';assert not dest.exists()
    folder=dest/'workspace';folder.mkdir(parents=True)
    rng=random.Random(2026103025)
    early=[['W11','TeamAlpha',3000,1000,'2028-01-05','2028-02-01','已完成',False],
           ['W12','TeamBeta',1900,400,'2028-01-25','2028-02-29','待确认',True],
           ['W13','TeamAlpha',7000,0,'2028-01-10','2028-01-31','已完成',True],
           ['W14','TeamGamma',1200,700,'2028-02-03','2028-02-16','已完成',True],
           ['W15','TeamGamma',2100,1000,'2028-02-10','2028-02-20','待确认',False]]
    late=[['W11','TeamAlpha',30000,0,'2028-01-05','2028-02-20','已完成',True],
          ['W13','TeamAlpha',9999,0,'2028-01-10','2028-02-18','已完成',True],
          ['W16','TeamBeta',3500,500,'2028-02-02','2028-02-29','已完成',False],
          ['W17','TeamAlpha',2400,900,'2028-02-01','2028-02-07','待确认',True],
          ['W18','TeamGamma',1800,800,'2028-02-11','2028-02-21','已完成',False],
          ['W19','TeamBeta',4000,0,'2028-02-20','2028-03-01','已完成',True]]
    rng.shuffle(early);rng.shuffle(late)
    book=Workbook();book.remove(book.active)
    for name,records,scale,order,header in [('早班',early,1,list(range(8)),3),('晚班',late,1000,[6,0,5,2,1,7,3,4],5)]:
        sheet=book.create_sheet(name);sheet.append(['工单结算 虚构资料'])
        while sheet.max_row<header-1:sheet.append([''])
        labels=['TicketID','Team','Charge（'+('千元' if scale==1000 else '元')+'）','Paid（元）','OpenedOn','ClosedOn','Status','AllowAdvance']
        sheet.append([labels[i] for i in order])
        for row in records:
            vals=[row[0],row[1],float(D(row[2])/scale),row[3],datetime.fromisoformat(row[4]),datetime.fromisoformat(row[5]),row[6],row[7]]
            sheet.append([vals[i] for i in order])
    book.save(folder/'工单结算.xlsx')
    seen=set();totals={}
    for r in early+late:
        if r[0] in seen:continue
        seen.add(r[0]);balance=D(r[2])-D(r[3])
        if '2028-02-01'<=r[5]<='2028-02-29' and (r[6]=='已完成' or r[6]=='待确认' and r[7]) and balance>=700:
            amount,count=totals.get(r[1],(D(0),0));totals[r[1]]=amount+balance,count+1
    rows=[[name,fmt(amount),str(count)] for name,(amount,count) in sorted(totals.items(),key=lambda p:(-p[1][0],p[0]))]
    cases=[{'id':'tickets_dual_date_word','prompt':'处理工单结算.xlsx，按早班、晚班的顺序合并，先按TicketID保留首次记录。仅纳入ClosedOn在2028年2月整月的工单；Status为已完成，或者Status为待确认且AllowAdvance为是。待结金额按Charge减Paid，只纳入待结金额不少于700元的，按Team汇总待结合计和工单数，待结合计降序。只要Team、待结合计、工单数三列。生成Word，标题“二月工单待结说明”，不添加审批意见。','rows':rows,'word':True,'word_numbers':[r[1] for r in rows]},
           {'id':'ticket_team_followup','parent':'tickets_dual_date_word','prompt':'那TeamAlpha呢？其余计算标准照旧，这次只要表格。','rows':[r for r in rows if r[0]=='TeamAlpha'],'word':False}]
    visits=[['V01','沪区','2028-04-01','已完成','线下','60分钟'],['V02','沪区','2028-04-15','复核完成','线上','1.5小时'],
            ['V03','沪区','2028-04-18','复核完成','线下','3小时'],['V04','苏区','2028-04-30','已完成','其他','2小时'],
            ['V05','苏区','2028-04-08','复核完成','线上','45分钟'],['V06','浙区','2028-04-10','已完成','线上','30分钟'],
            ['V07','浙区','2028-04-27','复核完成','线上','1小时'],['V08','苏区','2028-03-31','已完成','线上','6小时'],
            ['V09','浙区','2028-05-01','已完成','线上','5小时'],['V10','沪区','2028-04-20','已完成','线上','']]
    rng.shuffle(visits)
    with (folder/'预约随访.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['预约随访 虚构资料']);w.writerow([]);w.writerow(['统计口径以用户要求为准']);w.writerow(['VisitID','Region','RecordedOn','Progress','Channel','Duration']);w.writerows(visits)
    totals={}
    for r in visits:
        if '2028-04-01'<=r[2]<='2028-04-30' and r[5] and (r[3]=='已完成' or r[3]=='复核完成' and r[4]=='线上'):
            h=D(r[5].removesuffix('分钟').removesuffix('小时'))/(60 if r[5].endswith('分钟') else 1)
            count,hours=totals.get(r[1],(0,D(0)));totals[r[1]]=count+1,hours+h
    rows=[[name,str(count),fmt(hours)] for name,(count,hours) in sorted(totals.items(),key=lambda p:(-p[1][1],p[0]))]
    cases += [{'id':'visits_range_duration','prompt':'从预约随访.csv中选取RecordedOn在2028-04-01至2028-04-30且Duration非空的记录；Progress为已完成，或者Progress为复核完成且Channel为线上。按Region统计记录数与时长合计，时长用小时显示。时长合计降序，同小时按Region升序，只要Region、记录数、时长合计三列，不生成文稿。','rows':rows,'word':False},
              {'id':'visit_region_followup','parent':'visits_range_duration','prompt':'把沪区单独列出来，其他处理规则不变，仍然只要表格。','rows':[r for r in rows if r[0]=='沪区'],'word':False}]
    inventory=[['PK01',True,9,5,30],['PK02',True,12,6,30],['PK03',True,10,1,30],['PK04',False,20,0,100],['PK05',True,5,4,50],['PK06',True,8,1,None],['PK07',True,4,6,80]]
    rng.shuffle(inventory);book=Workbook();s=book.active;s.title='包装物料';s.append(['包装物料 虚构资料'])
    for cell,value in [('A2','物料号'),('B2','启用'),('C2','数量'),('C3','计划'),('D3','在库'),('E2','UnitPrice（元）')]:s[cell]=value
    for area in ['A2:A3','B2:B3','C2:D2','E2:E3']:s.merge_cells(area)
    for r in inventory:s.append(r)
    book.save(folder/'包装物料.xlsx')
    chosen=[]
    for code,enabled,planned,current,price in inventory:
        if enabled and price is not None and planned>current:
            gap=D(planned)-D(current);cost=gap*D(price)
            if cost>=100:chosen.append([code,gap,cost])
    chosen.sort(key=lambda r:(-r[2],r[0]));rows=[[r[0],fmt(r[1]),fmt(r[2])] for r in chosen]
    cases += [{'id':'packaging_detail_word','prompt':'处理包装物料.xlsx的包装物料页，只看启用为是、UnitPrice非空且计划大于在库的记录。缺口是计划减在库，预计金额是缺口乘UnitPrice，只纳入预计金额不少于100元的。按预计金额降序，同金额按物料号升序，只保留物料号、缺口、预计金额，保留逐条明细并附加预计金额总额和条数。生成Word，标题“包装物料补充说明”，不添加采购日期或供应商。','rows':rows,'summary_values':[fmt(sum((r[2] for r in chosen),D(0))),str(len(rows))],'word_numbers':[fmt(sum((r[2] for r in chosen),D(0)))],'word':True},
              {'id':'identity_between_tasks','parent':'packaging_detail_word','chat':True,'prompt':'你是谁？请用一句话回答。'},
              {'id':'return_packaging_threshold','parent':'packaging_detail_word','conversation_parent':'identity_between_tasks','prompt':'回到刚才的库存任务，把预计金额门槛改为不少于150元，其他处理规则不变，这次只要表格。','rows':[[r[0],fmt(r[1]),fmt(r[2])] for r in chosen if r[2]>=150],'summary_values':[fmt(sum((r[2] for r in chosen if r[2]>=150),D(0))),str(sum(r[2]>=150 for r in chosen))],'word':False}]
    (dest/'tasks.json').write_text(json.dumps({'seed':2026103025,'scope':'Five first-use development goals and two reserved first-use conversation goals on the same frozen files. Not independent user research.','cases':cases},ensure_ascii=False,indent=2)+'\n')
    freeze={'time':datetime.now().astimezone().isoformat(),'development_ids':[r['id'] for r in cases[:5]],'reserved_goal_ids':[r['id'] for r in cases[5:]],'model_runs_at_freeze':0,
            'hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()},
            'gold_method':'Independent Decimal/date logic from fictional source records; no production table tools or model-generated answers.'}
    (ROOT/'qa/v0.25/input-freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'goals':len(cases),'tickets':cases[0]['rows'],'visits':cases[2]['rows'],'packaging':cases[4]['rows']},ensure_ascii=False))


if __name__=='__main__':main()
