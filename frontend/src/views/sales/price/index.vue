<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  deleteProductPrice,
  getProductPrice,
  listProductPriceHistory,
  listProductPrices,
  updateProductPrice,
} from '@/api/sales'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import { hasPermission } from '@/utils/auth'
import type { ProductPrice, ProductPriceHistory, RemoteOption } from '@/types/erp'

const canManage = computed(() => hasPermission('sales:price:manage'))

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<ProductPrice, { keyword: string }>(
    (params) => listProductPrices(params),
    { keyword: '' },
  )

const SALES_CATEGORY_LABELS: Record<string, string> = {
  MACHINE: '整机',
  SPARE: '可售备件',
  INTERNAL: '内部件',
}

function categoryText(value?: string | null): string {
  return value ? SALES_CATEGORY_LABELS[value] ?? value : '—'
}

function money(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return toNumber(value).toFixed(2)
}

/** 参考毛利率 =（当前价格 - 标准成本）/ 当前价格 */
function marginText(row: ProductPrice): string {
  const price = toNumber(row.current_price)
  const cost = toNumber(row.standard_cost)
  if (price <= 0) return '—'
  return `${(((price - cost) / price) * 100).toFixed(1)}%`
}

function localToday(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

// ---------------- 新增产品价格 ----------------
const addVisible = ref(false)
const addSubmitting = ref(false)
const addFormRef = ref<FormInstance>()
const addForm = reactive<{
  material_id: number | undefined
  price: number
  effective_date: string
  remark: string
}>({
  material_id: undefined,
  price: 0,
  effective_date: '',
  remark: '',
})

const addRules: FormRules = {
  material_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  price: [{ required: true, message: '请输入价格', trigger: 'blur' }],
  effective_date: [{ required: true, message: '请选择生效日期', trigger: 'change' }],
}

/** 新增价格时从物料管理（仓库物料）中挑选启用的物料 */
async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({
    id: item.id,
    label: `${item.material_code} ${item.material_name}`,
  }))
}

async function onAddMaterialChange(materialId: number | undefined): Promise<void> {
  if (!materialId) return
  try {
    const product = await getProductPrice(materialId)
    if (product.current_price !== null && product.current_price !== undefined) {
      ElMessage.warning(`${product.material_code} 已有产品价格，请直接使用「调整价格」`)
    }
  } catch {
    // 尚未定价的物料也返回物料信息，查询失败不阻断新增
  }
}

function openAdd(): void {
  Object.assign(addForm, {
    material_id: undefined,
    price: 0,
    effective_date: localToday(),
    remark: '',
  })
  addVisible.value = true
}

async function submitAdd(): Promise<void> {
  const valid = await addFormRef.value?.validate().catch(() => false)
  if (!valid || addForm.material_id === undefined) return
  addSubmitting.value = true
  try {
    const existing = await getProductPrice(addForm.material_id)
    if (existing.current_price !== null && existing.current_price !== undefined) {
      ElMessage.warning(`${existing.material_code} 已有产品价格，请使用「调整价格」`)
      return
    }
    await updateProductPrice(addForm.material_id, {
      price: addForm.price,
      effective_date: addForm.effective_date || null,
      remark: addForm.remark || null,
    })
    ElMessage.success('产品价格已添加')
    addVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    addSubmitting.value = false
  }
}

// ---------------- 调整价格 ----------------
const adjustVisible = ref(false)
const adjustSubmitting = ref(false)
const adjustTarget = ref<ProductPrice | null>(null)
const adjustFormRef = ref<FormInstance>()
const adjustForm = reactive<{ price: number; effective_date: string; remark: string }>({
  price: 0,
  effective_date: '',
  remark: '',
})

const adjustRules: FormRules = {
  price: [{ required: true, message: '请输入价格', trigger: 'blur' }],
  effective_date: [{ required: true, message: '请选择生效日期', trigger: 'change' }],
}

function openAdjust(row: ProductPrice): void {
  adjustTarget.value = row
  Object.assign(adjustForm, {
    price: toNumber(row.current_price),
    effective_date: localToday(),
    remark: '',
  })
  adjustVisible.value = true
}

async function submitAdjust(): Promise<void> {
  const target = adjustTarget.value
  if (!target) return
  const valid = await adjustFormRef.value?.validate().catch(() => false)
  if (!valid) return
  adjustSubmitting.value = true
  try {
    await updateProductPrice(target.material_id, {
      price: adjustForm.price,
      effective_date: adjustForm.effective_date || null,
      remark: adjustForm.remark || null,
    })
    ElMessage.success('产品价格已更新')
    adjustVisible.value = false
    await load()
    if (detailVisible.value && detailTarget.value?.material_id === target.material_id) {
      const refreshed = rows.value.find((item) => item.material_id === target.material_id)
      await openDetail(refreshed ?? target)
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    adjustSubmitting.value = false
  }
}

/** 删除产品价格，物料回到「未定价」，历史记录一并清除 */
async function removePrice(row: ProductPrice): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.material_code} ${row.material_name}」的产品价格吗？历史价格记录会一并清除。`,
      '删除产品价格',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteProductPrice(row.material_id)
    ElMessage.success('产品价格已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 价格详细（历史 + 折线图） ----------------
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailTarget = ref<ProductPrice | null>(null)
const history = ref<ProductPriceHistory[]>([])

async function openDetail(row: ProductPrice): Promise<void> {
  detailTarget.value = row
  detailVisible.value = true
  detailLoading.value = true
  try {
    history.value = await listProductPriceHistory(row.material_id)
  } catch (error) {
    history.value = []
    ElMessage.error((error as Error).message)
  } finally {
    detailLoading.value = false
  }
}

interface ChartDot {
  x: number
  y: number
  date: string
  price: number
}

interface ChartAxisTick {
  x: number
  label: string
}

interface ChartData {
  width: number
  height: number
  left: number
  right: number
  top: number
  bottom: number
  path: string
  hasLine: boolean
  dots: ChartDot[]
  yTicks: Array<{ y: number; label: string }>
  xTicks: ChartAxisTick[]
}

/** 手写 SVG 折线图：横轴日期、纵轴价格，不引入图表库 */
const chart = computed<ChartData | null>(() => {
  if (!history.value.length) return null
  const width = 720
  const height = 300
  const left = 72
  const right = 28
  const top = 24
  const bottom = 48
  const innerW = width - left - right
  const innerH = height - top - bottom

  const items = [...history.value].sort((a, b) => a.effective_date.localeCompare(b.effective_date))
  const prices = items.map((item) => toNumber(item.price))
  const rawMin = Math.min(...prices)
  const rawMax = Math.max(...prices)
  const span = rawMax - rawMin
  const padding = span > 0 ? span * 0.15 : Math.max(rawMax * 0.1, 1)
  const minValue = Math.max(0, rawMin - padding)
  const maxValue = rawMax + padding

  const yOf = (value: number): number =>
    top + ((maxValue - value) / (maxValue - minValue)) * innerH

  const times = items.map((item) => new Date(`${item.effective_date}T00:00:00`).getTime())
  const tMin = times[0]
  const tMax = times[times.length - 1]
  const xs = tMax > tMin
    ? times.map((time) => left + ((time - tMin) / (tMax - tMin)) * innerW)
    : items.map((_, index) =>
        items.length === 1 ? left + innerW / 2 : left + (index / (items.length - 1)) * innerW,
      )

  const dots: ChartDot[] = items.map((item, index) => ({
    x: xs[index],
    y: yOf(prices[index]),
    date: item.effective_date,
    price: prices[index],
  }))

  const path = dots.map((dot, index) => `${index === 0 ? 'M' : 'L'}${dot.x},${dot.y}`).join(' ')

  const yTicks = Array.from({ length: 5 }, (_, index) => {
    const value = maxValue - ((maxValue - minValue) / 4) * index
    return { y: yOf(value), label: value.toFixed(2) }
  })

  // 横轴日期过多时抽样，避免标签互相重叠
  const step = Math.max(1, Math.ceil(dots.length / 6))
  const sampled = dots
    .map((dot, index) => ({ x: dot.x, label: dot.date.slice(5), index }))
    .filter((tick) => tick.index % step === 0)
  if (sampled[sampled.length - 1]?.index !== dots.length - 1) {
    const last = dots[dots.length - 1]
    sampled.push({ x: last.x, label: last.date.slice(5), index: dots.length - 1 })
  }
  const xTicks: ChartAxisTick[] = sampled.map((tick) => ({ x: tick.x, label: tick.label }))

  return { width, height, left, right, top, bottom, path, hasLine: dots.length > 1, dots, yTicks, xTicks }
})

/** 历史表格里「较上次变动」列 */
function deltaText(index: number): string {
  if (index === 0) return '—'
  const diff = toNumber(history.value[index].price) - toNumber(history.value[index - 1].price)
  if (diff === 0) return '持平'
  return `${diff > 0 ? '+' : ''}${diff.toFixed(2)}`
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">产品价格</span>
          <span class="table-toolbar__spacer" />
          <span class="table-toolbar__hint">可售物料（整机 / 可售备件）及已定价的其他仓库物料</span>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="关键字">
          <el-input
            v-model="query.keyword"
            placeholder="物料编码 / 名称"
            clearable
            style="width: 220px"
            @keyup.enter="search"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
          <el-button v-if="canManage" type="primary" plain @click="openAdd">新增价格</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="销售类别" width="110">
          <template #default="{ row }">{{ categoryText(row.sales_category) }}</template>
        </el-table-column>
        <el-table-column label="单位" width="80">
          <template #default="{ row }">{{ row.unit_code || '—' }}</template>
        </el-table-column>
        <el-table-column label="标准成本" width="110" align="right">
          <template #default="{ row }">{{ money(row.standard_cost) }}</template>
        </el-table-column>
        <el-table-column label="当前价格" width="110" align="right">
          <template #default="{ row }">
            <span v-if="row.current_price !== null && row.current_price !== undefined">
              {{ money(row.current_price) }}
            </span>
            <el-tag v-else size="small" type="info">未定价</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="参考毛利率" width="110" align="right">
          <template #default="{ row }">{{ marginText(row) }}</template>
        </el-table-column>
        <el-table-column label="生效日期" width="120">
          <template #default="{ row }">{{ row.effective_date || '—' }}</template>
        </el-table-column>
        <el-table-column label="历史价格" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">
              详细<template v-if="row.history_count">（{{ row.history_count }}）</template>
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <template v-if="canManage">
              <el-button link type="primary" @click="openAdjust(row)">调整价格</el-button>
              <el-button
                v-if="row.current_price !== null && row.current_price !== undefined"
                link
                type="danger"
                @click="removePrice(row)"
              >
                删除
              </el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>暂无产品价格数据</template>
      </el-table>

      <div class="pager">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="changePage"
          @size-change="changeSize"
        />
      </div>
    </el-card>

    <!-- 新增产品价格 -->
    <el-dialog v-model="addVisible" title="新增产品价格" width="520px">
      <el-form ref="addFormRef" :model="addForm" :rules="addRules" label-width="100px">
        <el-form-item label="物料" prop="material_id">
          <RemoteSelect
            v-model="addForm.material_id"
            :loader="loadMaterialOptions"
            placeholder="搜索物料编码 / 名称"
            style="width: 100%"
            @change="onAddMaterialChange"
          />
        </el-form-item>
        <el-form-item label="价格" prop="price">
          <el-input-number
            v-model="addForm.price"
            :min="0"
            :precision="2"
            :step="1"
            :controls="false"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="生效日期" prop="effective_date">
          <el-date-picker
            v-model="addForm.effective_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="定价说明">
          <el-input v-model="addForm.remark" placeholder="如：新物料首次定价" />
        </el-form-item>
      </el-form>
      <p class="form-tip">物料来源于物料管理（仓库）中的启用物料；已有价格的物料请用列表中的「调整价格」。</p>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" :loading="addSubmitting" @click="submitAdd">保存</el-button>
      </template>
    </el-dialog>

    <!-- 调整价格 -->
    <el-dialog v-model="adjustVisible" title="调整产品价格" width="520px">
      <el-form ref="adjustFormRef" :model="adjustForm" :rules="adjustRules" label-width="100px">
        <el-form-item label="物料">
          <span v-if="adjustTarget">
            {{ adjustTarget.material_code }} {{ adjustTarget.material_name }}
          </span>
        </el-form-item>
        <el-form-item label="标准成本">
          <span>{{ money(adjustTarget?.standard_cost) }}</span>
        </el-form-item>
        <el-form-item label="当前价格">
          <span>{{ money(adjustTarget?.current_price) }}</span>
        </el-form-item>
        <el-form-item label="新价格" prop="price">
          <el-input-number
            v-model="adjustForm.price"
            :min="0"
            :precision="2"
            :step="1"
            :controls="false"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="生效日期" prop="effective_date">
          <el-date-picker
            v-model="adjustForm.effective_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="定价说明">
          <el-input v-model="adjustForm.remark" placeholder="如：原材料涨价 / 年度调价" />
        </el-form-item>
      </el-form>
      <p class="form-tip">保存后新价格立即生效，并写入一条价格变动记录，可在「详细」中查看走势。</p>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button type="primary" :loading="adjustSubmitting" @click="submitAdjust">保存</el-button>
      </template>
    </el-dialog>

    <!-- 价格详细：历史表格 + 折线图 -->
    <el-dialog v-model="detailVisible" title="历史价格" width="900px">
      <el-descriptions v-if="detailTarget" :column="4" border size="small" class="price-summary">
        <el-descriptions-item label="物料编码">{{ detailTarget.material_code }}</el-descriptions-item>
        <el-descriptions-item label="物料名称">{{ detailTarget.material_name }}</el-descriptions-item>
        <el-descriptions-item label="标准成本">{{ money(detailTarget.standard_cost) }}</el-descriptions-item>
        <el-descriptions-item label="当前价格">{{ money(detailTarget.current_price) }}</el-descriptions-item>
      </el-descriptions>

      <div v-loading="detailLoading">
        <div class="chart-title">价格变动走势（横轴：生效日期，纵轴：价格）</div>
        <template v-if="chart">
          <svg
            class="price-chart"
            :viewBox="`0 0 ${chart.width} ${chart.height}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="产品价格变动折线图"
          >
            <!-- 横向网格与纵轴刻度 -->
            <g>
              <template v-for="tick in chart.yTicks" :key="`y-${tick.y}`">
                <line
                  :x1="chart.left"
                  :x2="chart.width - chart.right"
                  :y1="tick.y"
                  :y2="tick.y"
                  class="chart-grid"
                />
                <text :x="chart.left - 10" :y="tick.y + 4" class="chart-axis-label" text-anchor="end">
                  {{ tick.label }}
                </text>
              </template>
            </g>

            <!-- 坐标轴 -->
            <line
              :x1="chart.left"
              :x2="chart.left"
              :y1="chart.top"
              :y2="chart.height - chart.bottom"
              class="chart-axis"
            />
            <line
              :x1="chart.left"
              :x2="chart.width - chart.right"
              :y1="chart.height - chart.bottom"
              :y2="chart.height - chart.bottom"
              class="chart-axis"
            />

            <!-- 价格折线 -->
            <path v-if="chart.hasLine" :d="chart.path" class="chart-line" />
            <template v-for="dot in chart.dots" :key="`${dot.date}-${dot.price}`">
              <circle :cx="dot.x" :cy="dot.y" r="4" class="chart-dot">
                <title>{{ dot.date }}：{{ dot.price.toFixed(2) }}</title>
              </circle>
            </template>

            <!-- 横轴日期 -->
            <template v-for="tick in chart.xTicks" :key="`x-${tick.x}`">
              <text
                :x="tick.x"
                :y="chart.height - chart.bottom + 22"
                class="chart-axis-label"
                text-anchor="middle"
              >
                {{ tick.label }}
              </text>
            </template>
          </svg>
        </template>
        <el-empty v-else description="暂无价格变动记录" :image-size="80" />
      </div>

      <el-table :data="history" border size="small" max-height="260">
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column label="生效日期" prop="effective_date" width="130" />
        <el-table-column label="价格" width="120" align="right">
          <template #default="{ row }">{{ money(row.price) }}</template>
        </el-table-column>
        <el-table-column label="较上次变动" width="120" align="right">
          <template #default="{ $index }">{{ deltaText($index) }}</template>
        </el-table-column>
        <el-table-column label="说明" prop="remark" min-width="200" />
        <template #empty>暂无价格变动记录</template>
      </el-table>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.table-toolbar__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.price-summary {
  margin-bottom: 12px;
}

.chart-title {
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.price-chart {
  width: 100%;
  height: 300px;
  margin-bottom: 12px;
}

.chart-grid {
  stroke: var(--el-border-color-lighter);
  stroke-width: 1;
}

.chart-axis {
  stroke: var(--el-border-color);
  stroke-width: 1;
}

.chart-line {
  fill: none;
  stroke: var(--el-color-primary);
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.chart-dot {
  fill: var(--el-color-primary);
  stroke: #fff;
  stroke-width: 2;
}

.chart-axis-label {
  font-size: 12px;
  fill: var(--el-text-color-secondary);
}
</style>
