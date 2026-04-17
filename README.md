# iPhone Flipper Bot

Bot Telegram w Pythonie do wyszukiwania okazji na iPhone’y z:

- Vinted
- OLX
- Allegro Lokalnie

Bot:
- skanuje ogłoszenia automatycznie,
- publikuje okazje na kanał lub grupę Telegram,
- zapisuje już widziane ogłoszenia,
- liczy score okazji na podstawie mediany cen,
- tłumaczy opisy na język polski,
- działa na Railway.app.

---

# Wymagania

- Python 3.11+
- konto GitHub
- konto Railway
- bot Telegram utworzony przez BotFather
- kanał lub grupa Telegram, gdzie bot ma publikować oferty

---

# Struktura projektu

```text
iphone-flipper-bot/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── constants.py
│   ├── logging_setup.py
│   ├── bot_handlers.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── olx.py
│   │   ├── allegro_lokalnie.py
│   │   └── vinted.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── flipper_service.py
│   │   ├── market_baseline_service.py
│   │   └── translator_service.py
│   └── utils/
│       ├── __init__.py
│       ├── misc.py
│       ├── filters.py
│       ├── formatting.py
│       └── iphone_parser.py
├── data/
├── requirements.txt
├── Dockerfile
├── .gitignore
├── .env.example
└── README.md