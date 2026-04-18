# iPhone Flipper Bot — final hardened version

Ta wersja jest podkręcona pod realne problemy z marketplace'ów:
- ostrzejsze filtrowanie akcesoriów, części i pustych boxów,
- brak ślepego przypisywania modelu z samego search query,
- dokładniejsze detail page dla OLX i Allegro Lokalnie,
- czystsze opisy i ceny z Vinted,
- baseline liczone tylko z ofert, które same przechodzą filtry.

## Co naprawia

- etui, szkła, ładowarki, obudowy, pudełka,
- oferty typu „do iPhone 12”,
- części i rozbitki,
- śmieciowe opisy z Vinted,
- zatruwanie median przez złe oferty.

## Uruchomienie lokalnie

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python -m app.main
```

## Ważne po aktualizacji

Jeżeli stara baza była już zatruta błędnymi medianami, wyczyść ją przed startem:
- usuń cały plik `offers.db`, albo
- wyczyść przynajmniej tabelę `market_baselines`.

## Komendy bota

- `/start`
- `/health`
- `/scan_now`
