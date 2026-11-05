<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  activateBom,
  addBomItem,
  createBom,
  createMaterial,
  deleteBom,
  deleteBomItem,
  getBom,
  getBomTree,
  getMaterial,
  listBoms,
  listMaterials,
  setBomStatus,
  updateBomItem,
  updateMaterial,
} from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Bom, BomItem, BomTreeNode, Material, RemoteOption } from '@/types/erp'
import { hasPermission } from '@/utils/auth'

/** BOM 结构维护权限；无此权限时页面只读 */
const canManageBom = computed(() => hasPermission('system:bom:manage'))
/** 新建 BOM 时能否顺带建档母件物料 */
const canCreateMaterial = computed(() => hasPermission('system:material:manage'))

/** BOM 编辑器：左侧多层 BOM 树，右侧节点属性 / 版本 / 子项维护 */

const rootMaterialId = ref<number>()
const treeData = ref<BomTreeNode[]>([])
const treeLoading = ref(false)

const selectedMaterialId = ref<number>()
const nodeMaterial = ref<Material | null>(null)
const nodeBom = ref<Bom | null>(null)

// ---- 节点属性：ABC 分类与销售类别（在 BOM 表内直接维护） ----
const nodeAbc = ref('')
const nodeSalesCategory = ref('INTERNAL')
const classSaving = ref(false)

function syncNodeClassification(): void {
  nodeAbc.value = nodeMaterial.value?.abc_class ?? ''
  nodeSalesCategory.value = nodeMaterial.value?.sales_category ?? 'INTERNAL'
}

async function saveNodeClassification(): Promise<void> {
  const materialId = selectedMaterialId.value
  if (!materialId) return
  classSaving.value = true
  try {
    const updated = await updateMaterial(materialId, {
      abc_class: nodeAbc.value || null,
      sales_category: nodeSalesCategory.value,
    })
    nodeMaterial.value = updated
    ElMessage.success('物料分类已更新')
  } catch (error) {
    ElMessage.error((error as Error).message)
    syncNodeClassification()
  } finally {
    classSaving.value = false
  }
}

const versions = ref<Bom[]>([])
const selectedVersionId = ref<number>()
const versionItems = ref<BomItem[]>([])
const itemLoading = ref(false)

const selectedVersion = computed(() => versions.value.find((item) => item.id === selectedVersionId.value) ?? null)

/** 选项加载：物料 */
async function materialOptions(keyword: string): Promise<RemoteOption[]> {
  // 取后端允许的最大页长，避免"不输关键字时只列出前 20 个物料"把较早创建的物料整个藏掉
  const data = await listMaterials({ keyword, page: 1, page_size: 200 })
  return data.items.map((item) => ({
    id: item.id,
    label: `${item.material_code} ${item.material_name}`,
  }))
}

// ---------------- 新建整件 BOM ----------------

interface BomDraftRow {
  material_id?: number
  quantity: number
  lead_time_offset: number
  scrap_rate: number
}

const createBomVisible = ref(false)
const createBomSubmitting = ref(false)
const createBomFormRef = ref<FormInstance>()
const createBomForm = reactive({
  /** NEW：直接在弹窗里建档整机母件；EXISTING：选已有物料 */
  material_mode: 'NEW' as 'NEW' | 'EXISTING',
  material_id: undefined as number | undefined,
  new_material_code: '',
  new_material_name: '',
  new_unit_code: 'PCS',
  new_specification: '',
  bom_version: 'V1.0',
  effective_date: '',
  remark: '',
})
const createBomRows = ref<BomDraftRow[]>([])

function requireNewMaterialField(label: string) {
  return (_rule: unknown, value: unknown, callback: (error?: Error) => void): void => {
    if (createBomForm.material_mode === 'NEW' && !String(value ?? '').trim()) {
      callback(new Error(`请填写${label}`))
      return
    }
    callback()
  }
}

const createBomRules: FormRules = {
  material_id: [
    {
      validator: (_rule, value, callback) => {
        if (createBomForm.material_mode === 'EXISTING' && !value) {
          callback(new Error('请选择母件物料'))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
  new_material_code: [{ validator: requireNewMaterialField('母件编码'), trigger: 'blur' }],
  new_material_name: [{ validator: requireNewMaterialField('母件名称'), trigger: 'blur' }],
  new_unit_code: [{ validator: requireNewMaterialField('计量单位'), trigger: 'blur' }],
  bom_version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
}

function onMaterialModeChange(): void {
  createBomFormRef.value?.clearValidate(['material_id', 'new_material_code', 'new_material_name', 'new_unit_code'])
}

function openCreateBom(): void {
  Object.assign(createBomForm, {
    material_mode: canCreateMaterial.value ? 'NEW' : 'EXISTING',
    material_id: undefined,
    new_material_code: '',
    new_material_name: '',
    new_unit_code: 'PCS',
    new_specification: '',
    bom_version: 'V1.0',
    effective_date: '',
    remark: '',
  })
  createBomRows.value = [{ quantity: 1, lead_time_offset: 0, scrap_rate: 0 }]
  createBomVisible.value = true
}

function addCreateBomRow(): void {
  createBomRows.value.push({ quantity: 1, lead_time_offset: 0, scrap_rate: 0 })
}

function removeCreateBomRow(index: number): void {
  createBomRows.value.splice(index, 1)
}

async function submitCreateBom(): Promise<void> {
  const valid = await createBomFormRef.value?.validate().catch(() => false)
  if (!valid) return
  const items = createBomRows.value.filter((row) => row.material_id)
  if (!items.length) {
    ElMessage.warning('请至少添加一个子件')
    return
  }
  const duplicated = items.length !== new Set(items.map((row) => row.material_id)).size
  if (duplicated) {
    ElMessage.warning('同一子件不能重复添加')
    return
  }
  createBomSubmitting.value = true
  try {
    // 新建母件：先建档成品物料（整机 / 自制），再挂 BOM
    let parentId = createBomForm.material_id
    let parentLabel = ''
    if (createBomForm.material_mode === 'NEW') {
      const material = await createMaterial({
        material_code: createBomForm.new_material_code.trim(),
        material_name: createBomForm.new_material_name.trim(),
        material_type: 'FINISHED',
        supply_type: 'MAKE',
        unit_code: createBomForm.new_unit_code.trim() || 'PCS',
        specification: createBomForm.new_specification.trim() || null,
        sales_category: 'MACHINE',
        status: 'ACTIVE',
      })
      parentId = material.id
      parentLabel = `${material.material_code} ${material.material_name}`
    }
    if (!parentId) return

    const bom = await createBom({
      material_id: parentId,
      bom_version: createBomForm.bom_version.trim(),
      effective_date: createBomForm.effective_date || null,
      remark: createBomForm.remark || null,
      is_active: true,
      status: 'ACTIVE',
      items: items.map((row, index) => ({
        material_id: row.material_id,
        quantity: row.quantity,
        lead_time_offset: row.lead_time_offset,
        scrap_rate: row.scrap_rate,
        sequence_no: index + 1,
      })),
    })
    createBomVisible.value = false
    const prefix = parentLabel ? `已新建母件 ${parentLabel}，` : ''
    ElMessage.success(`${prefix}并生成 BOM ${bom.bom_code}（${items.length} 个子件）`)
    rootMaterialId.value = parentId
    rootLabel.value = parentLabel
    await loadTree()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    createBomSubmitting.value = false
  }
}

// ---------------- CSV 导入 BOM ----------------

interface CsvBomRow {
  line: number
  parentCode: string
  childCode: string
  quantity: number
  version: string
  leadOffset: number
  scrapRate: number
  remark: string
}

const importVisible = ref(false)
const importFileName = ref('')
const importPreview = ref<CsvBomRow[]>([])
const importErrors = ref<string[]>([])
const importSubmitting = ref(false)
/** 母件在物料管理中不存在时，自动按成品/整机建档 */
const importAutoCreateParent = ref(true)

const IMPORT_TEMPLATE = [
  '母件编码,子件编码,用量,版本,提前期偏置,损耗率,备注',
  'FG-1001,SF-2001,1,V1.0,0,0,塑料件',
  'FG-1001,SF-1001,4,V1.0,0,0,底盘螺丝',
].join('\n')

function openImportBom(): void {
  importFileName.value = ''
  importPreview.value = []
  importErrors.value = []
  importVisible.value = true
}

function downloadImportTemplate(): void {
  const blob = new Blob([`\uFEFF${IMPORT_TEMPLATE}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'BOM导入模板.csv'
  link.click()
  URL.revokeObjectURL(url)
}

/** 解析一行 CSV（支持双引号包裹与转义） */
function splitCsvLine(line: string): string[] {
  const cells: string[] = []
  let current = ''
  let quoted = false
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i]
    if (quoted) {
      if (char === '"' && line[i + 1] === '"') {
        current += '"'
        i += 1
      } else if (char === '"') {
        quoted = false
      } else {
        current += char
      }
    } else if (char === '"') {
      quoted = true
    } else if (char === ',') {
      cells.push(current.trim())
      current = ''
    } else {
      current += char
    }
  }
  cells.push(current.trim())
  return cells
}

function parseCsv(text: string): void {
  const errors: string[] = []
  const rows: CsvBomRow[] = []
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/).filter((line) => line.trim())
  if (lines.length < 2) {
    importPreview.value = []
    importErrors.value = ['文件内容为空，或只有表头']
    return
  }
  const headers = splitCsvLine(lines[0]).map((item) => item.replace(/\s/g, ''))
  const alias: Record<string, string[]> = {
    parent: ['母件编码', 'parent_code', 'parent_material_code', '母件'],
    child: ['子件编码', 'child_code', 'child_material_code', '子件'],
    quantity: ['用量', 'quantity', '单位用量'],
    version: ['版本', 'version', 'bom_version', '版本号'],
    lead: ['提前期偏置', 'lead_time_offset', '提前期'],
    scrap: ['损耗率', 'scrap_rate'],
    remark: ['备注', 'remark'],
  }
  const indexOf = (key: string): number =>
    headers.findIndex((header) => alias[key].includes(header))

  const idxParent = indexOf('parent')
  const idxChild = indexOf('child')
  const idxQty = indexOf('quantity')
  if (idxParent < 0 || idxChild < 0 || idxQty < 0) {
    importPreview.value = []
    importErrors.value = ['表头缺少必填列：母件编码 / 子件编码 / 用量']
    return
  }
  const idxVersion = indexOf('version')
  const idxLead = indexOf('lead')
  const idxScrap = indexOf('scrap')
  const idxRemark = indexOf('remark')

  lines.slice(1).forEach((line, offset) => {
    const lineNo = offset + 2
    const cells = splitCsvLine(line)
    const parentCode = cells[idxParent] ?? ''
    const childCode = cells[idxChild] ?? ''
    const qty = Number(cells[idxQty] ?? '')
    if (!parentCode || !childCode) {
      errors.push(`第 ${lineNo} 行：母件编码或子件编码为空`)
      return
    }
    if (!Number.isFinite(qty) || qty <= 0) {
      errors.push(`第 ${lineNo} 行：用量必须大于 0`)
      return
    }
    const lead = idxLead >= 0 ? Number(cells[idxLead] || 0) : 0
    const scrap = idxScrap >= 0 ? Number(cells[idxScrap] || 0) : 0
    if (!Number.isInteger(lead) || lead < 0) {
      errors.push(`第 ${lineNo} 行：提前期偏置必须为非负整数`)
      return
    }
    if (!Number.isFinite(scrap) || scrap < 0 || scrap >= 1) {
      errors.push(`第 ${lineNo} 行：损耗率必须在 0~1 之间`)
      return
    }
    rows.push({
      line: lineNo,
      parentCode,
      childCode,
      quantity: qty,
      version: (idxVersion >= 0 ? cells[idxVersion] : '') || 'V1.0',
      leadOffset: lead,
      scrapRate: scrap,
      remark: idxRemark >= 0 ? cells[idxRemark] ?? '' : '',
    })
  })
  importPreview.value = rows
  importErrors.value = errors
}

/** 读取上传文件：优先 UTF-8，Excel 中文环境默认导出的 ANSI(GBK) 自动兜底 */
async function readFileText(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer)
  } catch {
    return new TextDecoder('gbk').decode(buffer)
  }
}

async function onImportFileChange(file: { raw?: File }): Promise<void> {
  const raw = file.raw
  if (!raw) return
  importFileName.value = raw.name
  parseCsv(await readFileText(raw))
}

async function fetchAllMaterials(): Promise<Material[]> {
  const size = 200
  const first = await listMaterials({ page: 1, page_size: size })
  const items = [...first.items]
  const pages = Math.ceil(first.total / size)
  for (let page = 2; page <= pages; page += 1) {
    const next = await listMaterials({ page, page_size: size })
    items.push(...next.items)
  }
  return items
}

async function submitImportBom(): Promise<void> {
  if (!importPreview.value.length) {
    ElMessage.warning('没有可导入的有效行')
    return
  }
  importSubmitting.value = true
  try {
    const materials = await fetchAllMaterials()
    const codeMap = new Map(materials.map((item) => [item.material_code, item]))
    const groups = new Map<string, CsvBomRow[]>()
    importPreview.value.forEach((row) => {
      const key = `${row.parentCode}@@${row.version}`
      const list = groups.get(key) ?? []
      list.push(row)
      groups.set(key, list)
    })

    let headersCreated = 0
    let itemsCreated = 0
    let itemsUpdated = 0
    let parentsCreated = 0
    const failures: string[] = []
    let firstParentId: number | undefined

    for (const rows of groups.values()) {
      const parentCode = rows[0].parentCode
      const version = rows[0].version
      let parent = codeMap.get(parentCode)
      if (!parent && importAutoCreateParent.value) {
        // 母件缺失时自动建档：成品 / 自制 / 整机，名称默认取编码，可后续在物料管理里补充
        try {
          parent = await createMaterial({
            material_code: parentCode,
            material_name: parentCode,
            material_type: 'FINISHED',
            supply_type: 'MAKE',
            unit_code: 'PCS',
            sales_category: 'MACHINE',
            status: 'ACTIVE',
          })
          codeMap.set(parent.material_code, parent)
          parentsCreated += 1
        } catch (error) {
          failures.push(`${parentCode}：母件自动建档失败（${(error as Error).message}）`)
          continue
        }
      }
      if (!parent) {
        failures.push(`${parentCode}：母件物料不存在，请先在物料管理中维护，或勾选自动建档`)
        continue
      }
      const mapped = rows
        .map((row) => ({ row, child: codeMap.get(row.childCode) }))
        .filter((entry) => {
          if (!entry.child) failures.push(`${entry.row.childCode}：子件物料不存在`)
          return Boolean(entry.child)
        })
      if (!mapped.length) continue
      firstParentId = parent.id

      const existing = await listBoms({ material_id: parent.id, page: 1, page_size: 200 })
      const sameVersion = existing.items.find((item) => item.bom_version === version)
      const payloadItems = mapped.map(({ row, child }, index) => ({
        material_id: child!.id,
        quantity: row.quantity,
        lead_time_offset: row.leadOffset,
        scrap_rate: row.scrapRate,
        sequence_no: index + 1,
        remark: row.remark || null,
      }))

      if (!sameVersion) {
        await createBom({
          material_id: parent.id,
          bom_version: version,
          is_active: true,
          status: 'ACTIVE',
          items: payloadItems,
        })
        headersCreated += 1
        itemsCreated += payloadItems.length
      } else {
        const detail = await getBom(sameVersion.id)
        const existingItems = new Map(detail.items.map((item) => [item.material_id, item]))
        for (const payload of payloadItems) {
          const exists = existingItems.get(payload.material_id)
          if (exists) {
            // 已存在的子件按文件里的新用量 / 提前期 / 损耗率覆盖，保证重复导入可修正数据
            await updateBomItem(exists.id, {
              quantity: payload.quantity,
              lead_time_offset: payload.lead_time_offset,
              scrap_rate: payload.scrap_rate,
              sequence_no: payload.sequence_no,
              remark: payload.remark,
            })
            itemsUpdated += 1
            continue
          }
          await addBomItem(sameVersion.id, payload)
          itemsCreated += 1
        }
      }
    }

    if (firstParentId) {
      rootMaterialId.value = firstParentId
      await loadTree()
    }
    importVisible.value = false
    const suffix = failures.length ? `；${failures.length} 条失败：${failures.slice(0, 3).join('；')}` : ''
    ElMessage.success(
      `导入完成：新建母件 ${parentsCreated} 个、新建 BOM ${headersCreated} 个、新增子项 ${itemsCreated} 条、更新子项 ${itemsUpdated} 条${suffix}`,
    )
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    importSubmitting.value = false
  }
}

// ---------------- 根物料选择：按 BOM 结构逐层展开 + 直接打字搜索 ----------------

const pickerVisible = ref(false)
const pickerKeyword = ref('')
const pickerLoading = ref(false)
const searchResults = ref<Material[]>([])
const rootLabel = ref('')
let searchTimer: number | undefined

/** 懒加载：首层列成品，展开后按该物料的 BOM 结构继续下钻 */
async function loadPickerNodes(
  node: { level: number; data: { material_id?: number } },
  resolve: (data: BomTreeNode[]) => void,
): Promise<void> {
  if (node.level > 0) {
    try {
      const tree = await getBomTree(node.data.material_id as number)
      resolve(tree[0]?.children ?? [])
    } catch {
      resolve([])
    }
    return
  }
  try {
    const data = await listMaterials({ page: 1, page_size: 200 })
    const finished = data.items.filter((item) => item.material_type === 'FINISHED')
    const roots = finished.length ? finished : data.items
    resolve(
      roots.map((item) => ({
        material_id: item.id,
        material_code: item.material_code,
        material_name: item.material_name,
        quantity: 1,
        level: 0,
        lead_time_offset: 0,
        scrap_rate: 0,
        children: [],
      })) as BomTreeNode[],
    )
  } catch {
    resolve([])
  }
}

function onPickerInput(): void {
  window.clearTimeout(searchTimer)
  const kw = pickerKeyword.value.trim()
  if (!kw) {
    searchResults.value = []
    return
  }
  searchTimer = window.setTimeout(async () => {
    pickerLoading.value = true
    try {
      searchResults.value = (await listMaterials({ keyword: kw, page: 1, page_size: 50 })).items
    } finally {
      pickerLoading.value = false
    }
  }, 250)
}

/** 树节点或搜索结果统一作为根物料 */
async function pickMaterial(item: {
  material_id?: number
  id?: number
  material_code: string
  material_name: string
}): Promise<void> {
  const id = item.material_id ?? item.id
  if (!id) return
  rootMaterialId.value = id
  rootLabel.value = `${item.material_code} ${item.material_name}`
  pickerVisible.value = false
  pickerKeyword.value = ''
  searchResults.value = []
  await loadTree()
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
    syncNodeClassification()
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
const versionForm = reactive({ bom_version: '', effective_date: '', expiry_date: '', remark: '' })
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

/**
 * 重置弹窗内尚未提交的输入。
 * 有选中版本且已加载子项时，以其子项作为新版本的起点（即"在原基础修改"）；
 * 否则回到一行空行（从空白新建）。
 */
function resetVersionRows(): void {
  const base = selectedVersion.value
  if (base && versionItems.value.length) {
    versionItemRows.value = versionItems.value.map((item, index) => ({
      material_id: item.material_id,
      quantity: Number(item.quantity),
      lead_time_offset: item.lead_time_offset,
      scrap_rate: Number(item.scrap_rate),
      sequence_no: index + 1,
      remark: item.remark ?? '',
    }))
    return
  }
  versionItemRows.value = []
  addItemRow()
}

/** 「全部重置」：清空弹窗内本次未保存的版本信息与子项，回到基准状态，不触碰库里已有数据。 */
function resetVersionForm(): void {
  Object.assign(versionForm, { bom_version: '', effective_date: '', expiry_date: '', remark: '' })
  resetVersionRows()
  versionFormRef.value?.clearValidate()
}

function openCreateVersion(): void {
  if (!selectedMaterialId.value) {
    ElMessage.warning('请先在左侧选择物料节点')
    return
  }
  resetVersionForm()
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
      expiry_date: versionForm.expiry_date || null,
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

/** 进入页面自动展开「大众自动钳」的 BOM，避免空白等待用户手选根物料 */
async function loadDefaultTree(): Promise<void> {
  try {
    const data = await listMaterials({ keyword: 'FG-CLAMP-001', page: 1, page_size: 20 })
    const target = data.items.find((item) => item.material_code === 'FG-CLAMP-001')
    if (!target) return
    rootMaterialId.value = target.id
    rootLabel.value = `${target.material_code} ${target.material_name}`
    await loadTree()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(loadDefaultTree)
</script>

<template>
  <div class="bom-page">
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">BOM 表</span>
          <span class="table-toolbar__spacer" />
          <el-popover
            v-model:visible="pickerVisible"
            placement="bottom-end"
            :width="400"
            trigger="click"
            popper-class="bom-picker"
          >
            <template #reference>
              <el-input
                :model-value="rootLabel"
                placeholder="选择根物料"
                readonly
                style="width: 280px"
              />
            </template>
            <div class="bom-picker__panel">
              <el-input
                v-model="pickerKeyword"
                placeholder="输入物料编码 / 名称直接搜索"
                clearable
                @input="onPickerInput"
              />
              <div v-loading="pickerLoading" class="bom-picker__list">
                <template v-if="pickerKeyword.trim()">
                  <div
                    v-for="item in searchResults"
                    :key="item.id"
                    class="bom-picker__item"
                    @click="pickMaterial(item)"
                  >
                    <span class="bom-picker__code">{{ item.material_code }}</span>
                    <span class="bom-picker__name">{{ item.material_name }}</span>
                  </div>
                  <div v-if="!pickerLoading && !searchResults.length" class="bom-picker__empty">
                    无匹配物料
                  </div>
                </template>
                <el-tree
                  v-else
                  lazy
                  :load="loadPickerNodes"
                  :props="{ label: 'material_name', children: 'children' }"
                  node-key="material_id"
                  :expand-on-click-node="false"
                  @node-click="pickMaterial"
                >
                  <template #default="{ data }">
                    <span class="bom-picker__node">
                      <span class="bom-picker__code">{{ data.material_code }}</span>
                      <span class="bom-picker__name">{{ data.material_name }}</span>
                    </span>
                  </template>
                </el-tree>
              </div>
            </div>
          </el-popover>
          <el-button v-if="canManageBom" type="primary" plain @click="openCreateBom">新建整机 BOM</el-button>
          <el-button v-if="canManageBom" plain @click="openImportBom">导入 BOM</el-button>
          <el-button type="primary" :loading="treeLoading" @click="loadTree">展开结构树</el-button>
        </div>
      </template>

      <el-row :gutter="12">
        <el-col :xs="24" :md="8" :lg="7">
          <el-card shadow="never" class="bom-panel">
            <template #header><span>BOM 结构树</span></template>
            <el-tree
              v-loading="treeLoading"
              :data="treeData"
              node-key="material_id"
              :props="{ label: 'material_name', children: 'children' }"
              default-expand-all
              empty-text="选择根物料后展开，点节点即可编辑其 BOM"
              @node-click="selectNode"
            >
              <template #default="{ data }">
                <span class="bom-node">
                  <span class="bom-node__code">{{ data.material_code }}</span>
                  <span class="bom-node__name">{{ data.material_name }}</span>
                  <span class="bom-node__qty">×{{ data.quantity }}</span>
                  <el-tag size="small" type="info" effect="plain">L{{ data.level }}</el-tag>
                  <el-tag
                    v-if="data.children && data.children.length"
                    size="small"
                    type="success"
                    effect="plain"
                  >
                    子件 {{ data.children.length }}
                  </el-tag>
                  <el-tag v-else size="small" type="warning" effect="plain">末级</el-tag>
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
                <el-button v-if="canManageBom" type="primary" @click="openCreateItem">新增子项</el-button>
                <el-button v-if="canManageBom" @click="openCreateVersion">新增版本</el-button>
                <el-tag v-else type="info" effect="plain">只读</el-tag>
              </div>
            </template>

            <el-descriptions v-if="nodeMaterial" :column="3" border size="small">
              <el-descriptions-item label="物料">{{ nodeMaterial.material_code }}</el-descriptions-item>
              <el-descriptions-item label="名称">{{ nodeMaterial.material_name }}</el-descriptions-item>
              <el-descriptions-item label="供应类型">
                <StatusTag :status="nodeMaterial.supply_type" />
              </el-descriptions-item>
              <el-descriptions-item label="ABC 分类">
                <el-select
                  v-model="nodeAbc"
                  size="small"
                  clearable
                  placeholder="未分类"
                  style="width: 100%"
                  :disabled="classSaving"
                  @change="saveNodeClassification"
                >
                  <el-option label="A 类（高价值）" value="A" />
                  <el-option label="B 类（中等）" value="B" />
                  <el-option label="C 类（低值）" value="C" />
                </el-select>
              </el-descriptions-item>
              <el-descriptions-item label="销售类别">
                <el-select
                  v-model="nodeSalesCategory"
                  size="small"
                  style="width: 100%"
                  :disabled="classSaving"
                  @change="saveNodeClassification"
                >
                  <el-option label="整机" value="MACHINE" />
                  <el-option label="可售备件" value="SPARE" />
                  <el-option label="内部件" value="INTERNAL" />
                </el-select>
              </el-descriptions-item>
              <el-descriptions-item label="当前版本">{{ selectedVersion?.bom_version ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="直接子件">
                <el-tag size="small" type="success" effect="plain">{{ versionItems.length }} 项</el-tag>
              </el-descriptions-item>
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
                  <el-button link type="primary" @click.stop="selectVersion(row)">查看子项</el-button>
                  <template v-if="canManageBom">
                    <el-button link type="primary" :disabled="row.is_active" @click.stop="onActivate(row)">生效</el-button>
                    <el-button link :type="row.status === 'ACTIVE' ? 'danger' : 'success'" @click.stop="toggleVersionStatus(row)">
                      {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
                    </el-button>
                    <el-button link type="danger" @click.stop="removeVersion(row)">删除</el-button>
                  </template>
                </template>
              </el-table-column>
              <template #empty>该物料暂无 BOM 版本</template>
            </el-table>
          </el-card>

          <el-card shadow="never" class="bom-panel">
            <template #header>
              <span>子项明细（共 {{ versionItems.length }} 项）</span>
            </template>
            <el-table v-loading="itemLoading" :data="versionItems" size="small" border>
              <el-table-column label="序号" prop="sequence_no" width="60" />
              <el-table-column label="子件编码" prop="material_code" width="130">
                <template #default="{ row }">{{ row.material_code || `#${row.material_id}` }}</template>
              </el-table-column>
              <el-table-column label="子件名称" prop="material_name" min-width="140">
                <template #default="{ row }">{{ row.material_name || '—' }}</template>
              </el-table-column>
              <el-table-column label="单位" prop="unit_code" width="70" />
              <el-table-column label="用量" prop="quantity" width="90" align="right" />
              <el-table-column label="提前期偏置(天)" prop="lead_time_offset" width="130" align="right" />
              <el-table-column label="损耗率" prop="scrap_rate" width="90" align="right" />
              <el-table-column label="备注" prop="remark" min-width="120" />
              <el-table-column label="操作" width="130">
                <template #default="{ row }">
                  <template v-if="canManageBom">
                    <el-button link type="primary" @click="openEditItem(row)">修改</el-button>
                    <el-button link type="danger" @click="removeItem(row)">删除</el-button>
                  </template>
                  <span v-else class="readonly-hint">只读</span>
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
          <el-col :span="12">
            <el-form-item label="母件物料">
              <el-input :model-value="nodeMaterial ? `${nodeMaterial.material_code} ${nodeMaterial.material_name}` : ''" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="版本号" prop="bom_version">
              <el-input v-model="versionForm.bom_version" placeholder="如 V1.0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="生效日期">
              <el-date-picker v-model="versionForm.effective_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="失效日期">
              <el-date-picker
                v-model="versionForm.expiry_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="留空表示长期有效"
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="versionForm.remark" type="textarea" :rows="1" /></el-form-item>
      </el-form>

      <div class="bom-items-editor">
        <div class="table-toolbar">
          <span>子项明细（可一次填多行）</span>
          <span style="font-size: 12px; color: var(--el-text-color-secondary)">
            初始子项{{ selectedVersion ? `来自版本 ${selectedVersion.bom_version}` : '为空' }}，可直接增删后保存
          </span>
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
        <el-button @click="resetVersionForm">全部重置</el-button>
        <el-button @click="versionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="versionSubmitting" @click="submitVersion">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建整件 BOM -->
    <el-dialog v-model="createBomVisible" title="新建 BOM（整件）" width="900px">
      <el-form ref="createBomFormRef" :model="createBomForm" :rules="createBomRules" label-width="90px">
        <el-form-item label="母件来源">
          <el-radio-group
            v-model="createBomForm.material_mode"
            :disabled="!canCreateMaterial"
            @change="onMaterialModeChange"
          >
            <el-radio-button value="NEW">新建母件（整机）</el-radio-button>
            <el-radio-button value="EXISTING">选择已有物料</el-radio-button>
          </el-radio-group>
          <span class="form-hint">新建母件会自动建档为「成品 / 自制 / 整机」，编码不能与已有物料重复</span>
        </el-form-item>
        <el-row v-if="createBomForm.material_mode === 'NEW'" :gutter="12">
          <el-col :span="8">
            <el-form-item label="母件编码" prop="new_material_code">
              <el-input v-model="createBomForm.new_material_code" placeholder="如 FG-1001" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="母件名称" prop="new_material_name">
              <el-input v-model="createBomForm.new_material_name" placeholder="如 办公转椅" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="计量单位" prop="new_unit_code">
              <el-input v-model="createBomForm.new_unit_code" placeholder="PCS" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row v-if="createBomForm.material_mode === 'NEW'" :gutter="12">
          <el-col :span="12">
            <el-form-item label="规格型号">
              <el-input v-model="createBomForm.new_specification" placeholder="可选" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="版本号" prop="bom_version">
              <el-input v-model="createBomForm.bom_version" placeholder="如 V1.0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row v-else :gutter="12">
          <el-col :span="12">
            <el-form-item label="母件物料" prop="material_id">
              <RemoteSelect
                v-model="createBomForm.material_id"
                :loader="materialOptions"
                placeholder="搜索母件编码 / 名称"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="版本号" prop="bom_version">
              <el-input v-model="createBomForm.bom_version" placeholder="如 V1.0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="生效日期">
              <el-date-picker
                v-model="createBomForm.effective_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="留空表示立即生效"
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备注">
              <el-input v-model="createBomForm.remark" placeholder="可选" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="bom-items-editor">
        <div class="table-toolbar">
          <span>子项明细</span>
          <span class="table-toolbar__hint">新建后可在结构树中继续下钻维护子件自身的 BOM</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" plain size="small" @click="addCreateBomRow">+ 添加子件</el-button>
        </div>
        <el-table :data="createBomRows" size="small" border>
          <el-table-column label="序号" width="60">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="子件物料" min-width="220">
            <template #default="{ row }">
              <RemoteSelect
                v-model="row.material_id"
                :loader="materialOptions"
                placeholder="搜索物料编码 / 名称"
              />
            </template>
          </el-table-column>
          <el-table-column label="单位用量" width="120">
            <template #default="{ row }">
              <el-input-number
                v-model="row.quantity"
                :min="0.0001"
                :precision="4"
                :controls="false"
                style="width: 100%"
              />
            </template>
          </el-table-column>
          <el-table-column label="提前期偏置" width="110">
            <template #default="{ row }">
              <el-input-number
                v-model="row.lead_time_offset"
                :min="0"
                :controls="false"
                style="width: 100%"
              />
            </template>
          </el-table-column>
          <el-table-column label="损耗率" width="110">
            <template #default="{ row }">
              <el-input-number
                v-model="row.scrap_rate"
                :min="0"
                :max="0.9999"
                :step="0.01"
                :precision="4"
                :controls="false"
                style="width: 100%"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeCreateBomRow($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="createBomVisible = false">取消</el-button>
        <el-button type="primary" :loading="createBomSubmitting" @click="submitCreateBom">保存</el-button>
      </template>
    </el-dialog>

    <!-- CSV 导入 BOM -->
    <el-dialog v-model="importVisible" title="导入 BOM（CSV）" width="900px">
      <el-alert type="info" :closable="false" class="import-tip">
        <div class="import-tip__title">文件格式：UTF-8 编码的 CSV，第一行为表头，含以下列：</div>
        <div class="import-tip__code">
          母件编码,子件编码,用量,版本,提前期偏置,损耗率,备注
        </div>
        <div>必填：母件编码、子件编码、用量；版本默认 V1.0；提前期偏置默认 0；损耗率默认 0（取值 0~1）。</div>
        <div>同一母件 + 同一版本的多行会合并成一个 BOM；子件必须已在物料管理中维护。</div>
        <div>同版本已存在时，重复子件按文件中的用量 / 提前期偏置 / 损耗率覆盖更新；若同一母件导入多个版本，最后导入的版本为当前激活版本。</div>
      </el-alert>

      <el-checkbox v-model="importAutoCreateParent" :disabled="!canCreateMaterial" class="import-auto-create">
        母件不存在时自动建档（成品 / 自制 / 整机，名称默认取编码，可导入后在物料管理中改名）
      </el-checkbox>

      <div class="import-actions">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".csv,text/csv"
          :on-change="onImportFileChange"
        >
          <el-button type="primary" plain>选择 CSV 文件</el-button>
        </el-upload>
        <span class="import-file">{{ importFileName || '尚未选择文件' }}</span>
        <el-button link type="primary" @click="downloadImportTemplate">下载模板</el-button>
      </div>

      <el-alert
        v-if="importErrors.length"
        type="warning"
        :closable="false"
        class="import-errors"
        :title="`${importErrors.length} 行校验失败：${importErrors.slice(0, 3).join('；')}`"
      />

      <el-table v-if="importPreview.length" :data="importPreview" size="small" border max-height="320">
        <el-table-column label="行号" prop="line" width="60" />
        <el-table-column label="母件编码" prop="parentCode" min-width="130" />
        <el-table-column label="子件编码" prop="childCode" min-width="130" />
        <el-table-column label="用量" prop="quantity" width="90" align="right" />
        <el-table-column label="版本" prop="version" width="90" />
        <el-table-column label="提前期偏置" prop="leadOffset" width="100" align="right" />
        <el-table-column label="损耗率" prop="scrapRate" width="90" align="right" />
        <el-table-column label="备注" prop="remark" min-width="120" />
      </el-table>

      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="importSubmitting"
          :disabled="!importPreview.length"
          @click="submitImportBom"
        >
          导入（{{ importPreview.length }} 行）
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.bom-panel {
  margin-bottom: 12px;
}

.readonly-hint {
  font-size: 12px;
  color: #98a2ad;
}

.bom-items-editor {
  margin-top: 8px;
}

.table-toolbar__hint {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.import-tip {
  margin-bottom: 12px;
}

.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}

.import-auto-create {
  display: block;
  margin-bottom: 12px;
}

.import-tip__title {
  font-weight: 600;
  margin-bottom: 4px;
}

.import-tip__code {
  margin: 6px 0;
  padding: 6px 8px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #303133;
  background: #f5f7fa;
  border-radius: 4px;
  word-break: break-all;
}

.import-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.import-file {
  font-size: 12px;
  color: #606266;
}

.import-errors {
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