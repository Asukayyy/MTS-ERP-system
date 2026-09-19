<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { confirmInitialStockImport, listWarehouses, previewInitialStockImport } from '@/api/inventory'
import { confirmMpsImport, previewMpsImport } from '@/api/planning'
import {
  confirmBomImport,
  confirmMaterialsImport,
  previewBomImport,
  previewMaterialsImport,
} from '@/api/system'
import type { RemoteOption } from '@/types/erp'
import type {
  BomImportConfirm,
  BomImportPreview,
  InitialStockConfirm,
  InitialStockPreview,
  MaterialImportConfirm,
  MaterialImportPreview,
  MpsImportPreview,
} from '@/types/erp'

/**
 * 课程数据导入（规格 §37）：导入预览 → 数据校验 → 错误提示 → 确认导入。
 * 四组数据均调用后端 preview / confirm 接口，前端不做任何模拟。
 */

const SOURCE = 'course_chair_case'

const activeTab = ref('material')
const warehouseId = ref<number | undefined>(undefined)
const warehouseOptions = ref<RemoteOption[]>([])
const warehouseLoading = ref(false)

async function loadWarehouseOptions(): Promise<void> {
  warehouseLoading.value = true
  try {
    const data = await listWarehouses({ status: 'ACTIVE', page: 1, page_size: 100 })
    warehouseOptions.value = data.items.map((item) => ({
      id: item.id,
      label: `${item.warehouse_code} ${item.warehouse_name}`,
    }))
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    warehouseLoading.value = false
  }
}

// ---------------- 物料 ----------------

const materialPreview = ref<MaterialImportPreview | null>(null)
const materialConfirm = ref<MaterialImportConfirm | null>(null)
const materialLoading = ref(false)

async function doPreviewMaterials(): Promise<void> {
  materialLoading.value = true
  try {
    materialPreview.value = await previewMaterialsImport(SOURCE)
    materialConfirm.value = null
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    materialLoading.value = false
  }
}

async function doConfirmMaterials(): Promise<void> {
  materialLoading.value = true
  try {
    materialConfirm.value = await confirmMaterialsImport(SOURCE)
    ElMessage.success(`物料导入完成：新增 ${materialConfirm.value.created} 条`)
    await doPreviewMaterials()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    materialLoading.value = false
  }
}

// ---------------- BOM ----------------

const bomPreview = ref<BomImportPreview | null>(null)
const bomConfirm = ref<BomImportConfirm | null>(null)
const bomLoading = ref(false)

async function doPreviewBom(): Promise<void> {
  bomLoading.value = true
  try {
    bomPreview.value = await previewBomImport(SOURCE)
    bomConfirm.value = null
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    bomLoading.value = false
  }
}

async function doConfirmBom(): Promise<void> {
  bomLoading.value = true
  try {
    bomConfirm.value = await confirmBomImport(SOURCE)
    ElMessage.success(`BOM 导入完成：新建 BOM 头 ${bomConfirm.value.bom_headers_created} 个`)
    await doPreviewBom()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    bomLoading.value = false
  }
}

// ---------------- 期初库存 ----------------

const stockPreview = ref<InitialStockPreview | null>(null)
const stockConfirm = ref<InitialStockConfirm | null>(null)
const stockLoading = ref(false)

async function doPreviewStock(): Promise<void> {
  if (!warehouseId.value) {
    ElMessage.warning('请先选择导入仓库')
    return
  }
  stockLoading.value = true
  try {
    stockPreview.value = await previewInitialStockImport({
      source: SOURCE,
      warehouse_id: warehouseId.value,
    })
    stockConfirm.value = null
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    stockLoading.value = false
  }
}

async function doConfirmStock(): Promise<void> {
  if (!warehouseId.value) {
    ElMessage.warning('请先选择导入仓库')
    return
  }
  stockLoading.value = true
  try {
    stockConfirm.value = await confirmInitialStockImport({
      source: SOURCE,
      warehouse_id: warehouseId.value,
    })
    ElMessage.success(`期初库存导入完成：写入 ${stockConfirm.value.imported} 行`)
    await doPreviewStock()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    stockLoading.value = false
  }
}

// ---------------- MPS ----------------

const mpsPreview = ref<MpsImportPreview | null>(null)
const mpsLoading = ref(false)
const mpsForm = reactive({ mps_name: '', plan_year: undefined as number | undefined })

async function doPreviewMps(): Promise<void> {
  mpsLoading.value = true
  try {
    mpsPreview.value = await previewMpsImport({
      source: SOURCE,
      mps_name: mpsForm.mps_name || null,
      plan_year: mpsForm.plan_year ?? null,
    })
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    mpsLoading.value = false
  }
}

async function doConfirmMps(): Promise<void> {
  if (!mpsPreview.value || mpsPreview.value.summary.error_count > 0) {
    ElMessage.warning('存在校验失败行，请先修正后再确认导入')
    return
  }
  mpsLoading.value = true
  try {
    const mps = await confirmMpsImport({
      source: SOURCE,
      mps_name: mpsForm.mps_name || null,
      plan_year: mpsForm.plan_year ?? null,
    })
    ElMessage.success(`MPS 导入完成：${mps.mps_no}`)
    mpsPreview.value = null
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    mpsLoading.value = false
  }
}

onMounted(loadWarehouseOptions)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">课程数据导入</span>
          <span class="table-toolbar__spacer" />
          <span class="form-tip">数据源：{{ SOURCE }}（仓库根目录 data/seed 课程文件）</span>
        </div>
      </template>

      <el-alert
        class="import-tip"
        type="info"
        :closable="false"
        title="导入流程：先「导入预览」查看校验结果，确认无误后再「确认导入」。预览不会写入任何数据。"
      />

      <el-tabs v-model="activeTab">
        <el-tab-pane label="物料" name="material">
          <div class="table-toolbar">
            <span class="table-toolbar__spacer" />
            <el-button :loading="materialLoading" @click="doPreviewMaterials">导入预览</el-button>
            <el-button
              type="primary"
              :loading="materialLoading"
              :disabled="!materialPreview || materialPreview.summary.to_create === 0"
              @click="doConfirmMaterials"
            >
              确认导入
            </el-button>
          </div>

          <el-descriptions v-if="materialPreview" :column="5" border size="small" class="import-summary">
            <el-descriptions-item label="树中节点总数">{{ materialPreview.summary.total }}</el-descriptions-item>
            <el-descriptions-item label="待创建">{{ materialPreview.summary.to_create }}</el-descriptions-item>
            <el-descriptions-item label="已存在">{{ materialPreview.summary.existing }}</el-descriptions-item>
            <el-descriptions-item label="校验不通过">{{ materialPreview.summary.invalid }}</el-descriptions-item>
            <el-descriptions-item label="最大层级">{{ materialPreview.summary.max_level }}</el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="materialPreview && materialPreview.errors.length"
            class="import-error"
            type="error"
            :closable="false"
            :title="`数据校验发现 ${materialPreview.errors.length} 条错误`"
          />
          <el-table
            v-if="materialPreview && materialPreview.errors.length"
            :data="materialPreview.errors"
            border
            size="small"
            class="import-error-table"
          >
            <el-table-column label="物料编码" prop="material_code" width="160" />
            <el-table-column label="错误提示" prop="message" min-width="320" />
          </el-table>

          <el-table v-if="materialPreview" :data="materialPreview.materials" border size="small" max-height="420">
            <el-table-column label="物料编码" prop="material_code" width="160" />
            <el-table-column label="物料名称" prop="material_name" min-width="200" />
            <el-table-column label="物料类型" prop="material_type" width="120" />
            <el-table-column label="供应类型" prop="supply_type" width="120" />
            <el-table-column label="校验状态" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.status === 'TO_CREATE'" type="warning" size="small">待创建</el-tag>
                <el-tag v-else-if="row.status === 'EXISTING'" type="success" size="small">已存在</el-tag>
                <el-tag v-else type="danger" size="small">不通过</el-tag>
              </template>
            </el-table-column>
            <template #empty>预览结果为空</template>
          </el-table>

          <el-alert
            v-if="materialConfirm"
            class="import-result"
            type="success"
            :closable="false"
            :title="`确认导入结果：新增 ${materialConfirm.created} 条，跳过已存在 ${materialConfirm.skipped} 条，错误 ${materialConfirm.errors.length} 条`"
          />
        </el-tab-pane>

        <el-tab-pane label="BOM" name="bom">
          <div class="table-toolbar">
            <span class="table-toolbar__spacer" />
            <el-button :loading="bomLoading" @click="doPreviewBom">导入预览</el-button>
            <el-button
              type="primary"
              :loading="bomLoading"
              :disabled="!bomPreview || bomPreview.summary.bom_items === 0"
              @click="doConfirmBom"
            >
              确认导入
            </el-button>
          </div>

          <el-descriptions v-if="bomPreview" :column="5" border size="small" class="import-summary">
            <el-descriptions-item label="树中节点总数">{{ bomPreview.summary.total_nodes }}</el-descriptions-item>
            <el-descriptions-item label="最大层级">{{ bomPreview.summary.levels }}</el-descriptions-item>
            <el-descriptions-item label="BOM 头">{{ bomPreview.summary.bom_headers }}</el-descriptions-item>
            <el-descriptions-item label="BOM 子项">{{ bomPreview.summary.bom_items }}</el-descriptions-item>
            <el-descriptions-item label="层级判定规则">
              {{ bomPreview.summary.resolution_rule }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="bomPreview && bomPreview.errors.length"
            class="import-error"
            type="error"
            :closable="false"
            :title="`数据校验发现 ${bomPreview.errors.length} 条错误`"
          />
          <el-table
            v-if="bomPreview && bomPreview.errors.length"
            :data="bomPreview.errors"
            border
            size="small"
            class="import-error-table"
          >
            <el-table-column label="物料编码" prop="material_code" width="160" />
            <el-table-column label="错误提示" prop="message" min-width="320" />
          </el-table>

          <el-table v-if="bomPreview" :data="bomPreview.bom_items" border size="small" max-height="420">
            <el-table-column label="母件编码" prop="parent_material_code" width="160" />
            <el-table-column label="子件编码" prop="child_material_code" width="160" />
            <el-table-column label="单位用量" prop="quantity" width="110" align="right" />
            <el-table-column label="提前期偏置" prop="lead_time_offset" width="110" align="right" />
            <el-table-column label="损耗率" prop="scrap_rate" width="110" align="right" />
            <el-table-column label="层级" prop="level" width="80" align="right" />
            <template #empty>预览结果为空</template>
          </el-table>

          <el-alert
            v-if="bomConfirm"
            class="import-result"
            type="success"
            :closable="false"
            :title="`确认导入结果：新建 BOM 头 ${bomConfirm.bom_headers_created} 个、子项 ${bomConfirm.bom_items_created} 条，跳过 ${bomConfirm.skipped} 条，错误 ${bomConfirm.errors.length} 条`"
          />
        </el-tab-pane>

        <el-tab-pane label="期初库存" name="stock">
          <div class="table-toolbar">
            <span class="table-toolbar__spacer" />
            <el-button :loading="stockLoading" @click="doPreviewStock">导入预览</el-button>
            <el-button
              type="primary"
              :loading="stockLoading"
              :disabled="!stockPreview || stockPreview.summary.valid === 0"
              @click="doConfirmStock"
            >
              确认导入
            </el-button>
          </div>

          <el-form class="filter-bar" :inline="true" @submit.prevent>
            <el-form-item label="导入仓库">
              <el-select
                v-model="warehouseId"
                :loading="warehouseLoading"
                placeholder="请选择仓库（必选）"
                style="width: 260px"
              >
                <el-option v-for="item in warehouseOptions" :key="item.id" :label="item.label" :value="item.id" />
              </el-select>
            </el-form-item>
          </el-form>

          <el-descriptions v-if="stockPreview" :column="3" border size="small" class="import-summary">
            <el-descriptions-item label="总行数">{{ stockPreview.summary.total }}</el-descriptions-item>
            <el-descriptions-item label="可导入">{{ stockPreview.summary.valid }}</el-descriptions-item>
            <el-descriptions-item label="校验不通过">{{ stockPreview.summary.invalid }}</el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="stockPreview && stockPreview.errors.length"
            class="import-error"
            type="error"
            :closable="false"
            :title="`数据校验发现 ${stockPreview.errors.length} 条错误`"
          />
          <el-table
            v-if="stockPreview && stockPreview.errors.length"
            :data="stockPreview.errors"
            border
            size="small"
            class="import-error-table"
          >
            <el-table-column label="物料编码" prop="material_code" width="160" />
            <el-table-column label="错误提示" prop="message" min-width="320" />
          </el-table>

          <el-table v-if="stockPreview" :data="stockPreview.rows" border size="small" max-height="420">
            <el-table-column label="物料编码" prop="material_code" width="160" />
            <el-table-column label="物料名称" prop="material_name" min-width="200" />
            <el-table-column label="期初数量" prop="quantity" width="120" align="right" />
            <el-table-column label="校验状态" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.status === 'VALID'" type="success" size="small">可导入</el-tag>
                <el-tag v-else type="danger" size="small">不通过</el-tag>
              </template>
            </el-table-column>
            <template #empty>预览结果为空</template>
          </el-table>

          <el-alert
            v-if="stockConfirm"
            class="import-result"
            type="success"
            :closable="false"
            :title="`确认导入结果：写入 ${stockConfirm.imported} 行，错误 ${stockConfirm.errors.length} 条`"
          />
        </el-tab-pane>

        <el-tab-pane label="MPS 主生产计划" name="mps">
          <div class="table-toolbar">
            <span class="table-toolbar__spacer" />
            <el-button :loading="mpsLoading" @click="doPreviewMps">导入预览</el-button>
            <el-button
              type="primary"
              :loading="mpsLoading"
              :disabled="!mpsPreview || mpsPreview.summary.valid_count === 0 || mpsPreview.summary.error_count > 0"
              @click="doConfirmMps"
            >
              确认导入
            </el-button>
          </div>

          <el-form class="filter-bar" :inline="true" @submit.prevent>
            <el-form-item label="计划名称">
              <el-input v-model="mpsForm.mps_name" placeholder="留空由后端自动命名" style="width: 240px" />
            </el-form-item>
            <el-form-item label="计划年度">
              <el-input-number v-model="mpsForm.plan_year" :min="2000" :max="2100" :controls="false" />
            </el-form-item>
          </el-form>

          <el-descriptions v-if="mpsPreview" :column="5" border size="small" class="import-summary">
            <el-descriptions-item label="总行数">{{ mpsPreview.summary.total_rows }}</el-descriptions-item>
            <el-descriptions-item label="有效行">{{ mpsPreview.summary.valid_count }}</el-descriptions-item>
            <el-descriptions-item label="错误行">{{ mpsPreview.summary.error_count }}</el-descriptions-item>
            <el-descriptions-item label="计划年度">{{ mpsPreview.summary.plan_year }}</el-descriptions-item>
            <el-descriptions-item label="计划区间">
              {{ mpsPreview.summary.start_date || '-' }} ~ {{ mpsPreview.summary.end_date || '-' }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="mpsPreview && mpsPreview.errors.length"
            class="import-error"
            type="error"
            :closable="false"
            :title="`数据校验发现 ${mpsPreview.errors.length} 条错误，必须修正后才能确认导入`"
          />
          <el-table
            v-if="mpsPreview && mpsPreview.errors.length"
            :data="mpsPreview.errors"
            border
            size="small"
            class="import-error-table"
          >
            <el-table-column label="源文件行号" prop="row" width="120" align="right" />
            <el-table-column label="错误提示" prop="message" min-width="320" />
          </el-table>

          <el-table v-if="mpsPreview" :data="mpsPreview.valid_rows" border size="small" max-height="420">
            <el-table-column label="行号" prop="row_index" width="80" align="right" />
            <el-table-column label="物料编码" prop="material_code" width="160" />
            <el-table-column label="物料名称" prop="material_name" min-width="180" />
            <el-table-column label="期间" prop="period_label" width="120" />
            <el-table-column label="计划数量" prop="planned_qty" width="120" align="right" />
            <el-table-column label="开始日期" prop="start_date" width="110" />
            <el-table-column label="结束日期" prop="end_date" width="110" />
            <template #empty>预览结果为空</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.import-tip {
  margin-bottom: 12px;
}

.import-summary {
  margin-bottom: 12px;
}

.import-error {
  margin-bottom: 8px;
}

.import-error-table {
  margin-bottom: 12px;
}

.import-result {
  margin-top: 12px;
}
</style>