# Open items

Items deliberately deferred to a later phase. Each one must be closed (or explicitly
documented as a known limitation in the README) before submission.

## Deferred to the web-research phase

- [ ] **Verify real-company watchlist entries against public sources.** Several entries for
      real companies read as questionable and look like planted conflicts. Example: WL-0001 says
      Petróleos Mexicanos is "sujeto a sanciones internacionales". For each real-company flag,
      record whether public evidence confirms, contradicts, or says nothing, and use these as
      hand-labelled cases in the web/conflict evaluation set. Real companies with flags:
      PEMEX (WL-0001, WL-0002), Aerovías de México (WL-0003), Grupo Elektra (WL-0004),
      TV Azteca (WL-0005), Controladora Vuela/Volaris (WL-0006), Banco Azteca (WL-0007),
      Grupo Modelo (WL-0008), Coppel (WL-0009), Deacero (WL-0010), SuKarne (WL-0011),
      Jabalí (WL-0012), BITAL (watchlist), Alpek (watchlist).
- [ ] **Web identity verification.** Synthetic companies (e.g. "Tecnologías Bajío") do not exist
      publicly. The web will return similarly named real companies, so every web finding must be
      checked against internal state, industry and legal form before it is attached to a profile.
- [ ] **Web absence is neutral.** A private SME with no web footprint must not lose confidence
      just for that.
- [ ] **Snapshot web responses** (cassettes) so the evaluation can be reproduced.

## Deferred to the tools/profile phase

- [ ] Watchlist match tiers: `confirmed` (ClientId) vs `possible` (name/alias), each with its
      own threshold. Run it over **all** resolution candidates, not just the chosen one.
- [ ] `WATCHLIST_NOTE_VS_STATUS` conflict (e.g. note says "en curso" but status is `resuelto`).
- [ ] `FLAG_PREDATES_RELATIONSHIP` conflict (flag older than the client's first policy).
- [ ] `related_entities`: corporate group / historical-name links, e.g. BITAL and HSBC are
      separate ClientIds; Grupo Salinas covers Elektra, TV Azteca and Banco Azteca; Telmex and
      Telcel sit under the América Móvil ClientId while FEMSA and KOF have separate ClientIds.
      Surface these, never apply them to the decision.
- [ ] `reserved_mxn` means the registered reserve, not the outstanding one: closed claims keep
      a reserve of 1.0–1.4× incurred. Never sum it as open exposure.
- [ ] Credibility indicator for the client loss ratio (low exposure gives extreme loss ratios).
- [ ] Age of open and disputed claims (some date from 2021).
- [ ] Data governance: only name and state go to web search; `--no-external-llm` flag.
