# RDP Refactor F1 Checklist

This document captures the current F1 audit state for the `winfox.rdp`
refactor. It is based on the code as it exists today and is intended to be the
working checklist for F2 (`RDPPage`) and F3 (`RDPBrowser`).

## Goal

Determine exactly which parts of `winfox.rdp` are already local and which parts
still depend on `camoufox._rdp_legacy_impl`.

## Scope Snapshot

- `pythonlib/winfox/rdp/page.py` still subclasses legacy `RDPPage`.
- `pythonlib/winfox/rdp/browser.py` still subclasses legacy `RDPBrowser`.
- `frame.py`, `locator.py`, `dialog.py`, and `context.py` still reference
  legacy page/browser types in `TYPE_CHECKING` blocks.
- `camoufox.rdp_api` is already a thin facade to `winfox.rdp`.

## RDPPage

### Status

- New namespace home exists: `pythonlib/winfox/rdp/page.py`
- Class still inherits legacy implementation:
  `class RDPPage(_LegacyRDPPage)`
- No local `__init__` exists yet

### Done

The following page surface is already implemented locally in
`pythonlib/winfox/rdp/page.py`:

- Input primitives:
  - `_Mouse`
  - `_Keyboard`
- Page surface:
  - `url`
  - `url_cached`
  - `url_fresh`
  - `title`
  - `content`
  - `evaluate`
  - `query_selector`
  - `query_selector_all`
  - `locator`
  - `get_by_text`
  - `get_by_placeholder`
  - `get_by_label`
  - `get_by_test_id`
  - `get_by_role`
  - `first`
  - `nth`
  - `last`
  - `text_content`
  - `inner_text`
  - `inner_html`
  - `all_text_contents`
  - `all_inner_texts`
  - `get_attribute`
  - `count`
  - `exists`
  - `has_selector`
  - `is_visible`
  - `is_hidden`
  - `wait_for_text`
  - `wait_for_selector_count`
  - `wait_until_hidden`
  - `wait_until_visible`
  - `get_local_storage`
  - `set_local_storage`
  - `clear_local_storage`
  - `get_session_storage`
  - `set_session_storage`
  - `clear_session_storage`
  - `save_storage_state`
  - `load_storage_state`
  - `expect_popup`
  - `_ensure_bridge_ready`
  - `_enumerate_frames`
  - `_frame_eval_body`
  - `_frame_evaluate`
  - `frames`
  - `child_frames`
  - `frame`
  - `_ensure_dialog_shim`
  - `_resolve_dialog`
  - `expect_dialog`
  - `screenshot`
  - `_make_event_payload`
  - `_emit_event`
  - `_emit_event_threadsafe`
  - `_remember_network_event`
  - `_make_network_event_payload`
  - `_ensure_network_event_bridge`
  - `_network_event_poller`
  - `on`
  - `remove_listener`
  - `goto`
  - `_goto_impl`
  - `_wait_for_doc_event`
  - `reload`
  - `_reload_impl`
  - `wait_for_load_state`
  - `_wait_for_load_state_impl`
  - `start_capture`
  - `stop_capture`
  - `get_captured_responses`
  - `wait_for_response`
  - `start_spy`
  - `stop_spy`
  - `get_spied_requests`
  - `_apply_interception_rules`
  - `set_request_block_patterns`
  - `set_extra_http_headers`
  - `clear_interception`
  - `bg_fetch`
  - `fulfill_text`
  - `fulfill_json`
  - `click`
  - `hover`
  - `focus`
  - `press`
  - `fill`
  - `set_input_files`

### Remaining

The following pieces are still inherited from
`pythonlib/camoufox/_rdp_legacy_impl.py` and must move into
`pythonlib/winfox/rdp/page.py` before inheritance can be removed:

- Initialization and core state:
  - `__init__`
  - `is_closed`
  - `_ensure_open`
- Lifecycle and ownership:
  - `dispose`
  - `close`
- Persistent actor and console glue:
  - `_detach_persistent_console_listener`
  - `_attach_persistent_console_listener`
  - `_watch_target`
  - `_start_persistent_watcher`
  - `_refresh_target`
  - `_ensure_console`
  - `_eval_sync`
- Idle and behavior helpers:
  - `_idle_mouse_loop`
  - `_with_idle_mouse`
  - `simulate_tab_switch`
- Page-state helpers:
  - `bring_to_front`
  - `is_active`
  - `wait_for_url`
- Remaining feature helpers:
  - `wait_for_selector`
  - `clear_cookies`
  - `_get_memory_actor_id`
  - `force_gc`
  - `memory_usage`
  - `wait_for_network_idle`

### State Fields Still Backed by Legacy `__init__`

These fields are not yet initialized by local code and are therefore still
owned by the legacy base class:

- `_browser`
- `_client`
- `_loop`
- `_tab_actor_id`
- `_target_actor_id`
- `_console_actor_id`
- `_browsing_context_id`
- `_bridge`
- `_tab_id`
- `_url`
- `_console_started`
- `_target_ver`
- `_watcher_id`
- `_persistent_target_cb`
- `_persistent_console_cb`
- `_persistent_console_id`
- `_event_listeners`
- `_closed`
- `_nav_lock`
- `_last_emitted_event`
- `_network_events_started`
- `_network_event_task`
- `_request_event_ts`
- `_spy_event_ts`
- `_seen_network_events`
- `_seen_network_event_order`
- `_dialog_shim_ready`
- `_dialog_last_id`
- `_interception_block_patterns`
- `_interception_header_rules`
- `_interception_fulfill_rules`
- `mouse`
- `keyboard`

### Sensitive

- `page.py` has duplicated local methods that need deduplication before or
  during F2:
  - `_ensure_bridge_ready`
  - `_ensure_network_event_bridge`
  - `_network_event_poller`
  - `on`
- Local methods already depend on inherited internals, so removing inheritance
  before moving helpers will break runtime behavior:
  - `url` and `evaluate` depend on `_eval_sync`
  - `goto`, `_wait_for_doc_event`, and `_reload_impl` depend on `_with_idle_mouse`
  - browser page construction depends on `page._start_persistent_watcher()`
- `wait_for_selector` still lives only in the legacy class, but local methods
  `wait_until_hidden` and `wait_until_visible` already depend on it.

### F2 Entry Criteria

- Add local `RDPPage.__init__`
- Move all inherited helper methods listed above
- Deduplicate overlapping page methods in `page.py`
- Remove `class RDPPage(_LegacyRDPPage)` inheritance only after the above is done

## RDPBrowser

### Status

- New namespace home exists: `pythonlib/winfox/rdp/browser.py`
- Class still inherits legacy implementation:
  `class RDPBrowser(_LegacyRDPBrowser)`
- A local `__init__` already exists

### Done

The following browser behavior is already implemented locally in
`pythonlib/winfox/rdp/browser.py`:

- Class and state:
  - `_get_semaphore`
  - `__init__`
  - `_bridge_repair_attempted` state
- Page and context registry:
  - `_get_active_tab_id`
  - `_snapshot_tabs`
  - `_register_page`
  - `_unregister_page`
  - `_build_page_from_tab`
  - `list_pages`
  - `contexts`
  - `_unregister_context`
- Context lifecycle:
  - `_find_available_port`
  - `_allocate_context_ports`
  - `new_context`
  - `close_all_contexts`
- State and page lookup:
  - `get_active_page`
  - `save_state`
  - `save_state_to_file`
  - `load_state`
  - `load_state_from_file`
  - `wait_for_new_page`
  - `page_by_url`
  - `pages_by_url`
- Page closing and browser lifecycle:
  - `_close_page`
  - `start`
  - `_connect_rdp`
  - `_install_extension`
  - `_wait_for_bridge`
  - `_ensure_bridge_connected`
  - `_apply_overrides`
  - `_prepare_extension_runtime`
  - `_read_stderr`
  - `is_alive`
  - `is_connected`
  - `new_page`
  - `close`

### Remaining

The following pieces are still inherited from
`pythonlib/camoufox/_rdp_legacy_impl.py` and must move into
`pythonlib/winfox/rdp/browser.py` before inheritance can be removed:

- Page bulk-management helpers:
  - `close_all_pages`
  - `close_other_pages`
- Tab creation/waiting helper:
  - `_wait_for_new_tab_actor`
- Context-manager support:
  - `__aenter__`
  - `__aexit__`
- Proxy extension helper:
  - `_prepare_extension_with_proxy`

### Legacy Helper Imports Still Used by Browser

`browser.py` still imports these symbols from the legacy module:

- `_create_job_object`
- `_get_default_binary`
- `_kernel32`
- `_write_user_prefs`
- `logger`
- `EXTENSION_DIR`
- `DEFAULT_RDP_PORT`
- `DEFAULT_WS_PORT`

These are not inheritance, but they are still direct implementation coupling to
the legacy module and must be addressed in later batches.

### Sensitive

- `start()` still calls inherited `_prepare_extension_with_proxy()` when proxy
  auth is enabled.
- `wait_for_new_page()` and `new_page()` still call inherited
  `_wait_for_new_tab_actor()`.
- `browser._build_page_from_tab()` creates the new `winfox.rdp.page.RDPPage`,
  but immediately depends on inherited page helper `_start_persistent_watcher()`.
- Browser lifecycle is partly local and partly dependent on page inherited
  behavior because `page.dispose()` is still legacy.

### F3 Entry Criteria

- Move the remaining inherited browser methods listed above
- Decide where legacy helper imports should live after the split
- Remove `class RDPBrowser(_LegacyRDPBrowser)` inheritance only after page F2 is stable

## Dependency Boundary Notes

Current direct references to `camoufox._rdp_legacy_impl` inside `winfox.rdp`
still exist in:

- None.

F4 is complete once this remains true and `winfox.rdp` type references continue
to use local imports or `TYPE_CHECKING` imports only.

## Recommended Next Order

1. Implement local `RDPPage.__init__`
2. Move remaining inherited page helpers
3. Deduplicate overlapping methods in `page.py`
4. Make `RDPPage` inheritance-free
5. Move remaining browser helpers
6. Make `RDPBrowser` inheritance-free
7. Remove type-only imports from `camoufox._rdp_legacy_impl`

## F5 Status

- `pythonlib/camoufox/_rdp_legacy_impl.py` has been removed.
- `pythonlib/winfox/rdp` no longer depends on the legacy RDP implementation.
- `pythonlib/camoufox/rdp_api.py` remains the compatibility facade to
  `winfox.rdp`.

## F8 Status

- Core docs now describe `winfox.rdp` as the primary Python RDP implementation.
- `camoufox.rdp_api` is documented as a compatibility-only facade.
- `camoufox.legacy` is documented as the old Playwright-centric path.
