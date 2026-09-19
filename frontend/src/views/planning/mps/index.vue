<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  confirmMpsImport,
  createMps,
  deleteMps,
  listMps,
  previewMpsImport,
  setMpsStatus,
  updateMps,
} from '@/api/planning'
import { listMaterials } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { Mps, MpsImportPreview, RemoteOption } from '@/types/erp'

/** 课程附录 1 内置数据源标识 */
const COURSE_CASE_SOURCE = 'course_chair_case'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Mps, { status: string; year: number | undefined }>(
    (params) => listMps(params),
    { status: '', year: undefined },
  )

async function loadMaterialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, material_type: 'FINISHED', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.material_code} ${item.material_name}` }))
}

interface MpsLineForm {
  material_id: number | undefined
  period_label: string
  planned_qty: number
  start_date: string
  end_date: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  mps_name: string
  program_no: string
  plan_year: number
  start_date: string
  end_date: string
  remark: string
  items: MpsLineForm[]
}>({
  mps_name: '',
  program_no: '',
  plan_year: new Date().getFullYear(),
  start_date: '',
  end_date: '',
  remark: '',
  items: [],
})

const rules: FormRules = {
  plan_year: [{ required: true, message: '请输入计划年度', trigger: 'blur' }],
  start_date: [{ required: true, message: '请选择计划开始日期', trigger: 'change' }],
  end_date: [{ required: true, message: '请选择计划结束日期', trigger: 'change' }],
}

function addLine(): void {
  form.items.push({
    material_id: undefined,
    period_label: '',
    planned_qty: 1,
    start_date: '',
    end_date: '',
  })
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    mps_name: '',
    program_no: '',
    plan_year: new Date().getFullYear(),
    start_date: '',
    end_date: '',
    remark: '',
    items: [],
  })
  addLine()
  dialogVisible.value = true
}

function openEdit(row: Mps): void {
  editingId.value = row.id
  Object.assign(form, {
    mps_name: row.mps_name ?? '',
    program_no: row.program_no ?? '',
    plan_year: row.plan_year,
    start_date: row.start_date,
    end_date: row.end_date,
    remark: row.remark ?? '',
    items: row.items.map((item) => ({
      material_id: item.material_id,
      period_label: item.period_label ?? '',
      planned_qty: toNumber(item.planned_qty),
      start_date: item.start_date,
      end_date: item.end_date,
    })),
  })
  if (!form.items.length) addLine()
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const items = form.items.filter((item) => item.material_id !== undefined)
  if (!items.length) {
    ElMessage.warning('请至少添加一行 MPS 明细')
    return
  }
  submitting.value = true
  try {
    const payload = {
      mps_name: form.mps_name || null,
      program_no: form.program_no || null,
      plan_year: form.plan_year,
      start_date: form.start_date,
      end_date: form.end_date,
      remark: form.remark || null,
      items: items.map((item) => ({
        material_id: item.material_id,
        period_label: item.period_label || null,
        planned_qty: item.planned_qty,
        start_date: item.start_date,
        end_date: item.end_date,
      })),
    }
    if (editingId.value === null) {
      await createMps(payload)
      ElMessage.success('MPS 已新增')
    } else {
      await updateMps(editingId.value, payload)
      ElMessage.success('MPS 已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row: Mps, status: string): Promise<void> {
  try {
    await setMpsStatus(row.id, status)
    ElMessage.success('MPS 状态已更新')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: Mps): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除 MPS「${row.mps_no}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteMps(row.id)
    ElMessage.success('MPS 已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// ---------------- 课程附录 1：导入预览 / 确认 ----------------
const importVisible = ref(false)
const previewing = ref(false)
const confirming = ref(false)
const preview = ref<MpsImportPreview | null>(null)

async function doPreview(): Promise<void> {
  previewing.value = true
  try {
    preview.value = await previewMpsImport({ source: COURSE_CASE_SOURCE })
    ElMessage.success(
      `预览完成：有效 ${preview.value.summary.valid_count} 行，错误 ${preview.value.summary.error_count} 行`,
    )
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    previewing.value = false
  }
}

async function doConfirmImport(): Promise<void> {
  confirming.value = true
  try {
    const created = await confirmMpsImport({ source: COURSE_CASE_SOURCE })
    ElMessage.success(`导入成功，已生成 MPS：${created.mps_no}`)
    importVisible.value = false
    preview.value = null
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    confirming.value = false
  }
}

function openImport(): void {
  preview.value = null
  importVisible.value = true
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">主生产计划 MPS</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="openImport">课程案例导入</el-button>
          <el-button type="primary" @click="openCreate">新增 MPS</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="计划年度">
          <el-input-number v-model="query.year" :min="2000" :max="2100" :controls="false" placeholder="全部" style="width: 120px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="草稿" value="DRAFT" />
            <el-option label="已确认" value="CONFIRMED" />
            <el-option label="已下达" value="RELEASED" />
            <el-option label="执行中" value="IN_PROGRESS" />
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
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table :data="row.items" size="small" border class="nested-table">
              <el-table-column label="物料ID" prop="material_id" width="100" align="right" />
              <el-table-column label="期间" prop="period_label" width="110" />
              <el-table-column label="计划数量" prop="planned_qty" width="110" align="right" />
              <el-table-column label="已完工" prop="finished_qty" width="100" align="right" />
              <el-table-column label="开始日期" prop="start_date" width="110" />
              <el-table-column label="完成日期" prop="end_date" width="110" />
              <el-table-column label="状态" width="90">
                <template #default="{ row: item }"><StatusTag :status="item.status" /></template>
              </el-table-column>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="MPS 编号" prop="mps_no" min-width="150" />
        <el-table-column label="计划名称" prop="mps_name" min-width="150" />
        <el-table-column label="项目号" prop="program_no" min-width="120" />
        <el-table-column label="年度" prop="plan_year" width="80" align="right" />
        <el-table-column label="开始日期" prop="start_date" width="110" />
        <el-table-column label="结束日期" prop="end_date" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="270" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="changeStatus(row, 'CONFIRMED')">
              确认
            </el-button>
            <el-button v-if="row.status === 'CONFIRMED'" link type="primary" @click="changeStatus(row, 'RELEASED')">
              下达
            </el-button>
            <el-button v-if="row.status === 'RELEASED'" link type="warning" @click="changeStatus(row, 'IN_PROGRESS')">
              开始执行
            </el-button>
            <el-button v-if="row.status === 'IN_PROGRESS'" link type="success" @click="changeStatus(row, 'COMPLETED')">
              完成
            </el-button>
            <el-button
              v-if="['DRAFT', 'CONFIRMED', 'RELEASED'].includes(row.status)"
              link
              type="danger"
              @click="changeStatus(row, 'CANCELLED')"
            >
              取消
            </el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status === 'DRAFT'" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无 MPS 数据</template>
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

    <!-- 新增 / 修改 MPS -->
    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增 MPS' : '修改 MPS'" width="920px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="计划名称"><el-input v-model="form.mps_name" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="项目号"><el-input v-model="form.program_no" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="计划年度" prop="plan_year">
              <el-input-number v-model="form.plan_year" :min="2000" :max="2100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="开始日期" prop="start_date">
              <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="结束日期" prop="end_date">
              <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="备注"><el-input v-model="form.remark" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="table-toolbar">
        <span class="page-title">MPS 明细</span>
        <span class="table-toolbar__spacer" />
        <el-button size="small" @click="addLine">添加行</el-button>
      </div>
      <el-table :data="form.items" border size="small">
        <el-table-column label="产成品" min-width="220">
          <template #default="{ row }">
            <RemoteSelect v-model="row.material_id" :loader="loadMaterialOptions" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="期间" width="120">
          <template #default="{ row }"><el-input v-model="row.period_label" placeholder="如 2025-01" /></template>
        </el-table-column>
        <el-table-column label="计划数量" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.planned_qty" :min="0.0001" :controls="false" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="开始日期" width="150">
          <template #default="{ row }">
            <el-date-picker v-model="row.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="完成日期" width="150">
          <template #default="{ row }">
            <el-date-picker v-model="row.end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ $index }">
            <el-button link type="danger" @click="form.items.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 课程附录 1 导入 -->
    <el-dialog v-model="importVisible" title="课程案例导入（先预览后确认）" width="880px">
      <p class="form-tip">
        数据源：{{ COURSE_CASE_SOURCE }}（后端读取课程权威数据文件）。预览不写库，确认后才写入 MPS 头与行。
      </p>
      <div class="table-toolbar">
        <el-button type="primary" :loading="previewing" @click="doPreview">预览导入数据</el-button>
        <el-button
          type="success"
          :loading="confirming"
          :disabled="!preview || preview.summary.valid_count === 0"
          @click="doConfirmImport"
        >
          确认导入
        </el-button>
      </div>

      <template v-if="preview">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 12px">
          <el-descriptions-item label="总行数">{{ preview.summary.total_rows }}</el-descriptions-item>
          <el-descriptions-item label="有效行">{{ preview.summary.valid_count }}</el-descriptions-item>
          <el-descriptions-item label="错误行">{{ preview.summary.error_count }}</el-descriptions-item>
          <el-descriptions-item label="计划年度">{{ preview.summary.plan_year }}</el-descriptions-item>
          <el-descriptions-item label="开始日期">{{ preview.summary.start_date ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束日期">{{ preview.summary.end_date ?? '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="preview.errors.length"
          type="error"
          :closable="false"
          show-icon
          title="存在校验不通过的行"
          style="margin-bottom: 12px"
        >
          <div v-for="err in preview.errors" :key="err.row">第 {{ err.row + 1 }} 行：{{ err.message }}</div>
        </el-alert>

        <el-table :data="preview.valid_rows" border size="small" max-height="320">
          <el-table-column label="行号" prop="row_index" width="70" align="right" />
          <el-table-column label="物料编码" prop="material_code" min-width="130" />
          <el-table-column label="物料名称" prop="material_name" min-width="150" />
          <el-table-column label="期间" prop="period_label" width="110" />
          <el-table-column label="计划数量" prop="planned_qty" width="110" align="right" />
          <el-table-column label="开始日期" prop="start_date" width="110" />
          <el-table-column label="完成日期" prop="end_date" width="110" />
        </el-table>
      </template>

      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.nested-table {
  margin: 4px 0 4px 48px;
  width: calc(100% - 48px);
}
</style>