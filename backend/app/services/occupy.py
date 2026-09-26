"""占道掘路许可业务规则：登记校验、幂等去重、状态只进不退与恢复验收核对。"""
from __future__ import annotations

import re
import threading
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "occupy"
LIST_FIELDS = ["许可编号", "申请编号", "申请单位", "占道掘路路段", "占用时段", "恢复要求", "随附材料", "许可状态"]

# 必填项与退回原因：占用时段、恢复要求是许可的硬约束，空着必须说明原因再退回。
FIELD_REASONS = {
    "申请编号": "申请编号为空：同一份占道申请要靠它甄别，缺了无法防止重复生效，请补充后重新提交",
    "申请单位": "申请单位为空：许可主体不明确，后续恢复责任无法落实，请补充后重新提交",
    "占道掘路路段": "占道掘路路段为空：无法核定占道位置与交通影响范围，请补充后重新提交",
    "占用时段": "占用时段为空：无法核定占道起止与交通组织安排，请补充起止时间后重新提交",
    "恢复要求": "恢复要求为空：掘路后路面的恢复标准缺失，恢复验收将无据可依，请补充后重新提交",
    "随附材料": "随附材料为空：掘路方案、交通组织方案等是受理审核的依据，请补充后重新提交",
}

STATUS_ORDER = ["待受理", "审核中", "已批许可", "已恢复验收", "已归档"]
ACTION_RULES = {"受理申请": "审核中", "批准许可": "已批许可", "恢复验收": "已恢复验收", "归档许可": "已归档"}
NEGATIVE_ACTIONS: list[str] = []

# 多人同时提交时，查重、发号、写回执必须串行，回执逐条发放互不覆盖。
_lock = threading.Lock()
_receipt_seq = 0


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_receipt_no() -> str:
    global _receipt_seq
    _receipt_seq += 1
    return f"RCPT-{datetime.now():%Y%m%d}-{_receipt_seq:04d}"


def _requirement_items(text: str) -> list[str]:
    """把恢复要求拆成逐项条目，恢复验收结论要逐项对得上。"""
    return [part.strip() for part in re.split(r"[、；;。，,\n]+", text or "") if part.strip()]


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


class OccupyService:
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
            rows = [
                row
                for row in rows
                if keyword in str(row.get("许可编号", ""))
                or keyword in str(row.get("申请编号", ""))
                or keyword in str(row.get("占道掘路路段", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
        """登记占道申请：缺项带原因退回；同一申请编号重复提交只生效一次；每次都回执。"""
        operator = str(values.get("经办人") or "").strip() or "未留名经办"
        with _lock:
            receipt: dict[str, Any] = {
                "回执编号": _next_receipt_no(),
                "申请编号": str(values.get("申请编号") or "").strip(),
                "经办人": operator,
                "时间": _now(),
            }
            reasons = [reason for field, reason in FIELD_REASONS.items() if not str(values.get(field) or "").strip()]
            if reasons:
                receipt["结论"] = "退回"
                receipt["说明"] = "；".join(reasons)
                return None, receipt, receipt["说明"]
            for row in store.rows(MODULE):
                if row.get("申请编号") == receipt["申请编号"]:
                    receipt["结论"] = "重复提交"
                    receipt["许可编号"] = row.get("许可编号")
                    receipt["说明"] = f"该占道申请已登记为{row.get('许可编号')}，本次重复提交不再生效"
                    return row, receipt, receipt["说明"]
            rows = store.rows(MODULE)
            entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            entry["许可编号"] = f"OCCU-{entry['id']:04d}"
            for field in LIST_FIELDS:
                if field in ("许可编号", "许可状态"):
                    continue
                entry[field] = str(values.get(field) or "").strip()
            entry["status"] = STATUS_ORDER[0]
            entry["许可状态"] = STATUS_ORDER[0]
            entry["pending"] = True
            entry["abnormal"] = False
            entry["timeline"] = [{
                "动作": "登记申请",
                "状态从": "—",
                "状态到": STATUS_ORDER[0],
                "经办人": operator,
                "时间": receipt["时间"],
                "说明": f"占道申请登记，回执{receipt['回执编号']}",
            }]
            rows.append(entry)
            receipt["结论"] = "新登记"
            receipt["许可编号"] = entry["许可编号"]
            receipt["说明"] = f"占道申请已登记，许可编号{entry['许可编号']}，状态{STATUS_ORDER[0]}"
            return entry, receipt, receipt["说明"]

    def run_action(self, entry_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """许可流转：逐级向前、只进不退，每一步留下经办人与时间。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"占道掘路许可 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于占道掘路许可可执行范围"
        operator = str(values.get("经办人") or "").strip()
        if not operator:
            return None, "请提供经办人：许可流转的每一步都要留下经办人与时间"
        current = str(entry.get("status") or "")
        target = ACTION_RULES[action]
        if current not in STATUS_ORDER or target not in STATUS_ORDER:
            return None, "许可状态不在允许的状态序列里"
        current_idx = STATUS_ORDER.index(current)
        target_idx = STATUS_ORDER.index(target)
        if target_idx <= current_idx:
            return None, f"许可当前状态为「{current}」，状态只进不退，不能回到「{target}」"
        if target_idx > current_idx + 1:
            return None, f"许可需按「{'→'.join(STATUS_ORDER)}」逐级流转，「{current}」不能跳过中间环节进入「{target}」"
        note = f"许可{action}"
        if action == "恢复验收":
            conclusion = str(values.get("验收结论") or "").strip()
            if not conclusion:
                return None, "恢复验收结论为空：请对照申请中的恢复要求逐项填写验收结论"
            missing = [
                item
                for item in _requirement_items(str(entry.get("恢复要求") or ""))
                if _squash(item) not in _squash(conclusion)
            ]
            if missing:
                return None, f"恢复验收结论与申请中的恢复要求对不上，未覆盖：{'、'.join(missing)}；请逐项核实后再提交"
            entry["验收结论"] = conclusion
            note = f"验收结论：{conclusion}"
        entry["status"] = target
        entry["许可状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry.setdefault("timeline", []).append({
            "动作": action,
            "状态从": current,
            "状态到": target,
            "经办人": operator,
            "时间": _now(),
            "说明": note,
        })
        return entry, f"占道掘路许可已{action}（{current}→{target}），经办人：{operator}"
