<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createForecast,
  deleteForecast,
  getForecastSummary,
  listCustomers,
  listForecasts,
  listProducts,
  setForecastStatus,
  updateForecast,
} from '@/api/sales'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Forecast, ForecastSummary, RemoteOption } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    Forecast,
    {
      material_id: number | undefined
      status: string
      forecast_month: string
      sales_category: string
    }
  >((params) => listForecasts(params), {
    material_id: undefined,
    status: '',
    forecast_month: '',
    sales_category: '',
  })

/** 销售类别：整机 / 可售备件（如转椅轮子）/ 内部件 */
const SALES_CATEGORIES = [
  { value: 'MACHINE', label: '整机' },
  { value: 'SPARE', label: '可售备件' },
  { value: 'INTERNAL', label: '内部件' },
]

const summary = ref<ForecastSummary[]>([])

function summaryOf(category: string): { qty: number; count: number } {
  const hit = summary.value.find((item) => item.sales_category === category)
  return { qty: hit ? Number(hit.forecast_qty) : 0, count: hit?.count ?? 0 }
}

async function loadSummary(): Promise<void> {
  try {
    summary.value = await getForecastSummary({
      material_id: query.material_id,
      status: query.status || undefined,
      forecast_month: query.forecast_month || undefined,
      sales_category: query.sales_category || undefined,
    })
  } catch {
    summary.value = []
  }
}

async function doSearch(): Promise<void> {
  await search()
  await loadSummary()
}

async function doReset(): Promise<void> {
  await reset()
  await loadSummary()
}

/** 客户选项 */
async function loadCustomerOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listCustomers({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.customer_code} ${item.customer_name}` }))
}

/** 可销售成品选项 */
async function loadProductOptions(keyword: string): Promise<RemoteOption[]> {
  const list = await listProducts({ keyword })
  return list.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  customer_id: number | undefined
  material_id: number | undefined
  forecast_month: string
  forecast_qty: number
  remark: string
}>({
  customer_id: undefined,
  material_id: undefined,
  forecast_month: '',
  forecast_qty: 1,
  remark: '',
})

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  forecast_month: [{ required: true, message: '请选择预测月份', trigger: 'change' }],
  forecast_qty: [{ required: true, message: '请输入预测数量', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    customer_id: undefined,
    material_id: undefined,
    forecast_month: '',
    forecast_qty: 1,
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: Forecast): void {
  editingId.value = row.id
  Object.assign(form, {
    customer_id: row.customer_id ?? undefined,
    material_id: row.material_id,
    forecast_month: row.forecast_month,
    forecast_qty: Number(row.forecast_qty),
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const payload = {
      customer_id: form.customer_id ?? null,
      material_id: form.material_id,
      forecast_month: form.forecast_month,
      forecast_qty: form.forecast_qty,
      remark: form.remark || null,
    }
    if (editingId.value === null) {
      await createForecast(payload)
      ElMessage.success('销售预测已新增')
    } else {
      await updateForecast(editingId.value, payload)
      ElMessage.success('销售预测已修改')
    }
    dialogVisible.value = false
    await load()
    await loadSummary()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row: Forecast, status: string): Promise<void> {
  try {
    await setForecastStatus(row.id, status)
    ElMessage.success('状态已更新')
    await load()
    await loadSummary()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: Forecast): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除预测单「${row.forecast_no}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteForecast(row.id)
    ElMessage.success('销售预测已删除')
    await load()
    await loadSummary()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(() => {
  load()
  loadSummary()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">销售预测</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增预测</el-button>
        </div>
      </template>

      <div class="summary-cards">
        <div class="summary-card summary-card--machine">
          <span class="summary-card__label">整机预测</span>
          <span class="summary-card__value">{{ summaryOf('MACHINE').qty }}</span>
          <span class="summary-card__meta">{{ summaryOf('MACHINE').count }} 条预测</span>
        </div>
        <div class="summary-card summary-card--spare">
          <span class="summary-card__label">可售备件预测</span>
          <span class="summary-card__value">{{ summaryOf('SPARE').qty }}</span>
          <span class="summary-card__meta">{{ summaryOf('SPARE').count }} 条预测</span>
        </div>
        <div class="summary-card summary-card--internal">
          <span class="summary-card__label">内部件预测</span>
          <span class="summary-card__value">{{ summaryOf('INTERNAL').qty }}</span>
          <span class="summary-card__meta">{{ summaryOf('INTERNAL').count }} 条预测</span>
        </div>
      </div>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="物料">
          <RemoteSelect v-model="query.material_id" :loader="loadProductOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item label="销售类别">
          <el-select v-model="query.sales_category" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="item in SALES_CATEGORIES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="预测月份">
          <el-date-picker
            v-model="query.forecast_month"
            type="month"
            value-format="YYYY-MM"
            placeholder="全部"
            clearable
            style="width: 150px"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
            <el-option label="已完成" value="COMPLETED" />
            <el-option label="已取消" value="CANCELLED" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doSearch">查询</el-button>
          <el-button @click="doReset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="预测单号" prop="forecast_no" min-width="150" />
        <el-table-column label="客户" prop="customer_name" min-width="150" />
        <el-table-column label="销售类别" width="100">
          <template #default="{ row }">
            {{ SALES_CATEGORIES.find((item) => item.value === row.material_sales_category)?.label ?? '内部件' }}
          </template>
        </el-table-column>
        <el-table-column label="ABC" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.material_abc_class" :type="row.material_abc_class === 'A' ? 'danger' : row.material_abc_class === 'B' ? 'warning' : 'info'" size="small">
              {{ row.material_abc_class }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="140" />
        <el-table-column label="预测月份" prop="forecast_month" width="110" />
        <el-table-column label="预测数量" prop="forecast_qty" width="110" align="right" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="changeStatus(row, 'CONFIRMED')">
              确认
            </el-button>
            <el-button
              v-if="row.status === 'DRAFT' || row.status === 'CONFIRMED'"
              link
              type="success"
              @click="changeStatus(row, 'COMPLETED')"
            >
              完成
            </el-button>
            <el-button
              v-if="row.status === 'DRAFT' || row.status === 'CONFIRMED'"
              link
              type="warning"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无销售预测数据</template>
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

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增销售预测' : '修改销售预测'" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="客户">
          <RemoteSelect v-model="form.customer_id" :loader="loadCustomerOptions" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="物料" prop="material_id">
          <RemoteSelect v-model="form.material_id" :loader="loadProductOptions" style="width: 100%" />
        </el-form-item>
        <el-form-item label="预测月份" prop="forecast_month">
          <el-date-picker v-model="form.forecast_month" type="month" value-format="YYYY-MM" style="width: 100%" />
        </el-form-item>
        <el-form-item label="预测数量" prop="forecast_qty">
          <el-input-number v-model="form.forecast_qty" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.summary-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.summary-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #e6ebf2;
  background: #f7f9fc;
}

.summary-card--machine {
  border-color: #cfe3ff;
  background: #f2f8ff;
}

.summary-card--spare {
  border-color: #c8ebe4;
  background: #f1fbf8;
}

.summary-card__label {
  font-size: 12px;
  color: #5b6b7c;
}

.summary-card__value {
  font-size: 20px;
  font-weight: 600;
  color: #1f2d3d;
}

.summary-card__meta {
  font-size: 12px;
  color: #98a2ad;
}
</style>