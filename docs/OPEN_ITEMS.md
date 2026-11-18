# Open items

Items deliberately deferred to a later phase. Each one must be closed (or explicitly
documented as a known limitation in the README) before submission.

## Deferred to the web-research phase

- [x] **Verify real-company watchlist entries against public sources.** *(Done with live runs:
      3 of 8 corroborated, 0 contradicted, 5 without public evidence, including a critical
      sanctions flag with no public support; see `eval/REPORT.md` §5.)* Several watchlist
      entries for real public companies read as questionable and look like planted conflicts. For
      each one, record whether public evidence confirms, contradicts, or says nothing. The list of
      flags is produced at run time from the data (nothing from the dataset is stored here).
- [x] **Web identity verification.** Synthetic companies (e.g. "Tecnologías Arcoíris") do not exist
      publicly. The web will return similarly named real companies, so every web finding must be
      checked against internal state, industry and legal form before it is attached to a profile.
- [x] **Web absence is neutral.** A private SME with no web footprint must not lose confidence
      just for that.
- [ ] **Snapshot web responses** (cassettes) so the evaluation can be reproduced. *(Not done:
      requires live responses; unit tests use a fake client instead.)*

## Known limitations at submission

- [ ] **Cost per lookup in USD.** Usage per lookup is measured (`eval/REPORT.md` §5) but no dollar
      figure is reported: provider prices are not configured and are never hard-coded. To close:
      set `UW_PRICE_INPUT_PER_MTOK`, `UW_PRICE_OUTPUT_PER_MTOK` and `UW_PRICE_PER_WEB_SEARCH` for the
      chosen model and rerun `uv run python eval/run_web_eval.py --runs 2`.

## Deferred to the tools/profile phase

- [x] Watchlist match tiers: `confirmed` (ClientId) vs `possible` (name/alias), each with its
      own threshold. Run it over **all** resolution candidates, not just the chosen one.
- [x] `WATCHLIST_NOTE_VS_STATUS` conflict (e.g. note says "en curso" but status is `resuelto`).
- [x] `FLAG_PREDATES_RELATIONSHIP` conflict (flag older than the client's first policy).
- [x] `related_entities`: corporate group / historical-name links (a former name or a
      sister company recorded as a separate client; subsidiaries recorded under the parent's
      ClientId in some cases and separately in others).
      Surface these, never apply them to the decision.
- [x] `reserved_mxn` means the registered reserve, not the outstanding one: closed claims keep
      a reserve of 1.0–1.4× incurred. Never sum it as open exposure.
- [x] Credibility indicator for the client loss ratio (low exposure gives extreme loss ratios).
- [x] Age of open and disputed claims (some date from 2021).
- [x] Data governance: only name and state go to web search. (A `--no-external-llm` flag was
      not needed: leaving `OPENAI_API_KEY` unset disables every external call.)
