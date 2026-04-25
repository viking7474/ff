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
8. `await browser.wait_for_new_page(timeout=5000)` - doi mot page/tab moi xuat hien, ket hop registry va tab actor de giam race popup.
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
9. `await page.expect_popup(timeout=5000)` - doi popup/tab moi duoc mo boi hanh dong tu page nay.

## 4. DOM / selectors / locator

1. `await page.query_selector(selector)` - lay hinh hoc phan tu dau tien match selector.
2. `await page.query_selector_all(selector)` - lay danh sach hinh hoc cac phan tu match.
3. `await page.text_content(selector)` - lay text content cua phan tu match.
4. `await page.inner_text(selector)` - lay noi dung text render ra gan voi nguoi dung nhin thay.
5. `await page.inner_html(selector)` - lay noi dung HTML ben trong phan tu match.
6. `await page.all_text_contents(selector)` - lay text content cua tat ca phan tu match.
7. `await page.all_inner_texts(selector)` - lay innerText cua tat ca phan tu match.
8. `await page.get_attribute(selector, name)` - lay gia tri attribute cua phan tu match.
9. `await page.count(selector)` - dem so phan tu match selector.
10. `await page.exists(selector)` - tra ve `True` neu ton tai it nhat 1 phan tu match.
11. `await page.has_selector(selector)` - alias cua `exists(selector)`.
12. `await page.is_visible(selector)` - kiem tra selector hien co dang visible hay khong.
13. `await page.is_hidden(selector)` - kiem tra selector dang hidden hoac khong ton tai.
14. `await page.wait_for_text(text)` - doi den khi `document.body.innerText` chua chuoi can tim.
15. `await page.wait_for_selector_count(selector, n)` - doi den khi selector co dung `n` phan tu match.
16. `await page.wait_until_hidden(selector)` - doi den khi selector bien mat hoac bi hidden.
17. `await page.wait_until_visible(selector)` - doi den khi selector tro nen visible.
18. `page.first(selector)` / `page.nth(selector, index)` / `page.last(selector)` - tao locator helper cho phan tu dau, phan tu thu n, hoac phan tu cuoi.
19. `page.get_by_text(text, exact=False)` - tim phan tu theo text de doc/tuong tac de hon.
20. `page.get_by_placeholder(text, exact=False)` - tim input/textarea theo placeholder.
21. `page.get_by_label(text, exact=False)` - tim control theo label.
22. `page.get_by_test_id(value)` - tim phan tu theo `data-testid`.
23. `page.get_by_role(role, name=None, exact=False)` - tim phan tu theo role thuc dung (button, link, textbox, checkbox, radio, combobox).
24. `page.locator(selector)` - tao locator wrapper.
25. `await locator.wait_for()` - doi locator xuat hien/san sang.
26. `await locator.text_content()` - lay text content qua locator.
27. `await locator.inner_text()` - lay innerText qua locator.
28. `await locator.get_attribute(name)` - lay attribute qua locator.
29. `await locator.count()` - dem so phan tu qua locator.
30. `locator.first()` / `locator.last()` / `locator.nth(index)` - tao locator phong phu hon.
31. `locator.filter(has_text=..., exact=False)` - loc locator theo text.
32. `locator.locator(selector)` - chain locator con trong subtree cua locator cha.
33. `await locator.exists()` - kiem tra locator co ton tai hay khong.
34. `await locator.is_visible()` / `await locator.is_hidden()` - kiem tra trang thai visible/hidden cua locator.
35. `await page.wait_for_selector(selector)` - doi selector theo implementation hien tai.

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
8. `await page.set_request_block_patterns(patterns)` - chan request theo substring URL.
9. `await page.set_extra_http_headers(headers, patterns=None)` - override header request theo pattern URL.
10. `await page.fulfill_text(patterns, body, content_type="text/plain")` - mock response text cho request match pattern.
11. `await page.fulfill_json(patterns, data)` - mock response JSON cho request match pattern.
12. `await page.clear_interception()` - xoa interception rules hien tai.
13. `await page.wait_for_network_idle()` - doi network nhan roi.

## 9. Diagnostics

1. `await page.memory_usage()` - lay memory metrics cua tab hien tai.
2. `await page.force_gc()` - ep GC va cycle collection.

## 10. Storage va state

1. `await page.get_local_storage()` - lay toan bo `localStorage` cua page hien tai duoi dang dictionary.
2. `await page.set_local_storage(data)` - ghi nhieu gia tri vao `localStorage` cua page hien tai.
3. `await page.get_session_storage()` - lay toan bo `sessionStorage` cua page hien tai.
4. `await page.set_session_storage(data)` - ghi nhieu gia tri vao `sessionStorage` cua page hien tai.
5. `await page.save_storage_state()` - luu `localStorage` va `sessionStorage` cua page hien tai thanh mot state object cap page.
6. `await page.load_storage_state(state)` - nap lai storage state cap page vao page hien tai.
7. `await browser.save_state()` - luu state thuc dung gom cookies va `localStorage` theo origin.
8. `await browser.load_state(state)` - nap lai state da luu vao browser.
9. `await browser.save_state_to_file(path)` - ghi state browser ra file JSON.
10. `await browser.load_state_from_file(path)` - nap state browser tu file JSON.

## 11. Events

1. `page.on("load", callback)` - dang ky callback khi trang load xong.
2. `page.on("domcontentloaded", callback)` - callback cho DOM content loaded.
3. `page.on("framenavigated", callback)` - callback khi top-level target/navigation thay doi.
4. `page.on("request", callback)` - nhan event request o muc practical thong qua bridge.
5. `page.on("response", callback)` - nhan event response o muc practical thong qua bridge.
6. `page.on("requestfinished", callback)` - nhan event khi request ket thuc theo du lieu spy.
7. `page.on("requestfailed", callback)` - nhan event khi request that bai theo du lieu spy.
8. `page.remove_listener(event, callback)` - go callback da dang ky.

Payload event network hien tai thuong co:

1. `requestId`
2. `state`
3. `url`
4. `method`
5. `headers`
6. `requestBody`
7. `responseHeaders`
8. `responseBody`
9. `status`
10. `error`
11. `timestamp`
12. `page`

Trong nhieu truong hop, `request`, `response`, va `requestfinished` co the doi chieu voi nhau qua cung `requestId`.

## 12. Dialogs

1. `await page.expect_dialog(timeout=5000)` - doi dialog thuc dung duoc shim tu `alert/confirm/prompt`.
2. `dialog.type` - loai dialog (`alert`, `confirm`, `prompt`).
3. `dialog.message` - noi dung dialog.
4. `dialog.handled` - cho biet dialog da duoc xu ly hay chua.
5. `dialog.accepted` - cho biet dialog duoc chap nhan hay tu choi.
6. `dialog.prompt_text` - gia tri text duoc truyen vao prompt khi accept.
7. `await dialog.accept(prompt_text=None)` - chap nhan dialog theo practical shim hien tai.
8. `await dialog.dismiss()` - tu choi/bo qua dialog theo practical shim hien tai.

## 13. Frames

1. `await page.frames()` - liet ke cac frame/iframe hien co trong page.
2. `await page.child_frames(path=None)` - lay cac frame con truc tiep cua root page hoac cua mot frame path cu the.
3. `await page.frame(index=..., name=..., url_contains=..., path=...)` - lay 1 frame theo index, name, URL, hoac frame path.
4. `await frame.parent_frame()` - lay frame cha cua frame hien tai.
5. `await frame.child_frames()` - lay cac frame con truc tiep cua frame hien tai.
6. `await frame.evaluate(expression)` - evaluate trong frame same-origin.
7. `await frame.text_content(selector)` - lay text content trong frame same-origin.
8. `await frame.inner_text(selector)` - lay innerText trong frame same-origin.
9. `await frame.inner_html(selector)` - lay innerHTML trong frame same-origin.
10. `await frame.get_attribute(selector, name)` - lay attribute trong frame same-origin.
11. `await frame.count(selector)` - dem so phan tu trong frame same-origin.
12. `await frame.exists(selector)` - kiem tra selector trong frame same-origin.
13. `await frame.is_visible(selector)` - kiem tra visible trong frame same-origin.
14. `await frame.is_hidden(selector)` - kiem tra hidden trong frame same-origin.
15. `await frame.wait_for_text(text)` - doi text xuat hien trong frame same-origin.
16. `await frame.wait_for_selector(selector)` - doi selector trong frame same-origin.
17. `frame.locator(selector)` - tao locator ben trong frame same-origin.
18. `await frame.hover(selector)` - dua chuot den phan tu trong frame same-origin.
19. `await frame.click(selector)` - click phan tu trong frame same-origin.
20. `await frame.focus(selector)` - focus phan tu trong frame same-origin.
21. `await frame.press(selector, key)` - focus roi bam phim trong frame same-origin.
22. `frame.get_by_text(text, exact=False)` - tim phan tu trong frame theo text.
23. `frame.get_by_placeholder(text, exact=False)` - tim input/textarea trong frame theo placeholder.
24. `frame.get_by_label(text, exact=False)` - tim control trong frame theo label.
25. `frame.get_by_test_id(value)` - tim phan tu trong frame theo `data-testid`.
26. `frame.get_by_role(role, name=None, exact=False)` - tim phan tu trong frame theo role thuc dung.
27. `frame.locator(...).filter(has_text=..., exact=False)` - loc locator trong frame theo text.
28. `frame.locator(...).locator(selector)` - chain locator trong frame.

Gioi han hien tai:

1. same-origin frame duoc ho tro cho DOM/evaluate helpers va interaction helpers co ban.
2. cross-origin frame chi expose metadata.
3. neu co gang DOM/evaluate vao cross-origin frame thi se bao loi ro rang.
4. nested frame co the duoc lookup qua `path` trong frame model hien tai.
5. da co frame tree helpers o muc co ban de lay parent/child frames.

## Ghi chu thuc te

1. `RDPBrowser` khong phai la Playwright parity day du.
2. Multi-instance va multi-tab da co smoke/stress test trong repo.
3. Neu gap loi, xem them `docs/rdpbrowser_troubleshooting.md`.
4. `save_state()` / `load_state()` hien tai tap trung vao cookies va `localStorage`, chua phai browser context parity day du.
5. Repo hien da co hardening cho page-scoped storage state va file-based state round-trip.
6. Interception hien tai moi o muc toi thieu: block request, override header, va mock response text/json don gian.
7. Block rules va header rules hien duoc merge voi nhau, khong ghi de nhau.
8. Request bi chan co the xuat hien duoi `requestfailed` voi `error="blocked_by_interception"`.
9. Upload file hien tai la practical path cho `<input type="file">`, chua phai native file chooser parity.
10. Dialog hien tai la practical shim, chua phai native parity hoan chinh.
11. Frame model hien tai tap trung vao same-origin iframe, chua phai full frame parity.
12. Tai lieu dinh vi va so sanh voi Juggler nam o `docs/rdpbrowser_vs_juggler.md`.
