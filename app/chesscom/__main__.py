"""python -m app.chesscom - preuzmi poslednje partije i sačuvaj nove u bazu."""

from app.chesscom.fetcher import fetch_and_store

stats = fetch_and_store()
print(f"Preuzeto: {stats['fetched']}, novih: {stats['new']}, ukupno u bazi: {stats['total']}")
