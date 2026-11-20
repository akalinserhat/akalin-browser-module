# @akalin/browser_module

Akalin Hibrit Sanal Tarayıcı & AI Web Otomasyon Modülü.
`@akalin/module_core` (`IModuleDefinition` / `ModuleRegistry`) ve `@akalin/module_management` ile %100 uyumludur.

## Özellikler

- **Hibrit Yürütme Mimarisi**:
  - **Hızlı HTTP Modu**: JavaScript gerektirmeyen sayfaları milisaniyeler içinde okur ve [ref] etiketleriyle döner (sıfır ek RAM maliyeti).
  - **Docker Chromium Modu**: SPA / React / Vue sayfalarında veya tıklama (`click`), form doldurma (`type`), kaydırma (`scroll`) gibi gerçek etkileşimlerde Docker üzerindeki başsız Chromium'u kullanır.
- **Parametrik Proxy Entegrasyonu**: `akalin-proxy-service` üzerinden dinamik IP rotasyonu desteği.
- **Güvenli URL & SSRF Kalkanı**: Yerel ve iç ağ IP adreslerine yönelik istenmeyen istekleri engeller.
- **Modüler Yönetim Arayüzü**: Aktif oturumları, istek sayılarını ve telemetriyi izleme.

## Kurulum ve Docker Başlatma

```bash
# Docker konteynerini başlatma
docker compose up -d --build
```
