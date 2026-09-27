<template>
  <section class="page" data-module="inflow">
    <header class="page-head">
      <div>
        <h2>进水监控管理</h2>
        <p class="page-desc">进水异常按「在控 → 预警 → 已处置」闭环流转：pH 或氨氮超阈值必须转预警并派给处置人，未完成处置不能标记已处置，支持中途挂起与值班长退回。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记进水记录</button>
        <button class="btn" type="button" @click="exportRows">导出进水监控清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.cls">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
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
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['记录编号'] ?? '—' }}</td>
          <td>{{ row['所属厂站'] ?? '—' }}</td>
          <td>{{ row['监测时间'] ?? '—' }}</td>
          <td>{{ row['进水量'] ?? '—' }}</td>
          <td :class="{ 'over-limit': isNh3nOver(row) }">{{ row['氨氮浓度'] ?? '—' }}</td>
          <td :class="{ 'over-limit': isPhOver(row) }">{{ row['pH值'] ?? '—' }}</td>
          <td>
            <span class="status-tag" :class="statusClass(row.status)">{{ row.status }}</span>
            <span v-if="row.exceeded" class="exceed-flag" :title="row.exceed_reasons">超标</span>
          </td>
          <td>{{ row['处置人员'] || '—' }}</td>
          <td><span class="last-op" :title="lastOpTitle(row)">{{ row.last_op || '—' }}</span></td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">
              {{ row.status === '已处置' || row.status === '在控' ? '查看' : '处置' }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的进水监控记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条进水监控记录 · 当前值班：{{ session.operator }}（{{ session.role }}）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 处置弹窗：状态、明细、历史与列表同源，操作后两边一起刷新 -->
    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal modal-lg">
        <header class="modal-head">
          <div>
            <h3>{{ detail['记录编号'] }} · {{ detail['所属厂站'] }}</h3>
            <span class="status-tag" :class="statusClass(detail.status)">{{ detail.status }}</span>
            <span v-if="detail.exceeded" class="exceed-tip-inline">⚠ {{ detail.exceed_reasons }}</span>
          </div>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>

        <div class="modal-body">
          <dl class="detail-grid">
            <div><dt>监测时间</dt><dd>{{ detail['监测时间'] }}</dd></div>
            <div><dt>进水量</dt><dd>{{ detail['进水量'] }}</dd></div>
            <div><dt>COD浓度</dt><dd>{{ detail['COD浓度'] }}</dd></div>
            <div><dt>氨氮浓度</dt><dd :class="{ 'over-limit': isNh3nOver(detail) }">{{ detail['氨氮浓度'] }}</dd></div>
            <div><dt>pH值</dt><dd :class="{ 'over-limit': isPhOver(detail) }">{{ detail['pH值'] }}</dd></div>
            <div><dt>处置人员</dt><dd>{{ detail['处置人员'] || '待指派' }}</dd></div>
            <div class="detail-wide"><dt>处置结论</dt><dd>{{ detail['处置结论'] || '（处置未完成，暂无结论）' }}</dd></div>
          </dl>

          <section class="history-box">
            <h4>操作历史（交班后可核对上一步的操作时间与备注）</h4>
            <ul class="history-list">
              <li v-for="(item, index) in detail.history" :key="index">
                <span class="history-at">{{ item.at }}</span>
                <span class="history-operator">{{ item.operator }}</span>
                <span class="status-tag tag-action">{{ item.action }}</span>
                <span class="history-remark">{{ item.remark || '—' }}</span>
              </li>
              <li v-if="!detail.history.length" class="empty-state">暂无操作记录</li>
            </ul>
          </section>

          <section class="action-box">
            <h4>处置操作</h4>
            <div class="action-bar">
              <button
                v-for="action in detail.available_actions"
                :key="action"
                class="btn"
                :class="{ primary: activeAction === action }"
                type="button"
                :disabled="action === '退回' && !session.isShiftLead"
                :title="action === '退回' && !session.isShiftLead ? '只有值班长可以退回已处置记录' : ''"
                @click="chooseAction(action)"
              >
                {{ action }}
              </button>
              <span v-if="detail.available_actions.includes('退回') && !session.isShiftLead" class="action-hint">
                退回已处置记录需在右上角切换为值班长
              </span>
            </div>

            <form v-if="activeAction" class="action-form" @submit.prevent="submitAction">
              <label v-if="activeAction === '转预警'" class="filter-item">
                <span>处置人员（必填）</span>
                <input v-model="actionForm['处置人员']" placeholder="指派具体处置人，如 李工" />
              </label>
              <label v-if="activeAction === '处置完成'" class="filter-item action-form-wide">
                <span>处置结论（必填，没有结论不允许标记已处置）</span>
                <textarea v-model="actionForm['处置结论']" rows="2" placeholder="记录处置措施与现场结果"></textarea>
              </label>
              <label class="filter-item action-form-wide">
                <span>{{ remarkLabel }}</span>
                <textarea v-model="actionForm.remark" rows="2" :placeholder="remarkPlaceholder"></textarea>
              </label>
              <div class="action-form-foot">
                <button class="btn primary" type="submit">确认{{ activeAction }}</button>
                <button class="btn ghost" type="button" @click="activeAction = ''">取消</button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </div>

    <!-- 登记弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <header class="modal-head">
          <h3>登记进水记录</h3>
          <button class="btn ghost" type="button" @click="showCreate = false">关闭</button>
        </header>
        <div class="modal-body">
          <p class="form-tip">pH 值超出 6.0–9.0 或氨氮浓度高于 30 mg/L 时，必须同时填写处置人员，记录将直接进入预警。</p>
          <div class="form-grid">
            <label v-for="field in createFields" :key="field" class="filter-item">
              <span>{{ field }}{{ requiredFields.includes(field) ? '（必填）' : '' }}</span>
              <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
            </label>
          </div>
        </div>
        <footer class="modal-foot">
          <button class="btn primary" type="button" @click="submitCreate">登记</button>
          <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

interface HistoryItem {
  at: string
  operator: string
  action: string
  remark: string
}

interface InflowRow {
  id: number
  status: string
  last_op: string
  exceeded: boolean
  exceed_reasons: string
  available_actions: string[]
  history: HistoryItem[]
  '记录编号': string
  '所属厂站': string
  '监测时间': string
  '进水量': string
  'COD浓度': string
  '氨氮浓度': string
  'pH值': string
  '处置人员': string
  '处置结论': string
  [key: string]: string | number | boolean | string[] | HistoryItem[]
}

const ENDPOINT = '/api/inflow'
const PH_MIN = 6
const PH_MAX = 9
const NH3N_LIMIT = 30

const session = useSessionStore()
const columns = ['记录编号', '所属厂站', '监测时间', '进水量', '氨氮浓度', 'pH值', '状态', '处置人员', '最近操作']
const statuses = ['在控', '预警', '挂起', '已处置']

const rows = ref<InflowRow[]>([])
const total = ref(0)
const statusStats = ref<Record<string, number>>({})
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const statCards = computed(() => [
  { label: '在控', value: statusStats.value['在控'] ?? 0, cls: 'tag-incontrol-text' },
  { label: '预警（待处置）', value: statusStats.value['预警'] ?? 0, cls: 'tag-warning-text' },
  { label: '挂起（待恢复）', value: statusStats.value['挂起'] ?? 0, cls: 'tag-suspended-text' },
  { label: '已处置', value: statusStats.value['已处置'] ?? 0, cls: 'tag-resolved-text' },
])

// ---- 弹窗状态 ----
const detail = ref<InflowRow | null>(null)
const activeAction = ref('')
const actionForm = reactive({ '处置人员': '', '处置结论': '', remark: '' })

const showCreate = ref(false)
const createFields = ['记录编号', '所属厂站', '监测时间', '进水量', 'COD浓度', '氨氮浓度', 'pH值', '处置人员']
const requiredFields = ['记录编号', '所属厂站', '监测时间']
const createForm = reactive<Record<string, string>>({})

const remarkLabel = computed(() => {
  if (activeAction.value === '挂起') return '挂起原因（必填）'
  if (activeAction.value === '退回') return '退回原因（必填）'
  if (activeAction.value === '恢复处置') return '恢复备注'
  return '备注'
})
const remarkPlaceholder = computed(() => {
  if (activeAction.value === '挂起') return '说明为什么暂停处置，方便恢复时交接'
  if (activeAction.value === '退回') return '说明为什么退回预警，处置人将继续跟进'
  if (activeAction.value === '恢复处置') return '可说明恢复后的处置安排'
  return '可补充操作说明'
})

function statusClass(status: string): string {
  const map: Record<string, string> = {
    在控: 'tag-incontrol',
    预警: 'tag-warning',
    挂起: 'tag-suspended',
    已处置: 'tag-resolved',
  }
  return map[status] ?? ''
}

function toNumber(value: unknown): number | null {
  const n = Number.parseFloat(String(value ?? ''))
  return Number.isNaN(n) ? null : n
}

function isPhOver(row: InflowRow): boolean {
  const ph = toNumber(row['pH值'])
  return ph !== null && (ph < PH_MIN || ph > PH_MAX)
}

function isNh3nOver(row: InflowRow): boolean {
  const nh3n = toNumber(row['氨氮浓度'])
  return nh3n !== null && nh3n > NH3N_LIMIT
}

function lastOpTitle(row: InflowRow): string {
  return (row.history ?? []).map((h) => `${h.at} ${h.operator} ${h.action}：${h.remark || '—'}`).join('\n')
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  for (const field of createFields) createForm[field] = ''
  errorMessage.value = ''
  showCreate.value = true
}

function openDetail(row: InflowRow) {
  errorMessage.value = ''
  detail.value = row
  activeAction.value = ''
  actionForm['处置人员'] = row['处置人员'] || ''
  actionForm['处置结论'] = ''
  actionForm.remark = ''
}

function closeDetail() {
  detail.value = null
  activeAction.value = ''
}

function chooseAction(action: string) {
  activeAction.value = action
  actionForm.remark = ''
  if (action === '处置完成') actionForm['处置结论'] = ''
  errorMessage.value = ''
}

async function submitCreate() {
  errorMessage.value = ''
  const values: Record<string, string> = {}
  for (const field of createFields) values[field] = createForm[field]?.trim() ?? ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values, operator: session.operator, role: session.role }),
    })
    const result = (await response.json()) as { ok: boolean; message: string }
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    showCreate.value = false
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '进水记录登记失败'
  }
}

async function submitAction() {
  if (!detail.value) return
  errorMessage.value = ''
  const values: Record<string, string> = { action: activeAction.value }
  if (activeAction.value === '转预警') values['处置人员'] = actionForm['处置人员'].trim()
  if (activeAction.value === '处置完成') values['处置结论'] = actionForm['处置结论'].trim()
  try {
    const response = await request(`${ENDPOINT}/${detail.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values,
        remark: actionForm.remark.trim(),
        operator: session.operator,
        role: session.role,
      }),
    })
    const result = (await response.json()) as { ok: boolean; message: string; entry?: InflowRow }
    if (!result.ok || !result.entry) {
      errorMessage.value = result.message || '操作未生效'
      return
    }
    // 弹窗直接使用后端回写后的同一份记录，列表也同源刷新，状态不会不一致
    detail.value = result.entry
    activeAction.value = ''
    actionForm['处置结论'] = ''
    actionForm.remark = ''
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '进水监控操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('进水记录列表读取失败')
    const payload = (await response.json()) as { items?: InflowRow[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 弹窗若打开着，用最新列表里同 id 的记录同步
    if (detail.value) {
      const latest = rows.value.find((row) => row.id === detail.value?.id)
      if (latest) detail.value = latest
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '进水监控列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) statusStats.value = await response.json()
  } catch {
    // 统计卡片不影响主流程
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
