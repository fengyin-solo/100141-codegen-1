"""占道掘路许可接口：登记占道申请、批量提交回执、五档状态流转与退回补正。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, BatchPayload, BatchResult, EntryPayload, PageResult, Receipt
from app.services.occupy import OccupyService

router = APIRouter(prefix="/api/occupy", tags=["占道掘路许可"])

service = OccupyService()

LIST_FIELDS = ["许可编号", "申请编号", "路段", "占用时段", "恢复要求", "随附材料", "申请人", "状态"]
STATUSES = ["待受理", "审核中", "已批许可", "已恢复验收", "已归档", "已退回"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按许可编号或路段检索"),
    status: str | None = Query(default=None, description="待受理、审核中、已批许可、已恢复验收、已归档、已退回"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按许可编号/路段与状态过滤许可列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出占道掘路许可清单：返回当前全量数据。注册在 /{entry_id} 之前，避免被当成编号。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "occupy", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条许可明细（含流转记录）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"占道许可 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def submit_entry(payload: EntryPayload) -> ActionResult:
    """登记一份占道申请：重复提交只生效一次，占用时段或恢复要求为空会说明原因退回。"""
    ok, message, entry = service.submit_entry(payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/batch", response_model=BatchResult)
def submit_batch(payload: BatchPayload) -> BatchResult:
    """多人同时提交占道申请：逐条处理、逐条给出回执，单条失败不影响其他条目。"""
    if not payload.items:
        raise HTTPException(status_code=400, detail="批量提交至少要带一条占道申请")
    receipts = [Receipt(**receipt) for receipt in service.submit_batch(payload.items)]
    return BatchResult(ok=all(receipt.ok for receipt in receipts), receipts=receipts)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条许可执行受理、批准、恢复验收、归档、退回、补正提交；越档或回退会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
