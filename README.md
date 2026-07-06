# Omnibus Price Tracker — zamiennik płatnej apki

Ten projekt zastępuje apkę typu "Omnibus Insight" własnym rozwiązaniem:
codzienny snapshot cen zapisywany do metafieldów wariantów + snippet Liquid
pokazujący najniższą cenę z ostatnich 30 dni.

Koszt: 0 zł/mies.

## Krok 1 — Konfiguracja custom apki w Dev Dashboard

Twoja apka (np. "Price History Bot") już istnieje w Dev Dashboard Shopify.
Trzeba jeszcze nadać jej uprawnienia i ją zainstalować:

1. W Dev Dashboard wejdź w swoją apkę → zakładka **Wersje** (Versions).
2. Utwórz/edytuj wersję i w polu **App scopes** dodaj:
   - `read_products`
   - `write_products`
3. Kliknij **Release**.
4. Wejdź w **Home** (Strona główna) tej apki → **Install app** → wybierz swój sklep → **Install**.
5. Wejdź w **Ustawienia** (Settings) → skopiuj **ID klienta (Client ID)** i **Klucz tajny (Client secret)**.

**Nie generujemy tu żadnego osobnego "tokenu"** — skrypt sam wymienia
ID klienta + Klucz tajny na tymczasowy token przy każdym uruchomieniu
(tzw. "client credentials grant"). Dzięki temu nic nigdy nie wygasa —
ID klienta i Klucz tajny są stałe, dopóki nie usuniesz/nie zresetujesz apki.

**Klucz tajny traktuj jak hasło** — nie wklejaj go nigdzie poza sekretami GitHub (patrz Krok 3).

## Krok 2 — Definicja metafieldu (jednorazowo, przez UI admina sklepu)

1. W panelu sklepu: **Ustawienia → Dane niestandardowe (Custom data) → Warianty → Dodaj definicję**.
2. Namespace: `custom`, Key: `price_history`, Typ: **JSON**.
3. Zapisz.

(Ten krok jest opcjonalny — Shopify utworzy metafield automatycznie przy
pierwszym zapisie ze skryptu — ale ułatwia potem przegląd danych w adminie.)

## Krok 3 — Repozytorium GitHub + sekrety

1. Repozytorium `omnibus-price-tracker` jest już utworzone i zawiera pliki projektu.
2. W repo: **Settings → Secrets and variables → Actions → New repository secret**
   i dodaj trzy sekrety:
   - `SHOPIFY_STORE_DOMAIN` → np. `twoj-sklep.myshopify.com`
   - `SHOPIFY_CLIENT_ID` → ID klienta z Kroku 1
   - `SHOPIFY_CLIENT_SECRET` → Klucz tajny z Kroku 1
3. Workflow w `.github/workflows/update-price-history.yml` uruchomi się
   automatycznie codziennie o 02:15 UTC. Możesz go też odpalić ręcznie
   z zakładki **Actions → Aktualizacja historii cen (Omnibus) → Run workflow**,
   żeby od razu zacząć zbierać dane.

## Krok 4 — Dodanie snippetu do motywu

1. W **Edytorze kodu motywu** (Online Store → Themes → Edit code) wgraj plik
   `theme-snippet/omnibus-lowest-price.liquid` do folderu `snippets/`.
2. W pliku szablonu produktu (zwykle `sections/main-product.liquid`), tuż pod
   miejscem, gdzie wyświetlana jest cena, dodaj:

   ```liquid
   {% render 'omnibus-lowest-price', variant: product.selected_or_first_available_variant %}
   ```

3. Komunikat pojawi się w języku angielskim ("Lowest price in the last 30 days: ...") —
   przetłumacz go w swojej apce do tłumaczeń na potrzebne języki.

## Ważna uwaga prawna / praktyczna

- Przez pierwsze ~30 dni od uruchomienia historia będzie niepełna. Snippet
  celowo nic nie pokaże w tym czasie, dopóki nie ma danych sprzed dzisiejszej ceny.
- Komunikat pojawia się **tylko wtedy, gdy aktualna cena jest niższa** niż
  najniższa cena z historii sprzed dzisiaj — czyli dokładnie w momencie
  realnej obniżki, zgodnie z dyrektywą Omnibus.
- Ten kod obsługuje standardowy przypadek (produkty z ≤100 wariantami).
  Jeśli masz produkty z większą liczbą wariantów, skrypt wypisze ostrzeżenie
  w logach — daj znać, dopiszemy paginację.
- To nie jest porada prawna — konkretne wymogi dot. sposobu prezentacji ceny
  referencyjnej warto zweryfikować z prawnikiem/działem compliance.

## Testowanie lokalnie (opcjonalnie)

```bash
export SHOPIFY_STORE_DOMAIN="twoj-sklep.myshopify.com"
export SHOPIFY_CLIENT_ID="xxx"
export SHOPIFY_CLIENT_SECRET="xxx"
npm run update
```
