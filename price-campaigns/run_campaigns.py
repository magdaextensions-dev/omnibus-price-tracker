"""
Automatyzacja kampanii cenowych dla e-hairshop.
Czyta kampanie z opublikowanego arkusza Google (CSV), rozwiazuje konflikty
priorytetow, i aktualizuje ceny wariantow w Shopify przez Admin API GraphQL.

Wymagane zmienne srodowiskowe (ustawiane jako GitHub Secrets):
  SHOPIFY_STORE_DOMAIN   -> np. c2cae8-b1.myshopify.com
  SHOPIFY_ADMIN_TOKEN    -> token prywatnej/wlasnej aplikacji z uprawnieniem write_products
  SHEET_CSV_URL          -> link "Publikuj w internecie -> CSV" do arkusza kampanii
"""

import csv
import io
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

STORE_DOMAIN = os.environ["SHOPIFY_STORE_DOMAIN"]
ADMIN_TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
SHEET_CSV_URL = os.environ["SHEET_CSV_URL"]
API_VERSION = "2025-01"

GRAPHQL_URL = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
WARSAW = ZoneInfo("Europe/Warsaw")

META_NAMESPACE = "campaigns"
META_ORIGINAL_PRICE = "original_price"
META_ORIGINAL_COMPARE = "original_compare_at_price"
META_ACTIVE_CAMPAIGN = "active_campaign_name"


def graphql(query, variables=None):
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers={
            "X-Shopify-Access-Token": ADMIN_TOKEN,
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch_campaigns():
    resp = requests.get(SHEET_CSV_URL, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    campaigns = []
    for row in reader:
        name = (row.get("Nazwa kampanii") or "").strip()
        if not name or name.upper().startswith("PRZYKLAD") or name.upper().startswith("PRZYKŁAD"):
            continue
        try:
            start = parse_pl_datetime(row["Start (czas PL)"])
            end = parse_pl_datetime(row["Koniec (czas PL)"])
        except Exception as e:
            print(f"[UWAGA] Kampania '{name}': nie mozna sparsowac dat ({e}) - pomijam")
            continue

        target_type = (row.get("Typ celu") or "").strip()
        target_raw = (row.get("Cel (kolekcja lub produkty)") or "").strip()
        discount_type = (row.get("Typ rabatu") or "").strip()
        value_raw = (row.get("Wartosc rabatu") or "").strip()
        priority_raw = (row.get("Priorytet (opcjonalnie)") or "").strip()

        if not target_type or not target_raw or not discount_type or not value_raw:
            print(f"[UWAGA] Kampania '{name}': brakuje wymaganych pol - pomijam")
            continue

        try:
            value = float(value_raw.replace(",", "."))
        except ValueError:
            print(f"[UWAGA] Kampania '{name}': nieprawidlowa wartosc rabatu '{value_raw}' - pomijam")
            continue

        priority = None
        if priority_raw:
            try:
                priority = float(priority_raw.replace(",", "."))
            except ValueError:
                pass

        campaigns.append({
            "name": name,
            "target_type": target_type,
            "target_raw": target_raw,
            "discount_type": discount_type,
            "value": value,
            "priority": priority,
            "start": start,
            "end": end,
        })
    return campaigns


def parse_pl_datetime(text):
    text = text.strip()
    dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
    return dt.replace(tzinfo=WARSAW).astimezone(timezone.utc)


PRODUCT_QUERY = """
query getProduct($handle: String!) {
  productByHandle(handle: $handle) {
    id
    handle
    variants(first: 100) {
      edges {
        node {
          id
          title
          price
          compareAtPrice
          metafields(namespace: "campaigns", first: 10) {
            edges { node { key value } }
          }
        }
      }
    }
  }
}
"""

COLLECTION_QUERY = """
query getCollection($handle: String!, $cursor: String) {
  collectionByHandle(handle: $handle) {
    id
    products(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id
          handle
          variants(first: 100) {
            edges {
              node {
                id
                title
                price
                compareAtPrice
                metafields(namespace: "campaigns", first: 10) {
                  edges { node { key value } }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


def variant_metafields_dict(node):
    result = {}
    for edge in node["metafields"]["edges"]:
        result[edge["node"]["key"]] = edge["node"]["value"]
    return result


def resolve_target(target_type, target_raw):
    """Zwraca liste wariantow: [{variant_id, price, compare_at_price, metafields}]"""
    variants = []
    if target_type.lower() == "kolekcja":
        handle = target_raw.strip()
        cursor = None
        while True:
            data = graphql(COLLECTION_QUERY, {"handle": handle, "cursor": cursor})
            coll = data.get("collectionByHandle")
            if not coll:
                print(f"[UWAGA] Nie znaleziono kolekcji o handle '{handle}'")
                return []
            for edge in coll["products"]["edges"]:
                product = edge["node"]
                for vedge in product["variants"]["edges"]:
                    v = vedge["node"]
                    variants.append({
                        "variant_id": v["id"],
                        "product_id": product["id"],
                        "price": float(v["price"]),
                        "compare_at_price": float(v["compareAtPrice"]) if v["compareAtPrice"] else None,
                        "metafields": variant_metafields_dict(v),
                    })
            if not coll["products"]["pageInfo"]["hasNextPage"]:
                break
            cursor = coll["products"]["pageInfo"]["endCursor"]
    else:
        # Produkty: lista "handle" albo "handle:nazwa_wariantu" po przecinku
        entries = [e.strip() for e in target_raw.split(",") if e.strip()]
        for entry in entries:
            if ":" in entry:
                handle, variant_title = entry.split(":", 1)
                handle = handle.strip()
                variant_title = variant_title.strip()
            else:
                handle, variant_title = entry.strip(), None

            data = graphql(PRODUCT_QUERY, {"handle": handle})
            product = data.get("productByHandle")
            if not product:
                print(f"[UWAGA] Nie znaleziono produktu o handle '{handle}'")
                continue
            for vedge in product["variants"]["edges"]:
                v = vedge["node"]
                if variant_title and v["title"].strip().lower() != variant_title.lower():
                    continue
                variants.append({
                    "variant_id": v["id"],
                    "product_id": product["id"],
                    "price": float(v["price"]),
                    "compare_at_price": float(v["compareAtPrice"]) if v["compareAtPrice"] else None,
                    "metafields": variant_metafields_dict(v),
                })
    return variants


def compute_discounted_price(base_price, discount_type, value):
    dt = discount_type.lower()
    if dt == "procent":
        return round(base_price * (1 - value / 100), 2)
    if dt == "nowa cena":
        return round(value, 2)
    if dt == "stała kwota rabatu" or dt == "stala kwota rabatu":
        return round(max(base_price - value, 0), 2)
    raise ValueError(f"Nieznany typ rabatu: {discount_type}")


VARIANT_UPDATE_MUTATION = """
mutation updateVariants($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    userErrors { field message }
  }
}
"""


def apply_update(product_id, variant_id, price, compare_at_price, metafields_input):
    variant_payload = {
        "id": variant_id,
        "price": f"{price:.2f}",
    }
    if compare_at_price is not None:
        variant_payload["compareAtPrice"] = f"{compare_at_price:.2f}"
    else:
        variant_payload["compareAtPrice"] = None
    if metafields_input:
        variant_payload["metafields"] = metafields_input

    result = graphql(VARIANT_UPDATE_MUTATION, {
        "productId": product_id,
        "variants": [variant_payload],
    })
    errors = result["productVariantsBulkUpdate"]["userErrors"]
    if errors:
        print(f"[BLAD] Wariant {variant_id}: {errors}")


def main():
    now = datetime.now(timezone.utc)
    campaigns = fetch_campaigns()
    print(f"Wczytano {len(campaigns)} kampanii z arkusza.")

    # variant_id -> lista aktywnych kampanii ktore go dotycza
    variant_active_campaigns = {}
    # variant_id -> dane wariantu (do ponownego uzycia, unikamy duplikatow zapytan)
    variant_data_cache = {}

    for c in campaigns:
        is_active = c["start"] <= now <= c["end"]
        variants = resolve_target(c["target_type"], c["target_raw"])
        for v in variants:
            vid = v["variant_id"]
            variant_data_cache[vid] = v
            if is_active:
                variant_active_campaigns.setdefault(vid, []).append(c)

    touched = 0
    for vid, vdata in variant_data_cache.items():
        active_list = variant_active_campaigns.get(vid, [])
        meta = vdata["metafields"]
        stored_original_price = meta.get(META_ORIGINAL_PRICE)
        stored_original_compare = meta.get(META_ORIGINAL_COMPARE)

        if active_list:
            def sort_key(camp):
                prio = camp["priority"] if camp["priority"] is not None else float("inf")
                return (prio, -camp["value"])
            winner = sorted(active_list, key=sort_key)[0]

            base_price = float(stored_original_price) if stored_original_price else vdata["price"]
            base_compare = (
                float(stored_original_compare) if stored_original_compare
                else vdata["compare_at_price"]
            )

            new_price = compute_discounted_price(base_price, winner["discount_type"], winner["value"])

            if stored_original_price and float(stored_original_price) == base_price and \
               abs(vdata["price"] - new_price) < 0.005 and \
               meta.get(META_ACTIVE_CAMPAIGN) == winner["name"]:
                continue  # juz ustawione poprawnie, nic do zrobienia

            metafields_input = [
                {"namespace": META_NAMESPACE, "key": META_ORIGINAL_PRICE,
                 "type": "number_decimal", "value": f"{base_price:.2f}"},
                {"namespace": META_NAMESPACE, "key": META_ACTIVE_CAMPAIGN,
                 "type": "single_line_text_field", "value": winner["name"]},
            ]
            if base_compare is not None:
                metafields_input.append({
                    "namespace": META_NAMESPACE, "key": META_ORIGINAL_COMPARE,
                    "type": "number_decimal", "value": f"{base_compare:.2f}"
                })

            print(f"START/UPDATE: wariant {vid} -> {new_price} (kampania '{winner['name']}')")
            apply_update(vdata["product_id"], vid, new_price, base_price, metafields_input)
            touched += 1

        else:
            active_flag = meta.get(META_ACTIVE_CAMPAIGN)
            if active_flag:
                # Byla aktywna kampania, teraz sie skonczyla -> przywracamy cene.
                restore_price = float(stored_original_price) if stored_original_price else vdata["price"]
                restore_compare = float(stored_original_compare) if stored_original_compare else None
                print(f"KONIEC KAMPANII: wariant {vid} -> przywracam {restore_price}")
                # Metafield tekstowy mozna wyczyscic pustym stringiem.
                # Metafieldy liczbowe (original_price/compare) zostawiamy jako historyczny
                # zapis - nie sa odczytywane, gdy active_campaign_name jest puste.
                metafields_input = [
                    {"namespace": META_NAMESPACE, "key": META_ACTIVE_CAMPAIGN,
                     "type": "single_line_text_field", "value": ""},
                ]
                apply_update(vdata["product_id"], vid, restore_price, restore_compare, metafields_input)
                touched += 1

    print(f"Zakonczono. Zmodyfikowano {touched} wariantow.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[KRYTYCZNY BLAD] {e}", file=sys.stderr)
        sys.exit(1)
