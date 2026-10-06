"""Arayüz çizim ölçümü (yalnız ölçüm dalı; main'e girmez)."""
import statistics, sys, time
sys.path.insert(0, ".")
import tkinter as tk
from merkez import arayuz, ayarlar as A, tema


def say(w):
    return 1 + sum(say(c) for c in w.winfo_children())


def olc(gorunum, dondur=True):
    ayar = A.yukle(); ayar["gorunum"] = gorunum; ayar["tema"] = "light"
    if not dondur:
        arayuz._CizimiDondur.__enter__ = lambda self: self
        arayuz._CizimiDondur.__exit__ = lambda self, *a: False
    kok = tk.Tk()
    t = time.perf_counter(); app = arayuz.Uygulama(kok, ayar); kok.update(); acilis = time.perf_counter() - t
    for _ in range(3):
        kok.update(); time.sleep(0.2)
    for ad in app.sayfalar:
        app._sayfa_ac(ad); kok.update()
    gecis = {}
    for tur in range(3):
        for ad in ("web", "ayarlar", "ana", "ai", "raporlar", "bologna"):
            t = time.perf_counter(); app._sayfa_ac(ad); kok.update()
            gecis.setdefault(ad, []).append(time.perf_counter() - t)
    tema_s = []
    for _ in range(2):
        for _ in range(2):
            t = time.perf_counter()
            app.tema_var.set(not app.tema_var.get()); app._tema_degistir(); kok.update()
            tema_s.append(time.perf_counter() - t)
    t = time.perf_counter()
    for g in ("1100x760", "1400x900", "1200x800", "1320x900"):
        kok.geometry(g); kok.update()
    boyut = (time.perf_counter() - t) / 4
    n = say(kok)
    kok.destroy()
    ms = lambda x: f"{x * 1000:.0f}"
    print(f"\n### {gorunum} (dondurma {'açık' if dondur else 'kapalı'}) — {n} öğe")
    print(f"açılış {ms(acilis)} ms | boyutlandırma {ms(boyut)} ms | tema değişimi: "
          + ", ".join(ms(x) for x in tema_s) + " ms")
    for ad, v in gecis.items():
        print(f"  geçiş → {ad:9s} ort {ms(statistics.mean(v))} ms, en çok {ms(max(v))} ms")


if __name__ == "__main__":
    olc(sys.argv[1], sys.argv[2] == "1")
