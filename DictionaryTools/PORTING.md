# Tonymocchi Chat Translator v1.6 dictionary notes

This dictionary port is already integrated in both v1.6 PYC builds. Do not copy
the old four-snippet patch into the source again.

## Public JSON schema

- `preserveTerms`: keep the matched source spelling unchanged.
- `translateTerms`: replace a Russian tank term with its configured `ko` or
  `en` value. A legacy plain string is treated as Korean-only.
- `exactTranslations`: whole-message-only overrides for short or ambiguous
  abbreviations. The package uses this for `гг` and `лт`.
- `settings`: case folding, `е`/`ё` normalization and whole-word matching.

Example:

```json
{
  "translateTerms": {
    "голде": {"ko": "골탄", "en": "premium ammo"},
    "фугасы": {"ko": "고폭탄", "en": "HE shell"}
  },
  "exactTranslations": {
    "гг": {"ko": "ㅈㅈ", "en": "gg"}
  }
}
```

## Runtime implementation

The JSON is read once at startup. Exact messages use hash lookup. Single-word
inflections are found by one generic token scanner and a hash set; only the
small number of multi-word expressions are compiled into a longest-first regex.
Matched terms and map coordinates are replaced with `TMCXKEEP####X` tokens
before the network request and restored after it. A provider that damages a
token is rejected and the next provider is tried.

This is why editing JSON does not add per-message disk or JSON overhead. A
dictionary change also changes the cache namespace, so stale cached translations
are ignored automatically.

## Rebuilding

Edit `glossary.md` for Russian/Korean terminology and
`english_glossary.json` for the matching English output, then run:

```bash
python build_dictionary.py
python verify_dictionary.py
```

The builder writes a bilingual `preserve_dictionary.json` and enforces the
mod's 1 MiB / 10,000-entry limits. Terms marked `[off]` in the Markdown are not
embedded in sentences because replacing verbs or greetings with noun-like
tokens can damage machine-translation grammar.
