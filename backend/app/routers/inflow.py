"""进水监控接口：维护进水记录，覆盖超标预警、处置闭环、挂起恢复与值班长退回。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inflow import STATUSES, InflowService

router = APIRouter(prefix="/api/inflow", tags=["进水监控"])

service = InflowService()

LIST_FIELDS = ["记录编号", "所属厂站", "监测时间", "进水量", "COD浓度", "氨氮浓度", "pH值"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="在控、预警、挂起、已处置"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号与状态过滤进水监控列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def entry_stats() -> dict[str, int]:
    """看板卡片：在控、预警、挂起、已处置各有多少条。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出进水监控清单：返回当前全量数据，状态口径与列表页一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "inflow", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条进水记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"进水记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条进水记录；指标超阈值时必须同时指派处置人员并直接进入预警。"""
    entry, error = service.create_entry(
        payload.values, operator=payload.operator or "", remark=payload.remark or ""
    )
    if entry is None:
        return ActionResult(ok=False, message=error or "进水记录登记失败")
    return ActionResult(ok=True, message=error, entry=service.get_entry(int(entry["id"])))


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条进水记录执行转预警、处置完成、挂起、恢复处置、退回；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(
        entry_id,
        action,
        payload.values,
        operator=payload.operator or "",
        role=payload.role or "",
        remark=payload.remark or "",
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.get_entry(entry_id))
