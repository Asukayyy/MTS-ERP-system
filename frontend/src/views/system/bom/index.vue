<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  activateBom,
  addBomItem,
  createBom,
  deleteBom,
  deleteBomItem,
  getBom,
  getBomTree,
  getMaterial,
  listBoms,
  listMaterials,
  setBomStatus,
  updateBomItem,
} from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Bom, BomItem, BomTreeNode, Material, RemoteOption } from '@/types/erp'

/** BOM 编辑器：左侧多层 BOM 树，右侧节点属性 / 版本 / 子项维护 */

const rootMaterialId = ref<number>()
const treeData = ref<BomTreeNode[]>([])
const treeLoading = ref(false)

const selectedMaterialId = ref<number>()
const nodeMaterial = ref<Material | null>(null)
const nodeBom = ref<Bom | null>(null)

const versions = ref<Bom[]>([])
const selectedVersionId = ref<number>()
const versionItems = ref<BomItem[]>([])
const itemLoading = ref(false)

const selectedVersion = computed(() => versions.value.find((item) => item.id === selectedVersionId.value) ?? null)

/** 选项加载：物料 */
async function materialOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listMaterials({ keyword, page: 1, page_size: 20 })
  return data.items.map((item) => ({
    id: item.id,
    label: `${item.material_code} ${item.material_name}`,
  }))
}

/** 加载多层 BOM 树 */
async function loadTree(): Promise<void> {
  if (!rootMaterialId.value) {
    ElMessage.warning('请先选择根物料')
    return
  }
  treeLoading.value = true
  try {
    treeData.value = await getBomTree(rootMaterialId.value)
    await selectNode(treeData.value[0])
  } catch (error) {
    treeData.value = []
    ElMessage.error((error as Error).message)
  } finally {
    treeLoading.value = false
  }
}

/** 选中树节点：加载节点物料、该母件的 BOM 版本 */
async function selectNode(node?: BomTreeNode): Promise<void> {
  if (!node) return
  selectedMaterialId.value = node.material_id
  try {
    nodeMaterial.value = await getMaterial(node.material_id)
  } catch (error) {
    nodeMaterial.value = null
    ElMessage.error((error as Error).message)
  }
  await loadVersions(node.material_id)
}

async function loadVersions(materialId: number): Promise<void> {
  try {
    const data = await listBoms({ material_id: materialId, page: 1, page_size: 50 })
    versions.value = data.items
    const active = data.items.find((item) => item.is_active) ?? data.items[0]
    selectedVersionId.value = active ? active.id : undefined
    await loadVersionItems()
  } catch (error) {
    versions.value = []
    versionItems.value = []
    ElMessage.error((error as Error).message)
  }
}

async function selectVersion(row: Bom): Promise<void> {
  selectedVersionId.value = row.id
  await loadVersionItems()
}

async function loadVersionItems(): Promise<void> {
  if (!selectedVersionId.value) {
    nodeBom.value = null
    versionItems.value = []
    return
  }
  itemLoading.value = true
  try {
    nodeBom.value = await getBom(selectedVersionId.value)
    versionItems.value = nodeBom.value.items
  } catch (error) {
    versionItems.value = []
    ElMessage.error((error as Error).message)
  } finally {
    itemLoading.value = false
  }
}

// ---------------- 子项新增 / 修改 / 删除 ----------------

const itemDialogVisible = ref(false)
const itemSubmitting = ref(false)
const editingItemId = ref<number | null>(null)
const itemFormRef = ref<FormInstance>()
const itemForm = reactive({
  material_id: undefined as number | undefined,
  quantity: 1,
  lead_time_offset: 0,
  scrap_rate: 0,
  sequence_no: 1,
  remark: '',
})
const itemSupplyType = ref('')

const itemRules: FormRules = {
  material_id: [{ required: true, message: '请选择子件物料', trigger: 'change' }],
  quantity: [{ required: true, message: '请输入单位用量', trigger: 'blur' }],
}

async function onItemMaterialChange(id?: number): Promise<void> {
  itemSupplyType.value = ''
  if (!id) return
  try {
    const material = await getMaterial(id)
    itemSupplyType.value = material.supply_type
  } catch {
    itemSupplyType.value = ''
  }
}

function openCreateItem(): void {
  if (!selectedVersionId.value) {
    ElMessage.warning('请先选择 BOM 版本')
    return
  }
  editingItemId.value = null
  Object.assign(itemForm, {
    material_id: undefined,
    quantity: 1,
    lead_time_offset: 0,
    scrap_rate: 0,
    sequence_no: versionItems.value.length + 1,
    remark: '',
  })
  itemSupplyType.value = ''
  itemDialogVisible.value = true
}

function openEditItem(row: BomItem): void {
  editingItemId.value = row.id
  Object.assign(itemForm, {
    material_id: row.material_id,
    quantity: Number(row.quantity),
    lead_time_offset: row.lead_time_offset,
    scrap_rate: Number(row.scrap_rate),
    sequence_no: row.sequence_no,
    remark: row.remark ?? '',
  })
  void onItemMaterialChange(row.material_id)
  itemDialogVisible.value = true
}

async function submitItem(): Promise<void> {
  const valid = await itemFormRef.value?.validate().catch(() => false)
  if (!valid) return
  itemSubmitting.value = true
  try {
    if (editingItemId.value === null) {
      await addBomItem(selectedVersionId.value as number, { ...itemForm })
      ElMessage.success('子项已新增')
    } else {
      await updateBomItem(editingItemId.value, { ...itemForm })
      ElMessage.success('子项已修改')
    }
    itemDialogVisible.value = false
    await loadVersionItems()
    if (rootMaterialId.value) treeData.value = await getBomTree(rootMaterialId.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    itemSubmitting.value = false
  }
}

async function removeItem(row: BomItem): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该 BOM 子项？', '提示', { type: 'warning' })
    await deleteBomItem(row.id)
    ElMessage.success('子项已删除')
    await loadVersionItems()
    if (rootMaterialId.value) treeData.value = await getBomTree(rootMaterialId.value)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error((error as Error).message)
  }
}

// ---------------- 版本管理 ----------------

const versionDialogVisible = ref(false)
const versionSubmitting = ref(false)
const versionFormRef = ref<FormInstance>()
const versionForm = reactive({ bom_version: '', effective_date: '', remark: '' })
const versionRules: FormRules = {
  bom_version: [{ required: true, message: '请输入版本号，如 V2.0', trigger: 'blur' }],
}

/** 新增版本时一次填写的子项行 */
interface ItemRow {
  material_id?: number
  quantity: number
  lead_time_offset: number
  scrap_rate: number
  sequence_no: number
  remark: string
}

const versionItemRows = ref<ItemRow[]>([])

function addItemRow(): void {
  versionItemRows.value.push({
    material_id: undefined,
    quantity: 1,
    lead_time_offset: 0,
    scrap_rate: 0,
    sequence_no: versionItemRows.value.length + 1,
    remark: '',
  })
}

function removeItemRow(index: number): void {
  versionItemRows.value.splice(index, 1)
  versionItemRows.value.forEach((row, idx) => {
    row.sequence_no = idx + 1
  })
}

function openCreateVersion(): void {
  if (!selectedMaterialId.value) {
    ElMessage.warning('请先在左侧选择物料节点')
    return
  }
  Object.assign(versionForm, { bom_version: '', effective_date: '', remark: '' })
  versionItemRows.value = []
  addItemRow()
  versionDialogVisible.value = true
}

async function submitVersion(): Promise<void> {
  const valid = await versionFormRef.value?.validate().catch(() => false)
  if (!valid) return

  // 校验子项：未填物料的空行直接忽略；不允许子件与母件相同
  const rows = versionItemRows.value.filter((row) => row.material_id)
  if (rows.some((row) => row.material_id === selectedMaterialId.value)) {
    ElMessage.warning('子件不能是母件本身')
    return
  }
  const codes = new Set(rows.map((row) => row.material_id))
  if (codes.size !== rows.length) {
    ElMessage.warning('同一母件下子件不能重复')
    return
  }

  versionSubmitting.value = true
  try {
    await createBom({
      material_id: selectedMaterialId.value,
      bom_version: versionForm.bom_version,
      effective_date: versionForm.effective_date || null,
      is_active: false,
      status: 'ACTIVE',
      remark: versionForm.remark,
      items: rows.map((row) => ({
        material_id: row.material_id,
        quantity: row.quantity,
        lead_time_offset: row.lead_time_offset,
        scrap_rate: row.scrap_rate,
        sequence_no: row.sequence_no,
        remark: row.remark || null,
      })),
    })
    ElMessage.success('BOM 版本已新增，可在版本列表中「生效」，再于右侧查看子项')
    versionDialogVisible.value = false
    await loadVersions(selectedMaterialId.value as number)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    versionSubmitting.value = false
  }
}

async function onActivate(row: Bom): Promise<void> {
  try {
    await activateBom(row.id)
    ElMessage.success('已激活该 BOM 版本')
    if (selectedMaterialId.value) await loadVersions(selectedMaterialId.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function toggleVersionStatus(row: Bom): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setBomStatus(row.id, next)
    ElMessage.success('版本状态已更新')
    if (selectedMaterialId.value) await loadVersions(selectedMaterialId.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function removeVersion(row: Bom): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该 BOM 版本？其子项将一并删除。', '提示', { type: 'warning' })
    await deleteBom(row.id)
    ElMessage.success('版本已删除')
    if (selectedMaterialId.value) {
      await loadVersions(selectedMaterialId.value)
      if (rootMaterialId.value) treeData.value = await getBomTree(rootMaterialId.value)
    }
  } catch (error) {
    if (error !== 'cancel') ElMessage.error((error as Error).message)
  }
}

onMounted(() => {
  // 首次进入不自动加载，等待用户选择根物料
})
</script>

<template>
  <div class="bom-page">
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">BOM 编辑器</span>
          <span class="table-toolbar__spacer" />
          <RemoteSelect
            v-model="rootMaterialId"
            :loader="materialOptions"
            placeholder="选择根物料"
            style="width: 280px"
          />
          <el-button type="primary" :loading="treeLoading" @click="loadTree">展开多层 BOM</el-button>
        </div>
      </template>

      <el-row :gutter="12">
        <el-col :xs="24" :md="8" :lg="7">
          <el-card shadow="never" class="bom-panel">
            <template #header><span>多层 BOM 结构</span></template>
            <el-tree
              v-loading="treeLoading"
              :data="treeData"
              node-key="material_id"
              :props="{ label: 'material_name', children: 'children' }"
              default-expand-all
              empty-text="请选择根物料后展开"
              @node-click="selectNode"
            >
              <template #default="{ data }">
                <span class="bom-node">
                  <span class="bom-node__code">{{ data.material_code }}</span>
                  <span class="bom-node__name">{{ data.material_name }}</span>
                  <span class="bom-node__qty">×{{ data.quantity }}</span>
                  <el-tag size="small" type="info" effect="plain">L{{ data.level }}</el-tag>
                </span>
              </template>
            </el-tree>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="16" :lg="17">
          <el-card shadow="never" class="bom-panel">
            <template #header>
              <div class="table-toolbar">
                <span>节点属性</span>
                <span class="table-toolbar__spacer" />
                <el-button type="primary" @click="openCreateItem">新增子项</el-button>
                <el-button @click="openCreateVersion">新增版本</el-button>
              </div>
            </template>

            <el-descriptions v-if="nodeMaterial" :column="3" border size="small">
              <el-descriptions-item label="物料">{{ nodeMaterial.material_code }}</el-descriptions-item>
              <el-descriptions-item label="名称">{{ nodeMaterial.material_name }}</el-descriptions-item>
              <el-descriptions-item label="供应类型">
                <StatusTag :status="nodeMaterial.supply_type" />
              </el-descriptions-item>
              <el-descriptions-item label="当前版本">{{ selectedVersion?.bom_version ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="是否激活">
                <el-tag v-if="selectedVersion" :type="selectedVersion.is_active ? 'success' : 'info'" size="small">
                  {{ selectedVersion.is_active ? '已激活' : '未激活' }}
                </el-tag>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="状态">
                <StatusTag v-if="selectedVersion" :status="selectedVersion.status" />
                <span v-else>-</span>
              </el-descriptions-item>
            </el-descriptions>
            <el-empty v-else description="请在左侧选择物料节点" :image-size="60" />
          </el-card>

          <el-card shadow="never" class="bom-panel">
            <template #header><span>版本列表</span></template>
            <el-table :data="versions" size="small" border @row-click="selectVersion">
              <el-table-column label="版本" prop="bom_version" width="100" />
              <el-table-column label="生效日期" prop="effective_date" width="120" />
              <el-table-column label="失效日期" prop="expiry_date" width="120" />
              <el-table-column label="激活" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                    {{ row.is_active ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }"><StatusTag :status="row.status" /></template>
              </el-table-column>
              <el-table-column label="操作" width="220">
                <template #default="{ row }">
                  <el-button link type="primary" :disabled="row.is_active" @click.stop="onActivate(row)">生效</el-button>
                  <el-button link type="primary" @click.stop="selectVersion(row)">查看子项</el-button>
                  <el-button link :type="row.status === 'ACTIVE' ? 'danger' : 'success'" @click.stop="toggleVersionStatus(row)">
                    {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
                  </el-button>
                  <el-button link type="danger" @click.stop="removeVersion(row)">删除</el-button>
                </template>
              </el-table-column>
              <template #empty>该物料暂无 BOM 版本</template>
            </el-table>
          </el-card>

          <el-card shadow="never" class="bom-panel">
            <template #header>
              <span>子项明细（物料 / 用量 / 提前期偏置 / 损耗率 / 供应类型）</span>
            </template>
            <el-table v-loading="itemLoading" :data="versionItems" size="small" border>
              <el-table-column label="序号" prop="sequence_no" width="70" />
              <el-table-column label="子件物料ID" prop="material_id" width="110" />
              <el-table-column label="用量" prop="quantity" width="100" align="right" />
              <el-table-column label="提前期偏置(天)" prop="lead_time_offset" width="130" align="right" />
              <el-table-column label="损耗率" prop="scrap_rate" width="100" align="right" />
              <el-table-column label="备注" prop="remark" min-width="120" />
              <el-table-column label="操作" width="130">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openEditItem(row)">修改</el-button>
                  <el-button link type="danger" @click="removeItem(row)">删除</el-button>
                </template>
              </el-table-column>
              <template #empty>暂无子项，点击「新增子项」维护</template>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-dialog v-model="itemDialogVisible" :title="editingItemId === null ? '新增 BOM 子项' : '修改 BOM 子项'" width="560px">
      <el-form ref="itemFormRef" :model="itemForm" :rules="itemRules" label-width="120px">
        <el-form-item label="子件物料" prop="material_id">
          <RemoteSelect v-model="itemForm.material_id" :loader="materialOptions" @change="onItemMaterialChange" />
        </el-form-item>
        <el-form-item label="供应类型">
          <span v-if="itemSupplyType"><StatusTag :status="itemSupplyType" /></span>
          <span v-else class="form-tip">选择物料后自动带出</span>
        </el-form-item>
        <el-form-item label="单位用量" prop="quantity">
          <el-input-number v-model="itemForm.quantity" :min="0.0001" :precision="4" style="width: 100%" />
        </el-form-item>
        <el-form-item label="提前期偏置(天)">
          <el-input-number v-model="itemForm.lead_time_offset" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="损耗率">
          <el-input-number v-model="itemForm.scrap_rate" :min="0" :max="0.9999" :step="0.01" :precision="4" style="width: 100%" />
        </el-form-item>
        <el-form-item label="序号">
          <el-input-number v-model="itemForm.sequence_no" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="itemForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="itemSubmitting" @click="submitItem">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="versionDialogVisible" title="新增 BOM 版本（一次性填好版本与子项）" width="860px">
      <el-form ref="versionFormRef" :model="versionForm" :rules="versionRules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="母件物料">
              <el-input :model-value="nodeMaterial ? `${nodeMaterial.material_code} ${nodeMaterial.material_name}` : ''" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="版本号" prop="bom_version">
              <el-input v-model="versionForm.bom_version" placeholder="如 V1.0" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="生效日期">
              <el-date-picker v-model="versionForm.effective_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="versionForm.remark" type="textarea" :rows="1" /></el-form-item>
      </el-form>

      <div class="bom-items-editor">
        <div class="table-toolbar">
          <span>子项明细（可一次填多行）</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" plain size="small" @click="addItemRow">+ 添加子项</el-button>
        </div>
        <el-table :data="versionItemRows" size="small" border>
          <el-table-column label="序号" width="60">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="子件物料" min-width="220">
            <template #default="{ row }">
              <RemoteSelect v-model="row.material_id" :loader="materialOptions" placeholder="搜索物料编码/名称" />
            </template>
          </el-table-column>
          <el-table-column label="单位用量" width="130">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" :min="0.0001" :precision="4" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="提前期偏置" width="120">
            <template #default="{ row }">
              <el-input-number v-model="row.lead_time_offset" :min="0" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="损耗率" width="120">
            <template #default="{ row }">
              <el-input-number v-model="row.scrap_rate" :min="0" :max="0.9999" :step="0.01" :precision="4" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeItemRow($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="versionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="versionSubmitting" @click="submitVersion">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.bom-panel {
  margin-bottom: 12px;
}

.bom-node {
  display: flex;
  gap: 8px;
  align-items: center;
}

.bom-node__code {
  color: #909399;
}

.bom-node__qty {
  color: #e6a23c;
}
</style>