# -*- coding: utf-8 -*-
"""Verify the bilingual dictionary against the actual mod implementation.

Run with Python 3:

    python verify_dictionary.py
    python verify_dictionary.py --online

The optional online pass sends masked samples to the primary Google endpoint
used by the mod and checks that every placeholder is restored.
"""
from __future__ import print_function

import importlib.util
import json
import os
import sys
import time


HERE = os.path.dirname(os.path.abspath(__file__))


def find_file(candidates):
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise IOError('file not found: %r' % (candidates,))


SOURCE = find_file([
    os.path.join(HERE, '..', 'mod_TonymocchiChatTranslator_KO.py'),
    os.path.join(HERE, '..', 'Source', 'mod_TonymocchiChatTranslator_KO.py'),
])
DICTIONARY = find_file([
    os.path.join(HERE, 'preserve_dictionary.json'),
    os.path.join(HERE, '..', 'preserve_dictionary.json'),
    os.path.join(HERE, '..', 'Config', 'preserve_dictionary.json'),
])


def load_module():
    spec = importlib.util.spec_from_file_location('tmcx_verify_mod', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with open(DICTIONARY, 'rb') as stream:
        count = module.load_preserve_dictionary(stream.read())
    return module, count


HIT = [
    (u'да тут вся чепуха на голде', u'골탄', u'premium ammo'),
    (u'голды нет у меня', u'골탄', u'premium ammo'),
    (u'стреляй голдой', u'골탄', u'premium ammo'),
    (u'нужно бб и фугасы', u'은탄', u'standard ammo'),
    (u'арту убили сразу', u'자주포', u'SPG'),
    (u'бронебойным бей в борт', u'은탄', u'standard ammo'),
    (u'в кустах сижу жду', u'수풀', u'bush'),
    (u'гусеницу сбили', u'궤도', u'track'),
    (u'на базу идите', u'기지', u'base'),
]
MISS = [
    u'я иду домой', u'сегодня хорошая погода', u'полностью согласен',
    u'половина команды слилась', u'светлое будущее', u'артист выступает',
    u'базовый набор', u'поле зрения маленькое', u'что ты делаешь',
    u'как дела друг', u'надо было раньше', u'он меня не видит',
]


def translate_online(text, target):
    import urllib.parse
    import urllib.request
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36'
    url = ('https://clients5.google.com/translate_a/t?client=dict-chrome-ex'
           '&sl=ru&tl=%s&q=%s' %
           (target, urllib.parse.quote(text.encode('utf-8'), '')))
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8'))
    return data[0] if isinstance(data[0], str) else str(data)


def main():
    module, count = load_module()
    failures = 0
    print('loaded %d effective entries (%d bilingual inflection keys)' %
          (count, len(module._dictionary_translations)))

    for source, expected_ko, expected_en in HIT:
        for target, expected in (('ko', expected_ko), ('en', expected_en)):
            _masked, replacements = module.protect_dictionary_terms(source, target)
            if expected not in replacements:
                print('FAIL %s %s -> %r' % (target, source, replacements))
                failures += 1
            else:
                print('ok   %s %-34s -> %s' %
                      (target, source, ', '.join(replacements)))

    for source in MISS:
        _masked, replacements = module.protect_dictionary_terms(source, 'ko')
        if replacements:
            print('FAIL false match %-34s -> %r' % (source, replacements))
            failures += 1

    masked, replacements = module.protect_dictionary_terms(
        u'нужно бб и фугасы в C8', 'ko')
    if module.restore_dictionary_terms(masked, replacements) is None:
        print('FAIL normal placeholder restore')
        failures += 1
    if module.restore_dictionary_terms(u'broken', replacements) is not None:
        print('FAIL broken placeholder was accepted')
        failures += 1

    if '--online' in sys.argv:
        for target in ('ko', 'en'):
            for source, _ko, _en in HIT[:5]:
                masked, replacements = module.protect_dictionary_terms(source, target)
                output = module.restore_dictionary_terms(
                    translate_online(masked, target), replacements)
                print('%s %s\n  -> %s' % (target, source, output))
                if output is None:
                    failures += 1
                time.sleep(0.3)

    print('ALL PASS' if not failures else 'FAILED (%d)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
