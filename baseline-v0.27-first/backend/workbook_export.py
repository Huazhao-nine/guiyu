"""Editable typed Excel copies, formula-safe CSV and independent cell readback."""
import csv
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path
import re
from workbook_data import profile
from table_program import number,calendar_date,calendar_text,decimal_text


PLAIN=re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)')


def safe_text(value,escape):
    text=str(value)
    return text if PLAIN.fullmatch(text.strip()) else escape(text)


def typed_value(value,column,kind,escape):
    text=str(value).strip()
    if not text:return '',None
    if kind=='date':
        normalized=calendar_text(text)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',normalized):return safe_text(normalized,escape),None
        return calendar_date(normalized),'yyyy-mm-dd'
    if kind=='number':
        cleaned=text.replace(',','')
        percent=cleaned.endswith(('%','％')) or '%' in column or '％' in column
        literal=cleaned.rstrip('%％') if percent else cleaned
        if PLAIN.fullmatch(literal) and len(Decimal(literal).as_tuple().digits)<=15:
            dec=number(cleaned) if cleaned.endswith(('%','％')) else Decimal(literal)/(100 if percent else 1)
            # Excel has a 15-digit numeric limit. Exact larger values stay text.
            return float(dec),'0.00######%' if percent else '#,##0.00######' if re.search(r'金额|成本|单价|元|USD|均值|平均',column,re.I) else '#,##0.########'
    return safe_text(value,escape),None


def display(value,formatting=''):
    if value is None:return ''
    if isinstance(value,(date,datetime)):return value.strftime('%Y-%m-%d')
    if isinstance(value,(int,float,Decimal)):
        numeric=Decimal(str(value))
        return decimal_text(numeric*100)+'%' if '%' in formatting else decimal_text(numeric)
    return str(value)


def expected_cells(table,escape):
    kinds={f['column']:f['type'] for f in profile(table)['fields']}
    return [[safe_text(c,escape) for c in table['columns']]]+[
        [_expected(v,c,kinds[c],escape) for c,v in zip(table['columns'],r)] for r in table['rows']]


def _expected(value,c,kind,escape):
    v,fmt=typed_value(value,c,kind,escape)
    return display(v,fmt or '')


def read_cells(book,sheet_name):
    return [[display(c.value,c.number_format) for c in row] for row in book[sheet_name].iter_rows()]


def export_copies(path,csvpath,table,audit,escape):
    from openpyxl import Workbook,load_workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    book=Workbook();book.remove(book.active)
    def fill(name,data,typed=True):
        sheet=book.create_sheet(name);cols=data['columns']
        kinds={f['column']:f['type'] for f in profile(data)['fields']} if typed else {}
        sheet.append([safe_text(c,escape) for c in cols])
        for row in data['rows']:
            sheet.append([None]*len(cols))
            for i,(c,value) in enumerate(zip(cols,row),1):
                converted,fmt=typed_value(value,c,kinds.get(c,'text'),escape)
                cell=sheet.cell(sheet.max_row,i,converted)
                if fmt:cell.number_format=fmt
        for cell in sheet[1]:cell.font=Font(name='PingFang SC',bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='315E51')
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width=min(48,max(18,len(str(col[0].value))*2+4))
            for cell in col:cell.alignment=Alignment(wrap_text=True,vertical='top')
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
    fill('处理结果',table)
    for i,s in enumerate(table.get('summaries',[]),1):fill('汇总'+str(i),s)
    fill('来源核对',{'columns':['结果行','来源文件','来源工作表','原始行'],'rows':audit},False)
    book.save(path);Path(path).chmod(0o600)
    expected_csv=[[safe_text(v,escape) for v in r] for r in [table['columns']]+table['rows']]
    with Path(csvpath).open('w',encoding='utf-8-sig',newline='') as stream:csv.writer(stream).writerows(expected_csv)
    Path(csvpath).chmod(0o600)
    reopened=load_workbook(path,read_only=True,data_only=False)
    try:
        if read_cells(reopened,'处理结果')!=expected_cells(table,escape):raise ValueError('Excel单元格与处理结果不一致，未交付。')
        for i,s in enumerate(table.get('summaries',[]),1):
            if read_cells(reopened,'汇总'+str(i))!=expected_cells(s,escape):raise ValueError('汇总页与计算结果不一致，未交付。')
    finally:reopened.close()
    with Path(csvpath).open(encoding='utf-8-sig',newline='') as stream:
        if list(csv.reader(stream))!=expected_csv:raise ValueError('CSV副本与处理结果不一致，未交付。')
