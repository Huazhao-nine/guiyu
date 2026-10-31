"""Verify monetary subexpressions of an already executed bounded calculator call.

Uses the same allowlisted rational calculator, never eval. Unit propagation is
conservative: money*scalar, money/scalar, or same-currency addition/subtraction.
Unknown/mixed units and repeating intermediate values do not authorize amounts.
"""
import ast
from decimal import Decimal, InvalidOperation
from general_tools import run_tool


def verified_subtotals(expression, known_amounts):
    try:
        run_tool('calculate',{'expression':expression})
        tree=ast.parse(expression,mode='eval')
    except (ValueError,SyntaxError,TypeError):return []
    units={}
    for amount in known_amounts:
        units.setdefault(amount['value'],set()).add(amount['unit'])
    checked=[]
    def walk(node):
        if isinstance(node,ast.Expression):return walk(node.body)
        literal=ast.get_source_segment(expression,node)
        result=run_tool('calculate',{'expression':literal})['data']
        try:value=Decimal(result['exact_result'])
        except InvalidOperation:return None,None
        if isinstance(node,ast.Constant):
            candidates=units.get(value,set())
            return value,next(iter(candidates)) if len(candidates)==1 else 'scalar' if not candidates else None
        if isinstance(node,ast.UnaryOp):return value,walk(node.operand)[1]
        if not isinstance(node,ast.BinOp):return value,None
        _,left=walk(node.left);_,right=walk(node.right);unit=None
        if isinstance(node.op,(ast.Add,ast.Sub)) and left==right:unit=left
        if isinstance(node.op,ast.Mult):
            if left=='scalar':unit=right
            elif right=='scalar':unit=left
        if isinstance(node.op,ast.Div):
            if right=='scalar':unit=left
            elif left==right and left is not None:unit='scalar'
        if unit in ('元','USD'):
            checked.append({'expression':literal,'value':str(value),'unit':unit})
        return value,unit
    walk(tree)
    return checked
