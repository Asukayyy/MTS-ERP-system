<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { confirmStockOperation, createStockOperation, listWarehouses } from '@/api/inventory'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import type { RemoteOption } from '@/types/erp'

/**
 * 新建入库单 / 出库单弹窗。
 *
 * - 来源类型与列表筛选同口径：入库只有销售退货 / 采购到货 / 生产完工，出库只有销售发货 / 生产领料；
 * - 明细支持多行（物料 + 数量 + 行备注），数量按整数件管理；
 * - 提交时先建单（DRAFT）再用所选仓库确认，确认后结存才真正增加 / 减少，流水记录来源。
 */
const props = defineProps<{ modelValue: boolean; opType: 'INBOUND' | 'OUTBOUND' }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; created: [] }>()

const actionLabel = computed(() => (props.opType === 'INBOUND' ? '入库' : '出库'))

const SOURCE_TYPE_OPTIONS: Record<'INBOUND' | 'OUTBOUND', { value: string; label: string }[]> = {
  INBOUND: [
    { value: 'SALES_RETURN', label: '销售退货' },
    { value: 'PURCHASE_RECEIPT', label: '采购到货' },
    { value: 'PRODUCTION_COMPLETION', label: '生产完工' },
  ],
  OUTBOUND: [
    { value: 'SALES_SHIPMENT', label: '销售发货' },
    { value: 'MATERIAL_REQUISITION', label: '生产领料' },
  ],
}
const sourceTypeOptions = computed(() => SOURCE_TYPE_OPTIONS[props.opType])

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

/** 明细行：物料 + 数量 + 行备注 */
type ItemRow = { material_id: number | undefined; quantity: number; remark: string }

function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function emptyRow(): ItemRow {
  return { material_id: undefined, quantity: 1, remark: '' }
}

const formRef = ref<FormInstance>()
const submitting = ref(false)
const form = reactive<{
  source_type: string
  source_no: string
  warehouse_id: number | undefined
  op_date: string
  remark: string
  items: ItemRow[]
}>({
  source_type: SOURCE_TYPE_OPTIONS[props.opType][0].value,
  source_no: '',
  warehouse_id: undefined,
  op_date: today(),
  remark: '',
  items: [emptyRow()],
})

const rules: FormRules = {
  source_type: [{ required: true, message: '请选择来源类型', trigger: 'change' }],
  op_date: [{ required: true, message: '请选择业务日期', trigger: 'change' }],
  warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
}

function reset(): void {
  form.source_type = SOURCE_TYPE_OPTIONS[props.opType][0].value
  form.source_no = ''
  form.warehouse_id = undefined
  form.op_date = today()
  form.remark = ''
  form.items = [emptyRow()]
  formRef.value?.clearValidate()
}

watch(
  () => props.modelValue,
  (opened) => {
    if (opened) reset()
  },
)

function addRow(): void {
  form.items.push(emptyRow())
}

function removeRow(index: number): void {
  if (form.items.length <= 1) return
  form.items.splice(index, 1)
}

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

async function loadWarehouseOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listWarehouses({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.warehouse_code} ${item.warehouse_name}` }))
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const invalidRow = form.items.find((row) => !row.material_id || !Number.isInteger(row.quantity) || row.quantity <= 0)
  if (invalidRow) {
    ElMessage.warning('每条明细都要选择物料，并填写大于 0 的整数数量')
    return
  }

  submitting.value = true
  try {
    const created = await createStockOperation({
      op_type: props.opType,
      op_date: form.op_date,
      warehouse_id: form.warehouse_id,
      source_module: 'inventory',
      source_type: form.source_type,
      source_no: form.source_no || null,
      remark: form.remark || null,
      items: form.items.map((row) => ({
        material_id: row.material_id,
        quantity: row.quantity,
        remark: row.remark || null,
      })),
    })

    try {
      await confirmStockOperation(created.id, { warehouse_id: form.warehouse_id })
    } catch (error) {
      // 建单成功但确认失败（如出库可用量不足 5001）：单据保留在列表里，可再次确认
      emit('created')
      visible.value = false
      ElMessage.warning(
        `${actionLabel.value}单 ${created.operation_no} 已生成，但确认未成功：${(error as Error).message}；请稍后在列表中重新确认`,
      )
      return
    }

    ElMessage.success(`${actionLabel.value}单 ${created.operation_no} 已完成，库存结存已更新`)
    emit('created')
    visible.value = false
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="`新建${actionLabel}单`" width="900px">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="来源类型" prop="source_type">
            <el-select v-model="form.source_type" placeholder="请选择来源" style="width: 100%">
              <el-option
                v-for="item in sourceTypeOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="来源单号">
            <el-input v-model="form.source_no" placeholder="对应业务单据号，可选" clearable />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="业务日期" prop="op_date">
            <el-date-picker
              v-model="form.op_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="缺省为当天"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="16">
          <el-form-item :label="`${actionLabel}仓库`" prop="warehouse_id">
            <RemoteSelect
              v-model="form.warehouse_id"
              :loader="loadWarehouseOptions"
              placeholder="请选择仓库"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item label="备注">
            <el-input v-model="form.remark" placeholder="单据说明 / 原因" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="detail-head">
      <span>明细</span>
      <el-button link type="primary" @click="addRow">+ 添加一行</el-button>
    </div>

    <el-table :data="form.items" border size="small">
      <el-table-column label="物料" min-width="260">
        <template #default="{ row }">
          <RemoteSelect
            v-model="row.material_id"
            :loader="loadMaterialOptions"
            placeholder="请选择物料"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column :label="`${actionLabel}数量`" width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.quantity"
            :min="1"
            :precision="0"
            :step="1"
            :controls="false"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column label="行备注" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.remark" placeholder="可选" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" :disabled="form.items.length <= 1" @click="removeRow($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="form-tip">
      提交后立即按所选仓库确认：{{ actionLabel }}数量按整数件处理；出库可用量不足会被拒绝（错误码 5001），单据保留为待确认。
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        生成并确认{{ actionLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 4px 0 8px;
  font-weight: 600;
}
</style>
