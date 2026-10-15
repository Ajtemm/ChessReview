"""Posao u pozadini dok server radi: analiza novih partija, preuzimanje i raspored preuzimanja."""

import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app import analyzer, db, fetcher

# Uvicorn-ov logger, da se poruke vide u istom izlazu kao i server
log = logging.getLogger("uvicorn.error")


class AnalysisWorker:
    """Pozadinska nit koja analizira nove partije (status 'pending').

    Budi se na `trigger()` (npr. posle preuzimanja) ili posle `poll_seconds`,
    pa vidi i partije koje je ubacio fetcher pokrenut iz komandne linije.
    """

    def __init__(self, poll_seconds: float):
        self.poll_seconds = poll_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="analysis-worker", daemon=True)
        self._lock = threading.Lock()
        self._progress: tuple[int, int] | None = None  # (trenutna partija, ukupno) dok analiza traje

    def start(self) -> None:
        self._thread.start()

    def trigger(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        # Partija koja se upravo analizira se završava; ne čekamo predugo
        self._thread.join(timeout=10)

    def progress(self) -> dict:
        """Napredak analize za UI: {"running", "current", "total"}."""
        with self._lock:
            if self._progress is None:
                return {"running": False, "current": 0, "total": 0}
            current, total = self._progress
            return {"running": True, "current": current, "total": total}

    def _set_progress(self, current: int, total: int) -> None:
        with self._lock:
            self._progress = (current, total)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                # Partije sa greškom ne pokušavamo stalno; za njih je komanda analyzer-a
                stats = analyzer.analyze_pending(
                    ("pending",), should_stop=self._stop.is_set, on_progress=self._set_progress
                )
                if stats["done"] or stats["error"]:
                    log.info("Analiza u pozadini: %s", stats)
            except Exception:
                log.exception("Greška u pozadinskoj analizi")
            finally:
                with self._lock:
                    self._progress = None
            self._wake.wait(self.poll_seconds)


class FetchService:
    """Preuzimanje novih partija sa Chess.com-a, na dugme i po rasporedu.

    Istovremeno radi najviše jedno preuzimanje; posle preuzimanja odmah budi analizu.
    """

    def __init__(self, worker: AnalysisWorker):
        self.worker = worker
        self._busy = threading.Lock()   # zauzet dok preuzimanje traje
        self._lock = threading.Lock()   # štiti polja stanja ispod
        self.fetching = False
        self.last_fetch_at: str | None = None   # poslednje uspešno preuzimanje (ISO, UTC)
        self.last_result: dict | None = None
        self.last_error: str | None = None

    def start_in_background(self) -> bool:
        """Pokreće preuzimanje u posebnoj niti. False ako preuzimanje već traje."""
        if not self._busy.acquire(blocking=False):
            return False
        threading.Thread(target=self._run_locked, name="fetch", daemon=True).start()
        return True

    def run_scheduled(self) -> None:
        """Posao za APScheduler (već radi u njegovoj niti)."""
        if not self._busy.acquire(blocking=False):
            log.info("Preuzimanje već traje, zakazano preuzimanje se preskače")
            return
        self._run_locked()

    def _run_locked(self) -> None:
        try:
            with self._lock:
                self.fetching = True
                self.last_error = None
            stats = fetcher.fetch_and_store()
            with self._lock:
                self.last_result = stats
                self.last_fetch_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            log.info("Preuzimanje partija: %s", stats)
            # Budimo analizu i kad nema novih: pokupi i partije koje čekaju iz drugih razloga
            self.worker.trigger()
        except Exception as e:
            log.exception("Greška pri preuzimanju partija")
            with self._lock:
                self.last_error = str(e) or e.__class__.__name__
        finally:
            with self._lock:
                self.fetching = False
            self._busy.release()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "fetching": self.fetching,
                "last_fetch_at": self.last_fetch_at,
                "last_result": self.last_result,
                "last_error": self.last_error,
            }


class BackgroundServices:
    """Analiza, preuzimanje i raspored preuzimanja zajedno: pale se i gase sa serverom."""

    FETCH_JOB_ID = "fetch"

    def __init__(self, config: dict):
        self.worker = AnalysisWorker(float(config.get("analysis_poll_seconds", 60)))
        self.fetch = FetchService(self.worker)
        self.scheduler = BackgroundScheduler()
        # Automatsko preuzimanje: odmah po pokretanju, pa na interval iz config.json
        self.scheduler.add_job(
            self.fetch.run_scheduled, "interval",
            minutes=float(config["fetch_interval_minutes"]),
            id=self.FETCH_JOB_ID, next_run_time=datetime.now(timezone.utc),
            max_instances=1, coalesce=True,
        )

    def start(self) -> None:
        with db.connection() as conn:
            # Analize prekinute gašenjem servera vraćamo u red
            db.reset_interrupted(conn)
        self.worker.start()
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        self.worker.stop()

    def status(self) -> dict:
        """Stanje preuzimanja i analize za UI."""
        job = self.scheduler.get_job(self.FETCH_JOB_ID)
        next_run = job.next_run_time if job else None
        return {
            "fetch": {
                **self.fetch.snapshot(),
                "next_run_at": next_run.isoformat(timespec="seconds") if next_run else None,
            },
            "analysis": self.worker.progress(),
        }
