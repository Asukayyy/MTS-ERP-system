<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createEvaluation, listEvaluations, listSuppliers } from '@/api/procurement'
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

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">供应商评价</span>
          <span class="table-toolbar__spacer" />
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
        <el-table-column label="备注" prop="remark" min-width="160" />
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

    <el-dialog v-model="dialogVisible" title="新增供应商评价" width="640px">
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
  </div>
</template>

<style scoped>
.score-low {
  color: var(--el-color-danger);
  font-weight: 600;
}
</style>