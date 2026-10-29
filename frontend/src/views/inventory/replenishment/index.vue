<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  cancelReplenishmentRequest,
  confirmReplenishmentRequest,
  createReplenishmentRequest,
  generateFromSafetyStock,
  getSafetyStockSuggestions,
  listBalances,
  listReplenishmentRequests,
  listWarehouses,
} from '@/api/inventory'
import { createDemandFromReplenishment } from '@/api/planning'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import { fmtQty } from '@/utils/format'
import type { RemoteOption, ReplenishmentRequest, SafetyStockSuggestion } from '@/types/erp'

const SOURCE_LABELS: Record<string, string> = {
  REORDER: '采购补库',
  PRODUCTION: '生产补库',
}

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    ReplenishmentRequest,
    { status: string; source_type: string; material_id: number | undefined }
  >((params) => listReplenishmentRequests(params), { status: '', source_type: '', material_id: undefined })

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  material_id: number | undefined
  warehouse_id: number | undefined
  request_qty: number
  required_date: string
  source_type: string
  current_qty: number
  target_qty: number
  remark: string
}>({
  material_id: undefined,
  warehouse_id: undefined,
  request_qty: 1,
  required_date: '',
  source_type: 'REORDER',
  current_qty: 0,
  target_qty: 0,
  remark: '',
})

const rules: FormRules = {
  material_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
  request_qty: [{ required: true, message: '请输入补库数量', trigger: 'blur' }],
  required_date: [{ required: true, message: '请选择需求日期', trigger: 'change' }],
}

function openCreate(): void {
  Object.assign(form, {
    material_id: undefined,
    warehouse_id: undefined,
    request_qty: 1,
    required_date: '',
    source_type: 'REORDER',
    current_qty: 0,
    target_qty: 0,
    remark: '',
  })
  dialogVisible.value = true
}

/** 按所选物料 + 仓库查询真实结存，带出当前库存并推算目标库存 */
async function fillFromBalance(): Promise<void> {
  if (!form.material_id || !form.warehouse_id) {
    ElMessage.warning('请先选择物料与仓库')
    return
  }
  try {
    const data = await listBalances({
      material_id: form.material_id,
      warehouse_id: form.warehouse_id,
      page: 1,
      page_size: 50,
    })
    const current = data.items.reduce((sum, item) => sum + toNumber(item.available_quantity), 0)
    form.current_qty = current
    form.target_qty = current + (form.request_qty || 0)
    ElMessage.success(`已带出当前可用库存：${current}`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const created = await createReplenishmentRequest({
      material_id: form.material_id,
      warehouse_id: form.warehouse_id,
      request_qty: form.request_qty,
      required_date: form.required_date,
      source_type: form.source_type,
      current_qty: form.current_qty,
      target_qty: form.target_qty,
      remark: form.remark || null,
    })
    ElMessage.success(`补库需求已新增：${created.request_no}`)
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function doGenerateFromSafetyStock(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将按物料安全库存扫描可用量，自动生成补库需求（采购件转采购、自制件转生产），是否继续？',
      '按安全库存生成补库需求',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const result = await generateFromSafetyStock()
    ElMessage.success(`新建 ${result.created_count} 条，跳过 ${result.skipped_count} 条`)
    await load()
    await loadSuggestions()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 安全库存补库建议 ----------------

const suggestionLoading = ref(false)
const suggestions = ref<SafetyStockSuggestion[]>([])

async function loadSuggestions(): Promise<void> {
  suggestionLoading.value = true
  try {
    suggestions.value = await getSafetyStockSuggestions()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    suggestionLoading.value = false
  }
}

async function doConfirm(row: ReplenishmentRequest): Promise<void> {
  try {
    await confirmReplenishmentRequest(row.id)
    ElMessage.success('补库需求已确认，已按来源转入计划 / 采购')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCreateDemand(row: ReplenishmentRequest): Promise<void> {
  try {
    const demand = await createDemandFromReplenishment(row.id)
    ElMessage.success(`已生成计划需求：${demand.demand_no}`)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function doCancel(row: ReplenishmentRequest): Promise<void> {
  try {
    await cancelReplenishmentRequest(row.id)
    ElMessage.success('补库需求已取消')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(() => {
  load()
  loadSuggestions()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">安全库存补库建议（低于安全库存时系统自动生成补库需求）</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="loadSuggestions">刷新</el-button>
          <el-button type="primary" :disabled="!suggestions.length" @click="doGenerateFromSafetyStock">
            补生成缺失需求
          </el-button>
        </div>
      </template>
      <el-table v-loading="suggestionLoading" :data="suggestions" border size="small">
        <el-table-column label="物料编码" prop="material_code" min-width="130" />
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="仓库" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.warehouse_code }} {{ row.warehouse_name }}</template>
        </el-table-column>
        <el-table-column label="可用量" width="100" align="right"><template #default="{ row }">{{ fmtQty(row.available_quantity) }}</template></el-table-column>
        <el-table-column label="安全库存" width="100" align="right"><template #default="{ row }">{{ fmtQty(row.safety_stock) }}</template></el-table-column>
        <el-table-column label="建议补库量" width="110" align="right"><template #default="{ row }">{{ fmtQty(row.suggested_qty) }}</template></el-table-column>
        <el-table-column label="补库方式" width="100">
          <template #default="{ row }">{{ SOURCE_LABELS[row.source_type] || row.source_type }}</template>
        </el-table-column>
        <template #empty>暂无低于安全库存的物料</template>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 12px">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">补库需求</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增补库需求</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="物料">
          <RemoteSelect v-model="query.material_id" :loader="loadMaterialOptions" placeholder="全部" style="width: 220px" />
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="query.source_type" clearable placeholder="全部" style="width: 130px">
            <el-option label="采购补库" value="REORDER" />
            <el-option label="生产补库" value="PRODUCTION" />
          </el-select>
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
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="补库单号" prop="request_no" min-width="150" />
        <el-table-column label="物料编码" prop="material_code" min-width="120" />
        <el-table-column label="物料名称" prop="material_name" min-width="150" />
        <el-table-column label="仓库ID" prop="warehouse_id" width="90" align="right" />
        <el-table-column label="补库数量" width="110" align="right"><template #default="{ row }">{{ fmtQty(row.request_qty) }}</template></el-table-column>
        <el-table-column label="当前库存" width="110" align="right"><template #default="{ row }">{{ fmtQty(row.current_qty) }}</template></el-table-column>
        <el-table-column label="目标库存" width="110" align="right"><template #default="{ row }">{{ fmtQty(row.target_qty) }}</template></el-table-column>
        <el-table-column label="需求日期" prop="required_date" width="110" />
        <el-table-column label="来源" width="100">
          <template #default="{ row }">{{ SOURCE_LABELS[row.source_type] || row.source_type }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="处理去向" min-width="150">
          <template #default="{ row }">
            <span v-if="row.handled_module">{{ row.handled_module }} #{{ row.handled_ref_id ?? '-' }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="doConfirm(row)">
              确认并转计划/采购
            </el-button>
            <el-button
              v-if="row.status === 'CONFIRMED' && row.source_type === 'PRODUCTION'"
              link
              type="primary"
              @click="doCreateDemand(row)"
            >
              生成计划需求
            </el-button>
            <el-button
              v-if="['DRAFT', 'CONFIRMED'].includes(row.status)"
              link
              type="danger"
              @click="doCancel(row)"
            >
              取消
            </el-button>
            <span v-if="!['DRAFT', 'CONFIRMED'].includes(row.status)">-</span>
          </template>
        </el-table-column>
        <template #empty>暂无补库需求数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增补库需求" width="680px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="物料" prop="material_id">
          <RemoteSelect v-model="form.material_id" :loader="loadMaterialOptions" placeholder="请选择物料" style="width: 100%" />
        </el-form-item>
        <el-form-item label="仓库" prop="warehouse_id">
          <RemoteSelect v-model="form.warehouse_id" :loader="loadWarehouseOptions" placeholder="请选择仓库" style="width: 100%" />
        </el-form-item>
        <el-form-item label="补库数量" prop="request_qty">
          <el-input-number v-model="form.request_qty" :min="0.0001" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="需求日期" prop="required_date">
          <el-date-picker v-model="form.required_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="补库来源">
          <el-select v-model="form.source_type" style="width: 100%">
            <el-option label="采购补库（转采购）" value="REORDER" />
            <el-option label="生产补库（转计划）" value="PRODUCTION" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前 / 目标库存">
          <el-input-number v-model="form.current_qty" :min="0" :controls="false" style="width: 45%" />
          <span style="margin: 0 8px">→</span>
          <el-input-number v-model="form.target_qty" :min="0" :controls="false" style="width: 45%" />
          <el-button link type="primary" style="margin-left: 8px" @click="fillFromBalance">按结存带出</el-button>
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