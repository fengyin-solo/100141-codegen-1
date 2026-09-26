"""占道掘路许可业务规则：登记校验、五档流转、留痕与回执口径都收在这里。

许可状态只沿「待受理 → 审核中 → 已批许可 → 已恢复验收 → 已归档」向前流转，
「已退回」是链外状态：申请被退回后只能通过补正提交重新回到待受理，
链内状态一经前进不允许回到上一档。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "occupy"
STATUS_ORDER = ["待受理", "审核中", "已批许可", "已恢复验收", "已归档"]
RETURNED_STATUS = "已退回"
REQUIRED_FIELDS = ["申请编号", "路段", "申请人"]
ENTRY_FIELDS = ["申请编号", "路段", "占用时段", "恢复要求", "随附材料", "申请人"]
# 占用时段、恢复要求为空时不直接拒收，而是说明原因退回，给补正留入口
RETURN_FIELDS = ["占用时段", "恢复要求"]
CHAIN_ACTIONS = {"受理": "审核中", "批准": "已批许可", "恢复验收": "已恢复验收", "归档": "已归档"}
SIDE_ACTIONS = ["退回", "补正提交"]
PASS_WORDS = ("符合", "通过")
FAIL_WORDS = ("不符合", "未通过")

# 提交时的「查重再登记」必须整体串行，否则多人同时提交同一份申请会各自生效
_submit_lock = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _history(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return entry.setdefault("流转记录", [])


def _record(entry: dict[str, Any], *, action: str, operator: str, note: str) -> None:
    _history(entry).append({"时间": _now(), "经办人": operator, "动作": action, "说明": note})


def _refresh_flags(entry: dict[str, Any]) -> None:
    entry["pending"] = entry.get("status") != STATUS_ORDER[-1]
    entry["abnormal"] = entry.get("status") == RETURNED_STATUS


def _find_by_application(application_no: str) -> dict[str, Any] | None:
    for row in store.rows(MODULE):
        if str(row.get("申请编号", "")) == application_no:
            return row
    return None


def _next_permit_no(rows: list[dict[str, Any]]) -> str:
    seq = max((int(row.get("id", 0)) for row in rows), default=0) + 1
    return f"OCCU-{seq:04d}"


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
                if keyword in str(row.get("许可编号", "")) or keyword in str(row.get("路段", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def submit_entry(self, values: dict[str, Any]) -> tuple[bool, str, dict[str, Any] | None]:
        """登记一份占道申请并给出回执；同一份申请重复提交只生效一次。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return False, f"缺少必填字段：{'、'.join(missing)}", None
        operator = str(values.get("经办人") or "").strip()
        if not operator:
            return False, "请填写经办人，提交与流转每一步都要留痕", None
        application_no = str(values.get("申请编号") or "").strip()
        with _submit_lock:
            existing = _find_by_application(application_no)
            if existing is not None:
                message = (
                    f"申请 {application_no} 已登记为许可 {existing.get('许可编号')}"
                    f"（当前状态：{existing.get('status')}），重复提交不再生效"
                )
                if existing.get("status") == RETURNED_STATUS:
                    message += "；该申请已退回，请通过「补正提交」完善材料"
                return True, message, existing
            rows = store.rows(MODULE)
            entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            entry["许可编号"] = _next_permit_no(rows)
            entry.update({field: values.get(field) for field in ENTRY_FIELDS})
            entry["流转记录"] = []
            _record(entry, action="提交登记", operator=operator, note="占道掘路申请已登记，等待受理")
            lacking = [field for field in RETURN_FIELDS if not str(values.get(field) or "").strip()]
            if lacking:
                reason = "、".join(f"{field}为空" for field in lacking)
                entry["status"] = RETURNED_STATUS
                _record(entry, action="退回", operator=operator, note=f"{reason}，说明原因后退回，请补正后重新提交")
                _refresh_flags(entry)
                rows.append(entry)
                return False, f"{reason}，已说明原因退回（许可编号 {entry['许可编号']}），请通过「补正提交」完善后重新进入受理", entry
            entry["status"] = STATUS_ORDER[0]
            _refresh_flags(entry)
            rows.append(entry)
            return True, f"占道申请已受理登记，许可编号 {entry['许可编号']}，当前状态：待受理", entry

    def submit_batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """多人同时提交时逐条给出回执，单条失败不影响其他条目。"""
        receipts: list[dict[str, Any]] = []
        for index, values in enumerate(items, start=1):
            ok, message, entry = self.submit_entry(values)
            receipts.append({
                "序号": index,
                "申请编号": str(values.get("申请编号") or ""),
                "ok": ok,
                "message": message,
                "entry": entry,
            })
        return receipts

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        """推进或许可外动作；链内状态只能前进一档，回退一律拦下。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"占道许可 {entry_id} 不存在或已归档"
        operator = str(values.get("经办人") or "").strip()
        if not operator:
            return None, "请填写经办人，流转每一步都要留下经办人与时间"
        if action in CHAIN_ACTIONS:
            return self._advance(entry, action, operator, values)
        if action == "退回":
            return self._return(entry, operator, values)
        if action == "补正提交":
            return self._resubmit(entry, operator, values)
        return None, f"动作「{action}」不属于占道掘路许可可执行范围"

    def _advance(
        self,
        entry: dict[str, Any],
        action: str,
        operator: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        current = str(entry.get("status") or "")
        if current == RETURNED_STATUS:
            return None, f"许可 {entry.get('许可编号')} 已退回，请先补正提交再流转"
        if current not in STATUS_ORDER:
            return None, f"许可当前状态「{current}」不在允许的状态序列里"
        target = CHAIN_ACTIONS[action]
        if STATUS_ORDER.index(target) != STATUS_ORDER.index(current) + 1:
            return None, f"许可当前状态为「{current}」，不能{action}，状态只能逐档前进、不能回退"
        if action == "恢复验收":
            conclusion = str(values.get("验收结论") or "").strip()
            if not conclusion:
                return None, "恢复验收必须对照恢复要求填写验收结论"
            if any(word in conclusion for word in FAIL_WORDS):
                entry["abnormal"] = True
                _record(entry, action="恢复验收不通过", operator=operator, note=f"验收结论「{conclusion}」与恢复要求对不上，维持已批许可，整改后重新验收")
                return None, "验收结论为不符合恢复要求，许可维持已批许可，请整改后重新验收"
            if not any(word in conclusion for word in PASS_WORDS):
                return None, "验收结论要明确写出是否符合恢复要求（包含「符合」或「通过」）"
            entry["验收结论"] = conclusion
            note = f"对照恢复要求「{entry.get('恢复要求')}」验收通过，结论：{conclusion}"
            entry["status"] = target
            _record(entry, action=action, operator=operator, note=note)
            _refresh_flags(entry)
            return entry, f"许可 {entry.get('许可编号')} 恢复验收通过，进入已恢复验收"
        entry["status"] = target
        _record(entry, action=action, operator=operator, note=f"许可{action}，状态流转为{target}")
        _refresh_flags(entry)
        return entry, f"许可 {entry.get('许可编号')} 已{action}，当前状态：{target}"

    def _return(
        self,
        entry: dict[str, Any],
        operator: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        current = str(entry.get("status") or "")
        if current not in STATUS_ORDER[:2]:
            return None, f"许可当前状态为「{current}」，只有待受理、审核中可以退回"
        reason = str(values.get("退回原因") or "").strip()
        if not reason:
            return None, "退回必须说明原因"
        entry["status"] = RETURNED_STATUS
        _record(entry, action="退回", operator=operator, note=f"退回原因：{reason}")
        _refresh_flags(entry)
        return entry, f"许可 {entry.get('许可编号')} 已退回：{reason}"

    def _resubmit(
        self,
        entry: dict[str, Any],
        operator: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != RETURNED_STATUS:
            return None, f"许可当前状态为「{entry.get('status')}」，只有已退回的申请需要补正提交"
        lacking = [field for field in RETURN_FIELDS if not str(values.get(field) or "").strip()]
        if lacking:
            return None, f"补正材料仍缺少：{'、'.join(lacking)}，请补齐后再提交"
        for field in ENTRY_FIELDS:
            if field == "申请编号":
                continue  # 申请编号是查重键，补正不允许改写
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        _record(entry, action="补正提交", operator=operator, note="补正材料已齐全，重新进入待受理")
        _refresh_flags(entry)
        return entry, f"许可 {entry.get('许可编号')} 补正完成，重新进入待受理"
