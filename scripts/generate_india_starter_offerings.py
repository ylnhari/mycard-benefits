"""Generate the deterministic India starter card-variant catalog.

The records below contain public product identity only. They deliberately do
not encode who owns a card, how many cards exist, or any private card values.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "catalog" / "offerings"
NAMESPACE = uuid.UUID("b8ab0a43-3ba6-45b4-8ab1-c071415dbb12")

# slug, display name, issuer, product variant, network, optional merchant co-brand
OFFERINGS = (
    ("au-kosmos-rupay-select-credit", "AU Kosmos RuPay Select Credit Card", "au-small-finance-bank", "kosmos-credit", "rupay-select", None),
    ("au-priority-pass-membership", "AU Priority Pass Membership", "au-small-finance-bank", "priority-pass-membership", "priority-pass", None),
    ("au-vetta-credit", "AU Vetta Credit Card", "au-small-finance-bank", "vetta-credit", "unknown", None),
    ("axis-burgundy-mastercard-debit", "Axis Bank Burgundy Mastercard Debit Card", "axis-bank", "burgundy-debit", "mastercard", None),
    ("axis-flipkart-credit", "Flipkart Axis Bank Credit Card", "axis-bank", "flipkart-credit", "visa", "flipkart"),
    ("axis-myzone-credit", "Axis Bank MY ZONE Credit Card", "axis-bank", "my-zone-credit", "unknown", None),
    ("axis-myzone-platinum-rupay-credit", "Axis Bank MY ZONE Platinum RuPay Credit Card", "axis-bank", "my-zone-platinum-credit", "rupay", None),
    ("axis-neo-credit", "Axis Bank NEO Credit Card", "axis-bank", "neo-credit", "unknown", None),
    ("axis-prestige-debit", "Axis Bank Prestige Debit Card", "axis-bank", "prestige-debit", "unknown", None),
    ("axis-privilege-credit", "Axis Bank Privilege Credit Card", "axis-bank", "privilege-credit", "unknown", None),
    ("axis-select-credit", "Axis Bank SELECT Credit Card", "axis-bank", "select-credit", "unknown", None),
    ("axis-supermoney-rupay-platinum-credit", "super.money RuPay Platinum Axis Bank Credit Card", "axis-bank", "supermoney-platinum-credit", "rupay-platinum", "supermoney"),
    ("axis-virtual-debit", "Axis Bank Virtual Debit Card", "axis-bank", "virtual-debit", "unknown", None),
    ("city-union-bank-credit", "City Union Bank Credit Card", "city-union-bank", "credit-card", "unknown", None),
    ("dbs-debit", "DBS Bank Debit Card", "dbs-bank", "debit-card", "unknown", None),
    ("federal-bank-scapia-visa-signature-credit", "Scapia Federal Bank Visa Signature Credit Card", "federal-bank", "scapia-credit", "visa-signature", "scapia"),
    ("hdfc-millennia-credit", "HDFC Bank Millennia Credit Card", "hdfc-bank", "millennia-credit", "unknown", None),
    ("hdfc-millennia-debit", "HDFC Bank Millennia Debit Card", "hdfc-bank", "millennia-debit", "unknown", None),
    ("hdfc-pixel-credit", "HDFC Bank Pixel Credit Card", "hdfc-bank", "pixel-credit", "unknown", None),
    ("hdfc-priority-pass-membership", "HDFC Bank Priority Pass Membership", "hdfc-bank", "priority-pass-membership", "priority-pass", None),
    ("hdfc-regalia-gold-credit", "HDFC Bank Regalia Gold Credit Card", "hdfc-bank", "regalia-gold-credit", "visa", None),
    ("hdfc-rupay-credit", "HDFC Bank RuPay Credit Card", "hdfc-bank", "rupay-credit", "rupay", None),
    ("hdfc-swiggy-mastercard-credit", "Swiggy HDFC Bank Mastercard Credit Card", "hdfc-bank", "swiggy-credit", "mastercard", "swiggy"),
    ("hdfc-tata-neu-rupay-select-credit", "Tata Neu Infinity HDFC Bank RuPay Select Credit Card", "hdfc-bank", "tata-neu-infinity-credit", "rupay-select", "tata-neu"),
    ("hsbc-live-plus-credit", "HSBC Live+ Credit Card", "hsbc-india", "live-plus-credit", "unknown", None),
    ("hsbc-rupay-platinum-credit", "HSBC RuPay Platinum Credit Card", "hsbc-india", "rupay-platinum-credit", "rupay-platinum", None),
    ("hsbc-visa-debit", "HSBC Visa Debit Card", "hsbc-india", "visa-debit", "visa", None),
    ("icici-amazon-pay-visa-credit", "Amazon Pay ICICI Bank Visa Credit Card", "icici-bank", "amazon-pay-credit", "visa", "amazon-pay"),
    ("icici-coral-credit", "ICICI Bank Coral Credit Card", "icici-bank", "coral-credit", "unknown", None),
    ("icici-coral-debit", "ICICI Bank Coral Debit Card", "icici-bank", "coral-debit", "unknown", None),
    ("icici-coral-rupay-platinum-credit", "ICICI Bank Coral RuPay Platinum Credit Card", "icici-bank", "coral-platinum-credit", "rupay-platinum", None),
    ("icici-coral-visa-platinum-credit", "ICICI Bank Coral Visa Platinum Credit Card", "icici-bank", "coral-platinum-credit", "visa-platinum", None),
    ("icici-debit", "ICICI Bank Debit Card", "icici-bank", "debit-card", "unknown", None),
    ("icici-hpcl-coral-platinum-visa-credit", "HPCL ICICI Bank Coral Platinum Visa Credit Card", "icici-bank", "hpcl-coral-platinum-credit", "visa-platinum", "hpcl"),
    ("icici-makemytrip-credit", "MakeMyTrip ICICI Bank Credit Card", "icici-bank", "makemytrip-credit", "unknown", "makemytrip"),
    ("icici-rubyx-credit", "ICICI Bank Rubyx Credit Card", "icici-bank", "rubyx-credit", "unknown", None),
    ("icici-rupay-platinum-credit", "ICICI Bank RuPay Platinum Credit Card", "icici-bank", "rupay-platinum-credit", "rupay-platinum", None),
    ("icici-sapphiro-amex-credit", "ICICI Bank Sapphiro American Express Credit Card", "icici-bank", "sapphiro-credit", "american-express", None),
    ("icici-sapphiro-dreamfolks-membership", "ICICI Bank Sapphiro DreamFolks Membership", "icici-bank", "sapphiro-dreamfolks-membership", "dreamfolks", None),
    ("icici-sapphiro-mastercard-credit", "ICICI Bank Sapphiro Mastercard Credit Card", "icici-bank", "sapphiro-credit", "mastercard", None),
    ("icici-sapphiro-rupay-select-credit", "ICICI Bank Sapphiro RuPay Select Credit Card", "icici-bank", "sapphiro-credit", "rupay-select", None),
    ("icici-titanium-mastercard-debit", "ICICI Bank Titanium Mastercard Debit Card", "icici-bank", "titanium-debit", "mastercard", None),
    ("idfc-debit-legacy", "IDFC Bank Debit Card (Legacy)", "idfc-bank", "legacy-debit", "unknown", None),
    ("idfc-first-ashva-credit", "IDFC FIRST Bank Ashva Credit Card", "idfc-first-bank", "ashva-credit", "unknown", None),
    ("idfc-first-classic-credit", "IDFC FIRST Bank Classic Credit Card", "idfc-first-bank", "classic-credit", "unknown", None),
    ("idfc-first-millennia-visa-credit", "IDFC FIRST Bank Millennia Visa Credit Card", "idfc-first-bank", "millennia-credit", "visa", None),
    ("idfc-first-select-visa-infinite-debit", "IDFC FIRST Bank Select Visa Infinite Debit Card", "idfc-first-bank", "select-debit", "visa-infinite", None),
    ("idfc-first-visa-platinum-debit", "IDFC FIRST Bank Visa Platinum Debit Card", "idfc-first-bank", "visa-platinum-debit", "visa-platinum", None),
    ("idfc-first-wealth-credit", "IDFC FIRST Bank Wealth Credit Card", "idfc-first-bank", "wealth-credit", "unknown", None),
    ("indusind-eazydiner-platinum-credit", "EazyDiner IndusInd Bank Platinum Credit Card", "indusind-bank", "eazydiner-platinum-credit", "unknown", "eazydiner"),
    ("indusind-legend-visa-credit", "IndusInd Bank Legend Visa Credit Card", "indusind-bank", "legend-credit", "visa", None),
    ("indusind-legend-visa-signature-credit", "IndusInd Bank Legend Visa Signature Credit Card", "indusind-bank", "legend-credit", "visa-signature", None),
    ("indusind-nexxt-credit", "IndusInd Bank Nexxt Credit Card", "indusind-bank", "nexxt-credit", "unknown", None),
    ("indusind-select-debit", "IndusInd Bank Select Debit Card", "indusind-bank", "select-debit", "unknown", None),
    ("jupiter-debit", "Jupiter Debit Card", "jupiter", "debit-card", "unknown", None),
    ("kotak-credit", "Kotak Mahindra Bank Credit Card", "kotak-mahindra-bank", "credit-card", "unknown", None),
    ("kotak-ivy-league-debit", "Kotak Mahindra Bank Ivy League Debit Card", "kotak-mahindra-bank", "ivy-league-debit", "unknown", None),
    ("kotak-myntra-rupay-select-credit", "Myntra Kotak RuPay Select Credit Card", "kotak-mahindra-bank", "myntra-credit", "rupay-select", "myntra"),
    ("onecard-credit", "OneCard Credit Card", "onecard", "credit-card", "unknown", None),
    ("rbl-duet-credit", "RBL Bank Duet Credit Card", "rbl-bank", "duet-credit", "unknown", None),
    ("rbl-play-credit", "RBL Bank Play Credit Card", "rbl-bank", "play-credit", "unknown", None),
    ("rbl-supercard-credit", "RBL Bank SuperCard Credit Card", "rbl-bank", "supercard-credit", "unknown", None),
    ("rbl-zomato-credit", "Zomato RBL Bank Credit Card", "rbl-bank", "zomato-credit", "unknown", "zomato"),
    ("sbi-cashback-credit", "CASHBACK SBI Card", "sbi-card", "cashback-credit", "visa", None),
    ("slice-rupay-credit", "Slice RuPay Credit Card", "slice", "rupay-credit", "rupay", None),
    ("unicard-pay-later", "Uni Pay Later Card", "unicard", "pay-later", "unknown", None),
    ("yes-bank-credit", "YES BANK Credit Card", "yes-bank", "credit-card", "unknown", None),
    ("yes-bank-rio-rupay-credit", "Rio YES BANK RuPay Credit Card", "yes-bank", "rio-credit", "rupay", "rio"),
)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for slug, display_name, issuer_id, product_variant_id, network_id, co_brand_id in OFFERINGS:
        payload: dict[str, object] = {
            "id": str(uuid.uuid5(NAMESPACE, slug)),
            "slug": slug,
            "display_name": display_name,
            "issuer_id": issuer_id,
            "product_variant_id": product_variant_id,
            "network_id": network_id,
            "market": "IN",
            "aliases": [],
        }
        if co_brand_id is not None:
            payload["co_brand_id"] = co_brand_id
        path = OUTPUT / f"{slug}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
