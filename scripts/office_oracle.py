"""Small independent development oracle: negated source rules are not approvals."""
import re


def plain_markdown(text):
    return text.replace('**','').replace('__','')


def contains_wrong_claim(text,phrases):
    for clause in re.split(r'[，,。；;\n]',text):
        for phrase in phrases:
            for match in re.finditer(re.escape(phrase),clause):
                prefix=clause[:match.start()]
                if not re.search(r'(?:不得|不能|不应|不可|尚未|未获|并未|没有|并非|不代表)[^，,。；;\n]{0,12}$',prefix):
                    return True
    return False
