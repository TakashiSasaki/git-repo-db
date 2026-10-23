## Parse line-leading BOMs without weakening receipt verification

A GitHub job-log response can concatenate chunks containing U+FEFF at the first character of an interior timestamped line. On this initial Access log, one DATA record began with BOM at line13221. A timestamp regex anchored directly to the digit omitted that120-character base64 chunk: decoded1992701 bytes instead of advertised1992791, with a SHA256 mismatch. Retain that raw log and failed parser result.

When selecting actual receipt records, permit one optional BOM **only before the strict timestamp at line start**, for example:

```python
r'^\ufeff?\d{4}-\d\d-\d\dT\S+ (CI_RECEIPTS_(?:BEGIN|DATA|END)_V1 .+)$'
```

Do not strip BOMs, whitespace or arbitrary characters from payloads. Keep exactly one BEGIN, ordered DATA and matching END, strict base64, exact closed-ZIP byte length/SHA256 and compressed limit, unique ZIP members, complete index lengths/hashes and actual run/feature/checkout/tree binding. A parser adjustment does not authorize repairing an incomplete receipt or inferring missing payloads.

Here, the optional prefix recovers exactly1992791 bytes/SHA256 `65ab48ba62dad77faa806632c268fb642064e08ad59edf27d0bfd6c6b94c017d`, with123 verified indexed payloads. Twelve external controls accept original/normalized/single-prefix forms and reject missing, duplicated, reordered or corrupt DATA, malformed base64, payload/double-prefix BOM, duplicate BEGIN and a tampered index with a valid outer hash. See `test_bom_parser_controls.py`, `bom-parser-controls.json`, retained initial parser/hash failure and `plugin-access-receipt-diagnostic.json`. These are receipt-parser controls, not product tests or independent acceptance.
