/**
 * Omnibus Price History Updater
 * -------------------------------
 * Raz dziennie:
 *  1. Pobiera ceny wszystkich wariantów produktów ze sklepu.
 *  2. Dopisuje dzisiejszy snapshot do metafieldu custom.price_history (na wariancie).
 *  3. Przycina wpisy starsze niż PRICE_HISTORY_DAYS dni.
 *  4. Zapisuje z powrotem przez metafieldsSet (batch po 25 na wywołanie).
 *
 * Wymagane zmienne środowiskowe:
 *  SHOPIFY_STORE_DOMAIN   - np. "twoj-sklep.myshopify.com"
 *  SHOPIFY_ADMIN_TOKEN    - token Admin API custom app (scope: read_products, write_products)
 *
 * Opcjonalne:
 *  PRICE_HISTORY_DAYS     - domyślnie 30
 *  API_VERSION            - domyślnie "2024-10"
 */

const STORE_DOMAIN = process.env.SHOPIFY_STORE_DOMAIN;
const ADMIN_TOKEN = process.env.SHOPIFY_ADMIN_TOKEN;
const HISTORY_DAYS = parseInt(process.env.PRICE_HISTORY_DAYS || "30", 10);
const API_VERSION = process.env.API_VERSION || "2024-10";

if (!STORE_DOMAIN || !ADMIN_TOKEN) {
  console.error("Brakuje SHOPIFY_STORE_DOMAIN lub SHOPIFY_ADMIN_TOKEN w zmiennych środowiskowych.");
  process.exit(1);
}

const GRAPHQL_URL = `https://${STORE_DOMAIN}/admin/api/${API_VERSION}/graphql.json`;

async function shopifyGraphQL(query, variables = {}) {
  const res = await fetch(GRAPHQL_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Shopify-Access-Token": ADMIN_TOKEN,
    },
    body: JSON.stringify({ query, variables }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status} z Shopify: ${text}`);
  }

  const json = await res.json();
  if (json.errors) {
    throw new Error(`Błąd GraphQL: ${JSON.stringify(json.errors)}`);
  }
  return json.data;
}

const PRODUCTS_QUERY = `
  query ProductsWithVariants($cursor: String) {
    products(first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id
          title
          variants(first: 100) {
            edges {
              node {
                id
                price
                metafield(namespace: "custom", key: "price_history") {
                  value
                }
              }
            }
          }
        }
      }
    }
  }
`;

const METAFIELDS_SET_MUTATION = `
  mutation SetPriceHistory($metafields: [MetafieldsSetInput!]!) {
    metafieldsSet(metafields: $metafields) {
      metafields { id }
      userErrors { field message }
    }
  }
`;

function trimHistory(history, days) {
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return history.filter((entry) => new Date(entry.date).getTime() >= cutoff);
}

async function fetchAllVariants() {
  const variants = [];
  let cursor = null;
  let hasNextPage = true;

  while (hasNextPage) {
    const data = await shopifyGraphQL(PRODUCTS_QUERY, { cursor });
    for (const productEdge of data.products.edges) {
      const product = productEdge.node;
      for (const variantEdge of product.variants.edges) {
        variants.push({
          productTitle: product.title,
          id: variantEdge.node.id,
          price: variantEdge.node.price,
          existingMetafieldValue: variantEdge.node.metafield?.value ?? null,
        });
      }
      if (product.variants.edges.length === 100) {
        console.warn(
          `Uwaga: produkt "${product.title}" ma >=100 wariantów - część mogła zostać pominięta (brak paginacji wariantów w tym skrypcie).`
        );
      }
    }
    hasNextPage = data.products.pageInfo.hasNextPage;
    cursor = data.products.pageInfo.endCursor;
  }

  return variants;
}

function buildUpdatedMetafields(variants) {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const updates = [];

  for (const variant of variants) {
    let history = [];
    if (variant.existingMetafieldValue) {
      try {
        history = JSON.parse(variant.existingMetafieldValue);
        if (!Array.isArray(history)) history = [];
      } catch {
        history = [];
      }
    }

    const lastEntry = history[history.length - 1];
    const alreadyLoggedToday = lastEntry && lastEntry.date === today;

    if (!alreadyLoggedToday) {
      history.push({ date: today, price: variant.price });
    } else {
      // Nadpisz dzisiejszy wpis, gdyby cena zmieniła się kilka razy tego samego dnia
      lastEntry.price = variant.price;
    }

    history = trimHistory(history, HISTORY_DAYS);

    updates.push({
      ownerId: variant.id,
      namespace: "custom",
      key: "price_history",
      type: "json",
      value: JSON.stringify(history),
    });
  }

  return updates;
}

async function pushUpdatesInBatches(updates, batchSize = 25) {
  for (let i = 0; i < updates.length; i += batchSize) {
    const batch = updates.slice(i, i + batchSize);
    const data = await shopifyGraphQL(METAFIELDS_SET_MUTATION, { metafields: batch });
    if (data.metafieldsSet.userErrors.length > 0) {
      console.error("Błędy przy zapisie batcha:", JSON.stringify(data.metafieldsSet.userErrors));
    } else {
      console.log(`Zapisano batch ${i / batchSize + 1} (${batch.length} wariantów).`);
    }
    // Mały odstęp, żeby nie uderzyć w rate limit
    await new Promise((r) => setTimeout(r, 500));
  }
}

async function main() {
  console.log(`Start aktualizacji historii cen (${new Date().toISOString()})`);
  const variants = await fetchAllVariants();
  console.log(`Pobrano ${variants.length} wariantów.`);

  const updates = buildUpdatedMetafields(variants);
  await pushUpdatesInBatches(updates);

  console.log("Gotowe.");
}

main().catch((err) => {
  console.error("Błąd skryptu:", err);
  process.exit(1);
});
