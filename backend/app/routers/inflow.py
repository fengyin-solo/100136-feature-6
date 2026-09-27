"""进水监控接口：维护进水记录，覆盖阈值转预警、派单、挂起/恢复、完成处置与值班长退回。

状态口径只有一个：列表接口与预警弹窗都读取记录的 status 字段，
保证「同一条进水监控在监测列表页与预警弹窗里显示的状态一样」。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inflow import (
    NH3_N_LIMIT,
    PH_MAX,
    PH_MIN,
    SHIFT_LEADER,
    InflowService,
)

router = APIRouter(prefix="/api/inflow", tags=["进水监控"])

service = InflowService()

# 列表展示列保留原字段名；状态另起「状态」列，统一取后端 status
LIST_FIELDS = ["记录编号", "所属厂站", "监测时间", "进水量", "COD浓度", "氨氮浓度", "pH值", "状态"]
STATUSES = ["在控", "预警", "已挂起", "已处置"]


def _operator(values: dict[str, Any]) -> str | None:
    return values.get("operator") or values.get("操作人")


def _fail(message: str) -> ActionResult:
    return ActionResult(ok=False, message=message)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="在控、预警、已挂起、已处置"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号与状态过滤进水监控列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/thresholds")
def thresholds() -> dict[str, Any]:
    """返回预警阈值口径，前端弹窗与列表共用同一套判定标准。"""
    return {"pH区间": [PH_MIN, PH_MAX], "氨氮浓度上限": NH3_N_LIMIT, "退回角色": SHIFT_LEADER}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出进水监控清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "inflow", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条进水记录明细（含操作时间线）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"进水记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条进水记录；pH 或氨氮超阈值时必须转预警并指派处置人员。"""
    values = dict(payload.values)
    if payload.remark:
        values.setdefault("remark", payload.remark)
    entry, message = service.create_entry(values)
    if entry is None:
        return _fail(message)
    return ActionResult(ok=True, message="进水记录已登记", entry=entry)


@router.post("/{entry_id}/warn", response_model=ActionResult)
def warn_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """转预警：仅在指标超阈值时允许，且必须派给具体处置人员。"""
    values = payload.values
    entry, message = service.warn(
        entry_id,
        assignee=str(values.get("指派处置人员") or ""),
        operator=_operator(values),
        remark=values.get("remark") or payload.remark,
    )
    if entry is None:
        return _fail(message)
    return ActionResult(ok=True, message="已转为预警并完成派单", entry=entry)


@router.post("/{entry_id}/suspend", response_model=ActionResult)
def suspend_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """中途挂起处置：必须填写挂起原因，记录保留恢复入口。"""
    values = payload.values
    entry, message = service.suspend(
        entry_id,
        reason=str(values.get("挂起原因") or ""),
        operator=_operator(values),
        remark=values.get("remark") or payload.remark,
    )
    if entry is None:
        return _fail(message)
    return ActionResult(ok=True, message="处置已挂起，可随时恢复", entry=entry)


@router.post("/{entry_id}/resume", response_model=ActionResult)
def resume_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """从挂起恢复，回到预警继续处置。"""
    values = payload.values
    entry, message = service.resume(
        entry_id,
        operator=_operator(values),
        remark=values.get("remark") or payload.remark,
    )
    if entry is None:
        return _fail(message)
    return ActionResult(ok=True, message="已恢复处置，回到预警", entry=entry)


@router.post("/{entry_id}/complete", response_model=ActionResult)
def complete_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """标记已处置：处置措施与结果为空时一律拦下，不允许处置没完成就结单。"""
    values = payload.values
    entry, message = service.complete(
        entry_id,
        result=str(values.get("处置结果") or ""),
        operator=_operator(values),
        remark=values.get("remark") or payload.remark,
    )
    if entry is None:
        return _fail(message)
    return ActionResult(ok=True, message="处置完成，已标记已处置", entry=entry)


@router.post("/{entry_id}/reject", response_model=ActionResult)
def reject_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """值班长退回：已处置记录回到预警，进水量与监测时间保持不变。"""
    values = payload.values
    entry, message = service.reject(
        entry_id,
        role=values.get("角色") or values.get("role"),
        operator=_operator(values),
        remark=values.get("退回原因") or values.get("remark") or payload.remark,
    )
    if entry is None:
        return _fail(message)
    return ActionResult(ok=True, message="值班长已退回，记录回到预警", entry=entry)


@router.patch("/{entry_id}/readings", response_model=ActionResult)
def update_readings(entry_id: int, payload: EntryPayload) -> ActionResult:
    """补录/复核进水指标；复核后超阈值必须转预警并指派处置人员。"""
    values = dict(payload.values)
    if payload.remark:
        values.setdefault("remark", payload.remark)
    entry, message = service.update_readings(entry_id, values, operator=_operator(values))
    if entry is None:
        return _fail(message)
    return ActionResult(ok=True, message="进水指标已复核", entry=entry)
