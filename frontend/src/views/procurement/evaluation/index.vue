<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createAutoEvaluation,
  createEvaluation,
  deleteEvaluation,
  listEvaluations,
  listSuppliers,
} from '@/api/procurement'
import { listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import { usePagedTable, toNumber } from '@/composables/usePagedTable'
import type { RemoteOption, SupplierEvaluation } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<SupplierEvaluation, { supplier_id: number | undefined }>(
    (params) => listEvaluations(params),
    { supplier_id: undefined },
  )

async function loadSupplierOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listSuppliers({ keyword, status: 'ACTIVE', page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.supplier_code} ${item.supplier_name}` }))
}

async function loadEvaluatorOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

// ---------------- 算法公示 ----------------

const algorithmVisible = ref(true)

// ---------------- 手工录入 ----------------

const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<{
  supplier_id: number | undefined
  evaluate_date: string
  quality_score: number
  delivery_score: number
  price_score: number
  evaluator_id: number | undefined
  remark: string
}>({
  supplier_id: undefined,
  evaluate_date: '',
  quality_score: 80,
  delivery_score: 80,
  price_score: 80,
  evaluator_id: undefined,
  remark: '',
})

const rules: FormRules = {
  supplier_id: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  evaluate_date: [{ required: true, message: '请选择评价日期', trigger: 'change' }],
}

function openCreate(): void {
  Object.assign(form, {
    supplier_id: undefined,
    evaluate_date: '',
    quality_score: 80,
    delivery_score: 80,
    price_score: 80,
    evaluator_id: undefined,
    remark: '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    // 综合得分由后端按质量/交付/价格三项平均计算，前端不提交
    await createEvaluation({
      supplier_id: form.supplier_id,
      evaluate_date: form.evaluate_date,
      quality_score: form.quality_score,
      delivery_score: form.delivery_score,
      price_score: form.price_score,
      evaluator_id: form.evaluator_id ?? null,
      remark: form.remark || null,
    })
    ElMessage.success('供应商评价已登记')
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

// ---------------- 自动评价 ----------------

const autoDialogVisible = ref(false)
const autoSubmitting = ref(false)
const autoFormRef = ref<FormInstance>()
const autoForm = reactive<{
  supplier_id: number | undefined
  evaluate_date: string
  evaluator_id: number | undefined
  remark: string
}>({
  supplier_id: undefined,
  evaluate_date: '',
  evaluator_id: undefined,
  remark: '',
})

function openAuto(): void {
  Object.assign(autoForm, {
    supplier_id: undefined,
    evaluate_date: '',
    evaluator_id: undefined,
    remark: '',
  })
  autoDialogVisible.value = true
}

function fmtPct(rate: number | string | null | undefined): string {
  if (rate === null || rate === undefined) return '无数据'
  return `${(toNumber(rate) * 100).toFixed(2)}%`
}

async function submitAuto(): Promise<void> {
  const valid = await autoFormRef.value?.validate().catch(() => false)
  if (!valid) return
  autoSubmitting.value = true
  try {
    const result = await createAutoEvaluation({
      supplier_id: autoForm.supplier_id,
      evaluate_date: autoForm.evaluate_date || null,
      evaluator_id: autoForm.evaluator_id ?? null,
      remark: autoForm.remark || null,
    })
    autoDialogVisible.value = false
    await load()
    const deviation =
      result.price_deviation_pct === null || result.price_deviation_pct === undefined
        ? '无数据'
        : `${toNumber(result.price_deviation_pct).toFixed(2)}%`
    await ElMessageBox.alert(
      [
        `供应商：${result.supplier_name ?? result.supplier_id}`,
        `交期得分：${result.delivery_score}（按时到货率 ${fmtPct(result.on_time_rate)}，${result.receipt_on_time ?? '-'}/${result.receipt_total ?? '-'} 单按时）`,
        `质量得分：${result.quality_score}（检验合格率 ${fmtPct(result.qualified_rate)}）`,
        `价格得分：${result.price_score}（相对均价偏离 ${deviation}）`,
        `综合得分：${result.total_score}（${result.scored_dimensions ?? 3} 项有效维度平均）`,
      ].join('\n'),
      '自动评价完成',
      { confirmButtonText: '知道了' },
    )
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    autoSubmitting.value = false
  }
}

async function handleDelete(row: SupplierEvaluation): Promise<void> {
  try {
    await deleteEvaluation(row.id)
    ElMessage.success('评价已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

const autoRules: FormRules = {
  supplier_id: [{ required: true, message: '请选择供应商', trigger: 'change' }],
}

const isAuto = (row: SupplierEvaluation): boolean => !!row.remark?.startsWith('[自动评价]')

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never" class="algorithm-card">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">评价算法说明</span>
          <span class="table-toolbar__spacer" />
          <el-button link type="primary" @click="algorithmVisible = !algorithmVisible">
            {{ algorithmVisible ? '收起' : '展开' }}
          </el-button>
        </div>
      </template>
      <template v-if="algorithmVisible">
        <el-alert type="info" :closable="false" show-icon>
          <p><b>统计口径：</b>该供应商全部历史业务单据（已确认/已完成的到货单、有效采购订单）。</p>
          <p><b>交期得分</b> = 按时到货率 × 100。按时 = 到货单「到货日期」≤ 采购订单「预计到货日期」。</p>
          <p><b>质量得分</b> = 检验合格率 × 100 = 合格总量 ÷ 到货总量 × 100。</p>
          <p>
            <b>价格得分</b> = 100 − 平均偏离百分比。偏离% =（该供应商某物料订单均价 − 全部供应商同物料订单均价）
            ÷ 全部均价 × 100，按物料简单平均；<b>高于均价减分、低于均价加分</b>，结果截断到 0~100 分。
          </p>
          <p><b>综合得分</b> = 有数据维度的简单平均（缺业务数据的维度不计入），四舍五入保留 4 位小数。</p>
          <p class="tip">点击「自动评价」由系统按上述算法打分；「新增评价」用于主观补评的手工录入。</p>
        </el-alert>
      </template>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">供应商评价</span>
          <span class="table-toolbar__spacer" />
          <el-button type="success" @click="openAuto">自动评价</el-button>
          <el-button type="primary" @click="openCreate">新增评价</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="供应商">
          <RemoteSelect v-model="query.supplier_id" :loader="loadSupplierOptions" placeholder="全部" style="width: 240px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="供应商ID" prop="supplier_id" width="110" align="right" />
        <el-table-column label="供应商名称" prop="supplier_name" min-width="180" />
        <el-table-column label="评价日期" prop="evaluate_date" width="110" />
        <el-table-column label="质量得分" prop="quality_score" width="100" align="right" />
        <el-table-column label="交付得分" prop="delivery_score" width="100" align="right" />
        <el-table-column label="价格得分" prop="price_score" width="100" align="right" />
        <el-table-column label="综合得分" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'score-low': toNumber(row.total_score) < 60 }">{{ row.total_score }}</span>
          </template>
        </el-table-column>
        <el-table-column label="评价人" min-width="120">
          <template #default="{ row }">{{ row.evaluator_name || (row.evaluator_id ? `ID ${row.evaluator_id}` : '-') }}</template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="160">
          <template #default="{ row }">
            <el-tag v-if="isAuto(row)" size="small" type="success" effect="plain">自动</el-tag>
            {{ row.remark }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无供应商评价数据</template>
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

    <el-dialog v-model="dialogVisible" title="新增供应商评价（手工录入）" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="供应商" prop="supplier_id">
          <RemoteSelect v-model="form.supplier_id" :loader="loadSupplierOptions" placeholder="请选择供应商" style="width: 100%" />
        </el-form-item>
        <el-form-item label="评价日期" prop="evaluate_date">
          <el-date-picker v-model="form.evaluate_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="质量得分">
          <el-input-number v-model="form.quality_score" :min="0" :max="100" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="交付得分">
          <el-input-number v-model="form.delivery_score" :min="0" :max="100" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="价格得分">
          <el-input-number v-model="form.price_score" :min="0" :max="100" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="评价人">
          <RemoteSelect v-model="form.evaluator_id" :loader="loadEvaluatorOptions" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
        <div class="form-tip">综合得分由系统按「质量、交付、价格」三项评分取平均自动计算。</div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="autoDialogVisible" title="自动供应商评价" width="560px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        系统将按页面上方公示的算法，统计该供应商全部历史到货/订单数据，
        自动计算交期、质量、价格三项得分与综合得分。
      </el-alert>
      <el-form ref="autoFormRef" :model="autoForm" :rules="autoRules" label-width="110px">
        <el-form-item label="供应商" prop="supplier_id">
          <RemoteSelect v-model="autoForm.supplier_id" :loader="loadSupplierOptions" placeholder="请选择供应商" style="width: 100%" />
        </el-form-item>
        <el-form-item label="评价日期">
          <el-date-picker v-model="autoForm.evaluate_date" type="date" value-format="YYYY-MM-DD" placeholder="默认今天" style="width: 100%" />
        </el-form-item>
        <el-form-item label="评价人">
          <RemoteSelect v-model="autoForm.evaluator_id" :loader="loadEvaluatorOptions" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="autoForm.remark" type="textarea" :rows="2" placeholder="可选，将附加在 [自动评价] 标记之后" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="autoDialogVisible = false">取消</el-button>
        <el-button type="success" :loading="autoSubmitting" @click="submitAuto">开始评价</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.score-low {
  color: var(--el-color-danger);
  font-weight: 600;
}
.algorithm-card {
  margin-bottom: 16px;
}
.algorithm-card p {
  margin: 4px 0;
  line-height: 1.6;
}
.algorithm-card .tip {
  color: var(--el-text-color-secondary);
}
</style>
