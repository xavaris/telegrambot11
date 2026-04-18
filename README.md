
# iPhone Flipper Bot — repaired build

Najważniejsze poprawki:
- Vinted nie czyta już opisu/modelu z całego `body`
- model z Vinted bierze priorytetowo z tytułu i szczegółów oferty
- pamięć bierze z pola szczegółów
- twarde odrzucanie etui, case'ów, pudełek i części
- mediany bazowe liczą się tylko z ofert, które same przechodzą filtry
- publikacja do konkretnego forum topic przez `MESSAGE_THREAD_ID`

## Start
1. Uzupełnij `.env`
2. `pip install -r requirements.txt`
3. `playwright install chromium`
4. `python -m app.main`

## Ważne
Po wdrożeniu wyczyść starą tabelę `market_baselines` albo cały `offers.db`, bo stare mediany mogły być zatrute złymi ofertami.
