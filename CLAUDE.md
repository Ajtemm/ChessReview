# Chess Review

## Cilj
Lokalna web aplikacija koja preuzima moje poslednje Chess.com partije
(na klik i po rasporedu), analizira ih Stockfish-om i prikazuje Game Review
slično Chess.com-u: tabla, eval bar, grafikon, lista poteza sa oznakama.

## Tehnologije
- Python 3.13 (virtualno okruženje u .venv), FastAPI, SQLite, python-chess, APScheduler
- Frontend: čist HTML/CSS/JS, chessground, chess.js, Chart.js (lokalni fajlovi, bez CDN-a)
- Stockfish: putanja u config.json

## Funkcije
1. Lista partija: protivnik, rezultat, boja, datum, kontrola vremena, tačnost, status analize
2. Dugme "Preuzmi nove partije" + automatsko preuzimanje po intervalu iz config.json
3. Klik na partiju otvara Review: tabla, strelice potez napred/nazad (i tastatura),
   eval bar, grafikon ocene, lista poteza sa ikonicama, tačnost obe strane,
   strelica najboljeg poteza, objašnjenje za kritične poteze
4. Analiza u pozadini, bez blokiranja UI-ja

## Oznake poteza
Brilliant, Great, Best, Excellent, Good, Book, Inaccuracy, Mistake, Miss, Blunder
- Računaj preko win% (Lichess formula: 50 + 50*(2/(1+exp(-0.00368*cp))-1)),
  a oznaku određuj padom win% u odnosu na najbolji potez
- Book: poredi sa lokalnom bazom otvaranja (lichess chess-openings, TSV), ne sa mrežom
- Brilliant: najbolji ili skoro najbolji potez koji žrtvuje figuru, a pozicija
  posle ostaje dobra (ne već potpuno dobijena)
- Great: jedini dobar potez ili potez koji menja ishod
- Tačnost partije: Lichess formula

## Pravila
- Chess.com API: User-Agent sa mojim kontaktom iz config.json, pauza između zahteva
- Ne analiziraj ponovo partije koje su već u bazi (ključ: URL/ID partije)
- Rezultate analize čuvaj u SQLite (po potezu: FEN, ocena, najbolji potez, oznaka)
- Nikad ne hardkoduj putanje i korisničko ime, sve ide u config.json
- Ne dodavati nove biblioteke bez pitanja
- Pre većih izmena strukture pitaj
- Komentari u kodu na srpskom

## Komande
- Aktiviranje okruženja: .venv\Scripts\activate
- Instalacija: pip install -r requirements.txt
- Pokretanje dvoklikom: start.bat (server + otvara http://localhost:8000 u browseru)
- Pokretanje: uvicorn app.main:app --reload (u običnom konzolnom prozoru: cmd/PowerShell)
  - --reload na Windows-u gasi stari proces slanjem Ctrl+C preko konzole. Kad se server
    pokreće bez vidljive konzole (Claude preview, .claude/launch.json), taj signal često
    ne stigne i restart se zaglavi ("Reloading..." bez "Shutting down"; služi stari kod).
  - Zato je u .claude/launch.json server bez --reload: posle izmene Python koda restartuj
    server. Izmene u static/ ne traže restart.
- Testovi: pytest (testovi u tests/, podešavanje u pytest.ini)
- Analiza iz komandne linije: python -m app.analysis [--game URL | --show URL | --classify | --stats]
- Preuzimanje iz komandne linije: python -m app.chesscom

## Struktura
- app/main.py                 ulaz za uvicorn: FastAPI aplikacija, statički fajlovi, lifespan
- app/config.py, app/db.py    config.json i SQLite (`with db.connection() as conn:`), zajedničko
- app/analysis/               analiza partija
  - engine.py                 Stockfish: ocena pozicija (MultiPV 2)
  - classify.py               oznake poteza (Brilliant ... Blunder, Book, Miss)
  - scoring.py                win% i tačnost (Lichess formule)
  - openings.py               knjiga otvaranja (data/openings/*.tsv)
  - analyzer.py               analiza partija iz baze (Stockfish + oznake -> baza)
  - cli.py, __main__.py       komande (python -m app.analysis)
- app/chesscom/fetcher.py     Chess.com API (python -m app.chesscom)
- app/web/                    server
  - routes.py                 API i HTML stranice
  - review_data.py            podaci za UI (lista partija, Review ekran)
  - background.py             posao u pozadini: analiza novih partija, preuzimanje, scheduler
- static/                     frontend: index.html, review.html
  - css/                      style.css (zajednički), review.css
  - js/                       index.js (lista), review.js (Review ekran), board.js (tabla),
                              eval-chart.js (grafikon), labels.js (oznake), format.js, dom.js, sounds.js
  - vendor/                   chessground, Chart.js
- tests/                      pytest testovi
- config.json                 podešavanja (već postoji)

## Stanje
- [x] Fetcher + baza
- [x] Analizer (sve oznake poteza; tačnost; analiza u pozadini)
- [x] Lista partija (UI)
- [x] Review ekran (objašnjenje poteza za sada: oznaka + najbolji potez)
- [x] Scheduler + dugme za preuzimanje (preuzimanje i pri pokretanju servera)
