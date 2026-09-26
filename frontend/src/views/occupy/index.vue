<template>
  <section class="page" data-module="occupy">
    <header class="page-head">
      <div>
        <h2>占道掘路许可</h2>
        <p class="page-desc">登记占道掘路的路段、占用时段、恢复要求与随附材料，许可按待受理、审核中、已批许可、已恢复验收、已归档逐级流转，每步留下经办人与时间。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">登记占道申请</button>
        <button class="btn" type="button" @click="exportRows">导出许可清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="filter-bar create-panel" @submit.prevent="submitCreate">
      <label v-for="field in createFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="createForm[field]" :placeholder="`填写${field}`" />
      </label>
      <button class="btn primary" type="submit">提交申请</button>
      <button class="btn ghost" type="button" @click="showCreate = false">收起</button>
    </form>

    <div v-if="receipt" class="receipt-panel">
      <strong>提交回执 {{ receipt.回执编号 }}</strong>
      <span>结论：{{ receipt.结论 }}</span>
      <span v-if="receipt.许可编号">许可编号：{{ receipt.许可编号 }}</span>
      <span>经办人：{{ receipt.经办人 }}</span>
      <span>时间：{{ receipt.时间 }}</span>
      <span>{{ receipt.说明 }}</span>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="keyword" placeholder="按许可编号、申请编号或路段检索" />
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
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in nextActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="showTimeline(row)">流转记录</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无占道掘路许可数据，可先登记占道申请</td>
        </tr>
      </tbody>
    </table>

    <div v-if="acceptingRow" class="receipt-panel">
      <strong>恢复验收：{{ acceptingRow.许可编号 }}</strong>
      <span>申请中的恢复要求：{{ acceptingRow.恢复要求 }}</span>
      <label class="filter-item conclusion-item">
        <span>验收结论（需与恢复要求逐项对得上）</span>
        <textarea v-model="acceptConclusion" rows="3"></textarea>
      </label>
      <span class="row-actions">
        <button class="btn primary" type="button" @click="submitAccept">提交验收结论</button>
        <button class="btn ghost" type="button" @click="acceptingRow = null">取消</button>
      </span>
    </div>

    <div v-if="timelineRow" class="receipt-panel">
      <strong>流转记录：{{ timelineRow.许可编号 }}（当前 {{ timelineRow.status }}）</strong>
      <span v-for="(step, index) in timelineRow.timeline ?? []" :key="index">
        {{ step.时间 }} · {{ step.动作 }} · {{ step.状态从 }}→{{ step.状态到 }} · 经办人：{{ step.经办人 }} · {{ step.说明 }}
      </span>
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

type Row = Record<string, string | number | null> & { timeline?: Record<string, string>[] }

const ENDPOINT = '/api/occupy'
const columns = ["许可编号", "申请编号", "申请单位", "占道掘路路段", "占用时段", "恢复要求", "随附材料", "许可状态"]
const statuses = ["待受理", "审核中", "已批许可", "已恢复验收", "已归档"]
const nextActionMap: Record<string, string[]> = {
  "待受理": ["受理申请"],
  "审核中": ["批准许可"],
  "已批许可": ["恢复验收"],
  "已恢复验收": ["归档许可"],
  "已归档": [],
}
const createFields = ["申请编号", "申请单位", "占道掘路路段", "占用时段", "恢复要求", "随附材料"]

const store = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const stats = ref([{ label: '待受理', value: 0 }, { label: '审核中', value: 0 }, { label: '已批许可', value: 0 }])
const showCreate = ref(false)
const createForm = ref<Record<string, string>>({})
const receipt = ref<Record<string, string> | null>(null)
const acceptingRow = ref<Row | null>(null)
const acceptConclusion = ref('')
const timelineRow = ref<Row | null>(null)

function nextActions(row: Row) {
  return nextActionMap[String(row.status ?? '')] ?? []
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

async function submitCreate() {
  errorMessage.value = ''
  receipt.value = null
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value, 经办人: store.operator } }),
    })
    const payload = await response.json()
    receipt.value = payload.receipt ?? null
    if (!payload.ok) {
      errorMessage.value = payload.message ?? '占道申请被退回'
      return
    }
    createForm.value = {}
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '占道申请提交失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '恢复验收') {
    acceptingRow.value = row
    acceptConclusion.value = `已按恢复要求落实：${row.恢复要求 ?? ''}`
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, 经办人: store.operator } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message ?? '许可动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '许可操作失败'
  }
}

async function submitAccept() {
  if (!acceptingRow.value) return
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${acceptingRow.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '恢复验收', 经办人: store.operator, 验收结论: acceptConclusion.value } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message ?? '恢复验收未通过')
    }
    acceptingRow.value = null
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '恢复验收操作失败'
  }
}

async function showTimeline(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('流转记录读取失败')
    }
    timelineRow.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '流转记录读取失败'
  }
}

async function refreshStats() {
  try {
    const response = await request(`${ENDPOINT}?size=200`)
    if (!response.ok) return
    const payload = await response.json()
    const items: Row[] = payload.items ?? []
    stats.value = [
      { label: '待受理', value: items.filter((row) => row.status === '待受理').length },
      { label: '审核中', value: items.filter((row) => row.status === '审核中').length },
      { label: '已批许可', value: items.filter((row) => row.status === '已批许可').length },
    ]
  } catch {
    // 统计卡片刷新失败不挡列表
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('占道掘路许可列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await refreshStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '占道掘路许可列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.create-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.receipt-panel {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.conclusion-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.conclusion-item textarea {
  width: 100%;
  font-family: inherit;
}
</style>
