<template>
  <section class="page" data-module="inflow">
    <header class="page-head">
      <div>
        <h2>进水监控管理</h2>
        <p class="page-desc">
          进水异常按「在控 → 预警 → 已处置」流转：pH 或氨氮超阈值自动转预警并派单，
          处置完成方可结单，中途可挂起并留恢复入口，已处置结论由值班长退回。
        </p>
      </div>
      <div class="page-actions">
        <label class="role-switch">
          当前角色
          <select :value="session.role" @change="onRoleChange">
            <option>处置人员</option>
            <option>值班长</option>
          </select>
        </label>
        <button class="btn warn-btn" type="button" @click="openWarningCenter">
          预警中心<span v-if="warningCount" class="warn-dot">{{ warningCount }}</span>
        </button>
        <button class="btn primary" type="button" @click="openCreate">登记进水记录</button>
        <button class="btn" type="button" @click="exportRows">导出清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card" :class="item.cls">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
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
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>处置人员</th>
          <th>操作时间线</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '状态'" class="status-badge" :class="statusClass(row.status)">{{ row.status }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td>{{ row['指派处置人员'] || '—' }}</td>
          <td>
            <button class="link" type="button" @click="openDetail(row)">
              {{ row.timeline?.length ?? 0 }} 步留痕
            </button>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action.key"
              class="link"
              :class="action.danger ? 'danger-link' : ''"
              type="button"
              @click="openAction(action.key, row)"
            >
              {{ action.label }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 3" class="empty-state">暂无符合条件的进水监控记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条进水监控记录 · 预警阈值：pH {{ thresholds?.['pH区间'][0] ?? 6 }}~{{ thresholds?.['pH区间'][1] ?? 9 }}，氨氮 &gt; {{ thresholds?.['氨氮浓度上限'] ?? 45 }}mg/L</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 预警中心弹窗：与列表共用同一份 rows/status，保证两处状态显示一致 -->
    <div v-if="warningOpen" class="modal-mask" @click.self="warningOpen = false">
      <div class="modal modal-wide">
        <div class="modal-head">
          <h3>预警中心</h3>
          <button class="link" type="button" @click="warningOpen = false">关闭</button>
        </div>
        <p class="modal-tip">下列记录与监测列表共用同一状态口径；挂起中的记录请先恢复再处置。</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>记录编号</th>
              <th>所属厂站</th>
              <th>监测时间</th>
              <th>超标指标</th>
              <th>处置人员</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in warningRows" :key="String(row.id)">
              <td>{{ row['记录编号'] }}</td>
              <td>{{ row['所属厂站'] }}</td>
              <td>{{ row['监测时间'] }}</td>
              <td class="exceed-cell">{{ row['超标指标'] || '—' }}</td>
              <td>{{ row['指派处置人员'] || '—' }}</td>
              <td><span class="status-badge" :class="statusClass(row.status)">{{ row.status }}</span></td>
              <td class="row-actions">
                <button class="link" type="button" @click="openDetail(row); warningOpen = false">明细/留痕</button>
                <button
                  v-for="action in actionsFor(row)"
                  :key="action.key"
                  class="link"
                  type="button"
                  @click="openAction(action.key, row); warningOpen = false"
                >
                  {{ action.label }}
                </button>
              </td>
            </tr>
            <tr v-if="!warningRows.length">
              <td colspan="7" class="empty-state">当前没有预警或挂起中的进水记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 登记 / 指标复核弹窗 -->
    <div v-if="dialog?.mode === 'create' || dialog?.mode === 'readings'" class="modal-mask" @click.self="closeDialog">
      <form class="modal" @submit.prevent="submitDialog">
        <div class="modal-head">
          <h3>{{ dialog.mode === 'create' ? '登记进水记录' : `指标复核 · ${dialog.row['记录编号']}` }}</h3>
          <button class="link" type="button" @click="closeDialog">关闭</button>
        </div>
        <div class="form-grid">
          <template v-if="dialog.mode === 'create'">
            <label class="form-item"><span>记录编号 *</span><input v-model="form['记录编号']" /></label>
            <label class="form-item"><span>所属厂站 *</span><input v-model="form['所属厂站']" /></label>
            <label class="form-item"><span>监测时间 *</span><input v-model="form['监测时间']" placeholder="2026-09-27 08:00" /></label>
            <label class="form-item"><span>进水量</span><input v-model="form['进水量']" placeholder="如 32000m³" /></label>
          </template>
          <label class="form-item"><span>COD浓度</span><input v-model="form['COD浓度']" placeholder="如 280mg/L" /></label>
          <label class="form-item">
            <span>氨氮浓度（&gt;{{ thresholds?.['氨氮浓度上限'] ?? 45 }} 预警）</span>
            <input v-model="form['氨氮浓度']" placeholder="如 52mg/L" />
          </label>
          <label class="form-item">
            <span>pH值（{{ thresholds?.['pH区间'][0] ?? 6 }}~{{ thresholds?.['pH区间'][1] ?? 9 }} 外预警）</span>
            <input v-model="form['pH值']" placeholder="如 5.8" />
          </label>
          <label class="form-item">
            <span>指派处置人员（超阈值时必填）</span>
            <input v-model="form['指派处置人员']" placeholder="超阈值必须派给具体人员" />
          </label>
          <label class="form-item full"><span>备注</span><input v-model="form.remark" /></label>
        </div>
        <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="submit">{{ dialog.mode === 'create' ? '登记' : '提交复核' }}</button>
        </div>
      </form>
    </div>

    <!-- 流转动作弹窗 -->
    <div v-else-if="dialog?.mode === 'action'" class="modal-mask" @click.self="closeDialog">
      <form class="modal" @submit.prevent="submitDialog">
        <div class="modal-head">
          <h3>{{ actionMeta[dialog.action]?.title }} · {{ dialog.row['记录编号'] }}</h3>
          <button class="link" type="button" @click="closeDialog">关闭</button>
        </div>
        <div class="form-grid">
          <p class="modal-tip">{{ actionMeta[dialog.action]?.tip }}</p>
          <label v-if="dialog.action === 'warn'" class="form-item full">
            <span>指派处置人员 *</span>
            <input v-model="form['指派处置人员']" placeholder="必须派给具体处置人员" />
          </label>
          <label v-if="dialog.action === 'suspend'" class="form-item full">
            <span>挂起原因 *</span>
            <textarea v-model="form['挂起原因']" rows="3" placeholder="说明为何中途挂起，交班时可查"></textarea>
          </label>
          <label v-if="dialog.action === 'complete'" class="form-item full">
            <span>处置措施与结果 *</span>
            <textarea v-model="form['处置结果']" rows="3" placeholder="处置未完成不允许标记已处置"></textarea>
          </label>
          <label v-if="dialog.action === 'reject'" class="form-item full">
            <span>退回原因 *（仅值班长可执行）</span>
            <textarea v-model="form['退回原因']" rows="3" placeholder="退回后记录回到预警，进水量与监测时间不变"></textarea>
          </label>
          <label class="form-item full"><span>备注</span><input v-model="form.remark" /></label>
        </div>
        <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
        <div class="modal-foot">
          <button class="btn" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="submit">{{ actionMeta[dialog.action]?.title }}</button>
        </div>
      </form>
    </div>

    <!-- 明细 + 操作时间线：交班后新接手的人在这里看上一步操作时间与备注 -->
    <div v-else-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal modal-wide">
        <div class="modal-head">
          <h3>进水记录明细 · {{ detail['记录编号'] }}</h3>
          <button class="link" type="button" @click="detail = null">关闭</button>
        </div>
        <div class="detail-grid">
          <div><span>所属厂站</span><strong>{{ detail['所属厂站'] }}</strong></div>
          <div><span>监测时间</span><strong>{{ detail['监测时间'] }}</strong></div>
          <div><span>进水量</span><strong>{{ detail['进水量'] || '—' }}</strong></div>
          <div>
            <span>当前状态</span>
            <strong><span class="status-badge" :class="statusClass(detail.status)">{{ detail.status }}</span></strong>
          </div>
          <div><span>COD浓度</span><strong>{{ detail['COD浓度'] || '—' }}</strong></div>
          <div><span>氨氮浓度</span><strong>{{ detail['氨氮浓度'] || '—' }}</strong></div>
          <div><span>pH值</span><strong>{{ detail['pH值'] || '—' }}</strong></div>
          <div><span>处置人员</span><strong>{{ detail['指派处置人员'] || '—' }}</strong></div>
          <div class="detail-wide"><span>超标指标</span><strong>{{ detail['超标指标'] || '—' }}</strong></div>
          <div v-if="detail['挂起原因']" class="detail-wide"><span>挂起原因</span><strong>{{ detail['挂起原因'] }}</strong></div>
          <div class="detail-wide"><span>处置结果</span><strong>{{ detail['处置结果'] || '—' }}</strong></div>
        </div>
        <h4 class="timeline-title">操作时间线（交班留痕）</h4>
        <ul class="timeline">
          <li v-for="(item, index) in detail.timeline ?? []" :key="index" class="timeline-item">
            <div class="timeline-head">
              <span class="timeline-action" :class="statusClass(item['动作'] === '标记已处置' ? '已处置' : item['动作'] === '值班长退回' ? '预警' : '在控')">{{ item['动作'] }}</span>
              <span class="timeline-time">{{ item['时间'] }}</span>
            </div>
            <div class="timeline-meta">操作人：{{ item['操作人'] }}<template v-if="item['处置人员']"> · 处置人员：{{ item['处置人员'] }}</template></div>
            <div v-if="item['备注']" class="timeline-remark">备注：{{ item['备注'] }}</div>
          </li>
          <li v-if="!detail.timeline?.length" class="empty-state">暂无操作留痕</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Status = '在控' | '预警' | '已挂起' | '已处置'
type ActionKey = 'warn' | 'suspend' | 'resume' | 'complete' | 'reject' | 'readings'

interface TimelineItem {
  时间: string
  动作: string
  操作人: string
  处置人员: string
  备注: string
}

interface InflowRow {
  id: number
  status: Status
  记录编号: string
  所属厂站: string
  监测时间: string
  进水量: string
  COD浓度: string
  氨氮浓度: string
  pH值: string
  指派处置人员: string
  超标指标: string
  处置结果: string
  挂起原因: string
  timeline?: TimelineItem[]
  [key: string]: string | number | TimelineItem[] | null | undefined
}

interface ThresholdInfo {
  pH区间: [number, number]
  氨氮浓度上限: number
  退回角色: string
}

const ENDPOINT = '/api/inflow'
const session = useSessionStore()

const columns = ['记录编号', '所属厂站', '监测时间', '进水量', 'COD浓度', '氨氮浓度', 'pH值', '状态']
const statuses: Status[] = ['在控', '预警', '已挂起', '已处置']

const actionMeta: Record<ActionKey, { title: string; tip: string; endpoint: string; method: string }> = {
  warn: { title: '转预警并派单', tip: '仅当 pH 值或氨氮浓度超过阈值时可执行，必须指定具体处置人员。', endpoint: 'warn', method: 'POST' },
  suspend: { title: '挂起处置', tip: '处置中途暂停需写明原因，记录保留恢复入口，挂起期间不能标记已处置。', endpoint: 'suspend', method: 'POST' },
  resume: { title: '恢复处置', tip: '从挂起恢复，回到预警状态继续跟进。', endpoint: 'resume', method: 'POST' },
  complete: { title: '标记已处置', tip: '请填写实际处置措施与复测结果；处置没完成不允许标记已处置。', endpoint: 'complete', method: 'POST' },
  reject: { title: '值班长退回', tip: '退回后记录回到预警，进水量与监测时间保持不变，由原处置人员重新跟进。', endpoint: 'reject', method: 'POST' },
  readings: { title: '指标复核', tip: '复核后若超过阈值，必须指派处置人员并转为预警。', endpoint: 'readings', method: 'PATCH' },
}

const rows = ref<InflowRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const thresholds = ref<ThresholdInfo | null>(null)
const warningOpen = ref(false)

const detail = ref<InflowRow | null>(null)
const dialog = ref<
  | { mode: 'create' }
  | { mode: 'readings'; row: InflowRow }
  | { mode: 'action'; action: ActionKey; row: InflowRow }
  | null>(null)
const form = reactive<Record<string, string>>({})
const dialogError = ref('')

const warningRows = computed(() => rows.value.filter((row) => row.status === '预警' || row.status === '已挂起'))
const warningCount = computed(() => rows.value.filter((row) => row.status === '预警' || row.status === '已挂起').length)

const stats = computed(() => [
  { label: '在控', value: rows.value.filter((r) => r.status === '在控').length, cls: '' },
  { label: '预警待处置', value: rows.value.filter((r) => r.status === '预警').length, cls: 'stat-warn' },
  { label: '处置挂起', value: rows.value.filter((r) => r.status === '已挂起').length, cls: 'stat-suspend' },
  { label: '已处置', value: rows.value.filter((r) => r.status === '已处置').length, cls: 'stat-done' },
])

function statusClass(status: string): string {
  if (status === '预警') return 'st-warn'
  if (status === '已挂起') return 'st-suspend'
  if (status === '已处置') return 'st-done'
  return 'st-ok'
}

function actionsFor(row: InflowRow): { key: ActionKey; label: string; danger?: boolean }[] {
  if (row.status === '在控') {
    return [{ key: 'readings', label: '指标复核' }, { key: 'warn', label: '转预警' }]
  }
  if (row.status === '预警') {
    return [
      { key: 'suspend', label: '挂起' },
      { key: 'complete', label: '标记已处置' },
    ]
  }
  if (row.status === '已挂起') {
    return [{ key: 'resume', label: '恢复处置' }]
  }
  // 已处置：只有值班长能退回
  return session.isShiftLeader ? [{ key: 'reject', label: '值班长退回', danger: true }] : []
}

function onRoleChange(event: Event) {
  session.setRole((event.target as HTMLSelectElement).value as '处置人员' | '值班长')
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openWarningCenter() {
  warningOpen.value = true
}

function resetForm() {
  for (const key of Object.keys(form)) delete form[key]
  dialogError.value = ''
}

function openCreate() {
  resetForm()
  dialog.value = { mode: 'create' }
}

function openAction(action: ActionKey, row: InflowRow) {
  resetForm()
  if (action === 'readings') {
    form['COD浓度'] = row['COD浓度'] ?? ''
    form['氨氮浓度'] = row['氨氮浓度'] ?? ''
    form['pH值'] = row['pH值'] ?? ''
    dialog.value = { mode: 'readings', row }
    return
  }
  // 退回时带上当前角色，后端强校验值班长
  if (action === 'reject') form['角色'] = session.role
  dialog.value = { mode: 'action', action, row }
}

function closeDialog() {
  dialog.value = null
}

async function openDetail(row: InflowRow) {
  // 进详情时拉一次最新数据，保证交班后看到的是最新操作时间与备注
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    const payload = await response.json()
    detail.value = payload as InflowRow
  } catch {
    detail.value = row
  }
}

function payloadValues(): Record<string, string> {
  const values: Record<string, string> = { operator: session.operator, ...form }
  return Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined && v !== null))
}

async function submitDialog() {
  if (!dialog.value) return
  dialogError.value = ''
  try {
    let url = ''
    let method = 'POST'
    if (dialog.value.mode === 'create') {
      url = ENDPOINT
      method = 'POST'
    } else if (dialog.value.mode === 'readings') {
      url = `${ENDPOINT}/${dialog.value.row.id}/readings`
      method = 'PATCH'
    } else {
      url = `${ENDPOINT}/${dialog.value.row.id}/${actionMeta[dialog.value.action].endpoint}`
      method = actionMeta[dialog.value.action].method
    }
    const response = await request(url, { method, body: JSON.stringify({ values: payloadValues() }) })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      dialogError.value = payload.message || payload.detail || '操作未生效，请稍后重试'
      return
    }
    dialog.value = null
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '进水监控操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  query.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('进水记录列表读取失败')
    const payload = await response.json()
    rows.value = (payload.items ?? []) as InflowRow[]
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '进水监控列表读取失败'
  }
}

async function loadThresholds() {
  try {
    const response = await request(`${ENDPOINT}/thresholds`)
    if (response.ok) thresholds.value = await response.json()
  } catch {
    // 阈值取默认值即可，不阻塞页面
  }
}

onMounted(() => {
  void loadThresholds()
  void reload()
})
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; align-items: center; }
.role-switch { font-size: 12px; color: var(--muted); display: flex; flex-direction: column; gap: 2px; }
.role-switch select { padding: 4px 6px; border: 1px solid var(--border); border-radius: 6px; }
.warn-btn { position: relative; border-color: #d92d20; color: #b42318; }
.warn-dot { margin-left: 6px; background: #d92d20; color: #fff; border-radius: 10px; padding: 0 6px; font-size: 11px; }
.stat-warn .stat-value { color: #b42318; }
.stat-suspend .stat-value { color: #b54708; }
.stat-done .stat-value { color: #067647; }
.status-badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; white-space: nowrap; }
.st-ok { background: #e8f3ff; color: #175cd3; }
.st-warn { background: #fef3f2; color: #b42318; }
.st-suspend { background: #fffaeb; color: #b54708; }
.st-done { background: #ecfdf3; color: #067647; }
.danger-link { color: #b42318; }
.exceed-cell { color: #b42318; max-width: 220px; }
.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; padding: 16px 18px; width: 520px; max-height: 86vh; overflow: auto; }
.modal-wide { width: 860px; }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.modal-head h3 { margin: 0; font-size: 15px; }
.modal-tip { font-size: 12px; color: var(--muted); margin: 0 0 10px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-item { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-item.full { grid-column: 1 / -1; }
.form-item input, .form-item textarea, .form-item select { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px; color: #1f2937; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.detail-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px; }
.detail-grid div { background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 8px; }
.detail-grid .detail-wide { grid-column: span 2; }
.detail-grid span { display: block; font-size: 11px; color: var(--muted); margin-bottom: 2px; }
.detail-grid strong { font-size: 13px; font-weight: 600; }
.timeline-title { font-size: 13px; margin: 8px 0; }
.timeline { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.timeline-item { border-left: 3px solid var(--brand); background: #f8fafc; border-radius: 0 6px 6px 0; padding: 8px 10px; }
.timeline-head { display: flex; justify-content: space-between; align-items: center; }
.timeline-action { font-size: 12px; font-weight: 600; }
.timeline-time { font-size: 12px; color: var(--muted); }
.timeline-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
.timeline-remark { font-size: 13px; margin-top: 4px; }
</style>
