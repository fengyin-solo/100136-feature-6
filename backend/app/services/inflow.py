"""进水监控业务规则：在控 → 预警 → 已处置 的状态流转、阈值判定、派单与交班留痕都收在这里。

状态约定（列表页与预警弹窗统一取 status，避免两处口径不一致）：
- 在控：正常监控中；
- 预警：pH 值或氨氮浓度超过阈值，必须指派具体处置人员；
- 已挂起：处置中途暂停，保留恢复入口，不改变在控/预警的主线状态；
- 已处置：处置完成；已处置记录改结论只能由值班长退回，退回后回到预警。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "inflow"
REQUIRED_FIELDS = ["记录编号", "所属厂站", "监测时间"]
# 登记时可提交的指标字段；进水量与监测时间一经登记不再被后续编辑改动
EDITABLE_FIELDS = ["进水量", "COD浓度", "氨氮浓度", "pH值"]

# 进水监控状态：主线在控 → 预警 → 已处置，挂起为中途的暂停态
STATUS_CONTROLLED = "在控"
STATUS_WARNING = "预警"
STATUS_SUSPENDED = "已挂起"
STATUS_DISPOSED = "已处置"
STATUS_ORDER = [STATUS_CONTROLLED, STATUS_WARNING, STATUS_SUSPENDED, STATUS_DISPOSED]

# 触发预警的指标阈值：pH 正常区间 6~9；氨氮浓度上限 45mg/L
PH_MIN, PH_MAX = 6.0, 9.0
NH3_N_LIMIT = 45.0

# 值班长角色：已处置记录的退回操作只对值班长开放
SHIFT_LEADER = "值班长"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _as_float(value: Any) -> float | None:
    """从 '8.6'、'42mg/L' 之类的填报值里取出数字；取不到就当作未填报。"""
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def exceed_reasons(values: dict[str, Any]) -> list[str]:
    """按阈值判定进水指标是否超标，返回超标的指标说明；空列表表示在控范围内。"""
    reasons: list[str] = []
    ph = _as_float(values.get("pH值"))
    if ph is not None and not (PH_MIN <= ph <= PH_MAX):
        reasons.append(f"pH值 {ph:g} 超出正常区间 {PH_MIN:g}~{PH_MAX:g}")
    nh3n = _as_float(values.get("氨氮浓度"))
    if nh3n is not None and nh3n > NH3_N_LIMIT:
        reasons.append(f"氨氮浓度 {nh3n:g}mg/L 超过阈值 {NH3_N_LIMIT:g}mg/L")
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
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ---- 登记 ----------------------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        rows = store.rows(MODULE)
        if any(str(row.get("记录编号")) == str(values["记录编号"]).strip() for row in rows):
            return None, f"记录编号 {values['记录编号']} 已存在，请勿重复登记"

        reasons = exceed_reasons(values)
        assignee = str(values.get("指派处置人员") or "").strip()
        # 超过阈值时必须转预警并派给具体处置人员，不允许以在控状态绕过
        if reasons and not assignee:
            return None, "pH值或氨氮浓度已超过阈值，必须转为预警并指派具体处置人员"

        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field) or "").strip() for field in REQUIRED_FIELDS})
        entry.update({field: values.get(field) for field in EDITABLE_FIELDS})
        entry["指派处置人员"] = assignee
        entry["超标指标"] = "；".join(reasons)
        entry["处置结果"] = ""
        entry["挂起原因"] = ""
        entry["timeline"] = []
        self._apply(entry, STATUS_WARNING if reasons else STATUS_CONTROLLED)
        self._log(
            entry,
            "转预警" if reasons else "登记",
            values.get("operator"),
            values.get("remark") or ("；".join(reasons) if reasons else "进水监控登记，状态在控"),
        )
        rows.append(entry)
        return entry, ""

    # ---- 状态流转 -------------------------------------------------------------

    def warn(
        self,
        entry_id: int,
        *,
        assignee: str,
        operator: str | None = None,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进水记录 {entry_id} 不存在或已归档"
        if entry["status"] == STATUS_DISPOSED:
            return None, "已处置记录不能直接改判预警，需由值班长退回后再处置"
        if not assignee.strip():
            return None, "转预警必须指派具体处置人员"
        # 手工转预警也要满足阈值前提，避免预警被滥用
        reasons = exceed_reasons(entry)
        if not reasons:
            return None, "当前 pH 值与氨氮浓度均在阈值内，不满足转预警条件"
        entry["指派处置人员"] = assignee.strip()
        entry["超标指标"] = "；".join(reasons)
        self._apply(entry, STATUS_WARNING)
        self._log(entry, "转预警", operator, remark or entry["超标指标"], assignee=assignee.strip())
        return entry, ""

    def suspend(
        self,
        entry_id: int,
        *,
        reason: str,
        operator: str | None = None,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进水记录 {entry_id} 不存在或已归档"
        if entry["status"] != STATUS_WARNING:
            return None, "只有预警中的进水记录可以挂起处置"
        if not reason.strip():
            return None, "挂起必须填写挂起原因，便于交班时说明情况"
        entry["挂起原因"] = reason.strip()
        # 记住挂起前的主线状态（预警），恢复时原样回去
        entry["resume_to"] = STATUS_WARNING
        self._apply(entry, STATUS_SUSPENDED)
        self._log(entry, "挂起", operator, remark or reason.strip())
        return entry, ""

    def resume(
        self,
        entry_id: int,
        *,
        operator: str | None = None,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进水记录 {entry_id} 不存在或已归档"
        if entry["status"] != STATUS_SUSPENDED:
            return None, "只有已挂起的进水记录需要恢复"
        target = entry.pop("resume_to", STATUS_WARNING)
        entry["挂起原因"] = ""
        self._apply(entry, target)
        self._log(entry, "恢复", operator, remark or "处置恢复，回到预警继续跟进")
        return entry, ""

    def complete(
        self,
        entry_id: int,
        *,
        result: str,
        operator: str | None = None,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进水记录 {entry_id} 不存在或已归档"
        if entry["status"] == STATUS_SUSPENDED:
            return None, "处置处于挂起状态，请先恢复后再标记已处置"
        if entry["status"] != STATUS_WARNING:
            return None, "只有预警中的进水记录在处置完成后才能标记已处置"
        if not result.strip():
            return None, "处置未完成：请填写处置措施与结果后再标记已处置"
        entry["处置结果"] = result.strip()
        self._apply(entry, STATUS_DISPOSED)
        self._log(entry, "标记已处置", operator, remark or result.strip())
        return entry, ""

    def reject(
        self,
        entry_id: int,
        *,
        role: str | None = None,
        operator: str | None = None,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """值班长退回已处置记录：回到预警，进水量与监测时间保持不变。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进水记录 {entry_id} 不存在或已归档"
        if (role or "").strip() != SHIFT_LEADER:
            return None, "已处置记录改结论必须由值班长退回"
        if entry["status"] != STATUS_DISPOSED:
            return None, "只有已处置的记录可以退回"
        if not str(remark or "").strip():
            return None, "退回必须填写退回原因，留给接手的处置人员查看"
        if not str(entry.get("指派处置人员") or "").strip():
            return None, "退回需要明确处置人员，请先指派再退回"
        entry["处置结果"] = ""
        self._apply(entry, STATUS_WARNING)
        self._log(entry, "值班长退回", operator, str(remark).strip())
        return entry, ""

    # ---- 指标复核 -------------------------------------------------------------

    def update_readings(
        self,
        entry_id: int,
        values: dict[str, Any],
        *,
        operator: str | None = None,
        remark: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """补录/复核进水指标。一旦超过阈值：自动转预警并要求指派处置人员。

        进水量允许在此补录；监测时间一经登记固定不变，不在可改字段内。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进水记录 {entry_id} 不存在或已归档"
        if entry["status"] == STATUS_DISPOSED:
            return None, "已处置记录不能直接改结论或指标，需由值班长退回"

        for field in EDITABLE_FIELDS:
            if field in values and values.get(field) is not None:
                entry[field] = values.get(field)

        reasons = exceed_reasons(entry)
        if reasons:
            assignee = str(values.get("指派处置人员") or entry.get("指派处置人员") or "").strip()
            if not assignee:
                return None, "复核指标已超过阈值，必须指派具体处置人员后才能转预警"
            entry["指派处置人员"] = assignee
            entry["超标指标"] = "；".join(reasons)
            self._apply(entry, STATUS_WARNING)
            self._log(entry, "指标复核转预警", operator, remark or entry["超标指标"], assignee=assignee)
        else:
            entry["超标指标"] = ""
            self._log(entry, "指标复核", operator, remark or "进水指标复核，仍在阈值内")
        return entry, ""

    # ---- 内部工具 -------------------------------------------------------------

    def _apply(self, entry: dict[str, Any], status: str) -> None:
        entry["status"] = status
        # pending 供运营概览统计：预警与挂起都算待处理
        entry["pending"] = status in (STATUS_WARNING, STATUS_SUSPENDED)
        entry["abnormal"] = status in (STATUS_WARNING, STATUS_SUSPENDED)

    def _log(
        self,
        entry: dict[str, Any],
        action: str,
        operator: str | None = None,
        remark: str | None = None,
        *,
        assignee: str | None = None,
    ) -> None:
        """追加一条操作留痕；交班后新接手的人靠时间线看到每一步的操作人与时间、备注。"""
        entry.setdefault("timeline", []).append({
            "时间": _now(),
            "动作": action,
            "操作人": str(operator or "值班人员").strip(),
            "处置人员": assignee if assignee is not None else str(entry.get("指派处置人员") or ""),
            "备注": str(remark or "").strip(),
        })
