# Tonymocchi Chat Translator v1.5.0

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

**2026년 9월 6일, 게임 버전 1.45 기준으로 `izeberg.modssettingsapi_1.7.0`가 있어야 무조건 동작합니다.** 해당 모드는 [IzeBerg/modssettingsapi](https://github.com/izeberg/modssettingsapi)에서 받을 수 있습니다. 배포판은 [1.7.0 릴리스](https://github.com/izeberg/modssettingsapi/releases/tag/1.7.0)를 사용하세요.

한국어 번역 결과를 정상적으로 보려면 한글 패치의 한글 폰트(`fonts_ko.swf` 등)가 필요합니다. 한글 패치가 없는 사용자는 영어 번역을 선택하세요. 인터넷 연결도 필요합니다.

## 배포 파일

- `Korean_UI/mod_TonymocchiChatTranslator_KO.mtmod`: 한국어 설정창, 기본 번역 언어 한국어
- `English_UI/mod_TonymocchiChatTranslator_EN.mtmod`: 영어 설정창, 기본 번역 언어 영어
- `Source/mod_TonymocchiChatTranslator_KO.py`: 한국어 UI 모드의 컴파일 전 소스
- `Source/mod_TonymocchiChatTranslator_EN.py`: 영어 UI 모드의 컴파일 전 소스
- `Config/preserve_dictionary.json`: MTMOD에 포함된 JSON 보호 사전의 원본

두 MTMOD를 동시에 설치하지 마세요. 설정창 언어에 맞는 하나만 선택하면 되며, 두 배포판 모두 설정에서 출력 번역 언어를 한국어/영어로 바꿀 수 있습니다.

## 설치

1. 이전 버전의 `mod_*ChatTranslator.py`, `.pyc`, `.mtmod`가 `mods/`나 `res_mods/`에 중복 설치되어 있다면 먼저 정리합니다.
2. `izeberg.modssettingsapi_1.7.0`을 설치합니다.
3. KO 또는 EN MTMOD 하나만 Mir Tankov의 현재 클라이언트 버전 폴더 `mods/<current client version>/`에 넣습니다.
4. 게임을 완전히 종료했다가 다시 실행합니다.
5. 모드 설정에서 번역 언어, 아군/적군/본인 채팅, 표시 방식, 색상, 번역 엔진을 선택합니다.

## JSON 보호 사전

**사전에 미리 등록된 단어는 번역을 하지 않고 그대로 출력하는 게 원칙입니다.**

내부 경로:

```text
res/scripts/client/gui/mods/TonymocchiChatTranslator/preserve_dictionary.json
```

작동 예시:

| 입력 | 결과 |
|---|---|
| `ИС-7` | API를 호출하지 않고 `ИС-7` 그대로 표시 |
| `ИС-7 поехал в город` | `ИС-7`은 원형 보존, 나머지 러시아어만 번역 |
| `Объект 140!` | 대소문자·문장부호 설정에 따라 사전 일치 후 원문 유지 |

JSON에서 사용자가 조정할 수 있는 값:

| 키 | 기본값 | 의미 |
|---|---:|---|
| `enabled` | `true` | 보호 사전 사용 |
| `caseInsensitive` | `true` | 대소문자를 구분하지 않고 찾되 출력은 실제 입력 표기를 유지 |
| `normalizeYo` | `true` | 러시아어 `е`와 `ё`를 같은 글자로 비교 |
| `matchWholeWords` | `true` | 다른 단어 중간의 일부를 잘못 보호하지 않음 |
| `preserveTerms` | 배열 | 번역에서 제외할 단어·전차명·고유명사 |

### JSON 업데이트 방법

JSON 사전의 업데이트는 MTMOD를 압축 해제하여 JSON 안의 내용만 업데이트한 후에, 해당 JSON이 포함된 전체 패키지를 MTMOD로 만들어서 재활용할 수 있습니다.

1. MTMOD를 ZIP 압축 파일처럼 엽니다.
2. 위 경로의 `preserve_dictionary.json`만 UTF-8로 수정합니다.
3. `meta.xml`과 `res/`가 압축 파일의 최상위에 오도록 전체 패키지를 다시 ZIP으로 압축합니다. 중간에 상위 폴더가 하나 더 들어가면 모드가 로드되지 않습니다.
4. 확장자를 `.mtmod`로 바꾸고 기존 파일과 교체한 뒤 게임을 재시작합니다.

사전은 게임 시작 시 한 번만 읽습니다. 실행 중 JSON을 바꿔도 즉시 재로드되지 않으며, 새 MTMOD를 적용한 후 게임을 재시작해야 합니다.

## 속도 구조

- JSON을 매 채팅마다 읽지 않고 시작 시 한 번만 파싱합니다.
- 전체 문장 일치는 `frozenset` 해시 조회로 평균 O(1)에 판별합니다.
- 문장 안 단어 보호는 모드 시작 시 긴 단어 우선으로 한 번 컴파일한 정규식을 사용합니다.
- 사전 수정 시 개정 해시가 바뀌어 예전 규칙으로 생성된 번역 캐시만 자동으로 무효화됩니다.
- 기본 은어 표현집과 번역 캐시는 네트워크 호출 없이 즉시 응답합니다.
- 서로 다른 연속 채팅은 4개 워커가 독립 처리하고, 같은 문장이 동시에 들어오면 HTTP 요청 하나로 합친 뒤 모든 채팅 줄에 결과를 나눠 줍니다.

JSON은 바이트코드에 직접 넣은 상수보다 초기 1회 로딩 비용이 조금 있지만, 채팅 처리 중에는 이미 컴파일된 메모리 구조만 사용하므로 실전 처리 속도 차이는 사실상 없습니다.

## 기능

- 러시아어 문장만 보수적으로 판별하여 번역
- 영어·한국어·러시아어가 아닌 키릴 문자 중심 문장은 제외
- 기본 전술 핑·라디오 명령 무시
- 원문 유지 + 번역을 별도 줄로 표시하는 방식이 기본값
- 빠른 연속 채팅의 모든 번역 결과를 누락 없이 각각 표시
- `ахах`, `ахахахх` 같은 러시아어 웃음은 API 없이 한국어 `ㅋ`, 영어 `ha` 반복으로 변환
- 같은 문장의 캐시는 새 게임 세션에서도 `mods/Tonymocchi_chat_translator/cache.json`을 읽어 즉시 재사용
- 중복 모드 사본이 있으면 첫 인스턴스만 동작하고 나머지는 로그에 경로를 남김
- 기존의 기능 없는 테스트 버튼은 제거됨

## 번역 엔진과 주의사항

자동 모드는 API 키 없이 접속 가능한 Google, Google 보조 경로, Lingva, MyMemory를 순차적으로 사용합니다. 이들은 무료·키리스 접속이 가능하지만, 제3자 서비스이므로 무제한 사용과 항상 가능한 운영을 계약적으로 보장하지는 않습니다. 특정 엔진이 실패하면 자동 모드가 다음 엔진으로 빠르게 전환합니다.

원문은 먼저 표시되므로 API 장애가 있어도 기본 채팅은 사라지지 않습니다. 디버그 로그는 `mods/Tonymocchi_chat_translator/mod.log`에 저장됩니다.

## 검증 환경

- Mir Tankov 1.45 클라이언트 채팅 클래스 경로 기준
- CPython 2.7.18 PYC (`03 f3 0d 0a` magic)
- `izeberg.modssettingsapi_1.7.0` 템플릿 API 기준
- 오프라인 통합·회귀 테스트 14개

===

# English

## Prerequisites

**As of September 6, 2026, targeting Mir Tankov version 1.45, `izeberg.modssettingsapi_1.7.0` is strictly required for this mod to function.** You can obtain this dependency from [IzeBerg/modssettingsapi](https://github.com/izeberg/modssettingsapi). Please use the [1.7.0 Release](https://github.com/izeberg/modssettingsapi/releases/tag/1.7.0).

Displaying Korean translation output requires a Korean font patch (`fonts_ko.swf`, etc.). Users without a Korean localization patch should select English translation output in the settings. An active internet connection is also required.

---

## Package Files

- `Korean_UI/mod_TonymocchiChatTranslator_KO.mtmod`: Korean settings UI, defaults to Korean translation.
- `English_UI/mod_TonymocchiChatTranslator_EN.mtmod`: English settings UI, defaults to English translation.
- `Source/mod_TonymocchiChatTranslator_KO.py`: Uncompiled source for the Korean UI build.
- `Source/mod_TonymocchiChatTranslator_EN.py`: Uncompiled source for the English UI build.
- `Config/preserve_dictionary.json`: Source file of the JSON preserve dictionary bundled in the MTMOD.

> **Note:** Do **NOT** install both MTMOD files simultaneously. Select only one package based on your preferred UI language. Both versions allow you to switch the target translation output between Korean and English inside the mod settings.

---

## Installation

1. Remove any previous versions of `mod_*ChatTranslator.py`, `.pyc`, or `.mtmod` from `mods/` or `res_mods/` to avoid conflicts.
2. Install `izeberg.modssettingsapi_1.7.0`.
3. Place either the KO or EN `.mtmod` file into your current Mir Tankov client version directory: `mods/<current client version>/`.
4. Relaunch the game client completely.
5. Configure translation language, chat channels (Allies/Enemies/Self), display format, colors, and translation engines in the mod settings menu.

---

## JSON Preserve Dictionary

**Terms registered in the preserve dictionary are retained as-is without sending requests to translation APIs.**

Internal path:
```text
res/scripts/client/gui/mods/TonymocchiChatTranslator/preserve_dictionary.json
```

### Examples

| Input | Output |
|---|---|
| `ИС-7` | Displayed directly as `ИС-7` without calling the API |
| `ИС-7 поехал в город` | `ИС-7` is preserved; the rest of the Russian sentence is translated |
| `Объект 140!` | Original term preserved based on case/punctuation matching settings |

### Configurable JSON Keys

| Key | Default | Description |
|---|---:|---|
| `enabled` | `true` | Enables/disables the preserve dictionary |
| `caseInsensitive` | `true` | Case-insensitive matching while preserving original casing in output |
| `normalizeYo` | `true` | Treats Russian `е` and `ё` as equivalent during matching |
| `matchWholeWords` | `true` | Prevents accidental partial matching inside longer words |
| `preserveTerms` | Array | List of terms, vehicle names, and proper nouns to exclude from translation |

### Updating the JSON Dictionary

To update the dictionary, extract the MTMOD package, edit the JSON contents, re-pack the entire structure back into an MTMOD file, and reuse it.

1. Open the `.mtmod` file as a ZIP archive.
2. Edit `preserve_dictionary.json` at the path above using UTF-8 encoding.
3. Re-compress the entire package so that `meta.xml` and `res/` remain at the root of the ZIP structure. *(Placing them inside a subfolder will break mod loading).*
4. Rename the extension back to `.mtmod`, overwrite the existing package in your `mods/` directory, and restart the game.

> **Note:** The dictionary is parsed only once at game startup. Changes will not apply dynamically in-game until the client is restarted with the updated MTMOD.

---

## Performance Architecture

- **Single Parsing:** Parsed once at startup rather than reading the JSON file on every chat line.
- **O(1) Full Matching:** Full-sentence matches are checked in average O(1) time via `frozenset` hash lookup.
- **Precompiled Regex:** In-sentence term masking utilizes regex compiled at startup, prioritized by term length.
- **Revision Invalidation:** Dictionary modifications update the revision hash, automatically invalidating stale translation caches generated under previous rules.
- **Instant Response:** Local slang rules and cached entries return immediate responses without network calls.
- **Thread Pool & Deduplication:** Up to 4 worker threads independently process distinct chat bursts, while identical concurrent messages are merged into a single HTTP request and distributed to all matching chat lines.

---

## Features

- Conservative detection logic ensuring only Russian chat messages are translated.
- Excludes non-Russian Cyrillic scripts as well as standard English and Korean.
- Ignores default tactical pings and radio commands.
- Defaults to displaying the original chat alongside the translated line.
- Ensures all rapid consecutive chat lines are rendered without dropping messages.
- Converts Russian laughter (e.g., `ахах`, `ахахахх`) locally into repeated English `ha` or Korean `ㅋ` without API calls.
- Sentence caches persist across sessions via `mods/Tonymocchi_chat_translator/cache.json`.
- Duplicate mod installations are safely handled: only the first loaded instance operates, logging paths of ignored duplicates.
- Unused non-functional test UI elements have been removed.

---

## Translation Engines & Notes

Auto mode sequentially queries keyless APIs: **Google**, **Google Secondary**, **Lingva**, and **MyMemory**. While these services do not require API keys, they are third-party services and do not guarantee unlimited uptime or SLA. If an engine fails, Auto mode seamlessly shifts to the next available provider.

Original chat messages display instantly, ensuring chat visibility remains unaffected during API outages. Debug logs are written to `mods/Tonymocchi_chat_translator/mod.log`.

---

## Verification Environment

- Tested against Mir Tankov 1.45 client chat class structures.
- CPython 2.7.18 PYC (`03 f3 0d 0a` magic).
- `izeberg.modssettingsapi_1.7.0` template API contract.
- Validated with 14 offline integration and regression tests.
## Version history

### 1.5.0

- Added the user-editable JSON preserve dictionary to both KO and EN MTMODs.
- Compiles JSON once into a hash set and longest-first regex; no per-message disk or JSON work.
- Dictionary fingerprints safely invalidate translations cached under older rules.
- Preserves every registered term verbatim inside translated sentences.
- Retains the rapid-chat, duplicate-request coalescing, persistent-cache, and Russian-laughter fixes from 1.3.0.
