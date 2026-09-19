<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createOrderFromPlan,
  createPurchasePlan,
  getPurchasePlan,
  listPurchasePlans,
  listSuppliers,
  setPurchasePlanStatus,
} from '@/api/procurement'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { PurchasePlan, RemoteOption } from '@/types/erp'

const SOURCE_LABELS: Record<string, string> = {
  MRP: 'MRP 运算',
  REORDER: '订货点补库',
  MANUAL: '手工录入',
}

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<PurchasePlan, { status: string }>((params) => listPurchasePlans(params), { status: '' })

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, supply_type: 'BUY', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadSupplierOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listSuppliers({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.supplier_code} ${item.supplier_name}` }))
}

interface PlanLineForm {
  material_id: number | undefined
  required_qty: number
  required_date: string
  source_type: string
  source_reference_id: number | undefined
  supplier_id: number | undefined
  remark: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  plan_no: string
  plan_date: string
  remark: string
  items: PlanLineForm[]
}>({ plan_no: '', plan_date: '', remark: '', items: [] })

const rules: FormRules = {
  plan_date: [{ required: true, message: '请选择计划日期', trigger: 'change' }],
}

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<PurchasePlan | null>(null)

function addLine(): void {
  form.items.push({
    material_id: undefined,
    required_qty: 1,
    required_date: '',
    source_type: 'MANUAL',
    source_reference_id: undefined,
    supplier_id: undefined,
    remark: '',
  })
}

function removeLine(index: number): void {
  form.items.splice(index, 1)
}

function openCreate(): void {
  Object.assign(form, { plan_no: '', plan_date: '', remark: '', items: [] })
  addLine()
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.items.length === 0) {
    ElMessage.warning('请至少添加一行采购计划明细')
    return
  }
  if (form.items.some((item) => !item.material_id || !item.required_date)) {
    ElMessage.warning('请为每一行选择物料并填写需求日期')
    return
  }
  submitting.value = true
  try {
    await createPurchasePlan({
      plan_no: form.plan_no || null,
      plan_date: form.plan_date,
      remark: form.remark || null,
      items: form.items.map((item) => ({
        material_id: item.material_id,
        required_qty: item.required_qty,
        required_date: item.required_date,
        source_type: item.source_type,
        source_reference_id: item.source_reference_id ?? null,
        supplier_id: item.supplier_id ?? null,
        remark: item.remark || null,
      })),
    })
    ElMessage.success('采购计划已新增')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function openDetail(row: PurchasePlan): Promise<void> {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getPurchasePlan(row.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    detailLoading.value = false
  }
}

async function changeStatus(row: PurchasePlan, status: string): Promise<void> {
  try {
    await setPurchasePlanStatus(row.id, status)
    ElMessage.success('采购计划状态已更新')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 由计划生成采购订单 ----------------

const orderVisible = ref(false)
const orderSubmitting = ref(false)
const orderPlan = ref<PurchasePlan | null>(null)
const orderForm = reactive<{
  supplier_id: number | undefined
  order_date: string
  expected_date: string
  remark: string
}>({ supplier_id: undefined, order_date: '', expected_date: '', remark: '' })

function openOrder(row: PurchasePlan): void {
  orderPlan.value = row
  Object.assign(orderForm, { supplier_id: undefined, order_date: '', expected_date: '', remark: '' })
  orderVisible.value = true
}

async function submitOrder(): Promise<void> {
  if (!orderPlan.value) return
  if (!orderForm.supplier_id) {
    ElMessage.warning('请选择供应商')
    return
  }
  orderSubmitting.value = true
  try {
    const order = await createOrderFromPlan({
      plan_id: orderPlan.value.id,
      supplier_id: orderForm.supplier_id,
      order_date: orderForm.order_date || null,
      expected_date: orderForm.expected_date || null,
      remark: orderForm.remark || null,
    })
    ElMessage.success(`采购订单 ${order.order_no} 已生成`)
    orderVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    orderSubmitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">采购计划</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增采购计划</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
            <el-option label="已下达" value="RELEASED" />
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
        <el-table-column label="计划编号" prop="plan_no" min-width="150" />
        <el-table-column label="计划日期" prop="plan_date" width="110" />
        <el-table-column label="明细行数" width="100" align="right">
          <template #default="{ row }">{{ row.items?.length ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="180" />
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看明细</el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="changeStatus(row, 'CONFIRMED')">
              确认
            </el-button>
            <el-button v-if="row.status === 'CONFIRMED'" link type="primary" @click="changeStatus(row, 'RELEASED')">
              下达
            </el-button>
            <el-button v-if="row.status === 'RELEASED'" link type="success" @click="changeStatus(row, 'COMPLETED')">
              完成
            </el-button>
            <el-button
              v-if="!['COMPLETED', 'CANCELLED'].includes(row.status)"
              link
              type="warning"
              @click="openOrder(row)"
            >
              生成采购订单
            </el-button>
            <el-button
              v-if="['DRAFT', 'CONFIRMED', 'RELEASED'].includes(row.status)"
              link
              type="danger"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无采购计划数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增采购计划" width="960px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="计划编号">
              <el-input v-model="form.plan_no" placeholder="留空自动生成" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计划日期" prop="plan_date">
              <el-date-picker v-model="form.plan_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">采购计划明细</el-divider>
        <div class="table-toolbar">
          <span class="table-toolbar__spacer" />
          <el-button size="small" @click="addLine">添加明细行</el-button>
        </div>
        <el-table :data="form.items" border size="small">
          <el-table-column label="物料" min-width="200">
            <template #default="{ row }">
              <RemoteSelect v-model="row.material_id" :loader="loadMaterialOptions" placeholder="请选择物料" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="需求数量" width="130">
            <template #default="{ row }">
              <el-input-number v-model="row.required_qty" :min="0.0001" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="需求日期" width="150">
            <template #default="{ row }">
              <el-date-picker v-model="row.required_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="来源" width="130">
            <template #default="{ row }">
              <el-select v-model="row.source_type" style="width: 100%">
                <el-option label="手工录入" value="MANUAL" />
                <el-option label="MRP 运算" value="MRP" />
                <el-option label="订货点补库" value="REORDER" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="建议供应商" min-width="180">
            <template #default="{ row }">
              <RemoteSelect v-model="row.supplier_id" :loader="loadSupplierOptions" placeholder="可选" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeLine($index)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>请添加采购计划明细行</template>
        </el-table>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="采购计划明细" width="900px">
      <div v-loading="detailLoading">
        <el-descriptions v-if="detail" :column="3" border size="small">
          <el-descriptions-item label="计划编号">{{ detail.plan_no }}</el-descriptions-item>
          <el-descriptions-item label="计划日期">{{ detail.plan_date }}</el-descriptions-item>
          <el-descriptions-item label="状态"><StatusTag :status="detail.status" /></el-descriptions-item>
        </el-descriptions>
        <el-table v-if="detail" :data="detail.items" border size="small" style="margin-top: 12px">
          <el-table-column label="物料" min-width="200">
            <template #default="{ row }">
              {{ row.material_code ? `${row.material_code} ${row.material_name ?? ''}` : `ID ${row.material_id}` }}
            </template>
          </el-table-column>
          <el-table-column label="需求数量" prop="required_qty" width="110" align="right" />
          <el-table-column label="已下单数量" prop="ordered_qty" width="110" align="right" />
          <el-table-column label="需求日期" prop="required_date" width="110" />
          <el-table-column label="来源" width="110">
            <template #default="{ row }">{{ SOURCE_LABELS[row.source_type] || row.source_type }}</template>
          </el-table-column>
          <el-table-column label="建议供应商" min-width="160">
            <template #default="{ row }">
              {{ row.supplier_name || (row.supplier_id ? `ID ${row.supplier_id}` : '-') }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }"><StatusTag :status="row.status" /></template>
          </el-table-column>
          <template #empty>暂无明细</template>
        </el-table>
      </div>
    </el-dialog>

    <el-dialog v-model="orderVisible" title="由采购计划生成采购订单" width="620px">
      <el-form label-width="120px">
        <el-form-item label="采购计划">
          <el-input :model-value="orderPlan ? `${orderPlan.plan_no}（${orderPlan.plan_date}）` : ''" disabled />
        </el-form-item>
        <el-form-item label="供应商" required>
          <RemoteSelect
            v-model="orderForm.supplier_id"
            :loader="loadSupplierOptions"
            placeholder="请选择供应商（决定供货价与提前期）"
            style="width: 100%"
          />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="下单日期">
              <el-date-picker
                v-model="orderForm.order_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="默认今天"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预计到货">
              <el-date-picker
                v-model="orderForm.expected_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="按供货提前期推算"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="orderForm.remark" type="textarea" :rows="2" />
        </el-form-item>
        <div class="form-tip">仅「未下单数量 &gt; 0」的计划行会进入订单，单价取供应商供货价。</div>
      </el-form>
      <template #footer>
        <el-button @click="orderVisible = false">取消</el-button>
        <el-button type="primary" :loading="orderSubmitting" @click="submitOrder">生成订单</el-button>
      </template>
    </el-dialog>
  </div>
</template>