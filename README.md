# Futbolcu Düellosu

## Dosyalar
- `index.html`  : oyunun tamamı (React/Vite gerekmez)
- `build_players.py` : `players.json` üretir (Transfermarkt/Kaggle + Wikidata)
- `players.json` : script çalışınca oluşur, `index.html`'in yanına konur

## Veri üretme
```
pip install -r requirements.txt
# build_players.py içindeki USER_AGENT satırına kendi mailini yaz
python build_players.py
```
Daha seçici (daha ünlü) liste için: `python build_players.py --min-value 50 --min-caps 60`
Daha geniş liste için:              `python build_players.py --min-value 10 --min-sitelinks 8`

Otomatik indirme çalışmazsa Kaggle'dan `davidcariboo/player-scores` indir,
`players.csv`'yi bu klasöre koy: `python build_players.py --tm-csv players.csv`

## Yerelde çalıştırma
`python -m http.server 8000` -> http://localhost:8000
(Dosyaya çift tıklarsan players.json okunmaz, test verisine düşer ve ekranda uyarı çıkar.)

## Yayınlama
`index.html` + `players.json` dosyalarını Netlify / GitHub Pages / Vercel'e yükle.

## Kaynak / lisans
Transfermarkt veri seti: CC0 (kaggle.com/datasets/davidcariboo/player-scores).
Wikidata: CC0.

## Güncel takımlar
Takım önceliği: `team_overrides.json` > (2+ sezondur oynamayan = "Emekli / kulüpsüz") > Wikidata güncel kulüp (P54, bitiş tarihsiz) > Transfermarkt.
- `python build_players.py --tm-csv players.csv` -> takımları Wikidata'dan çeker, `wikidata_teams_cache.json`'a kaydeder.
- Güncel transferler için: `python build_players.py --tm-csv players.csv --refresh-teams`
- Wikidata'ya erişilemezse Transfermarkt takımına düşer.

## Türk oyuncular (ek liste)
Ünlü liste eşiği (zirve değer >= 20M€ veya >= 40 milli maç) Süper Lig oyuncularını dışarıda bırakıyordu.
Türk vatandaşlar için ayrı, düşük eşik var: `--tr-min-value 2 --tr-min-caps 5` (kapatmak için `--no-tr-extra`).
Bu oyuncular `"guessOnly": true` ile işaretlenir: tahmin listesinde çıkarlar ama hedef futbolcu olarak seçilmezler.
Wikidata'da önbellekte olmayan oyuncular otomatik çekilir (artımlı). Wikidata'ya bağlanmadan çalıştırmak için `--offline`.

## 4 büyükler
Fenerbahçe, Beşiktaş, Galatasaray ve Trabzonspor'un aktif kadrosundaki herkes listeye alınır (vatandaşlık/değer fark etmez).
Varsayılan kulüpler `--clubs 36,114,141,449` (Transfermarkt ID'leri). Başka kulüp eklemek için ID'yi ekle, kapatmak için `--clubs ''`.
Ek oyuncular `guessOnly` olur: tahmin listesinde çıkarlar ama hedef olmazlar.