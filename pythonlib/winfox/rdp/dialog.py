from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from camoufox.rdp_api import RDPPage


class RDPDialog:
    def __init__(
        self,
        page: "RDPPage",
        dialog_id: int,
        dialog_type: str,
        message: str,
        default_value: Optional[str] = None,
    ):
        self._page = page
        self._id = dialog_id
        self.type = dialog_type
        self.message = message
        self.default_value = default_value
        self.handled = False
        self.accepted: Optional[bool] = None
        self.prompt_text: Optional[str] = None

    def _update_from_state(self, state: Dict[str, Any]) -> None:
        self.handled = bool(state.get("handled", self.handled))
        self.accepted = state.get("accepted", self.accepted)
        self.prompt_text = state.get("promptText", self.prompt_text)

    async def accept(self, prompt_text: Optional[str] = None) -> None:
        if self.handled:
            return
        state = await self._page._resolve_dialog(self._id, accepted=True, prompt_text=prompt_text)
        if isinstance(state, dict):
            self._update_from_state(state)
        else:
            self.handled = True
            self.accepted = True
            self.prompt_text = prompt_text

    async def dismiss(self) -> None:
        if self.handled:
            return
        state = await self._page._resolve_dialog(self._id, accepted=False, prompt_text=None)
        if isinstance(state, dict):
            self._update_from_state(state)
        else:
            self.handled = True
            self.accepted = False
            self.prompt_text = None
