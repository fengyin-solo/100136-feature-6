"""进水监控业务规则：状态流转、超标判定、处置闭环与交接留痕都收在这里。

状态机：
    在控 ──转预警(必须指派处置人)──▶ 预警 ──处置完成(必须有处置结论)──▶ 已处置
                                     │  ▲                              │
                                   挂起│  └──恢复处置──────────────────┤
                                     ▼  │                              │
                                    挂起 ┘                              │
                                          已处置 ──退回(仅值班长)──▶ 预警

登记时若 pH 值或氨氮浓度超过阈值，必须直接转为预警并指派处置人员。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "inflow"
REQUIRED_FIELDS = ["记录编号", "所属厂站", "监测时间"]
BUSINESS_FIELDS = ["记录编号", "所属厂站", "监测时间", "进水量", "COD浓度", "氨氮浓度", "pH值"]

# 在控 → 预警 → 已处置为主线；挂起是预警中途的暂停分支
STATUSES = ["在控", "预警", "挂起", "已处置"]

# 进水指标阈值：pH 超出 6.0–9.0 区间或氨氮浓度高于 30 mg/L 即判定超标
PH_MIN, PH_MAX = 6.0, 9.0
NH3N_LIMIT = 30.0

# 退回只能回退状态，不允许顺手改动原始监测事实
IMMUTABLE_ON_RETURN = ["进水量", "监测时间"]

ACTION_RULES: dict[str, dict[str, Any]] = {
    "转预警": {"from": ("在控",), "to": "预警"},
    "处置完成": {"from": ("预警",), "to": "已处置"},
    "挂起": {"from": ("预警",), "to": "挂起"},
    "恢复处置": {"from": ("挂起",), "to": "预警"},
    "退回": {"from": ("已处置",), "to": "预警", "role": "值班长"},
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def exceed_reasons(entry: dict[str, Any]) -> list[str]:
    """根据阈值判定 pH、氨氮是否超标，返回可读的超标原因列表。"""
    reasons: list[str] = []
    ph = _to_float(entry.get("pH值"))
    if ph is not None and not (PH_MIN <= ph <= PH_MAX):
        reasons.append(f"pH值 {ph} 超出 {PH_MIN}–{PH_MAX} 允许区间")
    nh3n = _to_float(entry.get("氨氮浓度"))
    if nh3n is not None and nh3n > NH3N_LIMIT:
        reasons.append(f"氨氮浓度 {nh3n} 超过限值 {NH3N_LIMIT} mg/L")
    return reasons


class InflowService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate(row) for row in rows[start:start + size]], total

    def stats(self) -> dict[str, int]:
        rows = store.rows(MODULE)
        return {status: sum(1 for row in rows if row.get("status") == status) for status in STATUSES}

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._decorate(entry) if entry is not None else None

    def create_entry(
        self,
        values: dict[str, Any],
        *,
        operator: str = "",
        remark: str = "",
    ) -> tuple[dict[str, Any] | None, str | None]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in BUSINESS_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["处置人员"] = ""
        entry["处置结论"] = ""
        entry["history"] = []

        reasons = exceed_reasons(entry)
        if reasons:
            # 超标即必须转预警并派给具体处置人员，不允许只登记不处置
            assignee = str(values.get("处置人员") or "").strip()
            if not assignee:
                return None, f"{'；'.join(reasons)}，必须转成预警并指派具体处置人员"
            entry["处置人员"] = assignee
            entry["status"] = "预警"
            entry["pending"] = True
            entry["abnormal"] = True
            rows.append(entry)
            self._log(entry, "登记转预警", operator, remark or "；".join(reasons))
            return entry, "监测指标超标，已登记并转预警"

        entry["status"] = "在控"
        entry["pending"] = False
        entry["abnormal"] = False
        rows.append(entry)
        self._log(entry, "登记", operator, remark)
        return entry, "进水记录已登记，状态为在控"

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any],
        *,
        operator: str = "",
        role: str = "",
        remark: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进水记录 {entry_id} 不存在或已归档"
        rule = ACTION_RULES.get(action)
        if rule is None:
            return None, f"动作「{action}」不属于进水监控可执行范围"
        current = str(entry.get("status"))
        if current not in rule["from"]:
            allowed = "、".join(rule["from"])
            return None, f"当前状态为「{current}」，「{action}」只能在{allowed}状态下执行"
        required_role = rule.get("role")
        if required_role and role != required_role:
            return None, f"已处置记录改结论属于退回操作，只能由{required_role}执行"

        assignee = str(values.get("处置人员") or "").strip()
        conclusion = str(values.get("处置结论") or "").strip()

        if action == "转预警":
            if not assignee:
                return None, "转预警必须派给具体处置人员，请填写处置人员"
            entry["处置人员"] = assignee
        elif action == "处置完成":
            # 处置没完成（没有处置结论）就不允许标记已处置
            if not conclusion:
                return None, "处置尚未完成：请先登记处置结论，再标记已处置"
            entry["处置结论"] = conclusion
        elif action == "挂起":
            if not remark.strip():
                return None, "挂起必须填写挂起原因，方便恢复时交接"
        elif action == "退回":
            if not remark.strip():
                return None, "退回必须填写退回原因，回到预警后由处置人继续跟进"
            for field in IMMUTABLE_ON_RETURN:
                incoming = values.get(field)
                if incoming is not None and str(incoming).strip() != str(entry.get(field) or ""):
                    return None, f"退回只回退处置状态，{field}必须保持原值不变"

        target = rule["to"]
        entry["status"] = target
        entry["pending"] = target in ("预警", "挂起")
        entry["abnormal"] = target in ("预警", "挂起")
        self._log(entry, action, operator, remark)
        if action == "退回":
            # 原结论作废，但保留在历史备注里可追溯；处置人员仍为原责任人
            entry["处置结论"] = ""
        return entry, f"进水记录已{action}"

    def _log(self, entry: dict[str, Any], action: str, operator: str, remark: str) -> None:
        entry.setdefault("history", []).append(
            {"at": _now(), "operator": operator.strip() or "未留名", "action": action, "remark": remark.strip()}
        )

    def _decorate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表与详情共用同一份状态口径，避免两个页面显示不一致。"""
        row = dict(entry)
        reasons = exceed_reasons(entry)
        row["exceeded"] = bool(reasons)
        row["exceed_reasons"] = "；".join(reasons)
        row["available_actions"] = [
            name for name, rule in ACTION_RULES.items() if entry.get("status") in rule["from"]
        ]
        history = list(entry.get("history") or [])
        row["history"] = history
        row["last_op"] = (
            f"{history[-1]['at']} · {history[-1]['operator']} · {history[-1]['action']}"
            if history
            else ""
        )
        return row
