# Pilot official-source leads

Discovery pass: 2026-08-07

Status: discovery only. These links and independently written notes are a
review queue, not active catalog facts. No source admission, raw capture,
content hash, or human approval exists yet.

## Tata Neu Infinity HDFC Bank Credit Card

Primary leads:

- HDFC Bank current product page:
  <https://www.hdfc.bank.in/credit-cards/tata-neu-infinity-hdfc-bank-credit-card>
- HDFC Bank product FAQ, marked updated 2026-01-07:
  <https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/personal-banking/discover-products/cards/credit-cards/tata-neu-infinity-credit-card/pdf/tata_neu_infinity_card_faq.pdf>
- HDFC Bank detailed card terms:
  <https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/personal-banking/discover-products/cards/credit-cards/tata-neu-infinity-credit-card/pdf/tata_neu_infinity_card_tnc.pdf>
- Tata Neu Air India program page:
  <https://www.tataneu.com/v2/cdp/neucardairindia>

Candidate facts to verify independently against complete current terms:

- separate non-UPI Tata-brand, non-Tata, merchant-EMI, and UPI earn rules;
- an extra NeuPass layer for selected Tata Neu categories, with exclusions;
- monthly and annual fair-use caps that vary by category;
- domestic lounge vouchers tied to preceding spend and a separate
  international allowance;
- fee, fee-waiver, fuel-waiver, reward-expiry, posting, and reversal rules;
- network variants and whether inherited network benefits differ by variant.

Do not simplify an advertised combined earn rate into one card earn rule. The
base card component and any Tata Neu or merchant-membership component need
separate evidence and compatibility edges.

## HDFC Bank Regalia Gold Credit Card

Primary leads:

- HDFC Bank current product page:
  <https://www.hdfc.bank.in/credit-cards/regalia-gold-credit-card>
- HDFC Bank domestic lounge terms:
  <https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/personal-banking/discover-products/cards/credit-cards/regalia-gold-credit-card/pdfs/lounge-t-and-cs-and-list-Regalia-Gold.pdf>
- HDFC Bank reward-redemption guide:
  <https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/personal-banking/discover-products/cards/credit-cards/regalia-gold-credit-card/reward-points-redemption-through-smartbuy.pdf>
- HDFC Bank Travel Edge terms link surfaced from the product page:
  <https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/personal-banking/discover-products/cards/credit-cards/regalia-gold-credit-card/pdfs/regalia-gold-travel-edge-tnc.pdf>

Candidate facts to verify independently against the complete terms and the
bank's effective-2026 change notice:

- base and accelerated earn, statement-cycle cap, and excluded categories;
- distinct redemption values and monthly/booking limits by channel;
- domestic and international lounge conditions, including spend windows;
- welcome and spend-milestone vouchers with claim windows;
- SmartBuy portal multipliers and merchant-specific limits;
- Travel Edge benefits triggered by submitting a boarding pass, including the
  destination, timing, quarterly allowance, eligible benefit menu, and whether
  the qualifying flight must have been purchased with this card;
- insurance, Priority Pass, fee, fee-waiver, and foreign-currency terms.

The Travel Edge document currently carries a non-public classification label
inside a publicly reachable file. Do not ingest or publish from it
automatically until a human confirms that HDFC intentionally exposes it for
cardholder use and that the product page remains the governing entry point.

## Visa Infinite inherited benefits

Primary leads:

- Visa Infinite overview:
  <https://www.visa.co.in/pay-with-visa/find-a-card/visa-infinite.html>
- Visa Meet & Assist offer:
  <https://www.visa.co.in/en_in/visa-offers-and-perks/visa-meet-assist/168650>
- Visa Luxury Hotel Collection offer:
  <https://www.visa.co.in/en_in/visa-offers-and-perks/visa-luxury-hotel-collection/114996>

Candidate modeling questions:

- represent network-tier benefits once and inherit them into eligible issuer
  offerings without claiming that every Visa Infinite card participates;
- retain the network's cardholder/region eligibility separately from issuer
  eligibility;
- model past-period spend gates, international transaction type, booking
  channel, registration, geography, and fulfillment merchant as conditions;
- require issuer/network cross-checks before a network benefit becomes active
  for a specific card variant;
- preserve exact offer dates and withdraw inheritance when the network offer
  expires or the issuer's variant/network changes.

The Meet & Assist lead is particularly useful for the product model because it
combines network inheritance, a trailing international-spend threshold, a
separate fulfillment site, and a time-limited offer. It must remain conditional
until both network and card eligibility are reviewed.
