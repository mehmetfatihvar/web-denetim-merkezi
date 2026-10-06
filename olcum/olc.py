"""Arayüz çizim ölçümü (yalnız ölçüm dalı; main'e girmez)."""
import statistics, sys, threading, time
sys.path.insert(0, ".")
import tkinter as tk
from merkez import arayuz, ayarlar as A, tema

ms = lambda x: f"{x * 1000:.0f}"


def say(w):
    return 1 + sum(say(c) for c in w.winfo_children())


def olc(gorunum, senaryo):
    ayar = A.yukle(); ayar["arayuz_gorunumu"] = gorunum; ayar["tema"] = "light"
    kok = tk.Tk()
    t = time.perf_counter(); app = arayuz.Uygulama(kok, ayar); kok.update(); acilis = time.perf_counter() - t
    for _ in range(3):
        kok.update(); time.sleep(0.2)
    akis = None
    if senaryo in ("kayit", "akis"):
        satir = "  [{0}/17394] WARN  200  https://193.255.182.40/tr/akademik/fakulte/bolum/sayfa-{0}/alt-sayfa-ornek\n"
        for i in range(0, 20000, 500):
            app._yaz("".join(satir.format(j) for j in range(i, i + 500)))
        kok.update()
    if senaryo == "akis":       # çalışma sürüyor: saniyede 20 satır
        dur = threading.Event()
        def besle():
            i = 0
            while not dur.is_set():
                app._yaz_kuyruga(f"  [{i}/36899] link kontrol https://193.255.182.40/x/{i}\n"); i += 1
                time.sleep(0.05)
        akis = threading.Thread(target=besle, daemon=True); akis.start()
    for ad in app.sayfalar:
        app._sayfa_ac(ad); kok.update()
    gecis = {}
    for tur in range(3):
        for ad in ("web", "ayarlar", "ana", "ai", "raporlar"):
            t = time.perf_counter(); app._sayfa_ac(ad); kok.update()
            gecis.setdefault(ad, []).append(time.perf_counter() - t)
    parca = []
    for _ in range(4):
        app.tema_var.set(not app.tema_var.get())
        t0 = time.perf_counter()
        app.ayar["tema"] = "dark" if app.tema_var.get() else "light"
        app.p = tema.uygula(app.kok, app.ayar["tema"], app.hizli); t1 = time.perf_counter()
        app._tema_renkleri(); t2 = time.perf_counter()
        kok.update(); t3 = time.perf_counter()
        parca.append((t1 - t0, t2 - t1, t3 - t2))
    t = time.perf_counter()
    for g in ("1100x760", "1400x900", "1200x800", "1320x900"):
        kok.geometry(g); kok.update()
    boyut = (time.perf_counter() - t) / 4
    t = time.perf_counter()
    for _ in range(20):
        app._menu_uzerinde("web", True); kok.update(); app._menu_uzerinde("web", False); kok.update()
    hover = (time.perf_counter() - t) / 40
    n = say(kok)
    if akis:
        dur.set()
    kok.destroy()
    print(f"\n### {gorunum} / senaryo={senaryo} - {n} oge")
    print(f"acilis {ms(acilis)} ms | boyutlandirma {ms(boyut)} ms | menu hover {ms(hover)} ms")
    print("tema degisimi (tema.uygula + renkler + cizim): " +
          " | ".join(f"{ms(a)}+{ms(b)}+{ms(c)}" for a, b, c in parca) + " ms")
    for ad, v in gecis.items():
        print(f"  gecis -> {ad:9s} ort {ms(statistics.mean(v))} ms, en cok {ms(max(v))} ms")


if __name__ == "__main__":
    olc(sys.argv[1], sys.argv[2])
