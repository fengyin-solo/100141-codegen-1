<template>
  <section class="page" data-module="occupy">
    <header class="page-head">
      <div>
        <h2>占道掘路许可</h2>
        <p class="page-desc">登记占道掘路申请的路段、占用时段、恢复要求与随附材料，许可沿待受理、审核中、已批许可、已恢复验收、已归档逐档流转，每步留经办人与时间。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">
          {{ showCreate ? '收起登记表单' : '登记占道申请' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出许可清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="panel" @submit.prevent="submitCreate">
      <h3 class="panel-title">登记占道申请</h3>
      <div class="form-grid">
        <label class="form-item">
          <span>申请编号（重复提交只生效一次）</span>
          <input v-model="createForm.申请编号" readonly />
        </label>
        <label class="form-item">
          <span>路段 *</span>
          <input v-model="createForm.路段" placeholder="如：中山一路 K0+000~K0+180" />
        </label>
        <label class="form-item">
          <span>占用时段（为空将说明原因退回）</span>
          <input v-model="createForm.占用时段" placeholder="如：2026-10-08 至 2026-10-20 每日22:00-06:00" />
        </label>
        <label class="form-item">
          <span>恢复要求（为空将说明原因退回）</span>
          <input v-model="createForm.恢复要求" placeholder="如：按原路面结构恢复，沥青面层厚度不低于10cm" />
        </label>
        <label class="form-item">
          <span>随附材料</span>
          <input v-model="createForm.随附材料" placeholder="如：施工方案、交通组织方案" />
        </label>
        <label class="form-item">
          <span>申请人 *</span>
          <input v-model="createForm.申请人" placeholder="申请单位与联系人" />
        </label>
      </div>
      <div class="panel-actions">
        <button class="btn primary" type="submit" :disabled="submitting">
          {{ submitting ? '提交中…' : '提交申请' }}
        </button>
        <span class="panel-hint">网络重试或重复点击不会产生第二份许可，每份申请都会拿到回执。</span>
      </div>
    </form>

    <div v-if="receipts.length" class="panel">
      <h3 class="panel-title">提交回执（逐条）</h3>
      <ul class="receipt-list">
        <li v-for="(receipt, index) in receipts" :key="index" :class="receipt.ok ? 'receipt-ok' : 'receipt-bad'">
          <span class="receipt-time">{{ receipt.时间 }}</span>
          <span class="receipt-no">{{ receipt.申请编号 || '—' }}</span>
          <span>{{ receipt.message }}</span>
        </li>
      </ul>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>许可编号 / 路段</span>
        <input v-model="keyword" placeholder="按许可编号或路段检索" />
      </label>
      <label class="filter-item">
        <span>许可状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '状态'" class="badge" :data-status="row.status">{{ row.status }}</span>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="openHistory(row)">流转记录</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无占道掘路许可数据，可先登记占道申请</td>
        </tr>
      </tbody>
    </table>

    <div v-if="actionPanel" class="panel">
      <h3 class="panel-title">{{ actionPanel.action }} · {{ actionPanel.row.许可编号 }}</h3>
      <p v-if="actionPanel.action === '恢复验收'" class="panel-hint">
        请对照申请中的恢复要求验收：<strong>{{ actionPanel.row.恢复要求 || '（该申请未填写恢复要求）' }}</strong>
      </p>
      <div class="form-grid">
        <label v-if="actionPanel.action === '恢复验收'" class="form-item wide">
          <span>验收结论（需明确是否符合恢复要求）</span>
          <input v-model="actionPanel.input" placeholder="如：路面恢复符合恢复要求，验收通过" />
        </label>
        <label v-if="actionPanel.action === '退回'" class="form-item wide">
          <span>退回原因</span>
          <input v-model="actionPanel.input" placeholder="说明退回原因，告知申请人补正方向" />
        </label>
        <template v-if="actionPanel.action === '补正提交'">
          <label class="form-item">
            <span>占用时段 *</span>
            <input v-model="actionPanel.占用时段" placeholder="补正后的占用时段" />
          </label>
          <label class="form-item">
            <span>恢复要求 *</span>
            <input v-model="actionPanel.恢复要求" placeholder="补正后的恢复要求" />
          </label>
          <label class="form-item">
            <span>随附材料</span>
            <input v-model="actionPanel.随附材料" placeholder="补充的随附材料" />
          </label>
        </template>
      </div>
      <div class="panel-actions">
        <button class="btn primary" type="button" @click="confirmAction">确认{{ actionPanel.action }}</button>
        <button class="btn ghost" type="button" @click="actionPanel = null">取消</button>
      </div>
    </div>

    <div v-if="historyPanel" class="panel">
      <h3 class="panel-title">流转记录 · {{ historyPanel.许可编号 }}（当前状态：{{ historyPanel.status }}）</h3>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>经办人</th><th>动作</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="(step, index) in historyPanel.流转记录" :key="index">
            <td>{{ step.时间 }}</td>
            <td>{{ step.经办人 }}</td>
            <td>{{ step.动作 }}</td>
            <td>{{ step.说明 }}</td>
          </tr>
        </tbody>
      </table>
      <div class="panel-actions">
        <button class="btn ghost" type="button" @click="historyPanel = null">收起</button>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条占道掘路许可记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

interface HistoryStep {
  时间: string
  经办人: string
  动作: string
  说明: string
}

interface PermitRow {
  id: number
  许可编号: string
  申请编号: string
  路段: string
  占用时段: string
  恢复要求: string
  随附材料: string
  申请人: string
  验收结论?: string
  status: string
  pending: boolean
  abnormal: boolean
  流转记录?: HistoryStep[]
  [key: string]: unknown
}

interface ReceiptItem {
  时间: string
  申请编号: string
  ok: boolean
  message: string
}

interface ActionPanel {
  action: string
  row: PermitRow
  input: string
  占用时段: string
  恢复要求: string
  随附材料: string
}

const ENDPOINT = '/api/occupy'
const columns = ['许可编号', '申请编号', '路段', '占用时段', '恢复要求', '随附材料', '申请人', '状态']
const statuses = ['待受理', '审核中', '已批许可', '已恢复验收', '已归档', '已退回']
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  待受理: ['受理', '退回'],
  审核中: ['批准', '退回'],
  已批许可: ['恢复验收'],
  已恢复验收: ['归档'],
  已退回: ['补正提交'],
}

const session = useSessionStore()

const rows = ref<PermitRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const stats = ref([
  { label: '待受理许可', value: 0 },
  { label: '审核中许可', value: 0 },
  { label: '已批许可', value: 0 },
  { label: '已退回待补正', value: 0 },
])

const showCreate = ref(false)
const submitting = ref(false)
const createForm = ref({
  申请编号: newApplicationNo(),
  路段: '',
  占用时段: '',
  恢复要求: '',
  随附材料: '',
  申请人: '',
})
const receipts = ref<ReceiptItem[]>([])
const actionPanel = ref<ActionPanel | null>(null)
const historyPanel = ref<PermitRow | null>(null)

function newApplicationNo(): string {
  return `ZD-${Date.now()}-${Math.floor(Math.random() * 1000)}`
}

function actionsFor(row: PermitRow): string[] {
  return ACTIONS_BY_STATUS[row.status] ?? []
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function pushReceipt(ok: boolean, message: string, applicationNo: string) {
  receipts.value.unshift({
    时间: new Date().toLocaleString(),
    申请编号: applicationNo,
    ok,
    message,
  })
  receipts.value = receipts.value.slice(0, 10)
}

async function submitCreate() {
  if (submitting.value) {
    return
  }
  submitting.value = true
  errorMessage.value = ''
  const applicationNo = createForm.value.申请编号
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value, 经办人: session.operator } }),
    })
    const result = await response.json()
    pushReceipt(Boolean(result.ok), String(result.message ?? ''), applicationNo)
    if (result.ok) {
      // 上一份已生效，换下一份申请编号；未生效时保留编号，重试仍只生效一次
      createForm.value = {
        申请编号: newApplicationNo(),
        路段: '',
        占用时段: '',
        恢复要求: '',
        随附材料: '',
        申请人: '',
      }
    }
    await reload()
  } catch (error) {
    pushReceipt(false, error instanceof Error ? error.message : '提交失败', applicationNo)
  } finally {
    submitting.value = false
  }
}

function runAction(action: string, row: PermitRow) {
  errorMessage.value = ''
  if (action === '恢复验收' || action === '退回' || action === '补正提交') {
    actionPanel.value = {
      action,
      row,
      input: '',
      占用时段: row.占用时段,
      恢复要求: row.恢复要求,
      随附材料: row.随附材料,
    }
    return
  }
  void postAction(action, row, {})
}

async function confirmAction() {
  const panel = actionPanel.value
  if (!panel) {
    return
  }
  const extra: Record<string, string> = {}
  if (panel.action === '恢复验收') {
    extra['验收结论'] = panel.input
  } else if (panel.action === '退回') {
    extra['退回原因'] = panel.input
  } else if (panel.action === '补正提交') {
    extra['占用时段'] = panel.占用时段
    extra['恢复要求'] = panel.恢复要求
    extra['随附材料'] = panel.随附材料
  }
  const done = await postAction(panel.action, panel.row, extra)
  if (done) {
    actionPanel.value = null
  }
}

async function postAction(action: string, row: PermitRow, extra: Record<string, string>): Promise<boolean> {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, 经办人: session.operator, ...extra } }),
    })
    const result = await response.json()
    if (!result.ok) {
      errorMessage.value = String(result.message ?? '动作未生效')
      return false
    }
    await reload()
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '许可操作失败'
    return false
  }
}

async function openHistory(row: PermitRow) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('流转记录读取失败')
    }
    historyPanel.value = (await response.json()) as PermitRow
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '流转记录读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) {
    query.set('keyword', keyword.value)
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('占道掘路许可列表读取失败')
    }
    const payload = await response.json()
    rows.value = (payload.items ?? []) as PermitRow[]
    total.value = payload.total ?? rows.value.length
    await loadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '占道掘路许可列表读取失败'
  }
}

async function loadStats() {
  const response = await request(`${ENDPOINT}?size=200`)
  if (!response.ok) {
    return
  }
  const payload = await response.json()
  const all = (payload.items ?? []) as PermitRow[]
  const count = (status: string) => all.filter((row) => row.status === status).length
  stats.value = [
    { label: '待受理许可', value: count('待受理') },
    { label: '审核中许可', value: count('审核中') },
    { label: '已批许可', value: count('已批许可') },
    { label: '已退回待补正', value: count('已退回') },
  ]
}

onMounted(reload)
</script>

<style scoped>
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.panel-title {
  margin: 0 0 10px;
  font-size: 14px;
}
.panel-hint {
  color: var(--muted);
  font-size: 12px;
  margin: 4px 0 10px;
}
.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 14px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
.form-item.wide {
  grid-column: 1 / -1;
}
.receipt-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.receipt-list li {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.receipt-time {
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}
.receipt-no {
  font-weight: 600;
  white-space: nowrap;
}
.receipt-ok {
  color: #067647;
}
.receipt-bad {
  color: #b42318;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #eef2f6;
}
.badge[data-status='已归档'] {
  background: #e7f6ec;
  color: #067647;
}
.badge[data-status='已退回'] {
  background: #fef0ee;
  color: #b42318;
}
.filter-item select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  background: #fff;
}
</style>
