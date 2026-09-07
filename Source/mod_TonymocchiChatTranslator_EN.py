# -*- coding: utf-8 -*-
"""
Tonymocchi Chat Translator - Russian battle chat -> Korean / English.

Written for Mir Tankov (Мир танков) 1.4x, BigWorld Python 2.7.

Design notes
------------
* Nothing in this module may let an exception escape into the game. The gui
  Event dispatcher logs and RE-RAISES, which aborts every remaining subscriber
  of the same event. Every hook body is wrapped.
* No network call ever runs on the main thread. Requests go to a worker pool;
  results come back through a queue that is drained by a BigWorld.callback
  pump running on the main thread. BigWorld.* is never touched from a worker.
* The chat hook is discovered by introspection rather than by hard-coded class
  names, so a client patch that renames a controller does not break the mod.

Author: built to match the TonymocchiHitSound / TonymocchiHpBarPro conventions.
"""

from __future__ import absolute_import

import copy
import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
import types

try:
    import Queue as queue
except ImportError:  # pragma: no cover - py3 safety net only
    import queue

try:
    import urllib2
    from urllib import quote as _url_quote
except ImportError:  # pragma: no cover
    import urllib.request as urllib2
    from urllib.parse import quote as _url_quote

try:
    import BigWorld
except ImportError:  # pragma: no cover - allows offline syntax checks
    BigWorld = None

try:
    text_type = unicode
except NameError:  # pragma: no cover
    text_type = str

try:
    string_types = basestring
except NameError:  # pragma: no cover
    string_types = str


MOD_NAME = 'TonymocchiChatTranslator'
MOD_VERSION = '1.6.0'
UI_LANGUAGE = 'en'
LINKAGE = 'Tonymocchi.chattranslator.en'
SETTINGS_VERSION = 2

# Exact colour sampled from the reference screenshot.
DEFAULT_COLOR = '7FD4C0'

TREE_GLYPH = u'\u2514'  # the box-drawing corner shown in front of a translation

# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------

_DEFAULTS = {
    'enabled': True,

    # what to translate
    'targetLang': 0 if UI_LANGUAGE == 'ko' else 1,  # 0 = Korean, 1 = English
    'translateAlly': True,
    'translateEnemy': True,
    'translateSelf': False,
    'skipCommands': True,
    'minLetters': 2,        # ignore anything shorter than this many Cyrillic letters

    # how it is shown
    'displayMode': 1,       # 0 = hold & merge (one entry, two lines), 1 = separate entry
    'holdMs': 600,          # merge mode: how long a message may wait for its translation
    'showName': True,
    'colorize': True,
    'colorIdx': 0,

    # engine
    'provider': 0,          # 0 = auto failover, 1 = Google, 2 = Lingva, 3 = MyMemory
    'usePhrasebook': True,
    'useCache': True,

    'debug': False,
}

COLOR_TABLE = (
    ('mint',   DEFAULT_COLOR),
    ('gray',   'CCCCCC'),
    ('yellow', 'FFDD55'),
    ('cyan',   '66CCFF'),
    ('white',  'FFFFFF'),
    ('green',  '84FF7C'),
)

LANG_CODES = ('ko', 'en')


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------

def _game_root():
    try:
        root = os.getcwd()
        parent = os.path.basename(root).lower()
        if parent in ('win32', 'win64') and os.path.isdir(os.path.dirname(root)):
            return os.path.dirname(root)
        return root
    except Exception:
        return '.'


_LOG_DIR = os.path.join(_game_root(), 'mods', 'Tonymocchi_chat_translator')
_LOG_PATH = os.path.join(_LOG_DIR, 'mod.log')
_log_broken = False


def _log(msg, force=False):
    """Write to python.log always, and to our own file when debug is on."""
    try:
        line = '[%s] %s' % (MOD_NAME, msg)
    except Exception:
        return
    try:
        print(line)
    except Exception:
        pass
    cfg = globals().get('g_config')
    verbose = False
    try:
        verbose = bool(cfg and cfg.get('debug'))
    except Exception:
        verbose = False
    if not (force or verbose):
        return
    global _log_broken
    if _log_broken:
        return
    try:
        if not os.path.isdir(_LOG_DIR):
            os.makedirs(_LOG_DIR)
        handle = open(_LOG_PATH, 'ab')
        try:
            stamp = time.strftime('%Y-%m-%d %H:%M:%S')
            handle.write(('[%s] %s\n' % (stamp, msg)).encode('utf-8', 'replace'))
        finally:
            handle.close()
    except Exception:
        _log_broken = True


def _log_exc(prefix):
    try:
        _log('%s\n%s' % (prefix, traceback.format_exc()), force=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# config object
# ---------------------------------------------------------------------------

class _Config(object):
    def __init__(self):
        self.data = dict(_DEFAULTS)

    def update(self, incoming):
        if not incoming:
            return
        for key in _DEFAULTS:
            if key in incoming:
                self.data[key] = incoming[key]

    def get(self, key):
        return self.data.get(key, _DEFAULTS.get(key))

    def target(self):
        try:
            return LANG_CODES[int(self.get('targetLang'))]
        except Exception:
            return 'ko'

    def color(self):
        try:
            return COLOR_TABLE[int(self.get('colorIdx'))][1]
        except Exception:
            return DEFAULT_COLOR


g_config = _Config()


# ---------------------------------------------------------------------------
# Fixed settings UI language
#
# The release ships as two packages.  This constant deliberately fixes the
# settings window language instead of guessing it from installed font files.
# ---------------------------------------------------------------------------

def _ko_ui():
    return UI_LANGUAGE == 'ko'


def L(ko, en):
    """Pick the string for this package's fixed settings UI language."""
    try:
        return ko if _ko_ui() else en
    except Exception:
        return en


# ---------------------------------------------------------------------------
# text analysis
# ---------------------------------------------------------------------------

_RE_URL = re.compile(r'https?://\S+', re.I)
_RE_TAG = re.compile(r'<[^>]+>')
_RE_WS = re.compile(r'\s+', re.U)

# Cyrillic letters that Russian does not use. Their presence is a strong hint
# that the line is Ukrainian / Belarusian / Serbian, which we leave alone.
_NON_RUSSIAN_CYR = set(u'іїєґўјљњћђѓќѕѐ')


def _as_unicode(value):
    if value is None:
        return u''
    if isinstance(value, text_type):
        return value
    try:
        return value.decode('utf-8', 'replace')
    except Exception:
        try:
            return text_type(value)
        except Exception:
            return u''


def _strip_markup(text):
    """Remove chat markup so detection sees only what a human reads."""
    text = _RE_TAG.sub(u' ', text)
    text = _RE_URL.sub(u' ', text)
    return text


def count_scripts(text):
    """Return (cyrillic, latin, hangul) letter counts."""
    cyr = lat = han = 0
    for ch in text:
        o = ord(ch)
        if 0x0400 <= o <= 0x04FF or 0x0500 <= o <= 0x052F:
            cyr += 1
        elif (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A):
            lat += 1
        elif 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F:
            han += 1
    return cyr, lat, han


def looks_russian(text, min_letters):
    """True when the line is worth sending to a Russian translator.

    Deliberately conservative: English, Korean and mixed-but-mostly-Latin lines
    are left alone, which is what the spec asks for.
    """
    text = _strip_markup(_as_unicode(text))
    cyr, lat, han = count_scripts(text)
    if cyr < max(1, int(min_letters)):
        return False
    if han:
        # already translated, or a Korean player typing - never touch it
        return False
    if lat and cyr <= lat:
        # e.g. "gg wp Вася" - dominated by Latin, not a Russian sentence
        return False
    lowered = text.lower()
    hits = sum(1 for ch in lowered if ch in _NON_RUSSIAN_CYR)
    if hits >= 2:
        return False
    return True


# --- tactical command / ping filter ---------------------------------------
#
# Radial-menu commands ("Attacking A1!", "Affirmative!", ...) are noise: every
# player already understands them from the icon, and the Korean patch has
# translated them anyway. Filter them structurally where possible, and by
# phrase where not.

_COMMAND_STEMS = (
    u'атакую', u'атакуй', u'иду на базу', u'иду к базе', u'займи', u'занимаю',
    u'помогите', u'помоги мне', u'нужна помощь', u'нужен свет', u'дайте свет',
    u'подтверждаю', u'отрицательно', u'никак нет', u'так точно',
    u'внимание', u'осторожно', u'берегись', u'разворачивайся',
    u'перезаряжаюсь', u'перезарядка', u'орудие повреждено',
    u'отступаем', u'отступай', u'отхожу', u'назад',
    u'защищайте базу', u'база под атакой', u'захватываем базу', u'сбейте захват',
    u'обнаружен противник', u'противник обнаружен', u'вижу противника',
    u'хорошая игра', u'хорошо сыграно', u'спасибо за игру',
    u'я на позиции', u'жду вас', u'прикрой', u'прикрываю',
    u'следуй за мной', u'следую за', u'держись', u'держитесь',
    u'перезаряжаю', u'нет боеприпасов', u'орудие повреждено',
)

# "Атакую квадрат E4", "Иду в C7" and friends.
_RE_SQUARE = re.compile(u'\\b[a-kA-Kа-кА-К]\\s?(?:10|[1-9])\\b', re.U)


def looks_like_command(text):
    text = _RE_WS.sub(u' ', _strip_markup(_as_unicode(text))).strip().lower()
    if not text:
        return True
    for stem in _COMMAND_STEMS:
        if text.startswith(stem):
            return True
    # short line whose only content is a map square reference
    if len(text) <= 24 and _RE_SQUARE.search(text):
        stripped = _RE_SQUARE.sub(u' ', text)
        cyr, lat, han = count_scripts(stripped)
        if cyr <= 6:
            return True
    return False


def message_is_command(message):
    """Structural check - a real chat command carries a command id."""
    for attr in ('commandID', 'commandId', 'command', 'isCommand', 'chatCommand'):
        try:
            value = getattr(message, attr, None)
        except Exception:
            continue
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if value:
            return True
    return False


# ---------------------------------------------------------------------------
# built-in phrasebook
#
# Battle chat is extremely repetitive. Answering the most common lines locally
# is instant, costs no request, and reads better than a machine translation of
# gamer slang ("рак" is not a crustacean here).
# Key = normalised Russian, value = (korean, english).
# ---------------------------------------------------------------------------

PHRASEBOOK = {
    # greetings / courtesy
    u'привет': (u'안녕', u'hi'),
    u'всем привет': (u'모두 안녕', u'hi all'),
    u'прив': (u'ㅎㅇ', u'hi'),
    u'гл': (u'ㅎㅇ', u'gl'),
    u'глхф': (u'잘해보자', u'gl hf'),
    u'удачи': (u'행운을', u'good luck'),
    u'спасибо': (u'고마워', u'thanks'),
    u'спс': (u'ㄱㅅ', u'thx'),
    u'пасиб': (u'고마워', u'thanks'),
    u'благодарю': (u'감사합니다', u'thank you'),
    u'пожалуйста': (u'천만에', u'you are welcome'),
    u'извини': (u'미안', u'sorry'),
    u'извините': (u'죄송합니다', u'sorry'),
    u'сорри': (u'미안', u'sorry'),
    u'сори': (u'미안', u'sorry'),
    u'сорян': (u'미안', u'my bad'),
    u'прости': (u'미안', u'sorry'),
    u'мой косяк': (u'내 실수', u'my bad'),
    u'хорошая игра': (u'좋은 경기였어', u'good game'),
    u'гг': (u'ㅈㅈ', u'gg'),
    u'гг вп': (u'잘했어', u'gg wp'),
    u'красава': (u'잘한다', u'nice one'),
    u'молодец': (u'잘했어', u'well done'),
    u'красиво': (u'멋지다', u'nice'),
    u'пока': (u'잘 가', u'bye'),

    # calls for action
    u'давай': (u'가자', u'come on'),
    u'давайте': (u'가자', u'lets go'),
    u'вперед': (u'전진', u'push forward'),
    u'вперёд': (u'전진', u'push forward'),
    u'жми': (u'밀어', u'push'),
    u'пушим': (u'밀자', u'lets push'),
    u'толкать': (u'밀까', u'push?'),
    u'толкаем': (u'밀자', u'lets push'),
    u'атакуем': (u'공격하자', u'lets attack'),
    u'помоги': (u'도와줘', u'help me'),
    u'помогите': (u'도와줘', u'help'),
    u'хелп': (u'도와줘', u'help'),
    u'спасай': (u'구해줘', u'save me'),
    u'прикрой': (u'엄호해줘', u'cover me'),
    u'прикройте': (u'엄호해줘', u'cover me'),
    u'стой': (u'멈춰', u'stop'),
    u'стоп': (u'정지', u'stop'),
    u'стойте': (u'멈춰', u'hold'),
    u'ждем': (u'기다리자', u'lets wait'),
    u'жди': (u'기다려', u'wait'),
    u'подожди': (u'잠깐만', u'wait'),
    u'назад': (u'뒤로', u'fall back'),
    u'отходим': (u'후퇴하자', u'falling back'),
    u'отступаем': (u'후퇴', u'retreat'),
    u'бегом': (u'빨리', u'hurry'),
    u'быстрее': (u'더 빨리', u'faster'),
    u'сюда': (u'이쪽으로', u'over here'),
    u'иди сюда': (u'이리 와', u'come here'),
    u'идем': (u'가자', u'lets go'),
    u'за мной': (u'따라와', u'follow me'),
    u'разойдись': (u'흩어져', u'spread out'),
    u'не стой': (u'가만있지 마', u'dont just sit there'),
    u'не лезь': (u'들이대지 마', u'dont go in'),
    u'не спеши': (u'서두르지 마', u'dont rush'),
    u'осторожно': (u'조심해', u'careful'),
    u'аккуратнее': (u'조심해', u'be careful'),
    u'сзади': (u'뒤에 있어', u'behind you'),
    u'слева': (u'왼쪽', u'left side'),
    u'справа': (u'오른쪽', u'right side'),

    # map / roles
    u'база': (u'기지', u'base'),
    u'на базу': (u'기지로', u'to the base'),
    u'база пустая': (u'기지 비었어', u'base is empty'),
    u'кто на базе': (u'기지에 누구 있어', u'who is on base'),
    u'арта': (u'자주포', u'arty'),
    u'арта есть': (u'자주포 있어', u'they have arty'),
    u'арты нет': (u'자주포 없어', u'no arty'),
    u'свет': (u'정찰', u'spot'),
    u'дай свет': (u'정찰 좀', u'give me a spot'),
    u'нужен свет': (u'정찰 필요해', u'need a spot'),
    u'светите': (u'정찰해줘', u'spot for us'),
    u'кемпер': (u'캠핑충', u'camper'),
    u'не кемпи': (u'캠핑하지 마', u'stop camping'),
    u'фланг': (u'측면', u'flank'),
    u'фланг слился': (u'측면 무너졌어', u'the flank collapsed'),
    u'холм': (u'언덕', u'the hill'),
    u'город': (u'시가지', u'the town'),
    u'поле': (u'평지', u'the open field'),
    u'кусты': (u'수풀', u'the bushes'),
    u'мост': (u'다리', u'the bridge'),

    # status reports
    u'я топлюсь': (u'나 익사하고 있어', u'i am drowning'),
    u'топлюсь': (u'익사 중', u'drowning'),
    u'горю': (u'불붙었어', u'i am on fire'),
    u'я горю': (u'나 불붙었어', u'i am burning'),
    u'меня убили': (u'나 죽었어', u'i am dead'),
    u'я умер': (u'나 죽었어', u'i am dead'),
    u'я один': (u'나 혼자야', u'i am alone'),
    u'я перезаряжаюсь': (u'재장전 중', u'reloading'),
    u'перезаряжаюсь': (u'재장전 중', u'reloading'),
    u'нет снарядов': (u'포탄 없어', u'out of ammo'),
    u'нет хп': (u'체력 없어', u'no hp left'),
    u'мало хп': (u'체력 얼마 없어', u'low hp'),
    u'гусеница сбита': (u'궤도 나갔어', u'tracked'),
    u'сбили гуслю': (u'궤도 파손', u'i got tracked'),
    u'орудие повреждено': (u'주포 파손', u'gun damaged'),
    u'застрял': (u'끼었어', u'i am stuck'),
    u'я застрял': (u'나 끼었어', u'i am stuck'),
    u'еду': (u'가는 중', u'on my way'),
    u'уже еду': (u'이미 가는 중', u'already on my way'),
    u'сейчас приеду': (u'금방 갈게', u'coming now'),
    u'я тут': (u'나 여기 있어', u'i am here'),
    u'ща': (u'잠깐', u'one sec'),
    u'сейчас': (u'지금', u'right now'),
    u'минуту': (u'잠깐만', u'one minute'),
    u'отошел': (u'자리 비움', u'afk'),
    u'афк': (u'잠수', u'afk'),

    # slang / complaints - these are what a raw MT engine gets wrong
    u'рак': (u'발암', u'noob'),
    u'раки': (u'발암들', u'noobs'),
    u'нуб': (u'뉴비', u'noob'),
    u'нубы': (u'뉴비들', u'noobs'),
    u'слив': (u'폭삭 망함', u'a blowout loss'),
    u'слили': (u'다 말아먹었어', u'we threw it'),
    u'сливаем': (u'지고 있어', u'we are losing this'),
    u'что за команда': (u'이 팀 뭐냐', u'what a team'),
    u'куда': (u'어디 가', u'where are you going'),
    u'куда ты': (u'너 어디 가', u'where are you going'),
    u'зачем': (u'왜', u'why'),
    u'почему': (u'왜', u'why'),
    u'что делаешь': (u'뭐 하는 거야', u'what are you doing'),
    u'ты серьезно': (u'진심이야', u'seriously?'),
    u'везет': (u'운 좋네', u'lucky'),
    u'рандом': (u'랜덤 게임', u'random battles'),
    u'читер': (u'핵쟁이', u'cheater'),
    u'бот': (u'봇', u'bot'),
    u'жду репорт': (u'신고할게', u'reporting you'),
    u'репорт': (u'신고', u'report'),
    u'не пиши': (u'채팅 그만', u'stop typing'),
    u'молчи': (u'조용히 해', u'be quiet'),
    u'играй': (u'게임이나 해', u'just play'),
    u'учись играть': (u'게임 좀 배워', u'learn to play'),
    u'сучара': (u'개자식', u'bastard'),
    u'ебучая': (u'좆같은', u'fucking'),

    # yes / no
    u'да': (u'응', u'yes'),
    u'нет': (u'아니', u'no'),
    u'ок': (u'ㅇㅋ', u'ok'),
    u'окей': (u'오케이', u'okay'),
    u'ага': (u'응', u'yeah'),
    u'угу': (u'응', u'mhm'),
    u'понял': (u'알겠어', u'got it'),
    u'понятно': (u'알겠다', u'understood'),
    u'не понял': (u'못 알아들었어', u'i did not get that'),
    u'конечно': (u'물론', u'of course'),
    u'точно': (u'맞아', u'exactly'),
    u'верно': (u'맞아', u'correct'),
    u'согласен': (u'동의해', u'agreed'),
    u'не знаю': (u'몰라', u'i dont know'),
    u'все': (u'끝', u'thats it'),
    u'всё': (u'끝', u'thats it'),
}


def _normalise_phrase(text):
    text = _strip_markup(_as_unicode(text)).lower()
    text = text.replace(u'ё', u'е')
    text = _RE_PHRASE_PUNCT.sub(u' ', text)
    return _RE_WS.sub(u' ', text).strip()


_RE_PHRASE_PUNCT = re.compile(u'[!?.,;:)(\\-_*~"\u00ab\u00bb]+', re.U)
_RE_LAUGH_SEPARATORS = re.compile(u'[\\s!?.,;:()\\-_*~"\u00ab\u00bb]+', re.U)


def laughter_lookup(text, target):
    """Translate Russian а/х laughter locally, preserving its rough length."""
    raw = _strip_markup(_as_unicode(text)).lower().strip()
    compact = _RE_LAUGH_SEPARATORS.sub(u'', raw)
    if len(compact) < 4:
        return None
    if any(ch not in u'ах' for ch in compact):
        return None
    transitions = sum(1 for idx in range(1, len(compact))
                      if compact[idx] != compact[idx - 1])
    if transitions < max(2, len(compact) - 2):
        return None
    units = max(1, len(compact) // 2)
    if target == 'ko':
        return u'ㅋ' * units
    return u'ha' * units


def phrasebook_lookup(text, target):
    key = _normalise_phrase(text)
    if not key:
        return None
    entry = PHRASEBOOK.get(key)
    if entry is None:
        return None
    return entry[0] if target == 'ko' else entry[1]


# ---------------------------------------------------------------------------
# embedded local glossary and preserve dictionary
#
# The JSON is packaged inside the MTMOD. It is parsed once during init and is
# then represented by hash tables (whole-message O(1) checks), a generic token
# scanner for the thousands of single-word inflections, and one small compiled
# longest-first regex for multi-word entries. There is no file access, JSON
# parsing or per-entry loop on the chat hot path.
#
# preserveTerms are never translated. Entries under translateTerms (the public
# JSON name) or translations (the v1.6 preview alias) are answered locally for
# exact messages and locked to the configured ko/en wording inside longer
# messages. exactTranslations may override a term only when the whole message
# matches (e.g. "гг" -> "ㅈㅈ" without making it an embedded noun).
# ---------------------------------------------------------------------------

PRESERVE_DICTIONARY_RESOURCE = \
    'scripts/client/gui/mods/TonymocchiChatTranslator/preserve_dictionary.json'
PRESERVE_DICTIONARY_MAX_BYTES = 1024 * 1024
PRESERVE_DICTIONARY_MAX_TERMS = 10000

_dictionary_enabled = True
_dictionary_case_insensitive = True
_dictionary_normalize_yo = True
_dictionary_whole_words = True
_dictionary_exact = frozenset()
_dictionary_translations = {}
_dictionary_exact_translations = {}
_dictionary_match_keys = frozenset()
_dictionary_single_keys = frozenset()
_dictionary_pattern = None       # generic single-token scanner
_dictionary_phrase_pattern = None
_dictionary_revision = 'empty'
_RE_PRESERVE_TOKEN = re.compile(u'TMCXKEEP(\\d{4})X', re.I | re.U)
_DICTIONARY_WORD_CHARS = u'0-9A-Za-zА-Яа-яЁё_'
_DICTIONARY_TOKEN_PATTERN = re.compile(
    u'(?<![%s])[%s]+(?:[.\\-][%s]+)*(?![%s])'
    % (_DICTIONARY_WORD_CHARS, _DICTIONARY_WORD_CHARS,
       _DICTIONARY_WORD_CHARS, _DICTIONARY_WORD_CHARS), re.U)


def _dictionary_normalise(text, case_insensitive=None, normalize_yo=None):
    if case_insensitive is None:
        case_insensitive = _dictionary_case_insensitive
    if normalize_yo is None:
        normalize_yo = _dictionary_normalize_yo
    value = _strip_markup(_as_unicode(text))
    value = _RE_PHRASE_PUNCT.sub(u' ', value)
    value = _RE_WS.sub(u' ', value).strip()
    if case_insensitive:
        value = value.lower()
    if normalize_yo:
        value = value.replace(u'ё', u'е').replace(u'Ё', u'Е')
    return value


def _term_regex(term, normalize_yo):
    parts = []
    for ch in term:
        if ch.isspace():
            if not parts or parts[-1] != u'\\s+':
                parts.append(u'\\s+')
        elif normalize_yo and ch in u'её':
            parts.append(u'[её]')
        elif normalize_yo and ch in u'ЕЁ':
            parts.append(u'[ЕЁ]')
        else:
            parts.append(re.escape(ch))
    return u''.join(parts)


def _translation_pair(value):
    ko = en = u''
    if isinstance(value, dict):
        ko = _as_unicode(value.get('ko')).strip()
        en = _as_unicode(value.get('en')).strip()
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        ko = _as_unicode(value[0]).strip()
        en = _as_unicode(value[1]).strip()
    elif isinstance(value, string_types):
        # Compatibility with the Korean-only v2 dictionary supplied for the
        # original port.  Never leak that Korean value into the English target;
        # English will keep the Russian term and let the provider translate the
        # rest of the sentence.
        ko = _as_unicode(value).strip()
    return ko, en


def _parse_preserve_dictionary(raw):
    if not isinstance(raw, dict):
        raise ValueError('dictionary root must be a JSON object')
    settings = raw.get('settings') or {}
    if not isinstance(settings, dict):
        raise ValueError('dictionary settings must be a JSON object')
    enabled = bool(settings.get('enabled', True))
    case_insensitive = bool(settings.get('caseInsensitive', True))
    normalize_yo = bool(settings.get('normalizeYo', True))
    whole_words = bool(settings.get('matchWholeWords', True))
    terms = raw.get('preserveTerms') or []
    legacy_translations_raw = raw.get('translateTerms') or {}
    translations_raw = raw.get('translations') or {}
    exact_translations_raw = raw.get('exactTranslations') or {}
    if not isinstance(terms, list):
        raise ValueError('preserveTerms must be a JSON array')
    if not isinstance(legacy_translations_raw, dict):
        raise ValueError('translateTerms must be a JSON object')
    if not isinstance(translations_raw, dict):
        raise ValueError('translations must be a JSON object')
    if not isinstance(exact_translations_raw, dict):
        raise ValueError('exactTranslations must be a JSON object')
    merged_translations_raw = dict(legacy_translations_raw)
    # The preview key is accepted for compatibility and wins on collision.
    merged_translations_raw.update(translations_raw)
    if (len(terms) + len(merged_translations_raw) +
            len(exact_translations_raw) >
            PRESERVE_DICTIONARY_MAX_TERMS):
        raise ValueError('too many dictionary entries')

    preserve_sources = {}
    for value in terms:
        if not isinstance(value, string_types):
            continue
        term = _as_unicode(value).strip()
        if not term or len(term) > 200:
            continue
        key = _dictionary_normalise(term, case_insensitive, normalize_yo)
        if key and key not in preserve_sources:
            preserve_sources[key] = term

    translation_sources = {}
    translations = {}
    for source, value in merged_translations_raw.items():
        term = _as_unicode(source).strip()
        if not term or len(term) > 200:
            continue
        key = _dictionary_normalise(term, case_insensitive, normalize_yo)
        pair = _translation_pair(value)
        if not key or not (pair[0] or pair[1]) or key in preserve_sources:
            continue
        translation_sources[key] = term
        translations[key] = pair

    exact_translations = {}
    for source, value in exact_translations_raw.items():
        term = _as_unicode(source).strip()
        if not term or len(term) > 200:
            continue
        key = _dictionary_normalise(term, case_insensitive, normalize_yo)
        pair = _translation_pair(value)
        if not key or not (pair[0] or pair[1]) or key in preserve_sources:
            continue
        exact_translations[key] = pair

    exact = frozenset(preserve_sources.keys())
    regex_sources = dict(translation_sources)
    regex_sources.update(preserve_sources)
    match_keys = frozenset(regex_sources.keys())
    single_keys = frozenset()
    pattern = None
    phrase_pattern = None
    if enabled and regex_sources:
        flags = re.U | (re.I if case_insensitive else 0)
        if whole_words:
            # Nearly all generated Russian inflections are single tokens.  A
            # generic scanner plus a set lookup scales independently of the
            # dictionary size and avoids a 2,000+ alternative regex.
            single_sources = dict((key, value)
                                  for key, value in regex_sources.items()
                                  if not any(ch.isspace() for ch in value))
            phrase_sources = dict((key, value)
                                  for key, value in regex_sources.items()
                                  if any(ch.isspace() for ch in value))
            single_keys = frozenset(single_sources.keys())
            if single_keys:
                pattern = _DICTIONARY_TOKEN_PATTERN
            ordered_phrases = sorted(phrase_sources.values(),
                                     key=lambda item: len(item), reverse=True)
            if ordered_phrases:
                alternatives = [_term_regex(term, normalize_yo)
                                for term in ordered_phrases]
                body = u'(?:%s)' % u'|'.join(alternatives)
                body = (u'(?<![%s])%s(?![%s])'
                        % (_DICTIONARY_WORD_CHARS, body,
                           _DICTIONARY_WORD_CHARS))
                phrase_pattern = re.compile(body, flags)
        else:
            # Preserve the documented substring mode for custom dictionaries.
            ordered_terms = sorted(regex_sources.values(),
                                   key=lambda item: len(item), reverse=True)
            alternatives = [_term_regex(term, normalize_yo)
                            for term in ordered_terms]
            phrase_pattern = re.compile(u'(?:%s)' % u'|'.join(alternatives),
                                        flags)

    fingerprint = u'|'.join([
        u'1' if enabled else u'0',
        u'1' if case_insensitive else u'0',
        u'1' if normalize_yo else u'0',
        u'1' if whole_words else u'0',
        u'\n'.join(u'P\t%s' % key for key in sorted(exact)),
        u'\n'.join(u'T\t%s\t%s\t%s' % (key, translations[key][0],
                                         translations[key][1])
                    for key in sorted(translations)),
        u'\n'.join(u'E\t%s\t%s\t%s' % (key, exact_translations[key][0],
                                         exact_translations[key][1])
                    for key in sorted(exact_translations)),
    ]).encode('utf-8')
    revision = hashlib.sha1(fingerprint).hexdigest()[:12]
    return (enabled, case_insensitive, normalize_yo, whole_words,
            exact, translations, exact_translations, match_keys, single_keys,
            pattern, phrase_pattern, revision)


def _read_preserve_dictionary():
    try:
        import ResMgr
        section = ResMgr.openSection(PRESERVE_DICTIONARY_RESOURCE)
        if section is not None:
            return str(section.asBinary)
    except Exception:
        pass

    # Development/offline fallback. The release loads through ResMgr directly
    # from the MTMOD's VFS and never extracts this file at runtime.
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        candidates = (
            os.path.join(base, 'TonymocchiChatTranslator',
                         'preserve_dictionary.json'),
            os.path.join(base, 'preserve_dictionary.json'),
        )
        for path in candidates:
            if os.path.isfile(path):
                handle = open(path, 'rb')
                try:
                    return handle.read()
                finally:
                    handle.close()
    except Exception:
        pass
    return None


def load_preserve_dictionary(raw_bytes=None):
    global _dictionary_enabled
    global _dictionary_case_insensitive
    global _dictionary_normalize_yo
    global _dictionary_whole_words
    global _dictionary_exact
    global _dictionary_translations
    global _dictionary_exact_translations
    global _dictionary_match_keys
    global _dictionary_single_keys
    global _dictionary_pattern
    global _dictionary_phrase_pattern
    global _dictionary_revision
    try:
        if raw_bytes is None:
            raw_bytes = _read_preserve_dictionary()
        if raw_bytes is None:
            raise ValueError('embedded dictionary resource not found')
        if len(raw_bytes) > PRESERVE_DICTIONARY_MAX_BYTES:
            raise ValueError('embedded dictionary is larger than 1 MiB')
        decoded = (_as_unicode(raw_bytes.decode('utf-8-sig'))
                   if isinstance(raw_bytes, str) else _as_unicode(raw_bytes))
        compiled = _parse_preserve_dictionary(json.loads(decoded))
        (_dictionary_enabled,
         _dictionary_case_insensitive,
         _dictionary_normalize_yo,
         _dictionary_whole_words,
         _dictionary_exact,
         _dictionary_translations,
         _dictionary_exact_translations,
         _dictionary_match_keys,
         _dictionary_single_keys,
         _dictionary_pattern,
         _dictionary_phrase_pattern,
         _dictionary_revision) = compiled
        total = (len(_dictionary_exact) + len(_dictionary_translations) +
                 len(_dictionary_exact_translations))
        _log('dictionary loaded (preserve=%d, translations=%d, exact=%d, '
             'revision=%s)' % (len(_dictionary_exact),
                                len(_dictionary_translations),
                                len(_dictionary_exact_translations),
                                _dictionary_revision), force=True)
        return total
    except Exception:
        _dictionary_enabled = False
        _dictionary_exact = frozenset()
        _dictionary_translations = {}
        _dictionary_exact_translations = {}
        _dictionary_match_keys = frozenset()
        _dictionary_single_keys = frozenset()
        _dictionary_pattern = None
        _dictionary_phrase_pattern = None
        _dictionary_revision = 'invalid'
        _log_exc('preserve dictionary load failed; continuing without it')
        return 0


def dictionary_preserves_entire_message(text):
    if not _dictionary_enabled or not _dictionary_exact:
        return False
    return _dictionary_normalise(text) in _dictionary_exact


def dictionary_translation_lookup(text, target):
    if not _dictionary_enabled:
        return None
    key = _dictionary_normalise(text)
    if not key or key in _dictionary_exact:
        return None
    pair = _dictionary_exact_translations.get(key)
    if pair is None:
        pair = _dictionary_translations.get(key)
    if pair is None:
        return None
    value = pair[0] if target == 'ko' else pair[1]
    return value or None


def protect_dictionary_terms(text, target=None):
    pattern = _dictionary_pattern
    phrase_pattern = _dictionary_phrase_pattern
    source = _as_unicode(text)
    if (not _dictionary_enabled or
            (pattern is None and phrase_pattern is None)):
        return source, ()
    replacements = []

    def replace(match):
        index = len(replacements)
        if index > 9999:
            return match.group(0)
        original = match.group(0)
        key = _dictionary_normalise(original)
        if key not in _dictionary_match_keys:
            return original
        replacement = original
        if key not in _dictionary_exact:
            pair = _dictionary_translations.get(key)
            if pair is not None:
                translated = pair[0] if target == 'ko' else pair[1]
                if target in ('ko', 'en') and translated:
                    replacement = translated
                elif target in ('ko', 'en'):
                    # A legacy one-language mapping must not block the other
                    # target from translating this word normally.
                    return original
        replacements.append(replacement)
        return u'TMCXKEEP%04dX' % index

    def preserve_dynamic(match):
        index = len(replacements)
        if index > 9999:
            return match.group(0)
        replacements.append(match.group(0))
        return u'TMCXKEEP%04dX' % index

    # Phrases go first so a later token scan cannot split them.  Placeholder
    # names are not dictionary keys and therefore pass through the second scan.
    if phrase_pattern is not None:
        source = phrase_pattern.sub(replace, source)
    if pattern is not None:
        source = pattern.sub(replace, source)

    # Preserve grid references in ordinary sentences.  Short tactical-ping
    # messages are still rejected earlier by looks_like_command().
    source = _RE_SQUARE.sub(preserve_dynamic, source)
    return source, tuple(replacements)


def restore_dictionary_terms(text, replacements):
    if not replacements:
        return _as_unicode(text)
    restored = set()

    def replace(match):
        try:
            index = int(match.group(1))
            if 0 <= index < len(replacements):
                restored.add(index)
                return replacements[index]
        except Exception:
            pass
        return match.group(0)

    result = _RE_PRESERVE_TOKEN.sub(replace, _as_unicode(text))
    if len(restored) != len(replacements):
        return None
    return result


# ---------------------------------------------------------------------------
# persistent cache
# ---------------------------------------------------------------------------

CACHE_PATH = os.path.join(_LOG_DIR, 'cache.json')
CACHE_LIMIT = 4000

_cache = {}
_cache_dirty = False
_cache_lock = threading.Lock()


def _cache_prefix():
    return u'v3:%s\t' % _dictionary_revision


def _cache_key(text, target):
    return u'%s%s\t%s' % (_cache_prefix(), target, _normalise_phrase(text))


def cache_get(text, target):
    if not g_config.get('useCache'):
        return None
    with _cache_lock:
        return _cache.get(_cache_key(text, target))


def cache_put(text, target, value):
    global _cache_dirty
    if not value:
        return
    with _cache_lock:
        if len(_cache) >= CACHE_LIMIT:
            _cache.clear()
        _cache[_cache_key(text, target)] = value
        _cache_dirty = True


def cache_load():
    global _cache
    try:
        if not os.path.exists(CACHE_PATH):
            return
        handle = open(CACHE_PATH, 'rb')
        try:
            raw = json.loads(handle.read().decode('utf-8'))
        finally:
            handle.close()
        if isinstance(raw, dict):
            prefix = _cache_prefix()
            with _cache_lock:
                _cache = dict((_as_unicode(k), _as_unicode(v))
                              for k, v in raw.items()
                              if _as_unicode(k).startswith(prefix))
            _log('cache loaded (%d entries)' % len(_cache))
    except Exception:
        _log_exc('cache load failed')


def cache_save():
    global _cache_dirty
    try:
        if not _cache_dirty:
            return
        if not os.path.isdir(_LOG_DIR):
            os.makedirs(_LOG_DIR)
        with _cache_lock:
            payload = json.dumps(_cache, ensure_ascii=False).encode('utf-8')
            _cache_dirty = False
        handle = open(CACHE_PATH, 'wb')
        try:
            handle.write(payload)
        finally:
            handle.close()
    except Exception:
        _log_exc('cache save failed')


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36'

HTTP_TIMEOUT = 4.0

_ssl_ctx = None


def _get_ssl_context():
    """The game ships its own OpenSSL and often has no usable CA bundle."""
    global _ssl_ctx
    if _ssl_ctx is None:
        try:
            import ssl
            _ssl_ctx = ssl._create_unverified_context()
        except Exception:
            _ssl_ctx = False
    return _ssl_ctx or None


def http_get(url, timeout=HTTP_TIMEOUT):
    request = urllib2.Request(url)
    request.add_header('User-Agent', _UA)
    request.add_header('Accept', 'application/json, text/plain, */*')
    request.add_header('Accept-Language', 'en-US,en;q=0.9')
    ctx = _get_ssl_context()
    try:
        if ctx is not None:
            response = urllib2.urlopen(request, timeout=timeout, context=ctx)
        else:
            response = urllib2.urlopen(request, timeout=timeout)
    except TypeError:
        # older urllib2 without the context kwarg
        response = urllib2.urlopen(request, timeout=timeout)
    try:
        return response.read().decode('utf-8', 'replace')
    finally:
        try:
            response.close()
        except Exception:
            pass


def _q(text):
    return _url_quote(_as_unicode(text).encode('utf-8'), safe='')


# ---------------------------------------------------------------------------
# translation providers
#
# Each returns (translated_text, detected_source_language) or raises.
# All of them are keyless and free to call. None of them is contractually
# "unlimited", so the point of having four is that when one starts throttling
# the chain simply moves on to the next one.
# ---------------------------------------------------------------------------

def _provider_google(text, target):
    url = ('https://translate.googleapis.com/translate_a/single'
           '?client=gtx&sl=ru&tl=%s&dt=t&dj=1&q=%s' % (target, _q(text)))
    data = json.loads(http_get(url))
    chunks = data.get('sentences') or []
    out = u''.join(_as_unicode(c.get('trans', u'')) for c in chunks)
    src = _as_unicode(data.get('src') or u'')
    return out.strip(), (src.lower() or u'ru')


def _provider_google_alt(text, target):
    url = ('https://clients5.google.com/translate_a/t'
           '?client=dict-chrome-ex&sl=ru&tl=%s&q=%s' % (target, _q(text)))
    data = json.loads(http_get(url))
    # shape is either [["translated"]] or {"sentences":[...]}
    if isinstance(data, dict):
        chunks = data.get('sentences') or []
        return u''.join(_as_unicode(c.get('trans', u'')) for c in chunks).strip(), u'ru'
    out = data
    while isinstance(out, list) and out:
        out = out[0]
    return _as_unicode(out).strip(), u'ru'


_LINGVA_HOSTS = ('lingva.ml', 'translate.plausibility.cloud', 'lingva.lunar.icu')


def _provider_lingva(text, target):
    last = None
    for host in _LINGVA_HOSTS:
        try:
            url = 'https://%s/api/v1/ru/%s/%s' % (host, target, _q(text))
            data = json.loads(http_get(url))
            out = _as_unicode(data.get('translation') or u'').strip()
            if out:
                return out, u'ru'
        except Exception as exc:
            last = exc
    if last is not None:
        raise last
    raise RuntimeError('lingva: empty')


def _provider_mymemory(text, target):
    url = ('https://api.mymemory.translated.net/get?q=%s&langpair=ru|%s'
           % (_q(text), target))
    data = json.loads(http_get(url))
    out = _as_unicode((data.get('responseData') or {}).get('translatedText') or u'')
    out = out.strip()
    if not out or out.upper().startswith('MYMEMORY WARNING'):
        raise RuntimeError('mymemory: quota or empty')
    return out, u'ru'


PROVIDERS = (
    ('google', _provider_google),
    ('google_alt', _provider_google_alt),
    ('lingva', _provider_lingva),
    ('mymemory', _provider_mymemory),
)

# provider name -> unix time until which it is skipped
_cooldown = {}
_cooldown_lock = threading.Lock()
_COOLDOWN_SECS = 15.0


def _provider_chain():
    choice = int(g_config.get('provider') or 0)
    if choice == 0:
        order = list(PROVIDERS)
    elif choice == 1:
        order = [PROVIDERS[0], PROVIDERS[1]]
    elif choice == 2:
        order = [PROVIDERS[2]]
    elif choice == 3:
        order = [PROVIDERS[3]]
    else:
        order = list(PROVIDERS)
    now = time.time()
    with _cooldown_lock:
        ready = [p for p in order if _cooldown.get(p[0], 0) <= now]
    return ready or order


def translate_blocking(text, target):
    """Runs on a worker thread only. Returns (text, source_lang) or (None, None)."""
    request_text, replacements = protect_dictionary_terms(text, target)
    for name, fn in _provider_chain():
        try:
            out, src = fn(request_text, target)
            if out:
                out = restore_dictionary_terms(out, replacements)
                if not out:
                    raise ValueError('provider did not preserve dictionary tokens')
                with _cooldown_lock:
                    _cooldown.pop(name, None)
                return out, (src or u'ru')
        except Exception as exc:
            with _cooldown_lock:
                _cooldown[name] = time.time() + _COOLDOWN_SECS
            if g_config.get('debug'):
                _log('provider %s failed: %r' % (name, exc))
    return None, None


# ---------------------------------------------------------------------------
# worker pool + main-thread pump
#
# Workers never touch BigWorld. They push finished jobs into _result_q, and
# _pump() - which runs on the main thread via BigWorld.callback - drains it.
# ---------------------------------------------------------------------------

WORKERS = 4
PUMP_INTERVAL = 0.02

_request_q = queue.Queue()
_result_q = queue.Queue()
_workers_started = False
_inflight = 0
_inflight_groups = {}  # request key -> every chat row waiting for that result
_pending = []          # ordered, main thread only
_seq_counter = [0]


class _Pending(object):
    __slots__ = ('seq', 'emit', 'late_emit', 'text', 'target', 'hold_until',
                 'ordered', 'done', 'expired', 'result')

    def __init__(self, emit, text, target, hold_until, late_emit=None,
                 ordered=True):
        _seq_counter[0] += 1
        self.seq = _seq_counter[0]
        self.emit = emit
        self.late_emit = late_emit
        self.text = text
        self.target = target
        self.hold_until = hold_until
        self.ordered = ordered
        self.done = False
        self.expired = False
        self.result = None

    def finish(self, result):
        self.result = result
        self.done = True


def _worker_loop():
    while True:
        job = _request_q.get()
        if job is None:
            break
        try:
            out, src = translate_blocking(job.text, job.target)
            if out and src and not src.startswith(u'ru'):
                # the engine says this was not Russian after all - honour that
                out = None
            _result_q.put((job, out))
        except Exception:
            try:
                _result_q.put((job, None))
            except Exception:
                pass


def _start_workers():
    global _workers_started
    if _workers_started:
        return
    for i in range(WORKERS):
        thread = threading.Thread(target=_worker_loop)
        thread.setDaemon(True)
        thread.setName('%s-%d' % (MOD_NAME, i))
        thread.start()
    _workers_started = True
    _log('%d worker threads started' % WORKERS)


def _submit(pending):
    global _inflight
    key = _cache_key(pending.text, pending.target)
    group = _inflight_groups.get(key)
    if group is not None:
        group.append(pending)
        return
    _inflight_groups[key] = [pending]
    _inflight += 1
    _request_q.put(pending)


def _release_ready():
    """Emit finished / expired entries strictly in arrival order."""
    now = time.time()
    while _pending:
        head = _pending[0]
        if not head.done and now < head.hold_until:
            break
        _pending.pop(0)
        if not head.done:
            # The original line must not block the chat forever.  Keep the
            # job alive, though: _pump() will display a translation that
            # arrives after this short hold window.
            head.expired = True
        try:
            head.emit(head.result)
        except Exception:
            _log_exc('emit failed')


_save_tick = [0.0]


def _pump():
    global _inflight
    try:
        while True:
            try:
                request_job, out = _result_q.get_nowait()
            except queue.Empty:
                break
            _inflight = max(0, _inflight - 1)
            key = _cache_key(request_job.text, request_job.target)
            jobs = _inflight_groups.pop(key, None) or [request_job]
            if out:
                cache_put(request_job.text, request_job.target, out)
            for job in jobs:
                was_expired = getattr(job, 'expired', False)
                job.finish(out)
                if not job.ordered:
                    try:
                        job.emit(out)
                    except Exception:
                        _log_exc('separate-line emit failed')
                    continue
                late_emit = getattr(job, 'late_emit', None)
                if not (was_expired and out and late_emit is not None):
                    continue
                try:
                    late_emit(out)
                    _log('late translation displayed (seq=%d)' % job.seq)
                except Exception:
                    _log_exc('late emit failed')
        _release_ready()

        now = time.time()
        if now - _save_tick[0] > 60.0:
            _save_tick[0] = now
            cache_save()
    except Exception:
        _log_exc('pump')
    finally:
        try:
            if BigWorld is not None:
                BigWorld.callback(PUMP_INTERVAL, _pump)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# message helpers
# ---------------------------------------------------------------------------

def _get_text(message):
    if isinstance(message, string_types):
        return _as_unicode(message)
    for attr in ('text', 'message', 'body'):
        try:
            value = getattr(message, attr, None)
        except Exception:
            continue
        if isinstance(value, string_types) and value:
            return _as_unicode(value)
    return u''


def _with_text(message, new_text):
    """Return a message object carrying new_text, without touching the original."""
    if isinstance(message, string_types):
        return new_text
    try:
        clone = copy.copy(message)
        clone.text = new_text
        return clone
    except Exception:
        pass
    try:
        message.text = new_text
        return message
    except Exception:
        return message


def _sender_name(message):
    if isinstance(message, string_types):
        return u''
    for attr in ('originator', 'playerName', 'accountName', 'senderName', 'name'):
        try:
            value = getattr(message, attr, None)
        except Exception:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, string_types) and value:
            return _as_unicode(value)
    # ArenaMessageVO normally carries only avatarSessionID.  Resolve the same
    # display name that the stock battle message builder uses.
    try:
        avatar_session_id = getattr(message, 'avatarSessionID', None)
        if avatar_session_id:
            from helpers import dependency
            from skeletons.gui.battle_session import IBattleSessionProvider
            session = dependency.instance(IBattleSessionProvider)
            ctx = session.getCtx()
            value = ctx.getPlayerFullName(avatarSessionID=avatar_session_id,
                                          pName=getattr(message, 'accountName', None))
            if isinstance(value, string_types) and value:
                return _as_unicode(value)
    except Exception:
        pass
    return u''


def _is_own_message(message):
    if isinstance(message, string_types):
        return False
    try:
        from messenger.ext.player_helpers import isCurrentPlayer
        for attr in ('avatarSessionID', 'accountDBID'):
            value = getattr(message, attr, None)
            if value and isCurrentPlayer(value):
                return True
    except Exception:
        pass
    for attr in ('isCurrentPlayer', 'isMyMessage'):
        try:
            fn = getattr(message, attr, None)
        except Exception:
            continue
        if callable(fn):
            try:
                if fn():
                    return True
            except Exception:
                continue
    try:
        dbid = getattr(message, 'accountDBID', None)
        if dbid is not None and BigWorld is not None:
            player = BigWorld.player()
            mine = getattr(player, 'databaseID', None)
            if mine is not None and int(dbid) == int(mine):
                return True
    except Exception:
        pass
    return False


def _format_translation(name, translated):
    body = TREE_GLYPH + u' '
    if g_config.get('showName') and name:
        body += u'%s: ' % name
    body += translated
    if g_config.get('colorize'):
        body = u"<font color='#%s'>%s</font>" % (g_config.color(), body)
    return body


def _emit_translation_line(controller, orig, message, args, kwargs,
                           name, translated):
    """Put a translated-only row into the active battle chat.

    BattleLayout.addMessage formats a MessageVO by adding the sender name.
    Calling it for a translated-only row would therefore duplicate the name
    already present in _format_translation().  Prefer the battle view's
    already-formatted text entry point and retain the original call as a
    compatibility fallback.
    """
    line = _format_translation(name, translated)
    try:
        view = getattr(controller, '_view', None)
        if view is not None:
            try:
                from messenger.gui.Scaleform import FILL_COLORS
                fill_color = FILL_COLORS.BLACK
            except Exception:
                fill_color = 0
            avatar_session_id = getattr(message, 'avatarSessionID', '')
            try:
                view.addMessage(line, fillColor=fill_color,
                                avatarSessionID=avatar_session_id)
            except TypeError:
                view.addMessage(line, fillColor=fill_color)
            return
    except Exception:
        _log_exc('direct translation line failed')

    # Older clients without BattleLayout._view still get the translation.
    # Omit the embedded name here because the stock formatter adds it.
    fallback = TREE_GLYPH + u' ' + translated
    if g_config.get('colorize'):
        fallback = u"<font color='#%s'>%s</font>" % (g_config.color(), fallback)
    orig(controller, _with_text(message, fallback), *args, **kwargs)


# ---------------------------------------------------------------------------
# ally / enemy resolution
# ---------------------------------------------------------------------------

def _sender_side(message):
    """Return 'ally', 'enemy' or None when the side cannot be resolved."""
    try:
        from helpers import dependency
        from skeletons.gui.battle_session import IBattleSessionProvider
        session = dependency.instance(IBattleSessionProvider)
        avatar_session_id = getattr(message, 'avatarSessionID', None)
        if avatar_session_id:
            ctx = session.getCtx()
            if ctx.isEnemy(avatarSessionID=avatar_session_id):
                return 'enemy'
            if ctx.isAlly(avatarSessionID=avatar_session_id):
                return 'ally'

        dbid = getattr(message, 'accountDBID', None)
        if not dbid:
            return None
        arena_dp = session.getArenaDP()
        if arena_dp is None:
            return None
        veh_id = None
        for getter in ('getVehIDByAccDBID', 'getVehicleIDByAccDBID'):
            fn = getattr(arena_dp, getter, None)
            if callable(fn):
                try:
                    veh_id = fn(dbid)
                except Exception:
                    veh_id = None
            if veh_id:
                break
        if not veh_id:
            return None
        info = arena_dp.getVehicleInfo(veh_id)
        if info is None:
            return None
        return 'enemy' if arena_dp.isEnemyTeam(info.team) else 'ally'
    except Exception:
        return None


# ---------------------------------------------------------------------------
# interception
# ---------------------------------------------------------------------------

def _should_translate(message, text):
    cfg = g_config
    if not cfg.get('enabled'):
        return False
    if not text or len(text) > 300:
        return False
    if cfg.get('skipCommands'):
        if message_is_command(message):
            return False
    if _is_own_message(message) and not cfg.get('translateSelf'):
        return False
    side = _sender_side(message)
    if side == 'ally' and not cfg.get('translateAlly'):
        return False
    if side == 'enemy' and not cfg.get('translateEnemy'):
        return False
    if dictionary_preserves_entire_message(text):
        return False
    if dictionary_translation_lookup(text, cfg.target()) is not None:
        return True
    if cfg.get('skipCommands') and looks_like_command(text):
        return False
    if not looks_russian(text, cfg.get('minLetters')):
        return False
    return True


def _same_text(a, b):
    return _normalise_phrase(a) == _normalise_phrase(b)


def _queue_passthrough(controller, orig, message, args, kwargs):
    """Park an untranslated message behind the ones already waiting.

    Without this, a line that needs no translation overtakes a line that is
    still waiting for one, and the chat log ends up out of order.
    """
    def emit(_result, _c=controller, _o=orig, _m=message, _a=args, _k=kwargs):
        _o(_c, _m, *_a, **_k)

    pending = _Pending(emit, u'', u'', 0.0)
    pending.done = True
    _pending.append(pending)


def _intercept(controller, orig, message, args, kwargs):
    """Return True when this call has been fully handled here."""
    mode = int(g_config.get('displayMode') or 0)
    text = _get_text(message)

    if not _should_translate(message, text):
        if mode == 0 and _pending:
            _queue_passthrough(controller, orig, message, args, kwargs)
            return True
        return False

    target = g_config.target()
    name = _sender_name(message)

    instant = dictionary_translation_lookup(text, target)
    if instant is None:
        instant = laughter_lookup(text, target)
    if instant is None and g_config.get('usePhrasebook'):
        instant = phrasebook_lookup(text, target)
    if instant is None:
        instant = cache_get(text, target)

    if mode == 0:
        # hold the entry briefly, then show original + translation as one block
        def emit_merged(result, _c=controller, _o=orig, _m=message,
                        _a=args, _k=kwargs, _n=name, _t=text):
            payload = _m
            if result and not _same_text(result, _t):
                merged = _t + u'\n' + _format_translation(_n, result)
                payload = _with_text(_m, merged)
            _o(_c, payload, *_a, **_k)

        # If the network takes longer than the configured hold, the original
        # is released first and the completed translation is appended later.
        # The old code discarded that late result, which is why successful
        # translations appeared in cache.json but never appeared in battle.
        def emit_late(result, _c=controller, _o=orig, _m=message,
                      _a=args, _k=kwargs, _n=name):
            _emit_translation_line(_c, _o, _m, _a, _k, _n, result)

        if instant:
            emit_merged(instant)
            return True
        hold_ms = float(g_config.get('holdMs') or 0)
        pending = _Pending(emit_merged, text, target,
                           time.time() + max(0.0, hold_ms) / 1000.0,
                           late_emit=emit_late)
        _pending.append(pending)
        _submit(pending)
        return True

    # separate entry: original shows immediately, translation lands underneath
    orig(controller, message, *args, **kwargs)

    def emit_line(result, _c=controller, _o=orig, _m=message,
                  _a=args, _k=kwargs, _n=name, _t=text):
        if not result or _same_text(result, _t):
            return
        _emit_translation_line(_c, _o, _m, _a, _k, _n, result)

    if instant:
        emit_line(instant)
        return True
    # Separate-line mode has no global ordering dependency: every completed
    # translation is emitted immediately.  A slow earlier request therefore
    # cannot hide or delay the other rows in a burst.
    pending = _Pending(emit_line, text, target, 0.0, ordered=False)
    _submit(pending)
    return True


# ---------------------------------------------------------------------------
# hook installation (discovered, not hard-coded)
# ---------------------------------------------------------------------------

try:
    _CLASS_TYPES = (type, types.ClassType)
except AttributeError:  # pragma: no cover
    _CLASS_TYPES = (type,)

_EXACT_HOOKS = (
    # Mir Tankov 1.45: Team/Common/Squad controllers inherit this method.
    ('messenger.gui.Scaleform.channels.layout', 'BattleLayout', 'addMessage'),
)
_DISCOVERY_MODULES = (
    'messenger.gui.Scaleform.channels.bw_chat2.battle_controllers',
    'messenger.gui.Scaleform.channels.layout',
)

_hooked_methods = []
_in_hook = [0]


def _is_battle_controller(controller):
    try:
        module = (getattr(type(controller), '__module__', '') or '').lower()
    except Exception:
        return True
    if 'battle' in module:
        return True
    if 'lobby' in module or 'prebattle' in module:
        return False
    return True


def _wrap_method(cls, meth_name, orig):
    def hooked(self, message=None, *args, **kwargs):
        if _in_hook[0]:
            return orig(self, message, *args, **kwargs)
        _in_hook[0] += 1
        try:
            if message is not None and _is_battle_controller(self):
                if _intercept(self, orig, message, args, kwargs):
                    return None
        except Exception:
            _log_exc('intercept error')
        finally:
            _in_hook[0] = max(0, _in_hook[0] - 1)
        return orig(self, message, *args, **kwargs)

    try:
        hooked.__name__ = getattr(orig, '__name__', meth_name)
        hooked._TonymocchiChatTranslator_hooked = True
        hooked._TonymocchiChatTranslator_version = MOD_VERSION
        hooked._TonymocchiChatTranslator_orig = orig
    except Exception:
        pass
    setattr(cls, meth_name, hooked)
    _hooked_methods.append((cls, meth_name, orig))
    return True


def _hook_exact(modname, cls_name, meth_name):
    try:
        module = __import__(modname, {}, {}, ['*'])
        cls = getattr(module, cls_name)
        orig = getattr(cls, meth_name)
    except Exception:
        return 0
    if getattr(orig, '_TonymocchiChatTranslator_hooked', False):
        return 1
    try:
        if _wrap_method(cls, meth_name, orig):
            _log('hooked %s.%s.%s' % (modname, cls_name, meth_name))
            return 1
    except Exception:
        _log_exc('failed to hook %s.%s' % (cls_name, meth_name))
    return 0


def _hook_module(modname):
    count = 0
    try:
        module = __import__(modname, {}, {}, ['*'])
    except Exception:
        return 0
    for attr in dir(module):
        try:
            obj = getattr(module, attr, None)
        except Exception:
            continue
        if not isinstance(obj, _CLASS_TYPES):
            continue
        if getattr(obj, '__module__', None) != modname:
            continue
        identity = (modname + '.' + attr).lower()
        if 'battle' not in identity:
            continue
        target = None
        if callable(getattr(obj, 'addMessage', None)):
            target = 'addMessage'
        elif callable(getattr(obj, '_addMessage', None)):
            target = '_addMessage'
        if target is None:
            continue
        orig = getattr(obj, target)
        if getattr(orig, '_TonymocchiChatTranslator_hooked', False):
            count += 1
            continue
        try:
            if _wrap_method(obj, target, orig):
                count += 1
                _log('hooked %s.%s.%s' % (modname, attr, target))
        except Exception:
            _log_exc('failed to hook %s.%s' % (attr, target))
    return count


_hook_tries = [0]


def install_chat_hooks():
    total = 0
    for modname, cls_name, meth_name in _EXACT_HOOKS:
        total += _hook_exact(modname, cls_name, meth_name)
    if total == 0:
        for modname in _DISCOVERY_MODULES:
            total += _hook_module(modname)
    if total:
        _log('chat hooks installed on %d method(s)' % total, force=True)
        return total

    # The messenger package is imported lazily by the client, so an early miss
    # is expected rather than fatal. Keep retrying for a while before giving up.
    _hook_tries[0] += 1
    if _hook_tries[0] < 30 and BigWorld is not None:
        BigWorld.callback(2.0, install_chat_hooks)
    else:
        _log('CHAT HOOK NOT INSTALLED - this client layout is unknown to the '
             'mod; nothing will be translated. Please send mod.log.', force=True)
    return 0


# ---------------------------------------------------------------------------
# settings window (izeberg.modssettingsapi)
# ---------------------------------------------------------------------------

def _tip(header, body):
    return u'{HEADER}%s{/HEADER}{BODY}%s{/BODY}' % (header, body)


def _opts(labels):
    return [{'label': label} for label in labels]


def build_template():
    cfg = g_config
    column1 = [
        {'type': 'Label', 'text': L(u'번역', u'Translation')},
        {
            'type': 'Dropdown',
            'text': L(u'번역 언어', u'Translate into'),
            'varName': 'targetLang',
            'value': cfg.get('targetLang'),
            'width': 150,
            'options': _opts([L(u'한국어', u'Korean'), L(u'영어', u'English')]),
            'tooltip': _tip(
                L(u'번역 언어', u'Translate into'),
                L(u'한국어를 고르면 한글패치(fonts_ko.swf)가 설치되어 있어야 글자가 보입니다. '
                  u'한글패치가 없으면 영어를 고르세요.',
                  u'Korean output needs the Korean localisation patch (fonts_ko.swf) '
                  u'installed, otherwise Hangul renders as empty boxes. Pick English '
                  u'if you do not have it.')),
        },
        {
            'type': 'Dropdown',
            'text': L(u'번역 엔진', u'Engine'),
            'varName': 'provider',
            'value': cfg.get('provider'),
            'width': 150,
            'options': _opts([L(u'자동 (권장)', u'Auto (failover)'),
                              u'Google', u'Lingva', u'MyMemory']),
            'tooltip': _tip(
                L(u'번역 엔진', u'Engine'),
                L(u'자동으로 두면 한 엔진이 막혀도 다음 엔진으로 넘어갑니다.',
                  u'Auto walks down the provider list when one starts throttling.')),
        },
        {'type': 'Empty', 'height': 8},
        {
            'type': 'CheckBox',
            'text': L(u'아군 채팅 번역', u'Translate allies'),
            'varName': 'translateAlly',
            'value': cfg.get('translateAlly'),
        },
        {
            'type': 'CheckBox',
            'text': L(u'적군 채팅 번역', u'Translate enemies'),
            'varName': 'translateEnemy',
            'value': cfg.get('translateEnemy'),
        },
        {
            'type': 'CheckBox',
            'text': L(u'내 채팅도 번역', u'Translate my own messages'),
            'varName': 'translateSelf',
            'value': cfg.get('translateSelf'),
        },
        {
            'type': 'CheckBox',
            'text': L(u'전술 핑/명령 무시', u'Ignore tactical commands'),
            'varName': 'skipCommands',
            'value': cfg.get('skipCommands'),
            'tooltip': _tip(
                L(u'전술 핑/명령 무시', u'Ignore tactical commands'),
                L(u'"A1 지역으로 이동 중", "알겠다" 같은 라디오 명령은 번역하지 않습니다. '
                  u'아이콘만 봐도 아는 내용이라 채팅창만 지저분해집니다.',
                  u'Radial-menu commands such as "Attacking A1" or "Affirmative" are '
                  u'skipped - everyone reads those from the icon anyway.')),
        },
        {
            'type': 'Slider',
            'text': L(u'최소 러시아어 글자 수', u'Minimum Cyrillic letters'),
            'varName': 'minLetters',
            'value': cfg.get('minLetters'),
            'minimum': 1,
            'maximum': 10,
            'snapInterval': 1,
            'format': '{{value}}',
            'tooltip': _tip(
                L(u'최소 글자 수', u'Minimum letters'),
                L(u'이보다 짧은 러시아어는 무시합니다. 오탈자나 감탄사로 API를 낭비하지 않습니다.',
                  u'Lines with fewer Cyrillic letters than this are ignored, so typos '
                  u'and single-character noise do not burn requests.')),
        },
    ]

    column2 = [
        {'type': 'Label', 'text': L(u'표시', u'Display')},
        {
            'type': 'Dropdown',
            'text': L(u'표시 방식', u'Layout'),
            'varName': 'displayMode',
            'value': cfg.get('displayMode'),
            'width': 190,
            'options': _opts([L(u'원문 아래 붙여서', u'Under the original (one entry)'),
                              L(u'별도 줄로 (권장)', u'As a separate entry (recommended)')]),
            'tooltip': _tip(
                L(u'표시 방식', u'Layout'),
                L(u'첫 번째는 원문을 아주 잠깐 붙잡아 두었다가 번역과 함께 한 번에 출력합니다. '
                  u'순서가 절대 어긋나지 않습니다. 두 번째는 원문을 먼저 띄우고 번역이 도착하면 '
                  u'아래에 한 줄을 더 붙입니다.',
                  u'The first holds the original for a moment and prints it together '
                  u'with the translation, so ordering can never break. The second '
                  u'prints the original at once and adds a line when the translation '
                  u'arrives.')),
        },
        {
            'type': 'Slider',
            'text': L(u'대기 시간', u'Hold time'),
            'varName': 'holdMs',
            'value': cfg.get('holdMs'),
            'minimum': 0,
            'maximum': 2000,
            'snapInterval': 100,
            'format': '{{value}} ms',
            'tooltip': _tip(
                L(u'대기 시간', u'Hold time'),
                L(u'"원문 아래 붙여서" 방식에서 번역을 최대 이만큼 기다립니다. '
                  u'시간 안에 받으면 원문과 함께 출력하고, 늦게 도착하면 번역 줄을 뒤에 추가합니다. '
                  u'600ms 정도면 체감되지 않습니다.',
                  u'How long the "one entry" layout waits for a translation before it '
                  u'prints the original. A later result is appended as its own translation '
                  u'line instead of being discarded. 600 ms is imperceptible.')),
        },
        {'type': 'Empty', 'height': 8},
        {
            'type': 'CheckBox',
            'text': L(u'번역 줄에 닉네임 표시', u'Show nickname on the translation line'),
            'varName': 'showName',
            'value': cfg.get('showName'),
        },
        {
            'type': 'CheckBox',
            'text': L(u'번역 줄 색상 사용', u'Colour the translation line'),
            'varName': 'colorize',
            'value': cfg.get('colorize'),
        },
        {
            'type': 'Dropdown',
            'text': L(u'번역 줄 색상', u'Translation colour'),
            'varName': 'colorIdx',
            'value': cfg.get('colorIdx'),
            'width': 150,
            'options': _opts([L(u'민트', u'Mint'), L(u'회색', u'Gray'),
                              L(u'노랑', u'Yellow'), L(u'하늘', u'Cyan'),
                              L(u'흰색', u'White'), L(u'연두', u'Green')]),
        },
        {'type': 'Empty', 'height': 8},
        {
            'type': 'CheckBox',
            'text': L(u'내장 표현집 사용', u'Use the built-in phrasebook'),
            'varName': 'usePhrasebook',
            'value': cfg.get('usePhrasebook'),
            'tooltip': _tip(
                L(u'내장 표현집', u'Built-in phrasebook'),
                L(u'"рак", "свет", "топлюсь" 처럼 게임에서만 통하는 은어를 즉시, 그리고 '
                  u'기계번역보다 정확하게 옮깁니다. 내장 JSON 용어·보호 사전은 '
                  u'이 설정과 무관하게 적용됩니다.',
                  u'Game slang such as "рак", "свет" or "топлюсь" is answered locally, '
                  u'instantly, and more accurately than a raw machine translation. The '
                  u'embedded JSON glossary and preserve dictionary are applied independently.')),
        },
        {
            'type': 'CheckBox',
            'text': L(u'번역 캐시 사용', u'Cache translations'),
            'varName': 'useCache',
            'value': cfg.get('useCache'),
            'tooltip': _tip(
                L(u'번역 캐시', u'Translation cache'),
                L(u'같은 문장은 다시 요청하지 않습니다. 채팅은 반복이 많아서 요청량이 크게 줄어듭니다.',
                  u'Repeated lines are never requested twice. Battle chat repeats a lot, '
                  u'so this cuts request volume hard.')),
        },
        {
            'type': 'CheckBox',
            'text': L(u'디버그 로그', u'Debug log'),
            'varName': 'debug',
            'value': cfg.get('debug'),
            'tooltip': _tip(
                L(u'디버그 로그', u'Debug log'),
                L(u'mods/Tonymocchi_chat_translator/mod.log 에 자세한 기록을 남깁니다.',
                  u'Writes a verbose log to mods/Tonymocchi_chat_translator/mod.log.')),
        },
    ]

    return {
        'modDisplayName': L(u'Tonymocchi 채팅 번역기 (한국어 설정)',
                            u'Tonymocchi Chat Translator (English UI)'),
        'settingsVersion': SETTINGS_VERSION,
        'enabled': cfg.get('enabled'),
        'column1': column1,
        'column2': column2,
    }


def _on_settings(linkage, new_settings):
    try:
        if linkage != LINKAGE:
            return
        g_config.update(new_settings)
        _log('settings updated: %r' % (new_settings,))
    except Exception:
        _log_exc('settings callback failed')


_register_tries = [0]


def register_settings():
    try:
        from gui.modsSettingsApi import g_modsSettingsApi
    except Exception:
        _register_tries[0] += 1
        if _register_tries[0] < 20 and BigWorld is not None:
            BigWorld.callback(2.0, register_settings)
        else:
            _log('modsSettingsApi not found; running with defaults', force=True)
        return
    try:
        template = build_template()
        saved = g_modsSettingsApi.getModSettings(LINKAGE, template)
        if saved:
            g_modsSettingsApi.registerCallback(LINKAGE, _on_settings)
        else:
            saved = g_modsSettingsApi.setModTemplate(
                LINKAGE, template, _on_settings)
        g_config.update(saved)
        _log('settings registered', force=True)
    except Exception:
        _log_exc('settings registration failed; running with defaults')


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

_initialized = False
_RUNTIME_GUARD = '_tonymocchi_chat_translator_owner'


def _claim_runtime():
    """Allow one runtime instance, even if stale copies use another filename."""
    here = globals().get('__file__', '<unknown>')
    owner = getattr(sys, _RUNTIME_GUARD, None)
    if owner:
        if isinstance(owner, tuple) and owner[0] == __name__:
            return True
        active_path = owner[1] if isinstance(owner, tuple) else owner
        _log('DUPLICATE MOD COPY IGNORED; active=%s ignored=%s'
             % (active_path, here), force=True)
        return False
    try:
        setattr(sys, _RUNTIME_GUARD, (__name__, here))
    except Exception:
        pass
    return True


def init():
    global _initialized
    if _initialized:
        _log('%s %s already initialized; duplicate init ignored'
             % (MOD_NAME, MOD_VERSION))
        return
    if not _claim_runtime():
        return
    _initialized = True
    try:
        _log('%s %s loading (ui=%s, path=%s)'
             % (MOD_NAME, MOD_VERSION, UI_LANGUAGE,
                globals().get('__file__', '?')), force=True)
        dictionary_count = load_preserve_dictionary()
        cache_load()
        _start_workers()
        installed = install_chat_hooks()
        if BigWorld is not None:
            BigWorld.callback(PUMP_INTERVAL, _pump)
            BigWorld.callback(1.0, register_settings)
        else:
            register_settings()
        _log('%s %s ready (%d hook(s), phrasebook %d, dictionary entries %d)'
             % (MOD_NAME, MOD_VERSION, installed, len(PHRASEBOOK),
                dictionary_count), force=True)
    except Exception:
        _initialized = False
        _log_exc('init failed')


def fini():
    try:
        cache_save()
    except Exception:
        pass
