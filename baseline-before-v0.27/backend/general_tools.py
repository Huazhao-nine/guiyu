"""Small deterministic tools for a local assistant, with no file or process access.

``run_tool(name, arguments, *, now=None)`` returns JSON-compatible dictionaries
containing ``tool``, ``summary``, ``data`` and ``audit``. Invalid requests raise
``ValueError``; no partial result is returned.

calculate: {"expression": "(120.5 + 30) / 3", "precision": 2}
    precision is optional (0..8); rounding is ROUND_HALF_UP. Decimal literals
    are read from the original source, never from Python's binary float value.
    Exact rational arithmetic preserves all digits before the final Decimal
    conversion. ``exact_result`` is a finite decimal or a fraction such as 1/3;
    ``result`` is display-ready, and ``exact`` reports whether it is exact.
    Without a requested precision, repeating decimals display 8 decimal places;
    exact terminating decimals are preserved in full.

calendar: {"operation": "date_info", "date": "2026-10-22"}
          {"operation": "date_difference", "start": "2026-10-22", "end": "2026-10-31"}
          {"operation": "date_shift", "date": "2026-10-22", "days": 9}
          {"operation": "week_date", "date": "2026-10-22", "week_offset": 1, "weekday": 5}
    date is optional for date_info/date_shift/week_date and defaults to the local current
    date. now can inject a date, datetime, or strict ISO date for reproducibility.
    Differences use end - start: exclude the start date and include the end date;
    equal dates yield 0, and reversed dates produce a negative interval. These
    are calendar days, not working days or jurisdiction-specific holidays.
    week_date uses ISO weeks (Monday..Sunday); week_offset 0 is the reference
    date's week, 1 is next week, and weekday 1..7 selects Monday..Sunday.
"""
from __future__ import annotations

import ast
import calendar as _calendar
from datetime import date, datetime, timedelta
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
import re


MAX_EXPRESSION_LENGTH = 512
MAX_AST_NODES = 128
MAX_DEPTH = 20
MAX_OPERATIONS = 32
MAX_LITERAL_DIGITS = 32
MAX_FRACTION_BITS = 1024
MAX_INTERVAL_DAYS = 36500
WORKING_PRECISION = 80
DEFAULT_REPEATING_PLACES = 8
_MAGNITUDE_LIMIT = Fraction(10 ** 96)
_DECIMAL_LITERAL = re.compile(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z')
_ISO_DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}\Z')
_WEEKDAYS = ('星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日')
_INTERVAL_POLICY = '按日历天计算，不计起始日、计入结束日；同日为0，倒序为负。'


def _arguments(value, required, optional=()):
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError('工具参数必须是 JSON 对象。')
    if set(value) - (set(required) | set(optional)) or set(required) - set(value):
        raise ValueError('工具参数包含未知字段或缺少必要字段。')
    return value


def _integer(value, label, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'{label}需要是 {lower} 至 {upper} 之间的整数。')
    return value


def _bounded_fraction(value):
    if (value.numerator.bit_length() > MAX_FRACTION_BITS
            or value.denominator.bit_length() > MAX_FRACTION_BITS
            or abs(value) > _MAGNITUDE_LIMIT
            or (value and abs(value) < 1 / _MAGNITUDE_LIMIT)):
        raise ValueError('计算中的数值过大或精度过高，请拆分计算。')
    return value


class _Arithmetic(ast.NodeVisitor):
    """Evaluate a tiny AST allowlist; the Python evaluator is never invoked."""

    def __init__(self, source):
        self.source = source
        self.operands = []
        self.operations = 0
        self.depth = 0

    def visit(self, node):
        self.depth += 1
        try:
            if self.depth > MAX_DEPTH:
                raise ValueError('计算括号或运算嵌套过深。')
            return super().visit(node)
        finally:
            self.depth -= 1

    def generic_visit(self, node):
        raise ValueError('只支持数字、加减乘除和括号。')

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        literal = ast.get_source_segment(self.source, node)
        if (type(node.value) not in (int, float) or not isinstance(literal, str)
                or not _DECIMAL_LITERAL.fullmatch(literal)):
            raise ValueError('只支持普通十进制数字。')
        if sum(c.isdigit() for c in literal) > MAX_LITERAL_DIGITS:
            raise ValueError('单个数字最多支持32位十进制数字。')
        value = Decimal(literal)
        if not value.is_finite():
            raise ValueError('计算不能包含非有限数字。')
        self.operands.append(literal)
        return _bounded_fraction(Fraction(value))

    def _operation(self):
        self.operations += 1
        if self.operations > MAX_OPERATIONS:
            raise ValueError('一次计算的运算过多，请拆分计算。')

    def visit_UnaryOp(self, node):
        if type(node.op) not in (ast.UAdd, ast.USub):
            raise ValueError('只支持数字前的正负号。')
        self._operation()
        value = self.visit(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value

    def visit_BinOp(self, node):
        if type(node.op) not in (ast.Add, ast.Sub, ast.Mult, ast.Div):
            raise ValueError('只支持加减乘除，不支持幂、取余或整除。')
        self._operation()
        left, right = self.visit(node.left), self.visit(node.right)
        if isinstance(node.op, ast.Add):
            value = left + right
        elif isinstance(node.op, ast.Sub):
            value = left - right
        elif isinstance(node.op, ast.Mult):
            value = left * right
        else:
            if right == 0:
                raise ValueError('除数不能为0。')
            value = left / right
        return _bounded_fraction(value)


def _finite_decimal(value):
    """Format a terminating fraction without rounding; return None for repeats."""
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return None
    scale = max(twos, fives)
    scaled = abs(value.numerator) * (10 ** scale // value.denominator)
    digits = str(scaled).rjust(scale + 1, '0')
    result = digits if not scale else (digits[:-scale] + '.' + digits[-scale:]).rstrip('0').rstrip('.')
    return ('-' if value < 0 else '') + result


def _calculate(arguments):
    _arguments(arguments, ('expression',), ('precision',))
    expression = arguments['expression']
    if not isinstance(expression, str) or not 1 <= len(expression) <= MAX_EXPRESSION_LENGTH:
        raise ValueError('计算表达式需要是1至512个字符的文本。')
    expression = expression.strip()
    if not expression or not re.fullmatch(r'[0-9.\+\-*/() \t]+', expression):
        raise ValueError('只支持十进制数字、加减乘除和括号。')
    parenthesis_depth = 0
    for character in expression:
        if character == '(':
            parenthesis_depth += 1
            if parenthesis_depth > MAX_DEPTH:
                raise ValueError('计算括号或运算嵌套过深。')
        elif character == ')':
            parenthesis_depth -= 1
    precision = arguments.get('precision')
    if 'precision' in arguments:
        _integer(precision, '小数位数', 0, 8)
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError('计算表达式格式不正确。') from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise ValueError('一次计算的表达式过于复杂，请拆分计算。')
    evaluator = _Arithmetic(expression)
    fraction = evaluator.visit(tree)
    finite = _finite_decimal(fraction)
    exact_result = finite if finite is not None else f'{fraction.numerator}/{fraction.denominator}'
    display_places = precision if precision is not None else DEFAULT_REPEATING_PLACES if finite is None else None
    with localcontext(Context()) as context:
        # Up to 96 integer digits plus rounding places are admitted above.
        context.prec = max(WORKING_PRECISION, len(str(abs(fraction.numerator))) + 16)
        decimal_value = Decimal(fraction.numerator) / Decimal(fraction.denominator)
        if display_places is not None:
            result = format(decimal_value.quantize(Decimal(1).scaleb(-display_places), rounding=ROUND_HALF_UP), 'f')
        else:
            result = finite
    if Decimal(result) == 0:
        result = result.lstrip('-')
    exact = Fraction(Decimal(result)) == fraction
    display = expression.replace('*', '×').replace('/', '÷')
    marker = '=' if exact else '≈'
    summary = f'{display} {marker} {result}'
    if not exact:
        summary += f'（精确值：{exact_result}）'
    return {
        'tool': 'calculate', 'summary': summary,
        'data': {'expression': expression, 'display_expression': display, 'result': result,
                 'exact_result': exact_result, 'exact': exact, 'precision': precision,
                 'display_decimal_places': display_places,
                 'rounding': 'ROUND_HALF_UP' if display_places is not None else None},
        'audit': {'schema_version': 1, 'operands': evaluator.operands,
                  'operations': evaluator.operations, 'local_only': True,
                  'arithmetic': 'Decimal literals with exact rational arithmetic',
                  'default_repeating_places': DEFAULT_REPEATING_PLACES if finite is None and precision is None else None,
                  'exact_fraction': {'numerator': str(fraction.numerator), 'denominator': str(fraction.denominator)}}
    }


def _date(value, label='日期'):
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ValueError(f'{label}需要是 YYYY-MM-DD 格式的有效日期。')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f'{label}需要是 YYYY-MM-DD 格式的有效日期。') from exc


def _today(now):
    if now is None:
        return datetime.now().astimezone().date()
    if isinstance(now, datetime):
        return now.date()
    if isinstance(now, date):
        return now
    return _date(now, '参考日期')


def _date_fields(value):
    return {'date': value.isoformat(), 'weekday': _WEEKDAYS[value.weekday()],
            'weekday_index': value.isoweekday(), 'is_weekend': value.weekday() >= 5,
            'is_leap_year': _calendar.isleap(value.year)}


def _calendar_tool(arguments, now):
    if not isinstance(arguments, dict):
        raise ValueError('工具参数必须是 JSON 对象。')
    operation = arguments.get('operation')
    if operation not in ('date_info', 'date_difference', 'date_shift', 'week_date'):
        raise ValueError('日期工具仅支持查询日期、计算间隔、按天移动和查询某周的日期。')
    audit = {'schema_version': 1, 'local_only': True, 'calendar': 'Gregorian', 'day_unit': 'calendar_days'}
    if operation == 'date_difference':
        _arguments(arguments, ('operation', 'start', 'end'))
        start, end = _date(arguments['start'], '起始日期'), _date(arguments['end'], '结束日期')
        days = (end - start).days
        if abs(days) > MAX_INTERVAL_DAYS:
            raise ValueError('日期间隔最多支持36500天，请拆分计算。')
        data = {'operation': operation, 'start': start.isoformat(), 'end': end.isoformat(),
                'days': days, 'absolute_days': abs(days), 'counting_policy': _INTERVAL_POLICY,
                'start_weekday': _WEEKDAYS[start.weekday()], 'end_weekday': _WEEKDAYS[end.weekday()]}
        summary = f'从 {start.isoformat()} 到 {end.isoformat()} 相隔 {days} 天。{_INTERVAL_POLICY}'
        audit.update({'inputs': {'start': start.isoformat(), 'end': end.isoformat()},
                      'start_included': False, 'end_included': True, 'signed': True})
    else:
        required = {'date_info': ('operation',), 'date_shift': ('operation', 'days'),
                    'week_date': ('operation', 'week_offset', 'weekday')}[operation]
        _arguments(arguments, required, ('date',))
        current = _date(arguments['date']) if 'date' in arguments else _today(now)
        audit.update({'inputs': {'date': current.isoformat()}, 'used_reference_date': 'date' not in arguments})
        if operation == 'date_info':
            data = {'operation': operation, **_date_fields(current)}
            summary = f'{current.isoformat()} 是 {data["weekday"]}。'
        elif operation == 'date_shift':
            days = _integer(arguments['days'], '移动天数', -MAX_INTERVAL_DAYS, MAX_INTERVAL_DAYS)
            try:
                target = current + timedelta(days=days)
            except OverflowError as exc:
                raise ValueError('移动后的日期超出公历支持的年份范围。') from exc
            data = {'operation': operation, 'start': current.isoformat(), 'days': days,
                    'target_date': target.isoformat(), **_date_fields(target)}
            summary = f'{current.isoformat()} 移动 {days} 天后是 {target.isoformat()}（{data["weekday"]}）。'
            audit['inputs']['days'] = days
        else:
            week_offset = _integer(arguments['week_offset'], '相对周数', -52, 52)
            weekday = _integer(arguments['weekday'], '星期序号', 1, 7)
            try:
                target = current + timedelta(days=week_offset * 7 + weekday - current.isoweekday())
            except OverflowError as exc:
                raise ValueError('目标日期超出公历支持的年份范围。') from exc
            data = {'operation': operation, 'reference_date': current.isoformat(),
                    'week_offset': week_offset, 'target_date': target.isoformat(), **_date_fields(target)}
            week_label = '本周' if week_offset == 0 else '下周' if week_offset == 1 else '上周' if week_offset == -1 else f'相对第{week_offset}周'
            summary = f'以 {current.isoformat()} 为参考，{week_label}{data["weekday"]}是 {target.isoformat()}。'
            audit['inputs'].update({'week_offset': week_offset, 'weekday': weekday})
            audit['week_policy'] = 'ISO周从星期一开始；相对周数0为参考日期所在周，1为下周。'
    return {'tool': 'calendar', 'summary': summary, 'data': data, 'audit': audit}


def run_tool(name, arguments, *, now=None):
    """Run one validated, bounded, local tool. Invalid input raises ValueError."""
    if name == 'calculate':
        return _calculate(arguments)
    if name == 'calendar':
        return _calendar_tool(arguments, now)
    raise ValueError('未知本地工具。')
