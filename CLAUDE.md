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
- Pokretanje: uvicorn app.main:app --reload (u običnom konzolnom prozoru: cmd/PowerShell)
  - --reload na Windows-u gasi stari proces slanjem Ctrl+C preko konzole. Kad se server
    pokreće bez vidljive konzole (Claude preview, .claude/launch.json), taj signal često
    ne stigne i restart se zaglavi ("Reloading..." bez "Shutting down"; služi stari kod).
  - Zato je u .claude/launch.json server bez --reload: posle izmene Python koda restartuj
    server. Izmene u static/ ne traže restart.
- Testovi: pytest

## Struktura
- app/main.py        FastAPI, rute, scheduler
- app/fetcher.py     Chess.com API
- app/analyzer.py    Stockfish i oznake poteza
- app/db.py          SQLite
- static/            frontend
- config.json        podešavanja (već postoji)

## Stanje
- [x] Fetcher + baza
- [x] Analizer (sve oznake poteza; tačnost; analiza u pozadini)
- [x] Lista partija (UI)
- [x] Review ekran (objašnjenje poteza za sada: oznaka + najbolji potez)
- [x] Scheduler + dugme za preuzimanje (preuzimanje i pri pokretanju servera)
