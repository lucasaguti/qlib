# Data-Limitation Resolution Review

**Review date:** 2026-09-25 America/New_York (online checks completed 2026-09-26 UTC)  
**Repository revision reviewed:** `d19677c59a8d229f53681af26654e28cde74fe64`  
**Disposition:** development may continue; confirmatory claims remain blocked

## 2026-09-22 source gap

The date was a regular XNYS session. `exchange-calendars==4.13.2` reports an
open at 2026-09-22 13:30 UTC and close at 20:00 UTC. The registered BKNG and
SPY files contain the session, while the immutable ABNB and EXPE source
versions do not.

Current Yahoo historical pages and a diagnostic query of Yahoo's chart
endpoint were checked on 2026-09-26 UTC. The chart responses were retrieved at
02:04:36.794340 UTC (ABNB; response SHA-256
`810315e73089abf7500212855be196efe13cd105a829bafe4c32afe2fd041a69`) and
02:04:36.990540 UTC (EXPE; response SHA-256
`1908c3b8df365f49a286720dbde98100c8b943da5a2fbd0fbc6b307d650c6c75`).
Both now expose observations for the missing session:

| Security | Open | High | Low | Close | Adjusted close | Volume |
|---|---:|---:|---:|---:|---:|---:|
| ABNB | 169.08 | 169.60 | 160.70 | 161.81 | 161.81 | 4,960,700 |
| EXPE | 285.25 | 287.12 | 263.18 | 280.70 | 280.70 | 6,267,500 |

The page-rendered volumes differed slightly from the chart endpoint
(4,961,710 for ABNB and 6,271,050 for EXPE), while OHLC and adjusted close
agreed to the displayed precision. This variation reinforces that the later
observation is a different provider view, not proof of the bytes that should
have been returned by the 2026-09-24 extraction.

No source file was patched and no online response was retained as research
input. The registered versions remain immutable, and ABNB and EXPE on
2026-09-22 remain `MISSING_SOURCE`. A replacement may be admitted only as a
new source version with provider authorization, retrieval evidence, checksum,
and the availability and adjustment-state fields required by the charter.

Sources checked:

- ABNB historical page: <https://finance.yahoo.co.jp/quote/ABNB/history>
- EXPE historical page: <https://finance.yahoo.co.jp/quote/EXPE/history>
- Diagnostic chart requests used `query1.finance.yahoo.com/v8/finance/chart/{ticker}`
  with `period1=1789948800`, `period2=1790208000`, `interval=1d`,
  `events=div,splits`, and `includeAdjustedClose=true`.

## Price and corporate-action evidence

The diagnostic chart response establishes only that the displayed 2026-09-22
values were available when queried on 2026-09-26 UTC. It cannot establish
their availability at the original extraction time or reconstruct historical
provider versions at earlier forecast origins.

A full-range diagnostic action query between 02:00:19 and 02:00:21 UTC on
2026-09-26 matched every explicit dividend and split row in the four
registered CSVs:

| Security | Current endpoint actions | Registered actions | Canonical event-list SHA-256 |
|---|---|---|---|
| ABNB | none | none | `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a` |
| BKNG | 11 dividends, 1 split | 11 dividends, 1 split | `a3071374f914ae24f0f48eccdf9044d0cd6780cedadb30360f94998dd67d6785` |
| EXPE | 12 dividends | 12 dividends | `6c0a90403d063adca4853019b50bd07da5249fc179f50819a263ff019c4e7afe` |
| SPY | 31 dividends | 31 dividends | `c7e1b14d2c39c8070f716474752571632df31c07776209cc5f8c783e5c7beb01` |

The hashes cover compact JSON event lists with sorted keys and no whitespace;
they do not hash or retain Yahoo response bodies. Matching the current action
list is corroboration, not point-in-time evidence. The sources still lack:

- an immutable price version captured at each historical information cutoff;
- `price_available_at` evidence for each observation;
- an immutable adjustment-state version and its release/effective semantics;
- `adjustment_state_available_at` evidence; and
- a provider correction/revision history connecting raw close, actions, and
  adjusted close.

Accordingly, point-in-time price and corporate-action provenance remains
`BLOCKED`. The manifest field `point_in_time_vintage_verified: true` remains an
unsupported assertion and is not accepted by the pipeline.

## Rights review

No contract, subscription entitlement, institutional license, provider
permission, or user authorization accompanied the files. The current
`yfinance` documentation says the package is unaffiliated with Yahoo, directs
users to Yahoo's terms for data rights, and describes the Yahoo Finance API as
intended for personal use. Yahoo's current general terms prohibit automated
data collection without express prior permission and note that some service
content belongs to third parties. Those public terms do not provide the
project-specific grants required by the charter.

| Required right | Status | Evidence needed before confirmatory use |
|---|---|---|
| Automated extraction | `BLOCKED` | Express provider/vendor permission or a licensed delivery mechanism covering this extraction |
| Retention | `UNKNOWN` | Written term permitting immutable raw/interim/snapshot retention for the required period |
| ML processing | `UNKNOWN` | Written term permitting feature construction, model fitting, evaluation, and derived artifacts |
| Backup | `UNKNOWN` | Written term permitting redundant/archival copies and stating deletion obligations |

This is a research data-governance assessment, not legal advice. Public pages
were reviewed, but no rights were inferred from accessibility, the
open-source license of `yfinance`, or the project's academic purpose.

Terms reviewed:

- Yahoo Terms of Service: <https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html>
- Yahoo permissions guidance: <https://legal.yahoo.com/us/en/yahoo/permissions/requests/index.html>
- yfinance legal disclaimer: <https://github.com/ranaroussi/yfinance/blob/main/doc/source/index.rst>

## Confirmatory gate

Development-only pipeline and contract testing may continue with the current
immutable files. Confirmatory evaluation, conclusions, and claims may not use
them until all of the following are satisfied:

1. acquire a licensed, versioned source with the required extraction,
   retention, ML-processing, and backup rights;
2. retain per-observation price availability and adjustment-state evidence;
3. ingest any 2026-09-22 recovery as a new immutable source version rather
   than modifying `SRC-ABNB-001` or `SRC-EXPE-001`; and
4. rerun validation, rebuild downstream artifacts, and register every new
   checksum and version.
