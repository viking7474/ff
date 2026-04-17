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
