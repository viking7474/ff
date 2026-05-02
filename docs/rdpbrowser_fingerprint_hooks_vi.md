# Winfox RDP va Fingerprint Hook Native

Tai lieu nay giai thich cach nhom hook native tren `window` duoc xu ly khi dung `winfox.rdp`, va cach nen ap dung trong code Python.

## Van de can hieu dung

Danh sach hook nhu:

1. `window.setFontSpacingSeed(seed)`
2. `window.setAudioFingerprintSeed(seed)`
3. `window.setCanvasSeed(seed)`
4. `window.setFontList(fontList)`
5. `window.setNavigatorPlatform(platform)`
6. `window.setNavigatorOscpu(oscpu)`
7. `window.setNavigatorHardwareConcurrency(cores)`
8. `window.setNavigatorUserAgent(ua)`
9. `window.setScreenDimensions(width, height)`
10. `window.setScreenColorDepth(colorDepth)`
11. `window.setSpeechVoices(voices)`
12. `window.setTimezone(timezone)`
13. `window.setWebGLVendor(vendor)`
14. `window.setWebGLRenderer(renderer)`
15. `window.setWebRTCIPv4(ipv4)`
16. `window.setWebRTCIPv6(ipv6)`

khong phai la "polyfill JavaScript" thong thuong.

Day la cac hook native/WebIDL duoc browser patch san. Nghia la JavaScript tren page chi dang goi vao mot API da duoc noi san ben duoi Firefox/C++.

Vi vay, co 2 cau hoi khac nhau:

1. lam sao de du lieu fingerprint duoc dua vao browser som va on dinh
2. neu can, lam sao goi truc tiep cac hook `window.set...()` tu Python

## Playwright thuong lam gi

Voi Playwright, cach hay gap la dung:

1. `browserContext.addInitScript(...)`
2. `page.addInitScript(...)`

de dam bao doan JavaScript chay truoc script cua website tren moi document moi.

## Winfox RDP hien tai xu ly the nao

Voi `winfox.rdp`, co che chinh hien tai khong dua vao `addInitScript`.

Thay vao do, `RDPBrowser` dua fingerprint vao browser ngay tu luc launch.

Trong code hien tai:

1. `RDPBrowser(..., fingerprint=..., timezone=...)`
2. `browser.start()` tao `runtime_config`
3. `runtime_config` duoc JSON-encode va cat thanh cac bien moi truong `CAMOU_CONFIG_1`, `CAMOU_CONFIG_2`, ...
4. browser binary doc config nay ngay khi khoi dong
5. cac patch native/WebIDL ben trong browser ap dung fingerprint o tang sau

Noi ngan gon:

1. Playwright path: thuong day script vao moi page/document
2. Winfox RDP path hien tai: day fingerprint vao browser session ngay luc launch

Day la huong dung hon cho cac fingerprint sau nhu Canvas, Audio, WebGL, Screen, Navigator, Font, WebRTC, vi no dat gia tri ngay o tang browser/runtime, khong phai cho den khi page JavaScript moi bat dau goi.

## Luu y quan trong ve WebRTC IPv4/IPv6

Voi code hien tai, `setWebRTCIPv4()` va `setWebRTCIPv6()` khong nen duoc xem la dang di theo cung mot duong voi `canvas:seed`, `audio:seed`, `timezone`, `webgl:*`, `navigator:*`, `screen:*`.

Cu the:

1. `RDPBrowser.start()` dua `fingerprint` vao `runtime_config`
2. nhung `winfox.rdp` hien tai chi co explicit post-launch override cho `timezone`
3. khong co co che explicit trong `winfox.rdp` hien tai de tu dong goi `window.setWebRTCIPv4(...)` hay `window.setWebRTCIPv6(...)` cho moi page
4. va theo tai lieu patch hien co, WebRTC IP duoc ghi ro la khong set mac dinh tu global config

Nghia la:

1. cac key nhu `webrtc:ipv4` / `webrtc:ipv6` khong nen duoc coi la da duoc `winfox.rdp` ap dung browser-wide mot cach dam bao
2. neu ban can spoof WebRTC IP bang hai hook nay, hien tai ban phai goi thu cong o page-level

Vi vay, trong `winfox.rdp` hien tai:

1. `fingerprint=` la path chinh cho Canvas, Audio, WebGL, Navigator, Screen, Font, timezone va cac global override cung loai
2. `setWebRTCIPv4()` / `setWebRTCIPv6()` nen xem la manual native hook path, khong phai launch-time guaranteed path

## Special case: timezone

`timezone` hien tai duoc xu ly theo 2 lop:

1. duoc dua vao `runtime_config` luc launch
2. sau khi RDP ket noi, `RDPBrowser._apply_overrides()` con goi them:

```js
window.setTimezone("...")
```

tren tab dau tien qua WebConsole actor.

Muc dich la dam bao timezone hook duoc kich hoat ro rang ca o runtime va o document dang song.

## Cach nen dung voi Winfox

### Cach khuyen dung

Neu ban muon fingerprint on dinh cho toan bo browser session, hay truyen vao `RDPBrowser` ngay tu luc tao browser.

```python
import asyncio

from winfox.rdp import RDPBrowser


async def main():
    fingerprint = {
        # Day la payload runtime dua vao browser luc launch.
        # Cac key cu the phai khop voi build/browser patch ma ban dang dung.
        "canvas:seed": 123456,
        "audio:seed": 654321,
        "webgl:vendor": "Intel Inc.",
        "webgl:renderer": "Intel Iris OpenGL Engine",
        "navigator:userAgent": "Mozilla/5.0 ...",
        "navigator:platform": "Win32",
        "navigator:oscpu": "Windows NT 10.0; Win64; x64",
        "navigator:hardwareConcurrency": 8,
        "screen:width": 1920,
        "screen:height": 1080,
        "screen:colorDepth": 24,
    }

    async with RDPBrowser(
        executable_path=r"C:\path\to\winfox.exe",
        fingerprint=fingerprint,
        timezone="Asia/Ho_Chi_Minh",
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")


asyncio.run(main())
```

### Vi sao day la cach nen dung

1. fingerprint duoc dua vao browser truoc khi workflow that su bat dau
2. tat ca page/tab moi trong cung browser session se di cung mot runtime config
3. khong can lap lai `window.set...()` tren tung page theo kieu thu cong
4. giam nguy co document dau tien load truoc khi hook kip chay

Ngoai le quan trong:

1. WebRTC IPv4/IPv6 hien tai khong nen dua vao nhom "duoc dam bao ap dung qua `fingerprint=`"
2. neu can set WebRTC IP bang native hook, hay dung page-level manual override o phan duoi

## Neu ban muon goi truc tiep cac hook `window.set...()`

`winfox.rdp` van cho phep ban goi JavaScript tren page. Nghia la ban co the goi truc tiep nhung hook nay tu Python.

Tuy nhien, day nen xem la low-level fallback hoac explicit override, khong nen la co che chinh cho browser-wide fingerprinting.

Day la path dac biet quan trong cho `setWebRTCIPv4()` va `setWebRTCIPv6()` trong code hien tai.

### Vi du helper cho 1 page

```python
import asyncio
import json

from winfox.rdp import RDPBrowser


async def apply_native_hooks(page, config: dict) -> None:
    script = f"""
    (() => {{
      const cfg = {json.dumps(config)};

      if (cfg.fontSpacingSeed != null && window.setFontSpacingSeed) {{
        window.setFontSpacingSeed(cfg.fontSpacingSeed);
      }}
      if (cfg.audioSeed != null && window.setAudioFingerprintSeed) {{
        window.setAudioFingerprintSeed(cfg.audioSeed);
      }}
      if (cfg.canvasSeed != null && window.setCanvasSeed) {{
        window.setCanvasSeed(cfg.canvasSeed);
      }}
      if (cfg.fontList && window.setFontList) {{
        window.setFontList(cfg.fontList);
      }}
      if (cfg.platform && window.setNavigatorPlatform) {{
        window.setNavigatorPlatform(cfg.platform);
      }}
      if (cfg.oscpu && window.setNavigatorOscpu) {{
        window.setNavigatorOscpu(cfg.oscpu);
      }}
      if (cfg.hardwareConcurrency != null && window.setNavigatorHardwareConcurrency) {{
        window.setNavigatorHardwareConcurrency(cfg.hardwareConcurrency);
      }}
      if (cfg.userAgent && window.setNavigatorUserAgent) {{
        window.setNavigatorUserAgent(cfg.userAgent);
      }}
      if (cfg.screenWidth != null && cfg.screenHeight != null && window.setScreenDimensions) {{
        window.setScreenDimensions(cfg.screenWidth, cfg.screenHeight);
      }}
      if (cfg.colorDepth != null && window.setScreenColorDepth) {{
        window.setScreenColorDepth(cfg.colorDepth);
      }}
      if (cfg.voices && window.setSpeechVoices) {{
        window.setSpeechVoices(cfg.voices);
      }}
      if (cfg.timezone && window.setTimezone) {{
        window.setTimezone(cfg.timezone);
      }}
      if (cfg.webglVendor && window.setWebGLVendor) {{
        window.setWebGLVendor(cfg.webglVendor);
      }}
      if (cfg.webglRenderer && window.setWebGLRenderer) {{
        window.setWebGLRenderer(cfg.webglRenderer);
      }}
      if (cfg.webrtcIPv4 && window.setWebRTCIPv4) {{
        window.setWebRTCIPv4(cfg.webrtcIPv4);
      }}
      if (cfg.webrtcIPv6 && window.setWebRTCIPv6) {{
        window.setWebRTCIPv6(cfg.webrtcIPv6);
      }}

      return true;
    }})()
    """
    await page.evaluate(script)


async def main():
    async with RDPBrowser(executable_path=r"C:\path\to\winfox.exe") as browser:
        page = await browser.new_page()

        # Page moi thuong bat dau o about:blank.
        # Neu can explicit override, co the goi hook tai day truoc khi vao target site.
        # Day la cach hien tai nen dung cho WebRTC IPv4/IPv6.
        await apply_native_hooks(page, {
            "canvasSeed": 123456,
            "audioSeed": 654321,
            "platform": "Win32",
            "oscpu": "Windows NT 10.0; Win64; x64",
            "hardwareConcurrency": 8,
            "userAgent": "Mozilla/5.0 ...",
            "screenWidth": 1920,
            "screenHeight": 1080,
            "colorDepth": 24,
            "timezone": "Asia/Ho_Chi_Minh",
            "webglVendor": "Intel Inc.",
            "webglRenderer": "Intel Iris OpenGL Engine",
            "webrtcIPv4": "203.0.113.10",
            "webrtcIPv6": "2001:db8::10",
        })

        await page.goto("https://example.com")
        await page.wait_for_load_state("load")


asyncio.run(main())
```

## Han che hien tai cua `winfox.rdp`

`winfox.rdp` hien da co browser-level helper:

1. `await browser.set_init_script_hooks(script)`
2. `await browser.set_init_script_hooks([script1, script2, ...])`

API nay luu hook o browser-level, apply cho cac page dang duoc browser theo doi, va tu dong apply cho cac page/popup moi khi `RDPBrowser` dung page object moi.

Tuy nhien, no van la abstraction o tang Python/RDP hien tai, khong phai co che native giong Playwright context engine. Vi vay voi popup dieu huong rat som, ban van nen xem day la best-effort init hook path, con `fingerprint=` van la path chinh cho nhom fingerprint global.

## Vi du dung `browser.set_init_script_hooks(...)`

```python
import asyncio

from winfox.rdp import RDPBrowser


async def main():
    async with RDPBrowser(executable_path=r"C:\path\to\winfox.exe") as browser:
        await browser.set_init_script_hooks("""
            if (window.setWebRTCIPv4) {
                window.setWebRTCIPv4("203.0.113.10");
            }
            if (window.setWebRTCIPv6) {
                window.setWebRTCIPv6("2001:db8::10");
            }
        """)

        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")
```

Hoac voi nhieu hook tach rieng:

```python
await browser.set_init_script_hooks([
    'if (window.setWebRTCIPv4) window.setWebRTCIPv4("203.0.113.10");',
    'if (window.setWebRTCIPv6) window.setWebRTCIPv6("2001:db8::10");',
    'if (window.setTimezone) window.setTimezone("Asia/Ho_Chi_Minh");',
])
```

Vi vay:

1. neu muc tieu la browser-wide fingerprinting on dinh, hay dung `fingerprint=` luc launch
2. neu can manual hook, co the dung `browser.set_init_script_hooks(...)`
3. voi popup/tab moi, ban cung can ap dung lai helper neu ban chon huong manual
4. dieu nay dac biet dung voi WebRTC IPv4/IPv6 trong implementation hien tai

## Khuyen nghi thuc te

Neu ban dang dung nhung hook native nay de phuc vu anti-detect/fingerprint spoofing, thu tu uu tien nen la:

1. uu tien `RDPBrowser(fingerprint=..., timezone=...)`
2. dung `page.evaluate("window.set...")` cho cac hook can explicit page-level override
3. voi WebRTC IPv4/IPv6, hien tai hay mac dinh xem day la path chinh
4. khong xem manual page-level hook la thay the hoan toan cho launch-time runtime config doi voi cac nhom fingerprint global khac

## Tom tat

Voi `winfox.rdp`, cach xu ly dung khong phai la mo phong Playwright `addInitScript` nhu co che chinh.

Thay vao do:

1. fingerprint duoc dua vao browser ngay tu luc launch qua `fingerprint=` va `CAMOU_CONFIG_*`
2. browser patch native/WebIDL doc config nay va ap dung o tang sau
3. timezone con duoc kick them bang `window.setTimezone(...)` trong `_apply_overrides()`
4. WebRTC IPv4/IPv6 hien tai nen duoc xem la page-level manual hook path
5. neu can, ban van co the goi truc tiep `window.set...()` tu `page.evaluate(...)`, nhung do la fallback/override, khong phai path chinh cho nhom global fingerprint
