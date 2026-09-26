"""占道掘路许可接口：登记占道申请，覆盖受理申请、批准许可、恢复验收、归档许可等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.occupy import OccupyService

router = APIRouter(prefix="/api/occupy", tags=["占道掘路许可"])

service = OccupyService()

LIST_FIELDS = ["许可编号", "申请编号", "申请单位", "占道掘路路段", "占用时段", "恢复要求", "随附材料", "许可状态"]
STATUSES = ["待受理", "审核中", "已批许可", "已恢复验收", "已归档"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按许可编号、申请编号或路段检索"),
    status: str | None = Query(default=None, description="待受理、审核中、已批许可、已恢复验收、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按关键字与状态过滤占道掘路许可列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出占道掘路许可清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "occupy", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条占道掘路许可明细（含流转记录）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"占道掘路许可 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记占道申请：缺字段说明原因退回，重复提交不再生效，每次提交都给出回执。"""
    entry, receipt, message = service.create_entry(payload.values)
    return ActionResult(ok=receipt.get("结论") != "退回", message=message, entry=entry, receipt=receipt)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条许可执行受理申请、批准许可、恢复验收、归档许可；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
