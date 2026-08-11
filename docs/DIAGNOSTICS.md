# Manual diagnostics

MyCard has no telemetry and does not automatically collect or transmit logs.
Diagnostics are an explicit local export only. Call
`mycard_benefits.diagnostics.export_diagnostics` with the documented allowlist
(`app_version`, `platform`, `demo`, `diagnostic_code`, and `catalog_release`).
The exporter writes only those scalar values, never scans a directory and never
includes URLs, exception text, notifications, private paths, vault fields,
credentials, cookies, or OTPs.
