#!/usr/bin/env python3

import argparse
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

WDQS = "https://query.wikidata.org/sparql"
# Wikimedia kuralı: User-Agent'ta iletişim bilgisi olmalı. Kendi mailini yaz.
USER_AGENT = "FutbolcuDuellosu/1.0 (hobi projesi; iletisim: BURAYA_MAIL_YAZ@example.com)"
TM_PLAYERS_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz"

BATCH_SIZE = 150

# Transfermarkt'ta `last_season` = oyuncunun son oynadığı sezonun başlangıç yılı.
# Bu değerden küçükse oyuncu emekli/kulüpsüz sayılır ve `current_club_name` ESKİ kulüp olduğu için kullanılmaz.
CURRENT_SEASON = 2025
RETIRED_LABEL = "Emekli / kulüpsüz"
OVERRIDES_FILE = "team_overrides.json"   # {"Oyuncu Adı": "Güncel Takım"}  (transferleri elle düzeltmek için)


def load_team_overrides(path=OVERRIDES_FILE):
    f = Path(path)
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- #
# 1) Transfermarkt (Kaggle) tarafı
# --------------------------------------------------------------------------- #
def load_transfermarkt(path):
    src = path if path else TM_PLAYERS_URL
    print(f"[TM] okunuyor: {src}")
    try:
        df = pd.read_csv(src)
    except Exception as e:
        sys.exit(
            f"[HATA] Transfermarkt players dosyası okunamadı ({e}).\n"
            "Kaggle'dan 'davidcariboo/player-scores' veri setini indirip içindeki players.csv'yi\n"
            "bu klasöre koy ve şöyle çalıştır:  python build_players.py --tm-csv players.csv"
        )
    print(f"[TM] {len(df)} oyuncu, sütunlar: {list(df.columns)}")
    return df


def num(x):
    """NaN / boş değerleri None yapar, sayıyı int'e çevirir."""
    if x is None or pd.isna(x):
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


TURKISH_NAMES = {"Türkiye", "Turkey"}   # Transfermarkt iki yazımı da kullanıyor

# "4 büyükler": bu kulüplerin GÜNCEL kadrosundaki herkes (milliyet/değer fark etmez) listeye alınır.
# Transfermarkt kulüp ID'leri: 36 Fenerbahçe, 114 Beşiktaş, 141 Galatasaray, 449 Trabzonspor
BIG_CLUB_IDS = [36, 114, 141, 449]


def pick_candidates(df, min_value_m, min_caps, tr_min_value_m=None, tr_min_caps=None, club_ids=None, current_season=CURRENT_SEASON):
    """Ünlü liste (_core) + Türk oyuncular için daha düşük eşikli ek liste (_tr).
    Türk ek oyuncular oyunda TAHMİN edilebilir ama hedef futbolcu olarak seçilmez (guessOnly)."""
    peak = df.get("highest_market_value_in_eur")
    caps = df.get("international_caps")
    if peak is None:
        sys.exit("[HATA] 'highest_market_value_in_eur' sütunu yok; sütun adlarını yukarıdaki listeden kontrol et.")
    peak = peak.fillna(0)
    core = peak >= min_value_m * 1_000_000
    if caps is not None:
        core |= caps.fillna(0) >= min_caps
    else:
        print("[UYARI] 'international_caps' sütunu yok, sadece piyasa değerine göre seçiliyor.")

    is_tr = df["country_of_citizenship"].isin(TURKISH_NAMES) if "country_of_citizenship" in df else (core & False)
    tr_mask = is_tr & False
    if tr_min_value_m is not None or tr_min_caps is not None:
        if tr_min_value_m is not None:
            tr_mask = tr_mask | (peak >= tr_min_value_m * 1_000_000)
        if tr_min_caps is not None and caps is not None:
            tr_mask = tr_mask | (caps.fillna(0) >= tr_min_caps)
        tr_mask = is_tr & tr_mask

    # Seçili kulüplerin güncel kadrosu (son sezonu güncel olanlar; eski oyuncuların kulübü "son kulüp"tür)
    club_mask = core & False
    if club_ids and "current_club_id" in df:
        active = df["last_season"].fillna(0) >= current_season if "last_season" in df else True
        club_mask = df["current_club_id"].isin(club_ids) & active

    out = df[core | tr_mask | club_mask].copy()
    out["_core"] = core[out.index]
    out["_tr"] = (is_tr | club_mask)[out.index]      # düşük Wikipedia eşiği bu iki gruba uygulanır
    print(f"[TM] aday sayısı (değer >= {min_value_m}M€ veya milli maç >= {min_caps}): {int(core.sum())}"
          f" | ek Türk adayı: {int((tr_mask & ~core).sum())} | ek kulüp kadrosu: {int((club_mask & ~core & ~tr_mask).sum())}"
          f" | toplam: {len(out)}")
    return out


# --------------------------------------------------------------------------- #
# 2) Wikidata tarafı
# --------------------------------------------------------------------------- #
def run_sparql(query, retries=5):
    for attempt in range(retries):
        try:
            r = requests.post(
                WDQS,
                data={"query": query, "format": "json"},
                headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
                timeout=120,
            )
        except requests.RequestException as e:
            print(f"   ağ hatası: {e}")
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()["results"]["bindings"]
        if r.status_code in (429, 500, 502, 503, 504):
            wait = int(r.headers.get("Retry-After", 15 * (attempt + 1)))
            print(f"   Wikidata {r.status_code}, {wait} sn bekleniyor...")
            time.sleep(wait)
            continue
        r.raise_for_status()
    raise RuntimeError("Wikidata sorgusu tekrar tekrar başarısız oldu")


def build_query(tm_ids):
    values = " ".join(f'"{i}"' for i in tm_ids)
    return f"""
SELECT ?tm ?item ?itemLabel ?sl ?dob ?height ?pobLabel ?coord ?countryLabel WHERE {{
  VALUES ?tm {{ {values} }}
  ?item wdt:P2446 ?tm ;
        wikibase:sitelinks ?sl .
  OPTIONAL {{ ?item wdt:P569 ?dob . }}
  OPTIONAL {{ ?item wdt:P2048 ?height . }}
  OPTIONAL {{ ?item wdt:P19 ?pob . ?pob wdt:P625 ?coord . }}
  OPTIONAL {{ ?item wdt:P27 ?country . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}}"""


def val(b, key):
    return b[key]["value"] if key in b else None


TEAMS_CACHE = "wikidata_teams_cache.json"   # {oyuncu qid: güncel kulüp adı | null}
CLUBS_CACHE = "wikidata_clubs_cache.json"   # {takım qid: {"name":..., "club": true/false}}
TEAM_BATCH = 80      # oyuncu sorgusu (hafif tutuldu, 504 zaman aşımını önlemek için)
CLUB_BATCH = 150     # takım sorgusu

_PREFIXES = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd: <http://www.bigdata.com/rdf#>
"""


def build_open_team_query(qids):
    """1. sorgu (HAFİF): oyuncuların BİTİŞ TARİHİ OLMAYAN (P582 yok) takım üyelikleri (P54).
    Etiket servisi ve alt sınıf taraması yok; takım adı/türü 2. sorguda çözülür."""
    values = " ".join(f"wd:{q}" for q in qids)
    return _PREFIXES + f"""
SELECT ?item ?team ?start WHERE {{
  VALUES ?item {{ {values} }}
  ?item p:P54 ?st .
  ?st ps:P54 ?team .
  FILTER NOT EXISTS {{ ?st pq:P582 ?end . }}
  OPTIONAL {{ ?st pq:P580 ?start . }}
}}"""


def build_club_info_query(team_qids):
    """2. sorgu: benzersiz takımların adı + milli takım mı (P1532 var mı) + futbol kulübü mü."""
    values = " ".join(f"wd:{q}" for q in team_qids)
    return _PREFIXES + f"""
SELECT ?team ?teamLabel ?nat ?type ?sport WHERE {{
  VALUES ?team {{ {values} }}
  OPTIONAL {{ ?team wdt:P1532 ?nat . }}
  OPTIONAL {{ ?team wdt:P31 ?type . }}
  OPTIONAL {{ ?team wdt:P641 ?sport . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}}"""


FOOTBALL_CLUB = "Q476028"   # association football club
FOOTBALL = "Q2736"          # association football (spor dalı)


def qid_of(uri):
    return uri.rsplit("/", 1)[-1] if uri else None


def parse_club_info(bindings):
    """-> {takım qid: {"name": ad, "club": bool}}  (club = futbol kulübü ve milli takım DEĞİL)"""
    info = {}
    for b in bindings:
        t = qid_of(val(b, "team"))
        rec = info.setdefault(t, {"name": None, "nat": False, "fb": False})
        rec["name"] = rec["name"] or val(b, "teamLabel")
        if val(b, "nat"):
            rec["nat"] = True
        if qid_of(val(b, "type")) == FOOTBALL_CLUB or qid_of(val(b, "sport")) == FOOTBALL:
            rec["fb"] = True
    return {t: {"name": r["name"], "club": bool(r["fb"] and not r["nat"]
                                                and r["name"] and not re.fullmatch(r"Q\d+", r["name"]))}
            for t, r in info.items()}


def pick_current_team(rows, clubs):
    """rows: [(takım qid, başlangıç|None)], clubs: parse_club_info çıktısı.
    Sadece futbol kulüplerini alır, en son başlayanı seçer."""
    ok = [(t, s or "") for t, s in rows if clubs.get(t, {}).get("club")]
    if not ok:
        return None
    return clubs[max(ok, key=lambda r: r[1])[0]]["name"]


def _load(path, refresh):
    f = Path(path)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() and not refresh else {}


def _save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_current_teams(qids, cache_path=TEAMS_CACHE, refresh=False, clubs_path=CLUBS_CACHE):
    """Wikidata'dan güncel kulüpleri çeker. Sonuç: {oyuncu qid: takım adı | None}.
    Her parti bitince önbelleğe yazılır; yarıda kesilirse (Ctrl+C / ağ hatası) kaldığı yerden devam eder."""
    cache = _load(cache_path, refresh)
    clubs = _load(clubs_path, refresh)
    todo = [q for q in dict.fromkeys(qids) if q and q not in cache]
    print(f"[TEAM] önbellekte {len(cache)} oyuncu var, çekilecek: {len(todo)}")
    for start in range(0, len(todo), TEAM_BATCH):
        batch = todo[start:start + TEAM_BATCH]
        print(f"[TEAM] {start + 1}-{start + len(batch)} / {len(todo)}")
        try:
            rows = {q: [] for q in batch}
            for b in run_sparql(build_open_team_query(batch)):
                rows.setdefault(qid_of(val(b, "item")), []).append((qid_of(val(b, "team")), val(b, "start")))
            # Bu partideki, henüz tanımadığımız takımların adı/türü
            unknown = sorted({t for r in rows.values() for t, _ in r if t not in clubs})
            for i in range(0, len(unknown), CLUB_BATCH):
                clubs.update(parse_club_info(run_sparql(build_club_info_query(unknown[i:i + CLUB_BATCH]))))
        except Exception as e:
            print(f"[TEAM][UYARI] Wikidata sorgusu başarısız ({e}). "
                  "Çekilemeyenler için Transfermarkt takımı kullanılacak; scripti tekrar çalıştırırsan kaldığı yerden devam eder.")
            break
        for q in batch:
            cache[q] = pick_current_team(rows.get(q, []), clubs)
        _save(clubs_path, clubs)
        _save(cache_path, cache)
        time.sleep(1)
    return cache


def fetch_wikidata(tm_ids, cache_path, refresh, offline=False):
    """Önbellekte olmayan oyuncuları çeker (artımlı). Wikidata'da kaydı bulunamayanlar
    {"qid": None} olarak işaretlenir, her çalıştırmada yeniden sorgulanmaz."""
    cache_file = Path(cache_path)
    result = {}
    if cache_file.exists() and not refresh:
        result = json.loads(cache_file.read_text(encoding="utf-8"))
        print(f"[WD] önbellek kullanılıyor: {cache_file} ({len(result)} kayıt)")
    ids = [str(i) for i in tm_ids if str(i) not in result]
    if offline:
        print(f"[WD] --offline: {len(ids)} yeni oyuncu çekilmedi.")
        return result
    if not ids:
        return result
    print(f"[WD] önbellekte olmayan {len(ids)} oyuncu çekilecek")
    for start in range(0, len(ids), BATCH_SIZE):
        batch = ids[start:start + BATCH_SIZE]
        print(f"[WD] {start + 1}-{start + len(batch)} / {len(ids)}")
        try:
            bindings = run_sparql(build_query(batch))
        except Exception as e:
            print(f"[WD][UYARI] sorgu başarısız ({e}). Kalan oyuncular bu sefer eklenmedi; "
                  "scripti tekrar çalıştırırsan kaldığı yerden devam eder.")
            break
        for b in bindings:
            tm = val(b, "tm")
            rec = result.get(tm)
            if rec is None or not rec.get("qid"):
                rec = result[tm] = {"qid": None, "name": None, "sitelinks": 0, "dob": None,
                                    "height": None, "pob": None, "lat": None, "lon": None,
                                    "country": None}
            rec["qid"] = val(b, "item").rsplit("/", 1)[-1]
            rec["name"] = rec["name"] or val(b, "itemLabel")
            rec["sitelinks"] = int(val(b, "sl") or 0)
            rec["dob"] = rec["dob"] or val(b, "dob")
            rec["height"] = rec["height"] or val(b, "height")
            rec["country"] = rec["country"] or val(b, "countryLabel")
            coord = val(b, "coord")
            if coord and rec["lat"] is None:
                m = re.match(r"Point\(([-\d.eE+]+) ([-\d.eE+]+)\)", coord)
                if m:
                    rec["lon"], rec["lat"] = float(m.group(1)), float(m.group(2))
                    rec["pob"] = val(b, "pobLabel")
        for t in batch:                       # bulunamayanları işaretle
            result.setdefault(t, {"qid": None, "name": None, "sitelinks": 0, "dob": None,
                                  "height": None, "pob": None, "lat": None, "lon": None, "country": None})
        cache_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        time.sleep(2)  # Wikidata'ya nazik ol
    return result


# --------------------------------------------------------------------------- #
# 3) Birleştirme
# --------------------------------------------------------------------------- #
def norm_height(h):
    if h is None:
        return None
    try:
        h = float(h)
    except ValueError:
        return None
    if h < 3:          # metre cinsinden yazılmışsa
        h *= 100
    return int(round(h)) if 120 <= h <= 230 else None


def year_of(s):
    if not s:
        return None
    m = re.match(r"(-?\d{4})", s)
    return int(m.group(1)) if m else None


def peak_value_m(eur):
    v = num(eur)
    if v is None or v <= 0:
        return None
    m = round(v / 1_000_000, 1)
    return int(m) if m == int(m) else m


QUESTION_FIELDS = ["intlGoals", "intlCaps", "heightCm", "birthYear", "peakMarketValueM", "birthPlace"]


def has_foreign_script(name):
    """Latin dışı harf var mı? (Wikidata'da bazen Yunan 'Α' gibi benzer harfler karışıyor: 'Αrda Güler')"""
    import unicodedata
    for ch in name:
        if ch.isalpha():
            try:
                if not unicodedata.name(ch).startswith("LATIN"):
                    return True
            except ValueError:
                return True
    return False


def merge(tm_df, wd, min_sitelinks, min_fields, current_season=CURRENT_SEASON, overrides=None, wd_teams=None,
          tr_min_sitelinks=0, extra_min_fields=1):
    overrides = overrides or {}
    wd_teams = wd_teams or {}
    players = []
    skipped_fame = 0
    for _, row in tm_df.iterrows():
        tm_id = str(num(row.get("player_id")))
        w = wd.get(tm_id)
        if w and not w.get("qid"):          # Wikidata'da bulunamadı işaretli kayıt
            w = None

        is_core = bool(row.get("_core", True))
        is_tr = bool(row.get("_tr", False))
        guess_only = not is_core               # sadece Türk ek listesinden gelenler hedef olmaz

        # Wikidata'da kaydı varsa ama çok az dilde sayfası varsa "noname" say, atla
        # (Türk oyuncularda eşik daha düşük; geçenler sadece tahmin edilebilir, hedef olmaz)
        if w and w["sitelinks"] < min_sitelinks:
            if is_tr and w["sitelinks"] >= tr_min_sitelinks:
                guess_only = True
            else:
                skipped_fame += 1
                continue

        name = (w or {}).get("name") or row.get("name")
        if not isinstance(name, str) or re.fullmatch(r"Q\d+", name or "") or has_foreign_script(name):
            name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        birth_place = None
        if w and w["lat"] is not None and w["pob"] and not re.fullmatch(r"Q\d+", w["pob"]):
            birth_place = {"name": w["pob"], "lat": round(w["lat"], 4), "lon": round(w["lon"], 4)}

        country = row.get("country_of_citizenship")
        if not isinstance(country, str) or not country:
            country = (w or {}).get("country")

        team = row.get("current_club_name")
        team = team if isinstance(team, str) and team else None
        # TAKIM ÖNCELİĞİ:
        #  1) team_overrides.json (elle düzeltme)
        #  2) Transfermarkt'a göre 2+ sezondur hiç oynamamış => emekli / kulüpsüz
        #  3) Wikidata'daki güncel (bitiş tarihsiz) kulüp
        #  4) Transfermarkt'ın current_club_name'i (son sezonu güncelse), değilse emekli / kulüpsüz
        last_season = num(row.get("last_season"))
        inactive_long = last_season is not None and last_season < current_season - 1
        inactive_any = last_season is not None and last_season < current_season
        wd_team = wd_teams.get((w or {}).get("qid")) if w else None
        if inactive_long:
            team = RETIRED_LABEL if team else None
        elif wd_team:
            team = wd_team
        elif team and inactive_any:
            team = RETIRED_LABEL
        team = overrides.get(name.strip(), team)

        birth_year = year_of((w or {}).get("dob")) or year_of(str(row.get("date_of_birth") or ""))
        height = num(row.get("height_in_cm")) or norm_height((w or {}).get("height"))

        p = {
            "id": (w or {}).get("qid") or f"tm{tm_id}",
            "name": name.strip(),
            "country": country,
            "birthPlace": birth_place,
            "birthYear": birth_year,
            "heightCm": height,
            "team": team,
            "intlCaps": num(row.get("international_caps")),
            "intlGoals": num(row.get("international_goals")),
            "peakMarketValueM": peak_value_m(row.get("highest_market_value_in_eur")),
            "_sl": (w or {}).get("sitelinks", 0),
        }
        if guess_only:
            p["guessOnly"] = True
        filled = sum(1 for k in QUESTION_FIELDS if p[k] is not None)
        # Sadece tahmin edilebilir (guessOnly) oyuncularda en az 1 dolu alan yeter
        if filled >= (extra_min_fields if guess_only else min_fields):
            players.append(p)

    print(f"[MERGE] Wikipedia dil sayısı düşük diye elenen: {skipped_fame}")

    # Aynı isimli oyuncuları ayırt et (otomatik tamamlamada karışmasın)
    seen = {}
    for p in players:
        seen.setdefault(p["name"], []).append(p)
    for name, group in seen.items():
        if len(group) > 1:
            for p in group:
                p["name"] = f"{name} ({p['birthYear']})" if p["birthYear"] else f"{name} ({p['id']})"

    players.sort(key=lambda p: -p["_sl"])
    for p in players:
        del p["_sl"]
    return players


def report(players):
    print(f"\n[ÖZET] toplam oyuncu: {len(players)}")
    for k in QUESTION_FIELDS:
        n = sum(1 for p in players if p[k] is not None)
        print(f"   {k:18s} dolu: {n:5d}  ({100 * n / max(1, len(players)):.0f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tm-csv", help="Elindeki players.csv yolu (verilmezse otomatik indirir)")
    ap.add_argument("--min-value", type=float, default=20, help="Zirve piyasa değeri eşiği (milyon €)")
    ap.add_argument("--min-caps", type=int, default=40, help="Alternatif: milli maç eşiği")
    ap.add_argument("--min-sitelinks", type=int, default=12, help="Wikipedia dil sayısı alt sınırı")
    ap.add_argument("--min-fields", type=int, default=4, help="Dolu olması gereken soru alanı sayısı")
    ap.add_argument("--cache", default="wikidata_cache.json")
    ap.add_argument("--refresh", action="store_true", help="Wikidata'yı yeniden çek")
    ap.add_argument("--out", default="players.json")
    ap.add_argument("--tr-min-value", type=float, default=2, help="Türk oyuncular için zirve piyasa değeri eşiği (milyon €)")
    ap.add_argument("--tr-min-caps", type=int, default=5, help="Türk oyuncular için milli maç eşiği")
    ap.add_argument("--tr-min-sitelinks", type=int, default=0, help="Türk oyuncular için Wikipedia dil sayısı alt sınırı")
    ap.add_argument("--no-tr-extra", action="store_true", help="Türk oyuncu ek listesini kapat")
    ap.add_argument("--clubs", default=",".join(map(str, BIG_CLUB_IDS)),
                    help="Güncel kadrosu komple eklenecek Transfermarkt kulüp ID'leri (varsayılan: 4 büyükler). Kapatmak için --clubs ''")
    ap.add_argument("--extra-min-fields", type=int, default=1,
                    help="Sadece-tahmin (guessOnly) oyuncular için en az dolu alan sayısı")
    ap.add_argument("--offline", action="store_true", help="Wikidata'ya hiç bağlanma, sadece önbellekleri kullan")
    ap.add_argument("--refresh-teams", action="store_true", help="Wikidata'daki güncel takımları yeniden çek")
    ap.add_argument("--no-wd-teams", action="store_true", help="Takımı Wikidata'dan çekme, sadece Transfermarkt kullan")
    ap.add_argument("--current-season", type=int, default=CURRENT_SEASON,
                    help="Güncel sezonun başlangıç yılı (2025 = 2025/26). Bundan eski last_season => emekli/kulüpsüz")
    a = ap.parse_args()

    tm = load_transfermarkt(a.tm_csv)
    cand = pick_candidates(tm, a.min_value, a.min_caps,
                           None if a.no_tr_extra else a.tr_min_value, None if a.no_tr_extra else a.tr_min_caps,
                           [int(x) for x in a.clubs.split(",") if x.strip()], a.current_season)
    wd = fetch_wikidata(cand["player_id"].dropna().astype(int).tolist(), a.cache, a.refresh, a.offline)
    cand_ids = {str(i) for i in cand["player_id"].dropna().astype(int)}
    print(f"[WD] Wikidata'da eşleşen: {sum(1 for k, r in wd.items() if k in cand_ids and r.get('qid'))} / {len(cand)}")

    wd_teams = {}
    if not a.no_wd_teams:
        qids = [r["qid"] for r in wd.values() if r.get("qid")]
        wd_teams = fetch_current_teams(qids, refresh=a.refresh_teams) if not a.offline else _load(TEAMS_CACHE, False)
    players = merge(cand, wd, a.min_sitelinks, a.min_fields, a.current_season, load_team_overrides(), wd_teams,
                    a.tr_min_sitelinks, a.extra_min_fields)
    report(players)
    Path(a.out).write_text(json.dumps(players, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] {a.out} yazıldı. Oyun klasörüne index.html'in yanına koy.")


if __name__ == "__main__":
    main()