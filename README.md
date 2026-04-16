# iPhone Flipper Bot

Bot Telegram, który co 15 minut skanuje:
- Vinted.pl
- OLX.pl
- Allegro Lokalnie

i publikuje najlepsze cenowo oferty iPhone'ów.

## Uruchomienie lokalne

1. Skopiuj `.env.example` do `.env`
2. Uzupełnij zmienne
3. Zainstaluj zależności:
   ```bash
   pip install -r requirements.txt
   playwright install --with-deps chromium