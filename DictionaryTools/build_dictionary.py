# -*- coding: utf-8 -*-
"""glossary.md + english_glossary.json -> preserve_dictionary.json

이 폴더만 있으면 돌아갑니다. Python 3 로 실행하세요.

  python build_dictionary.py

기존 preserve_dictionary.json 이 있으면 preserveTerms 와 settings 는
그대로 물려받고 translateTerms 를 한·영 쌍으로 다시 만듭니다.
"""
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, 'glossary.md')
EN = os.path.join(HERE, 'english_glossary.json')
OUT = os.path.join(HERE, 'preserve_dictionary.json')

CYR = 'Ѐ-ӿ'

# 러시아어 명사 격변화 어미
ENDINGS = ('', 'а', 'я', 'ы', 'и', 'е', 'у', 'ю', 'ой', 'ей', 'ом', 'ем',
           'ам', 'ям', 'ами', 'ями', 'ах', 'ях', 'ов', 'ев')
VOWELS = 'аяоеёыиуюьй'

# 형용사는 어미가 두 글자라 명사 규칙으로는 어간을 잘못 만든다
ADJ_TAIL = ('ый', 'ий', 'ой', 'ая', 'ое', 'ые')
ADJ_ENDINGS = ('ый', 'ий', 'ой', 'ым', 'им', 'ом', 'ого', 'его', 'ому', 'ему',
               'ых', 'их', 'ыми', 'ими', 'ая', 'ую', 'ое', 'ее', 'ые', 'ие')

HEADER_KO = ('preserveTerms 는 번역하지 않고 원형을 유지할 단어입니다 (기존 동작 그대로). '
             'translateTerms 는 러시아어 게임 용어를 ko/en 목표어로 바꿔 넣을 매핑입니다. '
             '키는 전부 소문자이며 러시아어 격변화형이 자동 확장되어 있습니다. '
             '수정은 glossary.md 를 고친 뒤 build_dictionary.py 를 다시 돌리세요.')
HEADER_EN = ('preserveTerms keeps the original spelling (unchanged behaviour). '
             'translateTerms maps Russian tank-game slang to ko/en values; keys are '
             'lowercase and Russian case forms are pre-expanded. Regenerate from '
             'glossary.md and english_glossary.json with build_dictionary.py.')

DEFAULT_EXACT = {
    # Safe whole-message overrides.  They are intentionally not inserted into
    # longer sentences because short chat abbreviations can be grammatical.
    'гг': {'ko': 'ㅈㅈ', 'en': 'gg'},
    'лт': {'ko': '경전차', 'en': 'light tank'},
}


def inflect(word):
    """어간에 격변화 어미를 붙인 형태들. 짧은 약어(бб, лт)는 건드리지 않는다."""
    if len(word) < 4 or not re.match('^[%s]+$' % CYR, word):
        return []
    for tail in ADJ_TAIL:
        if word.endswith(tail) and len(word) - len(tail) >= 4:
            stem = word[:-len(tail)]
            return [stem + e for e in ADJ_ENDINGS]
    stem = word[:-1] if word[-1] in VOWELS else word
    if len(stem) < 3:
        return []
    return [stem + e for e in ENDINGS]


def parse():
    """glossary.md 의 표에서 (러시아어, 한국어) 쌍을 뽑는다."""
    pairs, seen = [], set()
    for line in io.open(MD, encoding='utf-8'):
        line = line.strip()
        if not line.startswith('|') or line.startswith('|---'):
            continue
        cols = [c.strip() for c in line.strip('|').split('|')]
        if len(cols) < 3:
            continue
        src, variants, ko = cols[0], cols[1], cols[2]
        note = cols[3] if len(cols) > 3 else ''
        # [off] 는 플레이스홀더로 쓰면 문장 구조를 깨는 항목 (동사·인사말)
        if '[off]' in note:
            continue
        if not src or not ko or src == '러시아어' or ko == '한국어':
            continue
        if not re.search('[%s]' % CYR, src):
            continue
        forms = [src] + [v.strip() for v in variants.split(',') if v.strip()]
        # 손으로 적은 형태가 자동 생성분보다 우선한다
        for f in forms:
            f = f.lower()
            if f and f not in seen:
                seen.add(f)
                pairs.append((f, ko))
        for f in list(forms):
            for g in inflect(f.lower()):
                if g not in seen:
                    seen.add(g)
                    pairs.append((g, ko))
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


def main():
    pairs = parse()
    with io.open(EN, encoding='utf-8-sig') as f:
        english = json.load(f)
    missing = sorted(set(ko for _ru, ko in pairs) - set(english))
    if missing:
        raise ValueError('english_glossary.json missing: %s' % ', '.join(missing))
    terms = {}
    for ru, ko in pairs:
        key = ru.lower()
        pair = {'ko': ko, 'en': english[ko]}
        terms.setdefault(key, pair)
        # settings.normalizeYo 가 켜지면 조회 키에서 ё 가 е 로 바뀐다.
        # 양쪽 다 넣어 두면 설정과 무관하게 맞는다.
        yo = key.replace('ё', 'е')
        if yo != key:
            terms.setdefault(yo, pair)

    base = {}
    if os.path.exists(OUT):
        with io.open(OUT, encoding='utf-8-sig') as f:
            base = json.load(f)

    out = {
        '_comment_ko': HEADER_KO,
        '_comment_en': HEADER_EN,
        'version': 3,
        'settings': base.get('settings') or {
            'enabled': True, 'caseInsensitive': True,
            'normalizeYo': True, 'matchWholeWords': True,
        },
        'preserveTerms': base.get('preserveTerms') or [],
        'translateTerms': terms,
        'exactTranslations': base.get('exactTranslations') or DEFAULT_EXACT,
    }
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))

    size = os.path.getsize(OUT)
    print('preserveTerms  : %d' % len(out['preserveTerms']))
    print('translateTerms : %d' % len(terms))
    print('exactTerms     : %d' % len(out['exactTranslations']))
    print('written %s (%.1f KB)' % (OUT, size / 1024.0))
    assert size <= 1048576, 'PRESERVE_DICTIONARY_MAX_BYTES(1MiB) 초과'
    assert len(terms) + len(out['preserveTerms']) <= 10000, \
        'PRESERVE_DICTIONARY_MAX_TERMS(10000) 초과'
    print('limits ok (max 1MiB / 10000 terms)')


if __name__ == '__main__':
    main()
