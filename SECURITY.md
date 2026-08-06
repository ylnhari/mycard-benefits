# Security

## Sensitive local vault

MyCard Benefits may store PAN, expiry, CVV, and PIN only because the user runs
the application for their own records on their own device. These values are
high-risk sensitive authentication data. This project does not claim PCI DSS
compliance and does not support hosted secret storage.

The encrypted vault core exists and is tested, but the current dashboard does
not expose a vault API or real-card controls. Never enter real data until a
later build enables those controls only after independent review and reports
its security self-checks as passing.

## Threat model

The design aims to protect against accidental commits/logging, casual household
access, offline inspection of copied runtime files, malicious catalog content,
and unintended network transmission. The signed health identity enables future
connection pinning, but the current Family Finance launcher does not yet verify
that signature; a wrong service at a configured address remains a known risk.
The design cannot guarantee protection from malware running as the user, a
compromised operating system, screen capture, swap/hibernation inspection, or
clipboard-monitoring software.

## Reporting

Do not open a public issue containing a vulnerability exploit, card data,
machine path, private URL, log, or screenshot. Until a private reporting channel
is published, provide only a high-level notification to the repository owner.

## Hard rules

- No secret values in logs, exception context, metrics, notifications, URLs,
  browser history, agent prompts, test output, or source-control history.
- No cloud vault sync or unattended secret reveal.
- No authentication/CAPTCHA/access-control bypass.
- No public deployment without a separate threat-model and compliance review.
