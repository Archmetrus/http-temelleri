# HTTP Temelleri — İstek Laboratuvarı

Tarayıcıdan yerel bir kitap API’sine istek göndererek HTTP’yi öğren. Projede
CRUD, özel başlıklar, oturum çerezi, Bearer token, HTTPS/TLS, CORS, ETag önbelleği
ve HTTP durum kodları için deneyler bulunur. Python ve HTTPS sertifikası için
OpenSSL dışında Python paketi gerekmez.

## Başlatma

### HTTP modu

Terminalde:

```bash
cd ~/PROJE/http-temelleri
python3 server.py
```

Tarayıcıda <http://localhost:8000> adresini aç. Durdurmak için terminalde
`Ctrl+C` tuşlarına bas.

### HTTPS modu

HTTPS sunucusunu çalıştır:

```bash
cd ~/PROJE/http-temelleri
python3 server.py --https
```

İlk çalıştırmada OpenSSL `certs/` klasörüne `localhost` için kendinden imzalı
sertifika üretir. Tarayıcıda <https://localhost:8443> adresini aç. Tarayıcı
güvenlik uyarısı gösterebilir; sertifika yalnızca bu yerel eğitim sunucusu
içindir, internette kullanılmamalıdır. Uyarıyı geçmek yerel sertifikayı
güvenilir hale getirmez. `certs/` git’e eklenmez.

HTTPS çerezde `Secure` bayrağını kullanır. Bu nedenle çerez/oturum deneyini
HTTPS modunda yapmak daha doğrudur. HTTP modu temel kavramları denemek içindir.

## Laboratuvar kullanımı

1. Yöntem listesinden GET, POST, PUT, PATCH veya DELETE seç.
2. Adres alanına `/api/books` gibi bir yol yaz. İstersen sorgu parametresi ekle.
3. POST, PUT veya PATCH için JSON gövdesini düzenle.
4. Özel istek başlığı alanına örneğin `X-Student: Ada` yazabilirsin.
5. İsteği gönder. Sonuç alanında istek özeti, durum kodu, geçen süre, yanıt
   başlıkları ve yanıt gövdesi görünür.

## Kitap API’si

| Amaç | Yöntem ve adres | Beklenen sonuç |
| --- | --- | --- |
| Kitapları listele | `GET /api/books` | `200`, kitap listesi |
| Tek kitabı oku | `GET /api/books/1` | `200`, kitap bilgisi |
| Ara, sayfala ve sırala | `GET /api/books?q=a&page=1&limit=2&sort=title&order=asc` | Filtrelenmiş liste ve sayfalama bilgisi |
| Yeni kitap ekle | `POST /api/books` | `201`, oluşturulan kitap |
| Kitabı tamamen güncelle | `PUT /api/books/1` | `200`, başlık ve yazarın ikisi de gönderilmeli |
| Kitabın bir alanını güncelle | `PATCH /api/books/1` | `200`, sadece gönderilen alan değişir |
| Kitabı sil | `DELETE /api/books/1` | `200`, silme sonucu |
| Sunucuyu kontrol et | `GET /api/health` | `200`, sağlık bilgisi |
| İstek başlığını oku | `GET /api/whoami` | `X-Student` başlığını JSON’da döndürür |

POST ve PUT için gövde:

```json
{
  "title": "Yeni Kitap",
  "author": "Öğrenci"
}
```

PATCH örneği: `{"title":"Yeni başlık"}`. Sıralamada `sort` değeri `id`,
`title` veya `author`; `order` değeri `asc` veya `desc` olabilir. `page` en az
1, `limit` 1–50 aralığında olmalı.

## Giriş, çerez ve Bearer token

Arayüzdeki giriş kartında iki deneme hesabından birini kullan:

| Kullanıcı adı | Parola | Yetki |
| --- | --- | --- |
| `student` | `http101` | Profil erişimi; yönetici alanında `403` |
| `teacher` | `teach101` | Profil ve öğretmen alanına erişim |

**Giriş yap** düğmesi `POST /api/login` isteği gönderir. Sunucu `HttpOnly`
oturum çerezi ayarlar ve yanıtta örnek bir Bearer token döndürür. Ardından:

- **Çerezle profili getir** düğmesi `/api/profile` isteğine çerezi tarayıcıyla
  otomatik ekler. JavaScript HttpOnly çerezin içeriğini okuyamaz.
- **Bearer token ile profili getir** token’ı `Authorization: Bearer …`
  başlığında gönderir. Bu demoda token yalnızca sayfa belleğinde tutulur.
- **Öğretmen alanını dene** student oturumunda `403`, oturumsuzken `401` verir.
- **Çıkış yap** oturumu ve o oturuma bağlı token’ları geçersiz kılar.

Demo kullanıcıları ve oturumlar yalnızca öğrenme içindir. Parolalar sabit,
oturumlar bellektedir ve sunucu yeniden başlayınca silinir. Gerçek uygulamada
bu örnekleri üretim kimlik doğrulaması gibi kullanma.

## HTTPS ve TLS

HTTP modu: `python3 server.py`

HTTPS modu: `python3 server.py --https` → <https://localhost:8443>

HTTPS, HTTP iletişimini TLS ile şifreler ve sunucu sertifikasını doğrulamaya
çalışır. Bu projedeki sertifika yerel ve kendinden imzalıdır; tarayıcı uyarısı
beklenen bir sonuçtur. Gerçek siteler güvenilir bir sertifika sağlayıcısından
sertifika kullanmalıdır.

## CORS ve preflight

CORS’u göstermek için API sunucusu açık kalsın. İkinci terminalde aynı çalışma
moduna göre ikinci komutu çalıştır:

```bash
# HTTP API çalışıyorsa:
python3 server.py --port 8001

# HTTPS API çalışıyorsa:
python3 server.py --port 8444 --https
```

İkinci porttaki <http://localhost:8001/cors-client> veya
<https://localhost:8444/cors-client> sayfasını aç. HTTPS sertifikası uyarısını
bu portta da geçmen gerekebilir. Deney sayfasındaki:

- **İzin verilen CORS isteği** API’ye özel `X-Demo-Header` gönderir. Tarayıcı
  önce `OPTIONS` preflight yapar; sunucu izin verilen ikinci localhost origin’ine
  erişim başlıklarıyla yanıt verir.
- **CORS izni olmayan isteği dene** sunucuya ulaşır ama API yanıtında CORS izni
  yoktur. Tarayıcı yanıtı sayfa JavaScript’ine göstermez.

İki port farklı origin sayılır. CORS sunucunun isteği almasını engelleyen bir
kimlik doğrulama sistemi değildir; tarayıcının yanıtı sayfaya açıp açmayacağını
kontrol eder. Network sekmesindeki `OPTIONS` ve asıl isteği karşılaştır.

## ETag ile koşullu istek ve önbellek

1. Laboratuvarda GET `/api/cache-demo` gönder.
2. Yanıt başlıklarındaki `ETag` değerini kopyala (tırnaklar dahil).
3. Özel başlık alanına `If-None-Match: "ETAG_DEGERI"` yaz; tırnak içini
   kopyaladığın gerçek ETag ile değiştir.
4. Aynı GET isteğini yeniden gönder. Değer eşleşirse `304 Not Modified` ve boş
   gövde gelir. Böylece istemci elindeki içeriği tekrar kullanabilir.

Kitap verisi değişirse ETag de değişir ve sunucu güncel içeriği `200` ile verir.

## Durum kodu deneyleri

Laboratuvarda GET adresini `/api/status-demo?code=401` yap. `code` değerini
`403`, `405`, `409`, `429` veya `500` ile değiştir. Bu endpoint seçilen kodun
anlamını öğretmek için kontrollü bir örnek yanıt verir; gerçek bir sunucu hatası
veya rate limit oluşturmaz.

- `401`: kimlik doğrulaması gerekli.
- `403`: kimlik doğrulandı, izin yok.
- `405`: yöntem desteklenmiyor; `Allow` başlığı izin verilen yöntemi gösterir.
- `409`: mevcut kaynakla çakışma.
- `429`: çok fazla istek; `Retry-After` bekleme süresini bildirir.
- `500`: sunucuda hata oluştu.

Gerçek akışlarda `/api/profile` oturumsuzken `401`, student hesabıyla
`/api/admin` isteği `403` döndürür.

## Tarayıcı geliştirici araçlarıyla hata ayıklama

1. Windows/Linux’ta `F12`, Mac’te `⌘⌥I` ile Geliştirici Araçları’nı aç.
2. **Network** sekmesini seç ve laboratuvarda bir istek gönder.
3. İstek satırını seç. **Headers** içinde Request URL, Request Method, Status
   Code, Request Headers ve Response Headers alanlarını incele.
4. **Payload** gönderilen gövdeyi, **Response** sunucu yanıtını gösterir.
5. CORS denemesinde `OPTIONS` preflight satırını ve Console’daki CORS açıklamasını
   bul.

## Terimler ve özet

HTTP alışverişi istemcinin **request (istek)** göndermesi ve sunucunun
**response (yanıt)** döndürmesiyle gerçekleşir. URL’de endpoint/path kaynak
adresidir; query parametreleri arama veya sayfalama gibi değerleri taşır.
**Header (başlık)** ek bilgi, **body (gövde)** taşınan veridir. `Content-Type`
içerik biçimini, `ETag` içeriğin sürümünü, `If-None-Match` koşullu isteği,
`Cache-Control` önbellek davranışını, `Cookie` ve `Authorization` kimlik
bilgilerini, CORS başlıkları tarayıcı erişim politikasını anlatır.

Veriler ve oturumlar bellekte saklanır; sunucu yeniden başlayınca başlangıç
kitaplarına döner ve oturumlar kapanır. Sunucu sadece yerel öğrenme içindir.
