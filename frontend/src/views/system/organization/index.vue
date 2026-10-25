<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createOrganization,
  getOrganizationTree,
  listOrganizationsFlat,
  listPersonnel,
  setOrganizationStatus,
  updateOrganization,
} from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Organization, Personnel, RemoteOption } from '@/types/erp'

/** 组织类型（对应后端 org_type 取值） */
const ORG_TYPES = [
  { value: 'COMPANY', label: '公司' },
  { value: 'FACTORY', label: '工厂' },
  { value: 'DEPARTMENT', label: '部门' },
  { value: 'WORKSHOP', label: '车间' },
  { value: 'WAREHOUSE', label: '仓库' },
]

const loading = ref(false)
const rows = ref<Organization[]>([])
const people = ref<Personnel[]>([])

/** 员工按组织分组，展开组织时作为末级子行展示 */
const peopleByOrg = computed(() => {
  const map = new Map<number, Personnel[]>()
  people.value.forEach((person) => {
    const list = map.get(person.org_id) ?? []
    list.push(person)
    map.set(person.org_id, list)
  })
  return map
})

type OrgRow = Organization & { _kind?: string; _path_code?: string; _level?: number }

/** 组织树 + 末级员工行；员工行 id 取负值避免与组织 id 冲突 */
const displayRows = computed<OrgRow[]>(() => decorate(rows.value))

/**
 * 生成层级编码：根组织 01、02…，子组织 01.01、01.02…，孙组织 01.01.01…
 * 编码本身即可看出从属关系，不依赖数据库自增 id。
 */
function decorate(nodes: Organization[], parentCode = '', depth = 1): OrgRow[] {
  return nodes.map((org, index) => {
    const pathCode = parentCode
      ? `${parentCode}.${String(index + 1).padStart(2, '0')}`
      : String(index + 1).padStart(2, '0')
    return {
      ...org,
      _path_code: pathCode,
      _level: depth,
      children: [
        ...decorate(org.children ?? [], pathCode, depth + 1),
        ...(peopleByOrg.value.get(org.id) ?? []).map(
          (person) =>
            ({
              id: -person.id,
              parent_id: org.id,
              org_code: person.employee_no,
              org_name: person.person_name,
              org_type: 'PERSON',
              manager_id: null,
              status: person.status,
              remark: person.position ?? '',
              _kind: 'person',
              _path_code: `${pathCode}.${person.employee_no}`,
              _level: depth + 1,
              children: [],
            }) as unknown as OrgRow,
        ),
      ],
    } as OrgRow
  })
}

/** 组织选项：用于上级组织下拉 */
async function loadOrgOptions(keyword: string): Promise<RemoteOption[]> {
  const list = await listOrganizationsFlat()
  const text = keyword.trim()
  return list
    .filter((item) => !text || item.org_code.includes(text) || item.org_name.includes(text))
    .map((item) => ({ id: item.id, label: `${item.org_code} ${item.org_name}` }))
}

/** 负责人选项：来源 system 员工 */
async function loadPersonnelOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  return data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
}

function isPerson(row: Organization): boolean {
  return (row as { _kind?: string })._kind === 'person'
}

/** 负责人显示姓名，找不到档案时回退为 #id */
function managerLabel(row: Organization): string {
  if (!row.manager_id) return '—'
  const person = people.value.find((item) => item.id === row.manager_id)
  return person ? person.person_name : `#${row.manager_id}`
}

/** 层级标签配色：L1 深、L2 中、L3 浅，逐级弱化 */
function levelTagType(row: OrgRow): 'primary' | 'success' | 'warning' | 'info' {
  const level = row._level ?? 1
  if (level === 1) return 'primary'
  if (level === 2) return 'success'
  if (level === 3) return 'warning'
  return 'info'
}

// 展开状态：默认收起，按层级逐层展开，避免全展开后分不清上下级
const expandAll = ref(false)
const tableKey = ref(0)

function toggleExpandAll(): void {
  expandAll.value = !expandAll.value
  tableKey.value += 1
}

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await getOrganizationTree()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
  // 员工权限独立的角色可能没有 system:personnel，拉不到就不展示末级员工行
  try {
    const data = await listPersonnel({ page: 1, page_size: 200 })
    people.value = data.items
  } catch {
    people.value = []
  }
}

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  org_code: string
  org_name: string
  parent_id: number | undefined
  org_type: string
  manager_id: number | undefined
  status: string
  remark: string
}>({
  org_code: '',
  org_name: '',
  parent_id: undefined,
  org_type: 'DEPARTMENT',
  manager_id: undefined,
  status: 'ACTIVE',
  remark: '',
})

const rules: FormRules = {
  org_code: [{ required: true, message: '请输入组织编码', trigger: 'blur' }],
  org_name: [{ required: true, message: '请输入组织名称', trigger: 'blur' }],
  org_type: [{ required: true, message: '请选择组织类型', trigger: 'change' }],
}

function resetForm(): void {
  Object.assign(form, {
    org_code: '',
    org_name: '',
    parent_id: undefined,
    org_type: 'DEPARTMENT',
    manager_id: undefined,
    status: 'ACTIVE',
    remark: '',
  })
}

function openCreate(): void {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Organization): void {
  editingId.value = row.id
  Object.assign(form, {
    org_code: row.org_code,
    org_name: row.org_name,
    parent_id: row.parent_id ?? undefined,
    org_type: row.org_type,
    manager_id: row.manager_id ?? undefined,
    status: row.status,
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
      org_name: form.org_name,
      parent_id: form.parent_id ?? null,
      org_type: form.org_type,
      manager_id: form.manager_id ?? null,
      status: form.status,
      remark: form.remark || null,
    }
    if (editingId.value === null) {
      await createOrganization({ ...payload, org_code: form.org_code })
      ElMessage.success('组织已新增')
    } else {
      await updateOrganization(editingId.value, payload)
      ElMessage.success('组织已修改')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: Organization): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setOrganizationStatus(row.id, next)
    ElMessage.success(next === 'ACTIVE' ? '组织已启用' : '组织已停用')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">组织机构</span>
          <span class="table-toolbar__spacer" />
          <el-button @click="toggleExpandAll">{{ expandAll ? '收起全部' : '展开全部' }}</el-button>
          <el-button @click="load">刷新</el-button>
          <el-button type="primary" @click="openCreate">新增组织</el-button>
        </div>
      </template>

      <el-table
        :key="tableKey"
        v-loading="loading"
        :data="displayRows"
        row-key="id"
        :tree-props="{ children: 'children' }"
        :default-expand-all="expandAll"
        :indent="26"
        border
        size="small"
      >
        <el-table-column label="组织 / 员工" min-width="240">
          <template #default="{ row }">
            <span class="org-name">
              <el-tag v-if="isPerson(row)" size="small" type="info" effect="plain">员工</el-tag>
              <el-tag v-else size="small" :type="levelTagType(row)" effect="dark">L{{ row._level }}</el-tag>
              <span :class="{ 'org-name__person': isPerson(row) }">{{ row.org_name }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="编码 / 工号" prop="org_code" min-width="150" />
        <el-table-column label="层级编码" width="170">
          <template #default="{ row }">
            <span class="org-path">{{ row._path_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="组织类型" width="110">
          <template #default="{ row }">
            <span v-if="isPerson(row)" class="org-person">员工</span>
            <template v-else>
              {{ ORG_TYPES.find((item) => item.value === row.org_type)?.label ?? row.org_type }}
            </template>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="120">
          <template #default="{ row }">
            <span v-if="!isPerson(row)">{{ managerLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="备注 / 岗位" prop="remark" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <template v-if="!isPerson(row)">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button
                link
                :type="row.status === 'ACTIVE' ? 'danger' : 'success'"
                @click="toggleStatus(row)"
              >
                {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
              </el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>暂无组织数据</template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增组织' : '修改组织'" width="620px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="组织编码" prop="org_code">
              <el-input v-model="form.org_code" :disabled="editingId !== null" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="组织名称" prop="org_name">
              <el-input v-model="form.org_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="上级组织">
              <RemoteSelect v-model="form.parent_id" :loader="loadOrgOptions" placeholder="顶级组织" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="组织类型" prop="org_type">
              <el-select v-model="form.org_type" style="width: 100%">
                <el-option v-for="item in ORG_TYPES" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人">
              <RemoteSelect v-model="form.manager_id" :loader="loadPersonnelOptions" placeholder="请选择员工" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="启用" value="ACTIVE" />
                <el-option label="停用" value="INACTIVE" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.org-person {
  font-size: 12px;
  color: #0a8f8b;
}

.org-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.org-name__person {
  color: #5b6b7c;
}

.org-path {
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
  color: #0a6ecb;
  letter-spacing: 0.3px;
}
</style>