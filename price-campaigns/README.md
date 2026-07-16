# Kampanie cenowe — instrukcja wdrożenia

Ten folder zawiera automatyzację, która co 5 minut sprawdza arkusz Google
"Kampanie cenowe" i sama zmienia ceny w Shopify (start kampanii, koniec
kampanii = przywrócenie ceny).

## Pliki w tym folderze

- `run_campaigns.py` — główny skrypt (czyta arkusz, aktualizuje Shopify)
- `requirements.txt` — lista bibliotek Python potrzebnych do działania
- `price-campaigns.yml` — harmonogram GitHub Actions (trzeba go przenieść
  do specjalnego folderu, patrz Krok 3 poniżej)

## Krok 1: Wgraj pliki do repo

1. Wejdź na swoje repo `omnibus-price-tracker` na GitHub.
2. Utwórz nowy folder `price-campaigns` (przy dodawaniu pliku możesz wpisać
   `price-campaigns/run_campaigns.py` jako nazwę — GitHub sam utworzy folder).
3. Wgraj tam `run_campaigns.py` i `requirements.txt`.

## Krok 2: Dodaj uprawnienie zapisu do istniejącej aplikacji Shopify

Ta automatyzacja używa **tej samej aplikacji i tych samych danych logowania**
co Omnibus (Client ID + Client Secret) — nic nowego nie trzeba tworzyć.
Trzeba tylko dodać jej uprawnienie do zapisu cen:

1. Shopify → Ustawienia → Aplikacje i kanały sprzedaży → Rozwijaj aplikacje.
2. Kliknij na aplikację używaną przez Omnibus.
3. Zakładka „Konfiguracja" → sekcja „Zakres dostępu Admin API" → „Skonfiguruj".
4. Wyszukaj `products`, zaznacz `write_products` (oprócz już zaznaczonego `read_products`).
5. Zapisz i potwierdź, jeśli Shopify poprosi o ponowną autoryzację uprawnień.

## Krok 3: Opublikuj arkusz Google jako CSV

1. Otwórz arkusz "Kampanie cenowe — e-hairshop".
2. Menu: **Plik → Udostępnij → Opublikuj w internecie**.
3. W oknie, które się pojawi: pierwsze pole ustaw na zakładkę **"Kampanie"**
   (nie "Cały dokument"), drugie pole zmień z "Strona internetowa" na **"CSV"**.
4. Kliknij **"Opublikuj"**, potwierdź.
5. Skopiuj wygenerowany link (będzie zaczynał się od
   `https://docs.google.com/spreadsheets/d/.../pub?...`) — będzie potrzebny
   w Kroku 5.

## Krok 4: Umieść workflow w prawidłowym folderze

GitHub Actions wymaga, żeby pliki harmonogramu leżały w folderze
`.github/workflows/`. W repo:

1. Utwórz plik o nazwie: `.github/workflows/price-campaigns.yml`
2. Wklej tam całą zawartość pliku `price-campaigns.yml`, który dostałaś.

## Krok 5: Dodaj jeden nowy sekret w GitHub

`SHOPIFY_STORE_DOMAIN`, `SHOPIFY_CLIENT_ID` i `SHOPIFY_CLIENT_SECRET` już
istnieją w repo (te same, co dla Omnibusa) — nie musisz ich dodawać ponownie.
Potrzebny jest tylko jeden nowy:

1. W repo: **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `SHEET_CSV_URL`, Secret: link z Kroku 3.

## Krok 6: Sprawdź, czy działa

1. W repo: zakładka **Actions**.
2. Znajdź workflow "Price Campaigns" po lewej.
3. Kliknij **"Run workflow"** (żeby przetestować od razu, bez czekania na harmonogram).
4. Kliknij na uruchomienie, które się pojawi, żeby zobaczyć logi —
   powinny pokazać, ile kampanii wczytano i czy któreś wariant zostały zaktualizowane.

Od teraz workflow uruchamia się automatycznie co 5 minut.

**UWAGA:** wewnętrzny harmonogram GitHub (`schedule` w pliku `.yml`) okazał
się niewystarczająco dokładny w praktyce — potrafił się opóźniać nawet
o kilka godzin. Dlatego dodałyśmy dodatkowe, niezawodne rozwiązanie —
patrz sekcja "ZEWNĘTRZNY HARMONOGRAM (cron-job.org)" poniżej. To ono,
nie wewnętrzny `schedule`, faktycznie odpowiada za punktualne uruchamianie.

## ZEWNĘTRZNY HARMONOGRAM (cron-job.org) — dlaczego i jak skonfigurowany

**Problem, który to rozwiązuje:** harmonogramy (`schedule`) w GitHub Actions
ustawione na częste odstępy (co 5 minut) są w praktyce silnie opóźniane przez
GitHub, szczególnie w mniej aktywnych repozytoriach — obserwowałyśmy
opóźnienia rosnące z ~5h do ~8h zamiast 5 minut. To ograniczenie
infrastruktury GitHub, nie coś, co da się naprawić w kodzie.

**Rozwiązanie:** darmowy zewnętrzny serwis **cron-job.org** wywołuje workflow
z zewnątrz, co 5 minut, przez GitHub API (`workflow_dispatch`). Zewnętrzne
serwisy tego typu są dokładne, bo to ich jedyne zadanie.

**Co zostało skonfigurowane:**

1. **Personal Access Token w GitHub** (Settings → Developer settings →
   Personal access tokens → Fine-grained tokens) — nazwa "Price Campaigns
   Trigger", dostęp tylko do repo `omnibus-price-tracker`, uprawnienie
   "Actions: Read and write".
   **WAŻNE:** ten token, w przeciwieństwie do Client ID/Secret, **wygasa
   (ustawione na max. dostępny okres, ok. 1 rok)** — trzeba go będzie
   ręcznie odnowić, wygenerować nowy w tym samym miejscu, i podmienić
   w konfiguracji cron-job.org. Warto ustawić sobie przypomnienie w
   kalendarzu na ok. rok od dzisiejszej daty.

2. **Konto na cron-job.org**, z jednym cronjobem:
   - URL: `https://api.github.com/repos/magdaextensions-dev/omnibus-price-tracker/actions/workflows/price-campaigns.yml/dispatches`
   - Metoda: `POST`
   - Harmonogram: co 5 minut, 24/7
   - Nagłówki: `Authorization: Bearer <token z punktu 1>`,
     `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - Treść żądania: `{"ref":"main"}`

Jeśli w przyszłości automatyzacja przestanie się uruchamiać co 5 minut —
najpierw sprawdź, czy token w cron-job.org nie wygasł (patrz punkt 1 powyżej),
zanim zaczniesz szukać błędu gdzie indziej.

**To samo rozwiązanie zastosowane do Omnibusa (ważne, kontekst prawny):**
Workflow Omnibusa (plik `.github/workflows/update-price-history.yml`,
widoczny w Actions jako "Aktualizacja historii cen (Omnibus)") miał ten sam
problem — wewnętrzny harmonogram GitHub uruchamiał go realnie **raz dziennie**
zamiast co godzinę/kilka minut. To nie tylko niewygodne, ale **potencjalny
problem zgodności z dyrektywą Omnibus UE** — im dłuższa luka między obniżką
ceny a zapisaniem jej w historii, tym dłużej sklep pokazuje obniżoną cenę
bez wymaganej informacji o najniższej cenie z 30 dni.

Rozwiązanie: w cron-job.org powstało drugie, osobne zadanie —
**„GitHub Actions - omnibus-price-history trigger"** — wywołujące
`update-price-history.yml` co 5 minut, tym samym tokenem GitHub
("Price Campaigns Trigger", uprawnienia obejmują całe repo, więc jeden
token obsługuje oba workflow). Ten sam token, ta sama zasada wygasania
za ok. rok — patrz punkt 1 powyżej, dotyczy obu zadań cron jednocześnie.

## WAŻNA NOTATKA TECHNICZNA (Dev Dashboard vs stary system Shopify)

Aplikacje tworzone w nowym **Dev Dashboard** Shopify (obecny standard) **nie
dają stałego, jednorazowo-skopiowanego tokenu** — jak to było w starszym
systemie ("Rozwijaj aplikacje" w klasycznym panelu). Zamiast tego:

- Dostajesz **Client ID + Client Secret** (te dwie wartości NIE wygasają).
- Token dostępu do API trzeba pobierać programowo, metodą "client credentials
  grant" — token jest ważny tylko 24h, ale skrypt pobiera nowy automatycznie
  przy każdym uruchomieniu, więc w praktyce nic nigdy nie wygasa "z Twojej
  perspektywy" — nie musisz nic odnawiać ręcznie.
- To dotyczy WSZYSTKICH nowych aplikacji tworzonych od teraz w Shopify na tym
  koncie (nie tylko tej do kampanii cenowych) — przy kolejnych automatyzacjach
  zakładaj od razu ten mechanizm, nie próbuj szukać "prostego tokenu do
  skopiowania", bo taka opcja może już nie być dostępna.

Jak sprawdzić aktualne uprawnienia (scopes) aplikacji w Dev Dashboard:
1. Wejdź na `dev.shopify.com/dashboard`.
2. Wybierz swoją organizację (jeśli masz więcej niż jedną).
3. Zakładka **„Apps"** → kliknij na aplikację.
4. Zakładka **„Configuration"** (albo „API access") — tam widać listę
   zaznaczonych zakresów dostępu (scopes), np. `read_products`, `write_products`.

## Jak to działa (skrócony opis techniczny)

- Skrypt pobiera dane z opublikowanego CSV arkusza.
- Dla każdej kampanii sprawdza, czy aktualny czas (UTC) jest między
  Start i Koniec (obie daty w arkuszu są w czasie polskim, skrypt sam
  przelicza na UTC z uwzględnieniem czasu letniego/zimowego).
- Rozwiązuje "Cel" (kolekcja / produkty / konkretne warianty) na listę
  konkretnych wariantów w Shopify.
- Jeśli kilka kampanii dotyczy tego samego wariantu naraz, wygrywa ta
  z niższym numerem w kolumnie "Priorytet" (a jeśli brak priorytetu —
  ta z większym rabatem).
- Oryginalna cena i cena porównawcza (przed rabatem) są zapisywane
  w metapolach wariantu (`campaigns.original_price`,
  `campaigns.original_compare_at_price`, `campaigns.active_campaign_name`) —
  to pozwala bezpiecznie przywrócić cenę po zakończeniu kampanii, nawet
  jeśli ktoś w międzyczasie ręcznie zmieni cenę w Shopify.
