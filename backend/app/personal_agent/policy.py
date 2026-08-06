from __future__ import annotations

from app.personal_agent.schemas import PermissionLevel


class PermissionPolicy:
    """Central policy: every external write requires explicit confirmation."""

    def __init__(self, confirm_local_actions: bool = True) -> None:
        self.confirm_local_actions = confirm_local_actions

    def requires_confirmation(self, permission: PermissionLevel) -> bool:
        if permission >= PermissionLevel.PROHIBITED:
            raise PermissionError("该能力被当前安全策略禁止。")
        return permission >= PermissionLevel.EXTERNAL_WRITE or (
            permission >= PermissionLevel.LOCAL_ACTION and self.confirm_local_actions
        )
