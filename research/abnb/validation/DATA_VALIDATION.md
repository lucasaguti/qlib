# Initial Dataset Validation

**Validation date:** 2026-09-25  
**Environment:** Python 3.12.10  
**Calendar check:** XNYS via `exchange-calendars==4.13.2`  
**Machine-readable report:** `data_validation.json`

## Result

The registered files pass byte-integrity, manifest-consistency, schema, ordering, and numeric-value checks. XNYS coverage has one warning. Point-in-time provenance is blocked, and data usage rights remain unknown. These inputs are approved for development and pipeline testing only, not confirmatory claims.

| Ticker | Rows | Coverage | Current/archive | XNYS coverage | Actions |
|---|---:|---|---|---|---|
| ABNB | 1,451 | 2020-12-10 to 2026-09-23 | Exact byte match | Missing 2026-09-22 | 0 dividends; 0 splits |
| BKNG | 1,942 | 2019-01-02 to 2026-09-23 | Exact byte match | Complete | 11 dividends; 1 split |
| EXPE | 1,941 | 2019-01-02 to 2026-09-23 | Exact byte match | Missing 2026-09-22 | 12 dividends; 0 splits |
| SPY | 1,942 | 2019-01-02 to 2026-09-23 | Exact byte match | Complete | 31 dividends; 0 splits |

Across the ABNB study period, the union contains 1,452 dates and the four-security intersection contains 1,451. ABNB and EXPE both lack the XNYS session dated 2026-09-22; BKNG and SPY contain it. Treat the absent observations as `MISSING_SOURCE`. Do not compress the calendar, fill either price, or use the September 2026 origin until the gap is resolved under the feature contract.

## Checks performed

- Recomputed SHA-256 hashes and compared current files with manifests.
- Confirmed every archived CSV is byte-identical to its corresponding current CSV.
- Confirmed exact required column order, row count, first observation, and last observation.
- Parsed dates and checked strict ordering, uniqueness, weekdays, XNYS membership, and expected-session gaps.
- Checked required numeric fields for missing, nonnumeric, nonfinite, or invalid values.
- Checked positive OHLC and adjusted-close values, OHLC bounds, nonnegative integer volume, and nonnegative dividends/splits.
- Counted and retained corporate-action rows without altering source values.
- Compared dates across the four securities from the first ABNB observation onward.

No duplicate dates, invalid dates, weekend dates, non-XNYS observations, missing numeric cells, nonfinite values, nonpositive prices, OHLC-bound violations, negative actions, negative volume, or fractional volume values were found.

## Unresolved provenance

The manifests assert `point_in_time_vintage_verified: true`, but that assertion remains unconfirmed because they do not retain:

- provider/package version;
- source timezone and source calendar version;
- per-observation price availability evidence;
- adjustment-state availability evidence;
- corporate-action version history; or
- retained evidence supporting historical availability.

The manifests also do not document extraction, retention, machine-learning, backup, or processing rights. These are research-readiness blockers, not mechanical CSV defects.

## Readiness decision

| Area | Status |
|---|---|
| Byte and archive integrity | PASS |
| Schema and value integrity | PASS |
| XNYS session coverage | WARNING |
| Point-in-time provenance | BLOCKED |
| Usage rights | UNKNOWN |
| Overall use | DEVELOPMENT_ONLY |

Feature construction may proceed only as explicitly labeled development work. Confirmatory evaluation remains blocked until provenance and rights are resolved or the project charter is explicitly amended.
