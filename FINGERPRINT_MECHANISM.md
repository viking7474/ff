# Cơ Chế Xử Lý Fingerprints Trong Camoufox

Tài liệu này giải thích cách Camoufox (thông qua các patch được áp dụng vào mã nguồn của Firefox) nhận và áp dụng các thông số fingerprint (giả mạo thiết bị, môi trường) được truyền vào từ bên ngoài.

## 1. Nguồn Gốc Dữ Liệu Fingerprint

Dữ liệu fingerprint được truyền vào trình duyệt dưới dạng một chuỗi **JSON** thông qua các **biến môi trường (Environment Variables)**.

Logic đọc dữ liệu này nằm trong file `additions/camoucfg/MaskConfig.hpp`, cụ thể trong namespace `MaskConfig`.

Hệ thống sẽ thử đọc các biến môi trường theo thứ tự:
1. `CAMOU_CONFIG_1`
2. `CAMOU_CONFIG_2`
3. ... `CAMOU_CONFIG_N`

Hệ thống sẽ nối (concatenate) nội dung của tất cả các biến môi trường này lại với nhau (để vượt qua giới hạn độ dài của một biến môi trường trên một số hệ điều hành).
Nếu không tìm thấy các biến `CAMOU_CONFIG_N`, hệ thống sẽ sử dụng biến môi trường mặc định là `CAMOU_CONFIG`.

Sau khi thu thập đầy đủ chuỗi kí tự, hệ thống sẽ parse chuỗi này thành đối tượng JSON thông qua thư viện `nlohmann/json`.

## 2. Cách Các Patches Sử Dụng Dữ Liệu Này

Các patch trong thư mục `patches/` (ví dụ: `fingerprint-injection.patch`, `navigator-spoofing.patch`, `screen-spoofing.patch`, v.v.) sẽ sửa đổi mã nguồn C++ của Firefox (như `nsGlobalWindowInner.cpp`, `BatteryManager.cpp`, `WorkerNavigator.cpp`) bằng cách:

1. Thêm chỉ thị include: `#include "MaskConfig.hpp"`
2. Chèn các câu lệnh điều kiện vào phần đầu của các hàm lấy thông số.

**Ví dụ trong mã nguồn (sau khi đã được patch):**

```cpp
double nsGlobalWindowInner::GetInnerWidth(ErrorResult& aError) {
  // Nếu có cấu hình "window.innerWidth" từ JSON, trả về giá trị đó.
  if (auto value = MaskConfig::GetDouble("window.innerWidth"))
    return value.value();

  // Nếu không, thực thi logic gốc của Firefox.
  FORWARD_TO_OUTER_OR_THROW(GetInnerWidthOuter, (aError), aError, 0);
}

void WorkerNavigator::GetUserAgent(nsString& aUserAgent, CallerType aCallerType,
                                   ErrorResult& aRv) const {
  // Trả về User-Agent giả mạo nếu có trong JSON
  if (auto value = MaskConfig::GetString("navigator.userAgent"))
    return aUserAgent.Assign(NS_ConvertUTF8toUTF16(value.value()));

  // ... Logic lấy User Agent thật
}
```

Các kiểu dữ liệu được hỗ trợ bao gồm chuỗi (`GetString`), số nguyên (`GetInt32`, `GetUint32`), số thực (`GetDouble`), boolean (`GetBool`, `CheckBool`), và cả các đối tượng JSON phức tạp lồng nhau (như cho WebGL parameters thông qua `GetNested`).

---

## 3. Mẫu Demo Truyền Dữ Liệu Fingerprint

Đây là một ví dụ minh họa cách truyền cấu hình giả mạo vào Camoufox sử dụng biến môi trường.

### File JSON mẫu (ví dụ đại diện)

Tưởng tượng chúng ta muốn giả mạo:
- Kích thước màn hình và cửa sổ
- User Agent
- Nền tảng (Platform)
- Trạng thái Pin

Nội dung JSON tương ứng sẽ trông như sau:

```json
{
  "window.innerWidth": 1024,
  "window.innerHeight": 768,
  "screen.width": 1920,
  "screen.height": 1080,
  "navigator.userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "navigator.platform": "Win32",
  "battery:charging": false,
  "battery:level": 0.55
}
```

### Chạy bằng dòng lệnh (Bash / Linux / macOS)

Để chạy trình duyệt với cấu hình trên, bạn có thể truyền thẳng chuỗi JSON (nhớ escape các dấu nháy kép hoặc sử dụng cú pháp nháy đơn bọc nháy kép) vào biến môi trường `CAMOU_CONFIG`:

```bash
export CAMOU_CONFIG='{"window.innerWidth": 1024, "window.innerHeight": 768, "screen.width": 1920, "screen.height": 1080, "navigator.userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "navigator.platform": "Win32", "battery:charging": false, "battery:level": 0.55}'

# Chạy Camoufox (thay đường dẫn /path/to/camoufox bằng đường dẫn thực tế đến file thực thi của Camoufox)
/path/to/camoufox
```

Đối với trường hợp cấu hình rất lớn (chứa thông số WebGL, AudioContext, Font List, v.v.) vượt qua giới hạn của hệ điều hành, bạn chia nhỏ file JSON và truyền vào `CAMOU_CONFIG_1`, `CAMOU_CONFIG_2`...:

```bash
export CAMOU_CONFIG_1='{"window.innerWidth": 1024, "window.innerHeight": 768, "screen.width": 1920, '
export CAMOU_CONFIG_2='"screen.height": 1080, "navigator.userAgent": "Mozilla/5.0", "battery:level": 0.55}'

/path/to/camoufox
```

Cơ chế này cho phép các wrapper (như Python library của Camoufox) có thể thiết lập các thông số fingerprint một cách linh hoạt, tạo môi trường thực thi giả lập hoàn hảo mà website không thể nhận biết được trình duyệt đang chạy trong chế độ headless hay bị điều khiển.

---

## 4. Port sang JavaScript (camoufox-js)

Ngoài trình điều khiển gốc viết bằng Python, cấu trúc quản lý và truyền cấu hình có thể được chuyển sang chạy native trên NodeJS/JavaScript bằng cách:
1. Dùng thư viện `fingerprint-generator` (của Apify) để sinh vân tay ngẫu nhiên dựa trên xác suất thống kê thực tế.
2. Dùng thư viện `geoip-lite` để tra cứu vị trí địa lý, lấy vĩ độ/kinh độ và múi giờ khớp với địa chỉ IP (Proxy).
3. Sử dụng `playwright.firefox.launch()` và chèn chuỗi JSON được sinh ra vào biến môi trường `env.CAMOU_CONFIG` để Camoufox tự động nhận biết.

Tham khảo bản nháp cài đặt Skeleton Node.js ở thư mục `jslib/` trong codebase.

### Cách chạy thử với file thực thi đã có sẵn (camoufox.exe) qua thư viện JavaScript

Nếu bạn đã build hoặc tải sẵn `camoufox.exe` (hoặc `camoufox` trên Linux/macOS) và muốn test trực tiếp khả năng inject fingerprint của thư viện JavaScript, bạn có thể thực hiện theo các bước sau tại thư mục `jslib`:

1. Cài đặt các thư viện cần thiết:
   ```bash
   cd jslib
   npm install
   ```

2. Chạy file test `run-existing.js` và chỉ định đường dẫn tới file thực thi thông qua biến môi trường `CAMOUFOX_PATH`:

   **Trên Windows (PowerShell):**
   ```powershell
   $env:CAMOUFOX_PATH="C:\duong\dan\toi\camoufox.exe"; node run-existing.js
   ```

   **Trên Windows (CMD):**
   ```cmd
   set CAMOUFOX_PATH=C:\duong\dan\toi\camoufox.exe
   node run-existing.js
   ```

   **Trên Linux / macOS:**
   ```bash
   CAMOUFOX_PATH=/duong/dan/toi/camoufox node run-existing.js
   ```

Đoạn script sẽ tự động tạo một fingerprint hợp lệ dựa trên cấu hình mạng (GeoIP) mặc định và khởi chạy Playwright mở trình duyệt Camoufox của bạn, truy cập vào một trang kiểm tra để bạn xác nhận cấu hình đã hoạt động.

### Thêm Nhãn Profile vào Thanh Địa Chỉ (AwesomeBar)

Được lấy cảm hứng từ cấu hình Identity của Chromium, một patch mới (`profile-label.patch`) đã được thêm vào hệ thống để cung cấp tính năng tương tự.
Nếu bạn truyền vào JSON cấu hình trường `"browser.profileName": "Tên Profile"`, thì chuỗi này sẽ được xuất hiện nổi bật bên cạnh ổ khoá / biểu tượng bảo mật trên thanh địa chỉ URL của Camoufox/Firefox, giúp dễ dàng phân biệt các profile đang mở khi test đa luồng.
## Danh Sách Toàn Bộ Các Giá Trị Cấu Hình (Hooked Configs)

Dưới đây là danh sách đầy đủ các biến môi trường/JSON field mà mã nguồn (các file patch) của Camoufox hiện đang lắng nghe và ghi đè, kèm theo giá trị ví dụ (demo):

- `AudioContext:maxChannelCount (e.g. 2)`
- `AudioContext:outputLatency (e.g. 0.01)`
- `AudioContext:sampleRate (e.g. 48000)`
- `audio:seed (e.g. 123456789)`
- `battery:charging (Boolean, e.g. true)`
- `battery:chargingTime (e.g. 0.0)`
- `battery:dischargingTime (e.g. Infinity)`
- `battery:level (e.g. 1.0)`
- `canvas:seed (e.g. 987654321)`
- `debug (Boolean, e.g. false)`
- `disableTheming (Boolean, e.g. false)`
- `document.body.clientHeight (e.g. 1080)`
- `document.body.clientLeft (e.g. 0)`
- `document.body.clientTop (e.g. 0)`
- `document.body.clientWidth (e.g. 1920)`
- `enableRemoteSubframes (Boolean, e.g. true)`
- `fonts (List of strings, e.g. ["Arial", "Times New Roman"])`
- `fonts:spacing_seed (e.g. 1234)`
- `geolocation:accuracy (e.g. 10)`
- `geolocation:latitude (e.g. 37.7749)`
- `geolocation:longitude (e.g. -122.4194)`
- `h2:disablePriority (Boolean, e.g. false)`
- `h2:enablePush (e.g. 0)`
- `h2:headerTableSize (e.g. 65536)`
- `h2:initialWindowSize (e.g. 131072)`
- `h2:maxConcurrentStreams (e.g. 100)`
- `h2:maxHeaderListSize (e.g. 262144)`
- `h2:pseudoHeaderOrder (e.g. "mpas")`
- `h2:windowUpdateSize (e.g. 15663105)`
- `headers.Accept-Encoding (e.g. "gzip, deflate, br, zstd")`
- `headers.Accept-Language (e.g. "en-US,en;q=0.9")`
- `headers.User-Agent (e.g. "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...")`
- `locale:language (e.g. "en")`
- `locale:region (e.g. "US")`
- `locale:script (e.g. "Latn")`
- `mediaDevices:enabled (Boolean, e.g. true)`
- `mediaDevices:micros (e.g. 1)`
- `mediaDevices:speakers (e.g. 1)`
- `mediaDevices:webcams (e.g. 1)`
- `navigator.appVersion (e.g. "5.0 (Windows)")`
- `navigator.globalPrivacyControl (Boolean, e.g. true)`
- `navigator.hardwareConcurrency (e.g. 8)`
- `navigator.language (e.g. "en-US")`
- `navigator.oscpu (e.g. "Windows NT 10.0; Win64; x64")`
- `navigator.platform (e.g. "Win32")`
- `navigator.userAgent (e.g. "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...")`
- `screen.availHeight (e.g. 1040)`
- `screen.availLeft (e.g. 0)`
- `screen.availTop (e.g. 0)`
- `screen.availWidth (e.g. 1920)`
- `screen.colorDepth (e.g. 24)`
- `screen.height (e.g. 1080)`
- `screen.pageXOffset (e.g. 0)`
- `screen.pageYOffset (e.g. 0)`
- `screen.pixelDepth (e.g. 24)`
- `screen.width (e.g. 1920)`
- `timezone (e.g. "America/New_York")`
- `voices (List of objects, e.g. [{"lang": "en-US", "name": "Alex", "voiceUri": "urn:moz-voice:1", "isDefault": true, "isLocalService": true}])`
- `voices:blockIfNotDefined (Boolean, e.g. true)`
- `voices:fakeCompletion (Boolean, e.g. true)`
- `voices:fakeCompletion:charsPerSecond (e.g. 15)`
- `webGl:contextAttributes.powerPreference (e.g. "high-performance")`
- `webGl:parameters (Object, e.g. {"37445": "Google Inc. (NVIDIA)"})`
- `webGl:parameters:blockIfNotDefined (Boolean, e.g. false)`
- `webGl:renderer (e.g. "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_11_0 ps_11_0, D3D11)")`
- `webGl:shaderPrecisionFormats (Object, e.g. {"35632,36338": {"rangeMin": 127, "rangeMax": 127, "precision": 23}})`
- `webGl:shaderPrecisionFormats:blockIfNotDefined (Boolean, e.g. false)`
- `webGl:supportedExtensions (List of strings, e.g. ["ANGLE_instanced_arrays", "EXT_blend_minmax"])`
- `webGl:vendor (e.g. "Google Inc. (NVIDIA)")`
- `webGl2:contextAttributes.powerPreference (e.g. "high-performance")`
- `webGl2:parameters (Object, similar to webGl:parameters)`
- `webGl2:parameters:blockIfNotDefined (Boolean, e.g. false)`
- `webGl2:shaderPrecisionFormats (Object, similar to webGl:shaderPrecisionFormats)`
- `webGl2:shaderPrecisionFormats:blockIfNotDefined (Boolean, e.g. false)`
- `webGl2:supportedExtensions (List of strings)`
- `window.devicePixelRatio (e.g. 1.0)`
- `window.history.length (e.g. 2)`
- `window.innerHeight (e.g. 900)`
- `window.innerWidth (e.g. 1600)`
- `window.outerHeight (e.g. 1080)`
- `window.outerWidth (e.g. 1920)`
- `window.screenX (e.g. 0)`
- `window.screenY (e.g. 0)`
- `window.scrollMaxX (e.g. 0)`
- `window.scrollMaxY (e.g. 0)`
- `window.scrollMinX (e.g. 0)`
- `window.scrollMinY (e.g. 0)`
- `showcursor` (Boolean, e.g. false) - Bật/tắt hiển thị con trỏ màu đỏ
- `browser.profileName` (e.g. "hoadeptrai") - Hiển thị tên Profile trên thanh URL
- `webrtc_ipv4_<userContextId>` (e.g. "123.123.123.123") - Được inject thông qua Javascript `window.setWebRTCIPv4()`
- `webrtc_ipv6_<userContextId>` (e.g. "2001:db8::1") - Được inject thông qua Javascript `window.setWebRTCIPv6()`

### Lưu ý về các Javascript WebIDL Hooks
Ngoài việc lấy cấu hình qua các biến môi trường (`CAMOU_CONFIG`) ngay từ khi khởi động thông qua C++ (MaskConfig), kiến trúc của Camoufox còn cung cấp một loạt các hàm Javascript (`Window` WebIDL hooks) để cấu hình trực tiếp từ Page/Browser Context (Playwright có thể gọi các hàm này thông qua cơ chế CDP/Juggler injection thay vì gán Environment Variables). Các hàm này bao gồm:

- `window.setFontSpacingSeed(unsigned long seed)`
- `window.setAudioFingerprintSeed(unsigned long seed)`
- `window.setCanvasSeed(unsigned long seed)`
- `window.setFontList(DOMString fontList)`
- `window.setNavigatorPlatform(DOMString platform)`
- `window.setNavigatorOscpu(DOMString oscpu)`
- `window.setNavigatorHardwareConcurrency(unsigned long cores)`
- `window.setNavigatorUserAgent(DOMString ua)`
- `window.setScreenDimensions(long width, long height)`
- `window.setScreenColorDepth(long colorDepth)`
- `window.setSpeechVoices(DOMString voices)`
- `window.setTimezone(DOMString timezone)`
- `window.setWebGLVendor(DOMString vendor)`
- `window.setWebGLRenderer(DOMString renderer)`
- `window.setWebRTCIPv4(DOMString ipv4)`
- `window.setWebRTCIPv6(DOMString ipv6)`

Để truyền những cấu hình này cho browser, khi sử dụng thư viện Playwright JS/Python, bạn cần chèn (inject) đoạn mã gọi các hàm trên vào context của trình duyệt (ví dụ: thông qua `page.addInitScript()` của Playwright).

Ví dụ:
```javascript
await page.addInitScript(() => {
    try {
        window.setWebRTCIPv4("123.123.123.123");
        window.setNavigatorPlatform("Win32");
        window.setTimezone("America/New_York");
    } catch(e) {}
});
```

Điều này rất hữu ích đối với WebRTC spoofing hoặc khi cần thay đổi fingerprint ngay lúc Runtime (khi ứng dụng đã được mở) mà không cần khởi động lại tiến trình của Firefox.
