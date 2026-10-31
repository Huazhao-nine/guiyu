"""Local JSON structure constraints for deterministic MLX generation.

This restricts syntax/shape only.  Source, numeric, unit and permission checks
remain in the tools.  No remote service or generated code is evaluated.
"""
import json
import time


class StructureError(ValueError):
    pass


class JSONGrammar:
    """A bounded JSON-schema subset with canonical property order."""
    def __init__(self, schema):
        import regex
        self.definitions = schema.get('$defs', {})
        if len(self.definitions) > 256:
            raise StructureError('结构定义过多。')
        self.names = {key: 'R'+str(i) for i, key in enumerate(self.definitions)}
        definitions = ''.join('(?<'+self.names[key]+'>'+self.pattern(value)+')'
                              for key, value in self.definitions.items())
        pattern = r'\s*'+self.pattern(schema)+r'\s*'
        if definitions:
            pattern = '(?(DEFINE)'+definitions+')'+pattern
        if len(pattern) > 600000:
            raise StructureError('参数结构超过本机生成范围。')
        self.regex = regex.compile(pattern)

    def pattern(self, schema):
        import re
        if '$ref' in schema:
            key = schema['$ref'].removeprefix('#/$defs/')
            if key not in self.names:
                raise StructureError('结构引用未定义。')
            return '(?&'+self.names[key]+')'
        if 'const' in schema:
            return re.escape(json.dumps(schema['const'], ensure_ascii=False))
        if 'enum' in schema:
            values = schema['enum']
            if not values:
                return r'(?!)'
            return '(?:'+'|'.join(re.escape(json.dumps(v, ensure_ascii=False)) for v in values)+')'
        if 'oneOf' in schema:
            return '(?:'+'|'.join(self.pattern(v) for v in schema['oneOf'])+')'
        kind = schema.get('type')
        if isinstance(kind, list):
            return '(?:'+'|'.join(self.pattern(dict(schema, type=k)) for k in kind)+')'
        if kind == 'string':
            minimum = schema.get('minLength', 0)
            maximum = schema.get('maxLength', 240)
            if not 0 <= minimum <= maximum <= 2400:
                raise StructureError('文字参数长度超过范围。')
            excluded = schema.get('not', {})
            if not isinstance(excluded,dict) or set(excluded)-{'enum'}:
                raise StructureError('未支持的文字排除结构。')
            forbidden = excluded.get('enum', [])
            if len(forbidden)>512 or any(not isinstance(v,str) for v in forbidden):
                raise StructureError('文字排除值超过范围。')
            exclusion = '(?!(?:'+'|'.join(re.escape(json.dumps(v,ensure_ascii=False)) for v in forbidden)+'))' if forbidden else ''
            return exclusion+r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})){'+str(minimum)+','+str(maximum)+'}"'
        if kind in ('integer', 'number'):
            return r'-?(?:0|[1-9][0-9]*)'+(r'(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?' if kind == 'number' else '')
        if kind == 'boolean':
            return '(?:true|false)'
        if kind == 'null':
            return 'null'
        if kind == 'array':
            lo, hi = schema.get('minItems', 0), schema.get('maxItems', 16)
            if not 0 <= lo <= hi <= 40:
                raise StructureError('数组参数长度超过范围。')
            if hi == 0:
                return r'\[\s*\]'
            item = self.pattern(schema['items'])
            body = item+r'(?:\s*,\s*'+item+'){'+str(max(0, lo-1))+','+str(hi-1)+'}'
            return r'\[\s*'+('(?:'+body+')?' if lo == 0 else body)+r'\s*\]'
        if kind == 'object':
            props = schema.get('properties', {})
            required = set(schema.get('required', []))
            if not required <= set(props):
                raise StructureError('必需参数未定义。')
            if schema.get('additionalProperties', False) is not False:
                raise StructureError('生成结构必须显式列出参数。')
            # All emitted objects have a required first property.  Unit maps
            # use a list of field/unit pairs instead of unconstrained keys.
            if not props:
                return r'\{\s*\}'
            names = list(props)
            if names[0] not in required:
                raise StructureError('结构首项需要是必需参数。')
            pieces = []
            for i, name in enumerate(names):
                pair = re.escape(json.dumps(name, ensure_ascii=False))+r'\s*:\s*'+self.pattern(props[name])
                if i:
                    pair = r'\s*,\s*'+pair
                if name not in required:
                    pair = '(?:'+pair+')?'
                pieces.append(pair)
            return r'\{\s*'+''.join(pieces)+r'\s*\}'
        raise StructureError('未支持的结构参数类型。')

    def status(self, text):
        try:
            match = self.regex.fullmatch(text, partial=True, timeout=.05)
        except TimeoutError:
            raise StructureError('参数结构校验超时，未执行工具。')
        return match is not None, match is not None and not match.partial


class JSONLogitsProcessor:
    """Choose the highest-scoring legal continuation without a vocab scan.

    At temperature zero, finding a legal token in the top K gives exactly the
    same argmax as masking the whole vocabulary. K expands when necessary;
    an unrepresentable structure fails closed rather than generating freely.
    """
    def __init__(self, tokenizer, schema, prompt_tokens):
        self.tokenizer = tokenizer
        self.grammar = JSONGrammar(schema)
        self.prompt_tokens = prompt_tokens
        self.eos = set(getattr(tokenizer, 'eos_token_ids', ()) or ())
        if not self.eos and getattr(tokenizer, 'eos_token_id', None) is not None:
            self.eos.add(tokenizer.eos_token_id)
        self.special = set(getattr(tokenizer, 'all_special_ids', ()) or ())
        self.calls = self.checked = 0
        self.seconds = 0.

    def choose(self, generated, ranked):
        prefix = self.tokenizer.decode(generated)
        valid, complete = self.grammar.status(prefix)
        if not valid:
            raise StructureError('本地参数结构已偏离约束，未执行工具。')
        for identifier in ranked:
            self.checked += 1
            if identifier in self.eos:
                if complete:
                    return identifier
                continue
            if complete or identifier in self.special:
                continue
            candidate = self.tokenizer.decode(generated+[identifier])
            # No invisible/control-token loops; partial UTF-8 is accepted only
            # when decoding still advances a valid JSON prefix.
            stable = prefix.rstrip('\ufffd')
            if not candidate.startswith(stable):
                continue
            if candidate == prefix:
                if not prefix.endswith('\ufffd') or all(self.tokenizer.decode(generated[:i]) == prefix
                    for i in range(max(0, len(generated)-3), len(generated))):
                    continue
            if self.grammar.status(candidate)[0]:
                return identifier
        return None

    def __call__(self, tokens, logits):
        import mlx.core as mx
        started = time.perf_counter()
        generated = tokens.tolist()[self.prompt_tokens:]
        # MLX may compute one look-ahead step before yielding an EOS.  That
        # token is a terminator, not part of the JSON text being constrained.
        if generated and generated[-1] in self.eos:
            generated=generated[:-1]
        # MLX supplies a single batch.  Never mutate the model's tensor.
        flat = logits.reshape(-1)
        size = flat.size
        chosen = None
        if self.grammar.status(self.tokenizer.decode(generated))[1]:
            ids = mx.array(sorted(i for i in self.eos if 0 <= i < size))
            if ids.size:chosen=ids[mx.argmax(flat[ids])].item()
        for count in (() if chosen is not None else (32, 128, 512, 2048, size)):
            count = min(count, size)
            ids = mx.argpartition(flat, size-count)[-count:] if count < size else mx.arange(size)
            values = flat[ids]
            order = mx.argsort(values)[::-1]
            ranked = ids[order].tolist()
            chosen = self.choose(generated, ranked)
            if chosen is not None:
                break
        if chosen is None:
            raise StructureError('本地模型无法继续生成合法参数，未执行工具。')
        mask = mx.full(flat.shape, -float('inf'))
        mask[chosen] = flat[chosen]
        self.calls += 1
        self.seconds += time.perf_counter()-started
        return mask.reshape(logits.shape)
