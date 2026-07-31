from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPlan:
    action: str
    target_user: str
    content: str
    requires_user_confirmation: bool = True


class ComputerUseGateway:
    """未来自动化的权限边界；第一阶段始终拒绝执行。"""

    def execute(self, plan: ExecutionPlan) -> None:
        raise PermissionError("第一阶段安全模式禁止执行任何输入、点击或发送操作。")

