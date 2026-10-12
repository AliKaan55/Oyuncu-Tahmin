# ⚽ Futbolcu Düellosu

İki kişilik, tarayıcıda oynanan bir futbol bilgi oyunu. Ekranda tek bir **hedef futbolcu** vardır. 5 tur boyunca bu futbolcunun 5 farklı özelliği sorulur (kariyerinde kaç takımda oynadı, milli takımda kaç gol attı, boyu kaç cm gibi). Her turda iki oyuncu sırayla, o özellikte hedefe **en yakın değere** sahip olduğunu düşündükleri başka bir futbolcuyu yazar. Hedefe daha çok yaklaşan turu kazanır.

Oyunun tamamı tek bir `index.html` dosyasıdır. React, Vite veya sunucu gerekmez.

## Özellikler

- **2 oyunculu düello:** 5 tur, sırayla tahmin. 1. oyuncunun tahmini, 2. oyuncu da tahmin edene kadar gizli kalır.
- **Lig modları:** Tüm Ligler, Trendyol Süper Lig, La Liga, Premier Lig. Lig seçilirse hedef futbolcu o ligdeki kulüplerden birinde oynayan biri olur.
- **Zorluk:** Kolay, Normal, Zor. Zorluk, hedef futbolcunun ne kadar tanındığına göre belirlenir.
- **Tahmin süresi:** 30 sn, 1 dk veya sınırsız.
- **Joker:** Her oyuncunun oyun boyunca 1 ipucu jokeri vardır. Kendi sırasında kullanılırsa o turun gerçek değerini içeren bir aralığı (doğum yeri sorusunda baş harfi) gösterir. Rakip görmez.
- **Oyuncu fotoğrafları:** Hedef futbolcunun fotoğrafı gösterilir. Fotoğraf yüklenemezse sırayla yedek kaynaklar denenir, hiçbiri çalışmazsa baş harf gösterilir.
- Ses efektleri (sağ üstteki düğmeyle kapatılabilir).

## Nasıl oynanır?

1. Oyuncu adlarını gir, **lig**, **zorluk** ve **tahmin süresini** seç, **Düelloyu Başlat**'a bas.
2. Ekranın ortasında hedef futbolcu ve o turun sorusu görünür.
3. Sırası gelen oyuncu "Hedefe en yakın futbolcu…" kutusuna bir oyuncu adı yazar ve tahmini kilitler.
4. Her iki oyuncu da tahmin edince hedefin gerçek değeri açılır. Hedefe daha yakın olan 1 puan alır (eşitlikte ikisi de 1 puan alır).
5. 5 tur sonunda toplam puanı yüksek olan düelloyu kazanır.

Kurallar:
- Hedef futbolcunun kendisi seçilemez.
- İki oyuncu aynı turda aynı futbolcuyu seçemez.
- Süre dolarsa o turda tahmin yapılmamış sayılır.

### Sorulan özellikler

Her oyunda bu listeden 5 tanesi rastgele seçilir:

| Özellik | Birim |
|---|---|
| Milli takımda attığı gol | gol |
| Milli takımda maç sayısı | maç |
| Boy | cm |
| Doğum yılı | yıl |
| Kariyer zirvesindeki piyasa değeri | milyon € |
| Kariyerinde toplam lig golü | gol |
| Kariyerde oynadığı takım sayısı | takım |
| Kazandığı kupa sayısı | kupa |
| Doğum yeri | km mesafe |

## Hedef futbolcu nasıl seçilir?

- **Tüm Ligler modu:** Dünya çapında tanınan (Wikipedia dil sayısı yüksek) oyuncular, zirve piyasa değeri en az 25 M€ olanlar ve Süper Lig oyuncuları hedef olabilir. Zorluk, Wikipedia dil sayısına (sitelinks) göre belirlenir: Kolay 60+, Normal 30–59, Zor 0–29.
- **Lig modları (Süper Lig, La Liga, Premier Lig):** Hedef, seçilen ligde oynayan oyunculardan seçilir. Zorluk o ligin kendi içinde, tanınırlık sıralamasına göre belirlenir: Kolay = ligin en tanınan %30'u, Normal = orta %40, Zor = en az tanınan %30.
- `"guessOnly": true` işaretli oyuncular (Türk oyuncular ve 4 büyüklerin kadroları gibi ek listeler) tahmin listesinde çıkar ama hedef olarak seçilmez.
- Hedef oyuncunun en az 5 sorulabilir özelliği (verisi dolu alanı) olmalıdır.

## Proje yapısı

| Dosya | Açıklama |
|---|---|
| `index.html` | Oyunun tamamı (arayüz, kurallar, mantık) |
| `players.json` | Oyuncu veritabanı. Oyun bu dosyayı okur |
| `build_players.py` | `players.json`'u üretir (Transfermarkt + Wikidata) |
| `add_league.py` | `players.json`'daki her oyuncuya `league` alanını ekler (lig modları için gerekli) |
| `players.csv` | Transfermarkt/Kaggle oyuncu verisi (kaynak) |
| `team_report.csv` | Takım belirleme raporu (hangi oyuncunun takımı nereden geldi) |
| `*_cache.json` | Wikidata ve Transfermarkt önbellekleri (tekrar indirmeyi önler) |
| `vercel.json`, `.vercelignore` | Vercel yayınlama ayarları |
| `tools/requirements.txt` | Python bağımlılıkları |

`players.json` içindeki bir oyuncu kaydı örneği:

```json
{
  "id": "Q615",
  "name": "Lionel Messi",
  "country": "Argentina",
  "birthPlace": { "name": "Rosario", "lat": -32.9575, "lon": -60.6394 },
  "birthYear": 1987,
  "heightCm": 170,
  "team": "Club Internacional de Fútbol Miami",
  "intlCaps": 204,
  "intlGoals": 125,
  "peakMarketValueM": 180,
  "leagueGoals": 575,
  "careerTeams": 5,
  "trophies": 46,
  "sitelinks": 225,
  "superLig": false,
  "league": null,
  "image": "https://img.a.transfermarkt.technology/portrait/header/28003-....jpg"
}
```

`league` alanı Transfermarkt lig kodlarını kullanır: `TR1` (Süper Lig), `ES1` (La Liga), `GB1` (Premier Lig). Takımı olmayan veya emekli oyuncularda `null` olur.

## Yerelde çalıştırma

```bash
python -m http.server 8000
```

Sonra tarayıcıda http://localhost:8000 adresini aç.

> `index.html` dosyasına çift tıklayarak açarsan tarayıcı `players.json`'u okuyamaz, oyun yerleşik test verisine düşer ve ekranda uyarı çıkar. Mutlaka bir yerel sunucu kullan.

## Oyuncu verisini üretme / güncelleme

```bash
pip install -r tools/requirements.txt

# build_players.py içindeki USER_AGENT satırına kendi mail adresini yaz (Wikimedia kuralı)
python build_players.py --tm-csv players.csv

# Lig bilgisini ekle (lig modları için gerekli, build'den sonra her seferinde çalıştır)
python add_league.py
```

Kullanışlı seçenekler:

| Seçenek | Ne yapar |
|---|---|
| `--min-value 50 --min-caps 60` | Daha seçici (daha ünlü) liste |
| `--min-value 10 --min-sitelinks 8` | Daha geniş liste |
| `--refresh-teams` | Güncel transferler için takımları Wikidata'dan yeniden çeker |
| `--offline` | Wikidata'ya bağlanmadan çalışır |
| `--tr-min-value 2 --tr-min-caps 5` | Türk oyuncular için eşikleri ayarlar (`--no-tr-extra` ile kapatılır) |
| `--clubs 36,114,141,449` | Aktif kadrosu listeye eklenecek kulüpler (Transfermarkt ID'leri, `--clubs ''` ile kapatılır) |

Otomatik indirme çalışmazsa Kaggle'dan [davidcariboo/player-scores](https://www.kaggle.com/datasets/davidcariboo/player-scores) veri setini indirip `players.csv` dosyasını proje klasörüne koy.

### Takım önceliği

`team_overrides.json` > (2+ sezondur oynamayan = "Emekli / kulüpsüz") > Wikidata güncel kulüp (P54, bitiş tarihsiz) > Transfermarkt. Wikidata'ya erişilemezse Transfermarkt takımına düşülür.

### Ek oyuncu listeleri

- **Türk oyuncular:** Ünlü liste eşiği Süper Lig oyuncularını dışarıda bıraktığı için Türk vatandaşlar ayrı, düşük bir eşikle eklenir. Bu oyuncular `guessOnly` olur.
- **4 büyükler:** Fenerbahçe, Beşiktaş, Galatasaray ve Trabzonspor'un aktif kadrosundaki herkes listeye alınır. Bunlar da `guessOnly` olur.

## Yayınlama (Vercel)

Proje statik bir sitedir. `vercel.json` build komutu gerektirmeyecek şekilde ayarlıdır.

1. Projeyi GitHub'a gönder (`git add . && git commit -m "..." && git push`).
2. Vercel'de repoyu bağla. Production branch `main` olmalıdır.
3. Her push'ta Vercel otomatik yeni sürüm yayınlar.

`.vercelignore` Python dosyalarını, CSV'leri ve önbellekleri yayından hariç tutar. Siteye yalnızca `index.html` ve `players.json` gerekir. Netlify veya GitHub Pages'e de bu iki dosya yüklenerek yayınlanabilir.

Yayından sonra eski sürüm görünüyorsa tarayıcıda `Ctrl+Shift+R` ile sert yenileme yap. `players.json` büyük bir dosya olduğu için tarayıcı önbelleğe almış olabilir.

## Fotoğraf yedek zinciri

Transfermarkt'ın resim sunucusu başka sitelerden gelen isteklerde görseli bazen engeller. Bu yüzden fotoğraf sırayla şu kaynaklardan denenir:

1. Transfermarkt (doğrudan)
2. Aynı fotoğraf `wsrv.nl` proxy'si üzerinden
3. Oyuncunun Wikidata / Wikimedia Commons fotoğrafı
4. Hiçbiri çalışmazsa oyuncunun baş harfi

## Kaynak / lisans

- Transfermarkt veri seti: CC0 ([kaggle.com/datasets/davidcariboo/player-scores](https://www.kaggle.com/datasets/davidcariboo/player-scores))
- Wikidata: CC0
- Oyuncu fotoğrafları Transfermarkt ve Wikimedia Commons'a aittir, proje bunları barındırmaz, yalnızca bağlantı üzerinden gösterir.