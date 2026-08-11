# Theme contract

Theme is a presentation preference owned by the browser UI. The current
implementation stores only `mycard-benefits-theme` in browser-local storage.

It is not vault data, catalog data, launcher state, or an installation identity.
It is never sent to an API, included in an import, diagnostics, or a signed
health request. Theme preferences remain local to this browser; no external
synchronization is part of this contract.

Theme has no cross-application synchronization contract.
