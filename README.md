# Omnibus Price Tracker — zamiennik płatnej apki

Ten projekt zastępuje apkę typu "Omnibus Insight" własnym rozwiązaniem:
codzienny snapshot cen zapisywany do metafieldów wariantów + snippet Liquid
pokazujący najniższą cenę z ostatnich 30 dni.

Koszt: 0 zł/mies. (GitHub Actions w darmowym tygodniu ma wystarczający limit
minut dla jednego zadania dziennie trwającego kilka-kilkanaście sekund).

## Krok 1 — Custom App w Shopify (żeby uzyskać token Admin API)

1. W panelu Shopify: **Ustawienia → Aplikacje i kanały sprzedaży → Rozwijaj aplikacje**.
2. Kliknij **Utwórz aplikację**, nadaj nazwę np. "Price History Bot".
3. W zakładce **Konfiguracja → Admin API integration** ustaw zakresy (scopes):
   - `read_products`
   - `write_products`
4. Zainstaluj aplikację w sklepie i skopiuj **Admin API access token**
   (pokazuje się tylko raz — zapisz go bezpiecznie).

**Token traktuj jak hasło — nie wklejaj go nigdzie w kodzie ani w chacie.**
Ty sam wykonujesz ten krok w panelu Shopify.

## Krok 2 — Definicja metafieldu (jednorazowo, przez UI)

1. **Ustawienia → Dane niestandardowe (Custom data) → Warianty → Dodaj definicję**.
2. Namespace: `custom`, Key: `price_history`, Typ: **JSON**.
3. Zapisz.

(Skrypt zadziała nawet bez tego kroku — Shopify utworzy metafield automatycznie
przy pierwszym zapisie — ale jawna definicja ułatwia potem przegląd danych w adminie.)

## Krok 3 — Repozytorium GitHub + sekrety

1. Wrzuć ten folder (`omnibus-price-tracker`) jako repozytorium na GitHub
   (może być prywatne).
2. W repo: **Settings → Secrets and variables → Actions → New repository secret**
   i dodaj dwa sekrety:
   - `SHOPIFY_STORE_DOMAIN` → np. `twoj-sklep.myshopify.com`
   - `SHOPIFY_ADMIN_TOKEN` → token z Kroku 1
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

3. Jeśli motyw zmienia wariant przez JS bez przeładowania strony (typowe dla
   Dawn i pochodnych), ten fragment odświeży się dopiero po przeładowaniu.
   Jeśli chcesz pełną reaktywność przy zmianie wariantu bez przeładowania,
   daj znać — dopiszę wersję z JS nasłuchującym na zmianę wariantu.

## Ważna uwaga prawna / praktyczna

- Przez pierwsze ~30 dni od uruchomienia historia będzie niepełna. Snippet
  celowo nic nie pokaże, dopóki nie ma choć jednego wpisu niższego od
  aktualnej ceny — ale to nie jest to samo, co "pełne 30 dni danych".
  Zalecane: uruchom `workflow_dispatch` ręcznie od razu, a przez pierwszy
  miesiąc traktuj wyświetlaną wartość jako orientacyjną, a docelowo dokładną
  dopiero po pełnym cyklu 30-dniowym.
- Ten kod obsługuje standardowy przypadek (produkty z ≤100 wariantami).
  Jeśli masz produkty z większą liczbą wariantów, skrypt wypisze ostrzeżenie
  w logach — wtedy trzeba dopisać paginację wariantów (mogę to dorobić, jeśli
  taki przypadek u Ciebie występuje).
- To nie jest porada prawna — konkretne wymogi dot. sposobu prezentacji ceny
  referencyjnej warto zweryfikować z prawnikiem/działem compliance, ten kod
  realizuje mechanikę "najniższa cena z 30 dni", którą wskazałeś.

## Testowanie lokalnie (opcjonalnie)

```bash
export SHOPIFY_STORE_DOMAIN="twoj-sklep.myshopify.com"
export SHOPIFY_ADMIN_TOKEN="shpat_xxx"
npm run update
```
