# RDPBrowser - Tai lieu tieng Viet

Tai lieu nay tong hop nhanh cac ham dang co cua `RDPBrowser` trong repo nay, kem vi du nho de chay thu.

## RDPBrowser la gi

`RDPBrowser` la backend automation cho Winfox dua tren 3 lop:

1. Firefox RDP de dieu khien browser va target
2. WebExtension bridge de gui lenh, xu ly proxy auth, network capture/spy
3. Experiment API de gui input trusted-like

Huong nay duoc dung nhu Python automation path chinh trong repo hien tai.

## Vi du nho

```python
import asyncio

from camoufox.rdp_api import RDPBrowser


async def main():
    async with RDPBrowser(
        executable_path=r"C:\path\to\winfox.exe",
        headless=False,
        rdp_port=6000,
        ws_port=8775,
    ) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.wait_for_load_state("load")

        print(await page.title())
        print(await page.text_content("h1"))
        print(await page.get_attribute("a", "href"))
        print(await page.count("a"))

        await page.screenshot("rdp_vi_example.png")


asyncio.run(main())
```

## Nhom ham hien co

## 1. Browser lifecycle

1. `await browser.new_page()` - tao page moi de dieu khien. Lan dau thuong gan vao tab khoi dong, cac lan sau se mo tab moi trong cung cua so.
2. `browser.list_pages()` - tra danh sach cac page dang con song ma browser dang theo doi.
3. `await browser.get_active_page()` - tra ve page dang la tab active neu bridge resolve duoc.
4. `await browser.page_by_url(pattern)` - tim page dau tien co URL chua `pattern`.
5. `await browser.pages_by_url(pattern)` - tim tat ca page co URL chua `pattern`.
6. `await browser.close_other_pages(page)` - dong tat ca page tru page duoc giu lai.
7. `await browser.close_all_pages()` - dong tat ca page dang duoc theo doi va xoa registry.
8. `await browser.wait_for_new_page(timeout=5000)` - doi mot page/tab moi xuat hien trong registry sau khi click hoac window.open.
9. `await browser.close()` - dong browser.

## 2. Page lifecycle va tab management

1. `await page.bring_to_front()` - chuyen tab cua page nay thanh tab dang active.
2. `await page.close()` - dong tab cua page nay va unregister khoi browser.
3. `page.is_closed()` - kiem tra page da dong/dispose chua.
4. `await page.is_active()` - kiem tra page nay co dang la tab active hay khong.

## 3. Navigation

1. `await page.goto(url)` - dieu huong den URL moi.
2. `await page.reload()` - tai lai trang hien tai.
3. `await page.wait_for_load_state("load")` - doi trang dat trang thai san sang.
4. `await page.wait_for_url(pattern)` - doi den khi URL hien tai chua chuoi `pattern`.
5. `page.url` - lay URL hien tai theo cach dong bo.
6. `page.url_cached` - lay URL cache da duoc cap nhat trong navigation.
7. `await page.url_fresh()` - lay URL moi nhat bang cach hoi truc tiep page.
8. `await page.title()` - lay `document.title`.

## 4. DOM / selectors / locator

1. `await page.query_selector(selector)` - lay hinh hoc phan tu dau tien match selector.
2. `await page.query_selector_all(selector)` - lay danh sach hinh hoc cac phan tu match.
3. `await page.text_content(selector)` - lay text content cua phan tu match.
4. `await page.inner_text(selector)` - lay noi dung text render ra gan voi nguoi dung nhin thay.
5. `await page.inner_html(selector)` - lay noi dung HTML ben trong phan tu match.
6. `await page.all_text_contents(selector)` - lay text content cua tat ca phan tu match.
7. `await page.get_attribute(selector, name)` - lay gia tri attribute cua phan tu match.
8. `await page.count(selector)` - dem so phan tu match selector.
9. `await page.exists(selector)` - tra ve `True` neu ton tai it nhat 1 phan tu match.
10. `await page.has_selector(selector)` - alias cua `exists(selector)`.
11. `await page.is_visible(selector)` - kiem tra selector hien co dang visible hay khong.
12. `await page.is_hidden(selector)` - kiem tra selector dang hidden hoac khong ton tai.
13. `await page.wait_for_text(text)` - doi den khi `document.body.innerText` chua chuoi can tim.
14. `await page.wait_for_selector_count(selector, n)` - doi den khi selector co dung `n` phan tu match.
15. `await page.wait_until_hidden(selector)` - doi den khi selector bien mat hoac bi hidden.
16. `await page.wait_until_visible(selector)` - doi den khi selector tro nen visible.
17. `page.locator(selector)` - tao locator wrapper.
18. `await locator.wait_for()` - doi locator xuat hien/san sang.
19. `await locator.text_content()` - lay text content qua locator.
20. `await locator.get_attribute(name)` - lay attribute qua locator.
21. `await locator.count()` - dem so phan tu qua locator.
22. `await page.wait_for_selector(selector)` - doi selector theo implementation hien tai.

## 5. JS va page content

1. `await page.evaluate(expression)` - thuc thi JavaScript va tra ket qua.
2. `await page.content()` - lay HTML day du cua document.

## 6. Input

1. `await page.click(selector)` - click phan tu bang selector.
2. `await page.hover(selector)` - dua chuot den giua phan tu match.
3. `await page.focus(selector)` - focus vao phan tu match.
4. `await page.press(selector, key)` - focus selector roi bam phim.
5. `await page.set_input_files(selector, paths)` - nap mot hoac nhieu file vao `<input type="file">` theo practical upload path hien tai.
6. `await page.fill(selector, text)` - clear va nhap text bang trusted bridge.
7. `await page.keyboard.type(text)` - go text tu ban phim.
8. `await page.keyboard.press(key)` - bam 1 phim.
9. `await page.mouse.move_smooth(x, y)` - di chuot human-like.
10. `await page.mouse.click(x, y)` - click tai toa do.
11. `await page.mouse.click_smooth(x, y)` - move + hover + click.
12. `await page.mouse.wheel(delta_x, delta_y)` - scroll 1 buoc.
13. `await page.mouse.wheel_smooth(delta_y)` - scroll human-like.

## 7. Screenshot / state helpers

1. `await page.screenshot(path)` - chup anh trang/tab hien tai.
2. `await page.simulate_tab_switch()` - mo phong blur/visibility change.
3. `await page.clear_cookies()` - xoa cookies qua extension.

## 8. Network

1. `await page.start_capture(patterns)` - bat capture response body.
2. `await page.stop_capture()` - tat capture.
3. `await page.get_captured_responses(clear=True|False)` - lay danh sach response da capture.
4. `await page.wait_for_response(pattern)` - doi response match pattern.
5. `await page.start_spy(patterns)` - bat request spy.
6. `await page.stop_spy()` - tat request spy.
7. `await page.get_spied_requests(clear=True|False)` - lay request da spy.
8. `await page.wait_for_network_idle()` - doi network nhan roi.

## 9. Diagnostics

1. `await page.memory_usage()` - lay memory metrics cua tab hien tai.
2. `await page.force_gc()` - ep GC va cycle collection.

## 10. Events

1. `page.on("load", callback)` - dang ky callback khi trang load xong.
2. `page.on("domcontentloaded", callback)` - callback cho DOM content loaded.
3. `page.on("framenavigated", callback)` - callback khi top-level target/navigation thay doi.
4. `page.on("request", callback)` - nhan event request o muc practical thong qua bridge.
5. `page.on("response", callback)` - nhan event response o muc practical thong qua bridge.
6. `page.on("requestfinished", callback)` - nhan event khi request ket thuc theo du lieu spy.
7. `page.on("requestfailed", callback)` - nhan event khi request that bai theo du lieu spy.
8. `page.remove_listener(event, callback)` - go callback da dang ky.

## 11. Dialogs

1. `await page.expect_dialog(timeout=5000)` - doi dialog thuc dung duoc shim tu `alert/confirm/prompt`.
2. `dialog.type` - loai dialog (`alert`, `confirm`, `prompt`).
3. `dialog.message` - noi dung dialog.
4. `await dialog.accept(prompt_text=None)` - chap nhan dialog theo practical shim hien tai.
5. `await dialog.dismiss()` - tu choi/bo qua dialog theo practical shim hien tai.

## Ghi chu thuc te

1. `RDPBrowser` khong phai la Playwright parity day du.
2. Multi-instance va multi-tab da co smoke/stress test trong repo.
3. Neu gap loi, xem them `docs/rdpbrowser_troubleshooting.md`.
4. Upload file hien tai la practical path cho `<input type="file">`, chua phai native file chooser parity.
5. Dialog hien tai la practical shim, chua phai native parity hoan chinh.
6. Tai lieu dinh vi va so sanh voi Juggler nam o `docs/rdpbrowser_vs_juggler.md`.
