# İSPARK Doluluk Logger

İstanbul İSPARK otoparklarının doluluk verisini her saat başı
`https://api.ibb.gov.tr/ispark/Park` üzerinden çekip `data/` altına CSV
olarak biriktiren, GitHub Actions ile bilgisayar kapalıyken de çalışan bir
sistem. 4-6 haftalık veri sonrası `analyze.py` ile ilçe/otopark bazlı
saatlik doluluk eğrileri çıkarılır.

## 1) GitHub'a private repo olarak push etme

```bash
cd isparklogger
git init
git add .
git commit -m "init: ispark logger"

# GitHub CLI ile (önerilen):
gh repo create isparklogger --private --source=. --remote=origin
git push -u origin main

# ya da GitHub web arayüzünden boş bir private repo oluşturup:
git remote add origin git@github.com:<kullanici-adi>/isparklogger.git
git branch -M main
git push -u origin main
```

Ekstra bir secret/ayar gerekmiyor — workflow, repoya varsayılan olarak
tanımlı `GITHUB_TOKEN`'ı kullanarak commit/push yapıyor. Repo
ayarlarında **Settings → Actions → General → Workflow permissions**
altında "Read and write permissions" seçili olduğundan emin olun (yeni
repolarda genelde varsayılan budur, değilse elle açın).

## 2) Actions'ın çalıştığını doğrulama

- GitHub'da repo → **Actions** sekmesine gidin.
- İlk çalıştırmayı beklemeden test etmek için "Log İSPARK occupancy"
  workflow'unu seçip **Run workflow** (workflow_dispatch) ile manuel
  tetikleyin.
- Çalışma bitince yeşil tik görmelisiniz; loglarda `wrote N rows to ...`
  satırını ve ardından bir commit/push adımını görürsünüz.
- Repoda `data/YYYY-MM/YYYY-MM-DD.csv` dosyasının güncellendiğini ve
  commit geçmişinde `ispark-bot` tarafından atılan `log: <tarih saat>`
  commit'lerini kontrol edin.
- Saat başı cron (`0 * * * *`) otomatik devreye girer; GitHub Actions
  cron'ları birkaç dakika gecikebilir, bu normaldir.

## 3) analyze.py'yi çalıştırma

En az birkaç günlük veri birikince (ideal olarak 4-6 hafta) yerelde:

```bash
git pull   # en güncel data/ klasörünü çek
python3 analyze.py
```

Çıktılar:
- `output/hourly_patterns.json` — ilçe → gün tipi (weekday/friday/
  saturday/sunday) → 24 saatlik dizi, 1-5 ölçeğine normalize edilmiş
  doluluk skorları. iOS uygulamasındaki `busyness_patterns.json`
  formatına yakın olacak şekilde tasarlandı.
- `output/summary.md` — en dolu 10 ilçe, en dolu 10 otopark ve veri
  kapsama özeti (toplam satır, gün sayısı, tarih aralığı).

Veri arttıkça daha fazla saat/gün-tipi hücresi anlamlı hale gelir; 3'ten
az gözlemi olan hücreler `null` bırakılır (uydurma veri yok).
Düzenli aralıklarla (ör. haftada bir) çalıştırıp `output/summary.md`
üzerinden kapsamı takip etmeniz önerilir.

## Tahmini veri boyutu

Yerel test çalıştırmasında tek bir saatlik fetch ~258 otopark satırı ve
~44 KB'lık bir CSV bloğu üretti. Buna göre kabaca:

- Saatlik: ~44 KB
- Günlük (24 fetch): ~1 MB
- Aylık (~30 gün): ~30-32 MB

6 haftalık bir toplama periyodu toplamda ~45-50 MB civarında veri
demek — GitHub repo limitleri açısından rahatlıkla yönetilebilir bir
boyut.
