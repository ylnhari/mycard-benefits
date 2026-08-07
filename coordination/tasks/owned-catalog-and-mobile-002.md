# Owned catalog and mobile dashboard slice

Status: completed (implementation approach superseded)
Owner: primary integrator
Date: 2026-08-07

> Historical record: the signed-session coupling described below was removed
> after owner feedback. MyCard is now independent of the personal launcher;
> this task remains as audit evidence for the original reviewed slice.

## Outcome

Make the local alpha useful for the owner without publishing private portfolio
data: add public product-variant records for the offerings already represented
in the authorized local import, show the encrypted vault's non-secret envelope
metadata only to a Rover-authenticated browser, and route the loopback app
through Rover for phone access.

## Cost and capability routing

- Claude Opus: large public documentation rewrite and public-source research.
- OpenCode `opencode/deepseek-v4-flash-free` through the registered local web
  service: independent read-only review after integration.
- Primary: private manifest/vault handling, Rover authentication boundary,
  integration, deterministic generation, and final verification.

This split avoids sending the owned-card selection, owner aliases, encrypted
records, or any other private financial data to a delegated runner.

## Authorized actions

- Add public product identity records derived locally from offering IDs. Product
  names are public facts; do not include ownership, counts, lifecycle history,
  aliases belonging to a person, or secret fields.
- Add a read-only My Cards view for non-secret vault envelope metadata. Require
  a valid Rover `rover_proxy` signed cookie and fail closed when Rover auth is
  absent or invalid. Do not reveal or decrypt secret fields.
- Register/adopt/start MyCard through Rover, restart Rover, and verify registry,
  local health, proxy health, and rendered mobile behavior.
- Rewrite end-user documentation and explain that `coordination/` is maintainer
  audit evidence which normal users can ignore.

## Source rules

- MyCardExpert and SaveSage are tier-6 discovery sources only.
- Publishable benefits require current official issuer, administering-party,
  network, or merchant terms and the existing human review gate.
- Do not copy source prose, logos, screenshots, or bulk catalog content.

## Forbidden

- No PAN, CVV, PIN, owner name, cardholder name, private nickname, raw Drive
  material, decrypted vault value, credential, or private path in a prompt,
  tracked file, log, or delegated evidence.
- No source-access bypass, purchase, application, booking, redemption, upload,
  remote bind widening, force-push, or publication beyond an explicit gate.
- Delegates may not approve their own work.

## Verification

- Catalog schema and deterministic loader tests.
- Authentication tests for missing, expired, future, malformed, and valid Rover
  cookies; responses expose only approved envelope fields.
- Existing Ruff, strict mypy, full pytest, and package build gates.
- Live app remains bound to `127.0.0.1:8777`.
- Rover project registry, API project state, proxy URL, and phone-sized rendered
  dashboard all agree.
- OpenCode review produces a bounded verdict or an honest timeout record.

## Completion evidence

- OpenCode `opencode/deepseek-v4-flash-free` returned `REVIEW_APPROVED` after
  independently checking every remediation item.
- Ruff, strict mypy across 32 source files, all 208 tests, and both package
  builds passed in the reviewed worktree.
- Twenty repeated focused ordering runs passed, and read-only regeneration of
  the 68 starter offering files was byte-identical.
- Live Rover and phone-sized rendered verification remain recorded in the
  append-only event log. Remote publication remains separately gated.
