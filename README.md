# Tonymocchi Chat Translator v1.6.0

Mir Tankov(Мир танков) 전투 채팅의 러시아어를 자동으로 한국어 또는 영어로 번역하여 원문 아래에 표시하는 MTMOD입니다.

아시아 버전(World of Tanks Asia)은 해당 링크를 참조하십시오: https://github.com/Kim7obu/WOTChatTranslator

World of Tanks ASIA version: https://github.com/Kim7obu/WOTChatTranslator (only support Korean, but you can edit the final output language as you want. Just notice the credit and licence.)

https://github.com/user-attachments/assets/d30bd9c1-c26d-4c71-8554-0645bd8ba36a

Sample Video (Full Video: https://youtu.be/jaIe-GtVuGI)

<img width="934" height="431" alt="shot_024" src="https://github.com/user-attachments/assets/d606f90c-df04-489c-874e-3f693763a61f" />

FIG 1. 한글 설정창 / Mod setting page, Korean

<img width="322" height="128" alt="image" src="https://github.com/user-attachments/assets/d96c6c44-a8d7-4ef0-b963-aff9436e664b" />

FIG 2. 실제 번역 이미지 / In-game Translation Example, Korean

## 필수 요구 사항

**2026년 9월 6일 게임 버전 1.45 기준으로,
`izeberg.modssettingsapi_1.7.0`가 있어야 무조건 동작합니다.**
해당 모드는 [IzeBerg/modssettingsapi](https://github.com/izeberg/modssettingsapi)에서
받을 수 있습니다. [1.7.0 릴리스](https://github.com/izeberg/modssettingsapi/releases/tag/1.7.0)를
사용하세요.

한국어 결과를 정상적으로 표시하려면 한글 패치의 한글 폰트
(`fonts_ko.swf` 등)가 필요합니다. 한글 패치가 없는 사용자는 영어 번역을
선택하세요. 사전에 없는 문장을 번역하려면 인터넷 연결이 필요합니다.

## 배포 파일

- `Korean_UI/mod_TonymocchiChatTranslator_KO.mtmod`: 한국어 설정창,
  기본 번역 언어 한국어
- `English_UI/mod_TonymocchiChatTranslator_EN.mtmod`: 영어 설정창,
  기본 번역 언어 영어
- `Source/*.py`: 각 MTMOD에 들어간 PYC의 CPython 2.7 컴파일 전 소스
- `Compiled/*.pyc`: MTMOD에 포함된 CPython 2.7 바이트코드 복사본
- `Config/preserve_dictionary.json`: 실제 MTMOD에 들어간 양언어 사전
- `DictionaryTools/`: 사전 원본, 영문 대응표, 빌더, 검증기
- `Tests/test_offline.py`: 빠른 연속 채팅과 사전·캐시·훅 회귀 검사

두 MTMOD를 동시에 설치하지 마세요. 둘 중 하나만 선택하면 되며,
두 배포판 모두 설정에서 출력 번역 언어를 한국어/영어로 바꿀 수 있습니다.

## 설치

1. 기존 `mod_*ChatTranslator.py`, `.pyc`, `.mtmod`가 `mods/`나
   `res_mods/`에 중복 설치되어 있다면 먼저 정리합니다.
2. `izeberg.modssettingsapi_1.7.0`을 설치합니다.
3. KO 또는 EN MTMOD 중 하나만 Mir Tankov의 현재 클라이언트 버전
   폴더 `mods/<current client version>/`에 넣습니다.
4. 게임을 완전히 종료했다가 다시 실행합니다.
5. 모드 설정에서 번역 언어, 아군/적군/본인 채팅, 표시 방식, 색상,
   번역 엔진을 선택합니다.

## v1.5.x에서 업데이트

이번에는 **JSON만 교체하면 안 됩니다.** v1.5.x PYC는 새
`translateTerms` 구조를 해석하지 못하므로 KO 또는 EN MTMOD 하나를 통째로
교체해야 합니다.

1. `mods/`와 `res_mods/` 아래의 이전 `mod_*ChatTranslator.py`, `.pyc`,
   `.mtmod` 중복 사본을 정리합니다.
2. KO 또는 EN MTMOD 하나를 현재 클라이언트 버전 폴더
   `mods/<current client version>/`에 넣습니다.
3. 게임을 완전히 종료했다가 다시 실행합니다.

v1.6.0을 한 번 설치한 뒤 같은 스키마의 사전 내용만 고치는 경우에는
`preserve_dictionary.json`만 교체해도 됩니다.

## 모드 동작

- 채팅에 올라온 러시아어를 한국어 또는 영어로 번역해 사용자
  클라이언트에만 표시합니다.
- 영어 문장과 러시아어가 아닌 문장은 번역하지 않습니다.
- 기본 전술 핑·라디오 명령은 구조적 명령 ID와 보조 문자열 판정으로
  무시합니다.
- 기본 표시 방식은 원문을 즉시 보여 준 뒤, 완료된 번역을 별도 줄로
  추가하는 `별도 줄로` 모드입니다.
- 상대가 빠르게 여러 줄을 보내도 각 완료 결과를 독립적으로 표시하며,
  마지막 줄만 남는 문제를 해결했습니다.
- 같은 문장이 동시에 들어오면 HTTP 요청 하나로 합친 뒤 모든 채팅 줄에
  결과를 나누어 줍니다.
- 캐시에 같은 문장이 있으면 새 게임 세션에서도 API를 다시 호출하지
  않고 즉시 표시합니다.
- `ахах`, `ахахахх` 같은 러시아어 웃음은 API 없이 문자열 길이의
  절반만큼 한국어 `ㅋ` 또는 영어 `ha`를 즉시 출력합니다.
- 기능이 없던 테스트 버튼은 제거했습니다.

## JSON 사전

내부 경로:

```text
res/scripts/client/gui/mods/TonymocchiChatTranslator/preserve_dictionary.json
```

**`preserveTerms` 보존 사전에 미리 등록된 단어는 번역하지 않고 그대로
출력하는 것이 원칙입니다.** `translateTerms`는 사용자가 명시적으로
교체할 러시아어 게임 용어를 정의하는 별도 매핑입니다.

| JSON 키 | 역할 |
|---|---|
| `preserveTerms` | 전차명·고유명사를 원문 표기 그대로 보존 |
| `translateTerms` | 문장 안의 러시아어 용어를 `ko`/영어 `en` 고정 용어로 치환 |
| `exactTranslations` | 채팅 전체가 해당 표현일 때만 즉시 치환 |
| `settings` | 대소문자, `е/ё`, 단어 경계 판정 설정 |

배포 사전은 검수된 179개 표제어의 격변화형을 확장한
`translateTerms` 2,464개를 포함합니다. `е/ё` 정규화 후 실제 메모리에서는
2,383개의 양언어 매핑으로 작동합니다.

```json
{
  "preserveTerms": ["World of Tanks", "ИС-7", "Объект 140"],
  "translateTerms": {
    "голде": {"ko": "골탄", "en": "premium ammo"},
    "бронебойным": {"ko": "은탄", "en": "standard ammo"}
  },
  "exactTranslations": {
    "гг": {"ko": "ㅈㅈ", "en": "gg"},
    "лт": {"ko": "경전차", "en": "light tank"}
  }
}
```

단어를 토큰으로 가린 뒤 외부 번역을 하고 결과에 고정 용어를 복원하므로,
`голде`·`голдой`·`голды`가 문장 안에 있어도 `골탄 / premium ammo`으로
유지됩니다. `C8` 같은 맵 좌표도 같은 방식으로 보호합니다. 토큰이 훼손된
응답은 버리고 다음 번역 엔진으로 재시도합니다.

### JSON 수정·재패키징

JSON 사전의 업데이트는 MTMOD를 압축 해제하여 JSON 안의 내용만
업데이트한 후, 해당 JSON이 포함된 전체 패키지를 MTMOD로 만들어서
재활용할 수 있습니다.

1. MTMOD를 ZIP처럼 엽니다.
2. 위 경로의 JSON을 BOM 없는 UTF-8로 수정합니다.
3. `meta.xml`과 `res/`가 압축 파일의 최상위에 있도록 ZIP으로 다시
   압축한 뒤 확장자를 `.mtmod`로 바꿉니다.
4. 기존 MTMOD를 교체하고 게임을 재시작합니다.

사전은 게임 시작 시 한 번만 읽습니다. `DictionaryTools/glossary.md`와
`english_glossary.json`을 수정한 뒤 `python build_dictionary.py`를 실행하면
격변화형을 포함한 JSON을 재생성할 수 있습니다.

## 속도 구조

- JSON은 매 채팅마다 읽지 않고 게임 시작 시 한 번만 파싱합니다.
- 전체 문장 일치는 해시 조회로 평균 O(1)입니다.
- 2천 개가 넘는 단일 단어 활용형은 거대 정규식이 아니라 토큰 스캐너가
  한 번 훑고 해시 집합에서 찾습니다.
- 여러 단어로 된 소수의 표현만 긴 표현 우선 정규식으로 한 번 컴파일합니다.
- CPython 2.7.18 실측: 로더 집계 2,404개 항목 시작 로딩 약 21ms,
  20,000회 반복 기준 문장당 사전 처리 약 0.034ms.
- 사전 내용이 바뀌면 개정 해시가 바뀌어 이전 규칙으로 만든 캐시만
  자동으로 무효화됩니다.
- 네트워크 요청은 4개 워커에서 실행되고 결과는 0.02초 주기로 게임
  메인 스레드에 안전하게 전달됩니다.

## 번역 엔진과 주의사항

자동 모드는 API 키 없이 접속 가능한 Google, Google 보조 경로, Lingva,
MyMemory를 순차적으로 사용합니다. 요금·API 키가 필요 없는 공개 접속
경로이지만, 제3자 서비스이므로 무제한 사용과 항상 가능한 운영을 계약적으로
보장하지는 않습니다. 특정 엔진이 실패하면 자동 모드가 다음 엔진으로
전환합니다.

원문은 먼저 표시되므로 API 장애가 있어도 기본 채팅은 사라지지 않습니다.
로그와 캐시는 `mods/Tonymocchi_chat_translator/`에 저장됩니다.

## 검증 환경

- Mir Tankov 1.45 채팅 클래스 경로
- CPython 2.7.18 PYC (`03 f3 0d 0a` magic)
- `izeberg.modssettingsapi_1.7.0` 템플릿 API
- 오프라인 통합·회귀 테스트 18개
- 사전 KO/EN 활용형·오매칭·토큰 복원 검사

---

# English

Tonymocchi Chat Translator is an MTMOD that translates Russian Mir Tankov
(Мир танков) battle chat into Korean or English and displays each result on a
separate line below the original message.

## Prerequisites

**As of September 6, 2026, targeting Mir Tankov version 1.45,
`izeberg.modssettingsapi_1.7.0` is strictly required for this mod to function.**
Download it from
[IzeBerg/modssettingsapi](https://github.com/izeberg/modssettingsapi) and use the
[1.7.0 release](https://github.com/izeberg/modssettingsapi/releases/tag/1.7.0).

Displaying Korean output requires a Korean localization font such as
`fonts_ko.swf`. Users without a Korean font patch should select English output.
An active internet connection is required for sentences not covered by the
local dictionary, phrasebook, or persistent cache.

## Package Files

- `Korean_UI/mod_TonymocchiChatTranslator_KO.mtmod`: Korean settings UI and
  Korean as the default output language.
- `English_UI/mod_TonymocchiChatTranslator_EN.mtmod`: English settings UI and
  English as the default output language.
- `Source/*.py`: uncompiled CPython 2.7 source corresponding to each MTMOD.
- `Compiled/*.pyc`: standalone copies of the CPython 2.7 bytecode bundled in
  the MTMOD files.
- `Config/preserve_dictionary.json`: the bilingual dictionary bundled in both
  MTMOD files.
- `DictionaryTools/`: editable glossary sources, English mappings, dictionary
  builder, and verifier.
- `Tests/test_offline.py`: regression tests for rapid chat, dictionary handling,
  cache behavior, and the chat hook.

Do **not** install both MTMOD files at the same time. Choose one based on the
preferred settings UI language. Both builds can switch the translation output
between Korean and English from the settings menu.

## Installation

1. Remove duplicate or outdated `mod_*ChatTranslator.py`, `.pyc`, and `.mtmod`
   files from `mods/` and `res_mods/`.
2. Install `izeberg.modssettingsapi_1.7.0`.
3. Place either the KO or EN MTMOD in the current Mir Tankov client version
   directory: `mods/<current client version>/`.
4. Fully close and relaunch the game client.
5. Configure the target language, Allies/Enemies/Self channels, display mode,
   color, and translation provider in the mod settings.

## Updating from v1.5.x

Replacing only the JSON is **not sufficient for this update**. The v1.5.x PYC
does not understand the new `translateTerms` structure, so replace the complete
KO or EN MTMOD package.

After v1.6.0 has been installed once, later dictionary-only updates using the
same schema require replacing only `preserve_dictionary.json` inside the MTMOD
and restarting the game.

## Mod Behavior

- Translates Russian chat into Korean or English only on the user's client.
- Leaves English and non-Russian messages untranslated.
- Ignores standard tactical pings and radio commands using structural command
  IDs plus conservative text checks.
- Shows the original message immediately, then appends the completed translation
  as a separate chat line by default.
- Handles rapid chat messages independently, preventing the previous issue in
  which only the last completed translation appeared.
- Coalesces identical concurrent messages into one HTTP request, then distributes
  the result to every corresponding chat line.
- Reuses a matching cached translation immediately, including in a new game
  session, without making another API request.
- Converts Russian laughter such as `ахах` and `ахахахх` locally. Korean
  output repeats `ㅋ` and English output repeats `ha` according to half of the
  compact source length.
- Allows only the first loaded copy to run and logs the paths of ignored
  duplicate installations.
- Removes the old non-functional test button.

## JSON Dictionary

Internal path:

```text
res/scripts/client/gui/mods/TonymocchiChatTranslator/preserve_dictionary.json
```

**Terms registered under `preserveTerms` are retained in their original spelling
without translation.** `translateTerms` is a separate, explicit mapping for
Russian tank-game terminology selected by the user.

| JSON key | Purpose |
|---|---|
| `preserveTerms` | Preserves vehicle names and proper nouns exactly as written |
| `translateTerms` | Restores an explicit Korean `ko` or English `en` term inside a translated sentence |
| `exactTranslations` | Applies only when the entire chat message matches the entry |
| `settings` | Controls case folding, `е/ё` normalization, and whole-word matching |

The bundled dictionary contains 2,464 inflected entries generated from 179
reviewed Russian headwords. After `е/ё` normalization, it operates as 2,383
bilingual in-memory mappings.

```json
{
  "preserveTerms": ["World of Tanks", "ИС-7", "Объект 140"],
  "translateTerms": {
    "голде": {"ko": "골탄", "en": "premium ammo"},
    "бронебойным": {"ko": "은탄", "en": "standard ammo"}
  },
  "exactTranslations": {
    "гг": {"ko": "ㅈㅈ", "en": "gg"},
    "лт": {"ko": "경전차", "en": "light tank"}
  }
}
```

Terms are replaced with stable placeholders before an external translation
request and restored afterward. Consequently, inflected forms such as `голде`,
`голдой`, and `голды` remain `골탄 / premium ammo` inside longer sentences.
Map coordinates such as `C8` are protected in the same way. If a provider
damages or removes a placeholder, its response is rejected and the next
provider is tried.

### Updating and Repackaging the JSON

The dictionary can be updated without recompiling the PYC after v1.6.0 is
installed:

1. Open the MTMOD as a ZIP archive.
2. Edit the JSON at the internal path above using UTF-8 without a BOM.
3. Recompress the complete package with `meta.xml` and `res/` at the ZIP root.
   Placing them inside another parent directory prevents the mod from loading.
4. Rename the extension to `.mtmod`, replace the installed package, and restart
   the game.

The dictionary is parsed once during game startup and is not reloaded while the
client is running. To rebuild all Russian inflections, edit
`DictionaryTools/glossary.md` and `english_glossary.json`, then run:

```bash
python build_dictionary.py
python verify_dictionary.py
```

## Performance Architecture

- The JSON is parsed once at startup and is never read on the per-message hot
  path.
- Whole-message matches use hash lookup with average O(1) behavior.
- More than 2,000 single-word inflections are scanned once per message and
  checked against a hash set instead of being compiled into a giant alternation
  regex.
- Only the small group of multi-word expressions is compiled into a
  longest-first regex at startup.
- Dictionary changes produce a new revision hash, automatically ignoring cache
  entries generated under older dictionary rules.
- Four worker threads process distinct network translations. Results are passed
  safely back to the game thread at 0.02-second intervals.
- Measured under CPython 2.7.18: approximately 21 ms to load 2,404 loader-counted
  entries and approximately 0.034 ms of dictionary processing per sample message
  over 20,000 iterations.

## Translation Engines and Limitations

Auto mode tries keyless endpoints in this order: Google, the secondary Google
route, Lingva, and MyMemory. They do not require a paid API key, but they are
third-party services and do not contractually guarantee unlimited usage,
availability, or an SLA. If one provider fails, Auto mode moves to the next
available provider.

The original chat line is displayed first, so an API outage cannot hide normal
battle chat. Debug logs and the persistent cache are stored under
`mods/Tonymocchi_chat_translator/`.

## Verification Environment

- Mir Tankov 1.45 battle-chat class structure.
- CPython 2.7.18 PYC with magic bytes `03 f3 0d 0a`.
- `izeberg.modssettingsapi_1.7.0` template API.
- 18 offline integration and regression tests.
- Separate Korean/English inflection, false-match, and placeholder-restoration
  checks.

## Version History

### 1.6.0

- Integrated the supplied 2,464-form Russian tank glossary.
- Added bilingual `ko`/`en` values and safe compatibility with Korean-only v2
  dictionary files.
- Added whole-message `гг -> ㅈㅈ / gg` and `лт -> 경전차 / light tank`.
- Applied the reviewed `бб -> 은탄 / standard ammo` terminology.
- Replaced the giant term-alternation regex with a token scanner plus hash
  lookup while retaining a compact regex for multi-word entries.
- Protected map coordinates such as `C8` during external translation.
- Retained the rapid-chat fix, duplicate-request fan-out, persistent cache,
  laughter conversion, duplicate-runtime guard, and removal of the test button.

### 1.5.0

- Added the original user-editable JSON preserve dictionary.
- Loaded the dictionary once and invalidated stale cache entries by dictionary
  revision.
