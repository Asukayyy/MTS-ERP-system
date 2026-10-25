<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  createPersonnel,
  createUser,
  getOrganizationTree,
  listOrganizationsFlat,
  listPersonnel,
  listRoles,
  listUsers,
  setPersonnelStatus,
  setUserRoles,
  setUserStatus,
} from '@/api/system'
import { hasPermission } from '@/utils/auth'
import type { PageData } from '@/types/api'
import type { Organization, Personnel, Role, User } from '@/types/erp'

const loading = ref(false)
const saving = ref(false)
const personnel = ref<Personnel[]>([])
const users = ref<User[]>([])
const roles = ref<Role[]>([])
const orgs = ref<Organization[]>([])
const orgTree = ref<Organization[]>([])

type OrgOption = Organization & { display_name: string; children?: OrgOption[] }

/** 组织树转成带层级编码的选项：01 公司 / 01.01 部门 / 01.01.01 车间 */
const orgOptions = computed<OrgOption[]>(() => decorateOrg(orgTree.value))

function decorateOrg(nodes: Organization[], parentCode = ''): OrgOption[] {
  return nodes.map((org, index) => {
    const pathCode = parentCode
      ? `${parentCode}.${String(index + 1).padStart(2, '0')}`
      : String(index + 1).padStart(2, '0')
    return {
      ...org,
      display_name: `${pathCode} ${org.org_name}`,
      children: decorateOrg(org.children ?? [], pathCode),
    }
  })
}

const keyword = ref('')
const orgId = ref<number | undefined>()
const selectedId = ref<number | null>(null)
/** 点击选中待分配的角色（拖拽之外的备用方式） */
const activeRoleId = ref<number | null>(null)
const draggingRole = ref<Role | null>(null)
const dragOverId = ref<number | null>(null)

const createVisible = ref(false)
const createForm = reactive({ username: '', password: '123456' })
const pendingPerson = ref<Personnel | null>(null)
const pendingRole = ref<Role | null>(null)

// ---- 新增员工（人事建档） ----
const personVisible = ref(false)
const personSubmitting = ref(false)
const personFormRef = ref<FormInstance>()
const personForm = reactive({
  employee_no: '',
  person_name: '',
  gender: '',
  id_card: '',
  org_id: undefined as number | undefined,
  position: '',
  phone: '',
  email: '',
  hire_date: '',
  remark: '',
})

const personRules: FormRules = {
  employee_no: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  person_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  org_id: [{ required: true, message: '请选择所属部门', trigger: 'change' }],
  id_card: [
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback()
        if (!/^\d{17}[\dXx]$/.test(value)) return callback(new Error('身份证号格式不正确'))
        callback()
      },
      trigger: 'blur',
    },
  ],
}

function openCreatePerson() {
  Object.assign(personForm, {
    employee_no: '',
    person_name: '',
    gender: '',
    id_card: '',
    org_id: undefined,
    position: '',
    phone: '',
    email: '',
    hire_date: '',
    remark: '',
  })
  personVisible.value = true
}

async function submitPerson() {
  const valid = await personFormRef.value?.validate().catch(() => false)
  if (!valid) return
  personSubmitting.value = true
  try {
    await createPersonnel({
      employee_no: personForm.employee_no.trim(),
      person_name: personForm.person_name.trim(),
      gender: personForm.gender || null,
      id_card: personForm.id_card.trim() || null,
      org_id: personForm.org_id,
      position: personForm.position || null,
      phone: personForm.phone || null,
      email: personForm.email || null,
      hire_date: personForm.hire_date || null,
      remark: personForm.remark || null,
    })
    ElMessage.success('员工已建档')
    personVisible.value = false
    await loadAll()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    personSubmitting.value = false
  }
}

// ---- 离职 / 复职 ----
const dismissingId = ref<number | null>(null)
const restoringId = ref<number | null>(null)

async function dismissPerson(person: Personnel): Promise<void> {
  const account = userOf(person)
  try {
    await ElMessageBox.confirm(
      account
        ? `确认开除 ${person.person_name}（${person.employee_no}）？其登录账号 ${account.username} 将同时停用。`
        : `确认开除 ${person.person_name}（${person.employee_no}）？`,
      '开除员工',
      { type: 'warning', confirmButtonText: '确认开除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  dismissingId.value = person.id
  try {
    const updated = await setPersonnelStatus(person.id, 'INACTIVE')
    personnel.value = personnel.value.map((item) => (item.id === updated.id ? updated : item))
    if (account) {
      const disabled = await setUserStatus(account.id, 'INACTIVE')
      users.value = users.value.map((item) => (item.id === disabled.id ? disabled : item))
    }
    ElMessage.success(`${person.person_name} 已办理离职`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    dismissingId.value = null
  }
}

async function restorePerson(person: Personnel): Promise<void> {
  restoringId.value = person.id
  try {
    const updated = await setPersonnelStatus(person.id, 'ACTIVE')
    personnel.value = personnel.value.map((item) => (item.id === updated.id ? updated : item))
    const account = userOf(person)
    if (account && account.status === 'INACTIVE') {
      const enabled = await setUserStatus(account.id, 'ACTIVE')
      users.value = users.value.map((item) => (item.id === enabled.id ? enabled : item))
    }
    ElMessage.success(`${person.person_name} 已复职`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    restoringId.value = null
  }
}

/** 员工 ID → 账号 */
const userMap = computed(() => {
  const map = new Map<number, User>()
  users.value.forEach((user) => {
    if (user.personnel_id) map.set(user.personnel_id, user)
  })
  return map
})

const orgNameMap = computed(() => {
  const map = new Map<number, string>()
  orgs.value.forEach((org) => map.set(org.id, org.org_name))
  return map
})

const filteredPeople = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return personnel.value.filter((person) => {
    if (orgId.value && person.org_id !== orgId.value) return false
    if (!kw) return true
    return (
      person.person_name.toLowerCase().includes(kw) ||
      person.employee_no.toLowerCase().includes(kw)
    )
  })
})

/** 无角色管理权限的账号（HR）不展示超级管理员角色，避免越权提权 */
const roleLibrary = computed(() =>
  roles.value.filter((role) => role.role_code !== 'ADMIN' || hasPermission('system:role')),
)

const accountCount = computed(() => users.value.filter((u) => u.personnel_id).length)

function userOf(person: Personnel): User | undefined {
  return userMap.value.get(person.id)
}

function orgNameOf(person: Personnel): string {
  return orgNameMap.value.get(person.org_id) ?? `组织 ${person.org_id}`
}

async function loadAll() {
  loading.value = true
  try {
    const [people, accounts, roleList, orgList, tree] = await Promise.all([
      fetchAll((page, size) => listPersonnel({ page, page_size: size })),
      fetchAll((page, size) => listUsers({ page, page_size: size })),
      listRoles('ACTIVE'),
      listOrganizationsFlat(),
      getOrganizationTree(),
    ])
    personnel.value = people
    users.value = accounts
    roles.value = roleList
    orgs.value = orgList
    orgTree.value = tree
  } finally {
    loading.value = false
  }
}

/** 按后端单页上限（200）逐页取全量，避免员工超过一页时漏人 */
async function fetchAll<T>(
  fetcher: (page: number, size: number) => Promise<PageData<T>>,
): Promise<T[]> {
  const size = 200
  const first = await fetcher(1, size)
  const items = [...first.items]
  const pages = Math.ceil(first.total / size)
  for (let page = 2; page <= pages; page += 1) {
    const next = await fetcher(page, size)
    items.push(...next.items)
  }
  return items
}

function selectPerson(person: Personnel) {
  selectedId.value = person.id
  if (activeRoleId.value) {
    const role = roleLibrary.value.find((item) => item.id === activeRoleId.value)
    if (role) assignRole(person, role)
  }
}

function pickRole(role: Role) {
  activeRoleId.value = activeRoleId.value === role.id ? null : role.id
}

function startDrag(event: DragEvent, role: Role) {
  draggingRole.value = role
  event.dataTransfer?.setData('text/plain', String(role.id))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy'
}

function endDrag() {
  draggingRole.value = null
  dragOverId.value = null
}

function dropOnPerson(event: DragEvent, person: Personnel) {
  event.preventDefault()
  dragOverId.value = null
  const role = draggingRole.value
  draggingRole.value = null
  if (role) assignRole(person, role)
}

/** 把角色分配给员工；员工未开通账号时先走建号流程 */
async function assignRole(person: Personnel, role: Role) {
  if (person.status !== 'ACTIVE') {
    ElMessage.warning(`${person.person_name} 已离职，请先复职再分配角色`)
    return
  }
  const account = userOf(person)
  if (!account) {
    pendingPerson.value = person
    pendingRole.value = role
    createForm.username = person.employee_no
    createForm.password = '123456'
    createVisible.value = true
    return
  }
  if (account.roles.some((item) => item.id === role.id)) {
    ElMessage.info(`${person.person_name} 已拥有「${role.role_name}」`)
    return
  }
  await replaceRoles(account, [...account.roles.map((item) => item.id), role.id])
}

async function removeRole(person: Personnel, role: Role) {
  const account = userOf(person)
  if (!account) return
  await replaceRoles(
    account,
    account.roles.filter((item) => item.id !== role.id).map((item) => item.id),
  )
}

async function replaceRoles(account: User, roleIds: number[]) {
  saving.value = true
  try {
    const updated = await setUserRoles(account.id, roleIds)
    users.value = users.value.map((user) => (user.id === updated.id ? updated : user))
    ElMessage.success('角色已更新')
  } finally {
    saving.value = false
  }
}

async function submitCreate() {
  const person = pendingPerson.value
  const role = pendingRole.value
  if (!person || !role) return
  if (!createForm.username.trim()) {
    ElMessage.warning('请填写登录名')
    return
  }
  if (createForm.password.length < 6) {
    ElMessage.warning('初始密码至少 6 位')
    return
  }
  saving.value = true
  try {
    const user = await createUser({
      personnel_id: person.id,
      username: createForm.username.trim(),
      password: createForm.password,
      display_name: person.person_name,
      role_ids: [role.id],
    })
    users.value = [...users.value, user]
    createVisible.value = false
    ElMessage.success(`已为 ${person.person_name} 开通账号并分配「${role.role_name}」`)
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="hr-page">
    <header class="hr-head">
      <div class="hr-head__text">
        <h2>人事工作台</h2>
        <p>拖动右侧角色到员工卡片即可分配；员工未开通账号时会先引导建号。</p>
      </div>
      <div class="hr-head__count">
        <span>员工 {{ personnel.length }}</span>
        <span>已开通 {{ accountCount }}</span>
        <span>角色 {{ roles.length }}</span>
      </div>
    </header>

    <div class="hr-body">
      <section class="hr-panel">
        <div class="hr-panel__title">
          <span>员工</span>
          <el-button type="primary" @click="openCreatePerson">新增员工</el-button>
        </div>

        <div class="hr-filters">
          <el-input
            v-model="keyword"
            placeholder="输入姓名或工号搜索"
            clearable
            class="hr-filter-keyword"
          />
          <el-tree-select
            v-model="orgId"
            :data="orgOptions"
            node-key="id"
            :props="{ label: 'display_name', children: 'children' }"
            check-strictly
            default-expand-all
            filterable
            clearable
            placeholder="全部部门（按层级）"
            class="hr-filter-org"
            popper-class="hr-org-popper"
          />
          <span class="hr-filters__count">共 {{ filteredPeople.length }} 人</span>
        </div>

        <div v-loading="loading" class="person-list">
          <article
            v-for="person in filteredPeople"
            :key="person.id"
            class="person-card"
            :class="{
              'is-selected': selectedId === person.id,
              'is-drop': dragOverId === person.id,
              'is-inactive': person.status !== 'ACTIVE',
            }"
            @click="selectPerson(person)"
            @dragover.prevent="dragOverId = person.id"
            @dragleave="dragOverId = null"
            @drop="dropOnPerson($event, person)"
          >
            <div class="person-avatar">{{ person.person_name.slice(0, 1) }}</div>
            <div class="person-main">
              <div class="person-name">
                {{ person.person_name }}
                <span class="person-no">{{ person.employee_no }}</span>
              </div>
              <div class="person-dept">
                {{ orgNameOf(person) }}<template v-if="person.position"> · {{ person.position }}</template>
              </div>
              <div class="person-roles">
                <template v-if="userOf(person)">
                  <el-tag
                    v-for="role in userOf(person)!.roles"
                    :key="role.id"
                    closable
                    size="small"
                    @close.stop="removeRole(person, role)"
                  >
                    {{ role.role_name }}
                  </el-tag>
                  <span v-if="!userOf(person)!.roles.length" class="muted">未分配角色</span>
                </template>
                <span v-else class="muted">未开通账号</span>
              </div>
            </div>
            <div class="person-actions">
              <el-tag v-if="userOf(person)" type="success" effect="plain" size="small">
                {{ userOf(person)!.username }}
              </el-tag>
              <el-tag v-else type="warning" effect="plain" size="small">待建号</el-tag>
              <el-tag v-if="person.status !== 'ACTIVE'" type="info" effect="plain" size="small">
                已离职
              </el-tag>
              <el-button
                v-if="person.status === 'ACTIVE'"
                link
                type="danger"
                size="small"
                :loading="dismissingId === person.id"
                @click.stop="dismissPerson(person)"
              >
                开除
              </el-button>
              <el-button
                v-else
                link
                type="primary"
                size="small"
                :loading="restoringId === person.id"
                @click.stop="restorePerson(person)"
              >
                复职
              </el-button>
            </div>
          </article>
          <el-empty v-if="!loading && !filteredPeople.length" description="没有匹配的员工" />
        </div>
      </section>

      <aside class="hr-panel hr-roles">
        <div class="hr-panel__title">
          <span>角色库</span>
          <span class="hint">拖到左侧员工卡片</span>
        </div>
        <div class="role-list">
          <div
            v-for="role in roleLibrary"
            :key="role.id"
            class="role-card"
            :class="{ 'is-active': activeRoleId === role.id }"
            draggable="true"
            @dragstart="startDrag($event, role)"
            @dragend="endDrag"
            @click="pickRole(role)"
          >
            <div class="role-name">
              {{ role.role_name }}
              <span class="role-code">{{ role.role_code }}</span>
            </div>
            <div class="role-desc">{{ role.description || '暂无说明' }}</div>
            <div class="role-meta">{{ role.permissions?.length ?? 0 }} 项权限</div>
          </div>
          <el-empty v-if="!roleLibrary.length" description="暂无可用角色" />
        </div>
      </aside>
    </div>

    <el-dialog v-model="personVisible" title="新增员工" width="640px">
      <el-form ref="personFormRef" :model="personForm" :rules="personRules" label-width="90px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="工号" prop="employee_no">
              <el-input v-model="personForm.employee_no" placeholder="如 EMP001" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓名" prop="person_name">
              <el-input v-model="personForm.person_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="性别">
              <el-select v-model="personForm.gender" clearable style="width: 100%">
                <el-option label="男" value="MALE" />
                <el-option label="女" value="FEMALE" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="身份证号" prop="id_card">
              <el-input v-model="personForm.id_card" maxlength="18" placeholder="18 位身份证号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属部门" prop="org_id">
              <el-tree-select
                v-model="personForm.org_id"
                :data="orgOptions"
                node-key="id"
                :props="{ label: 'display_name', children: 'children' }"
                check-strictly
                default-expand-all
                filterable
                clearable
                placeholder="请选择部门（按层级）"
                popper-class="hr-org-popper"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="岗位">
              <el-input v-model="personForm.position" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号">
              <el-input v-model="personForm.phone" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱">
              <el-input v-model="personForm.email" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入职日期">
              <el-date-picker
                v-model="personForm.hire_date"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="personForm.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="personVisible = false">取消</el-button>
        <el-button type="primary" :loading="personSubmitting" @click="submitPerson">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="createVisible" title="开通账号并分配角色" width="440px">
      <el-form label-width="82px">
        <el-form-item label="员工">
          <span>{{ pendingPerson?.person_name }}（{{ pendingPerson?.employee_no }}）</span>
        </el-form-item>
        <el-form-item label="登录名" required>
          <el-input v-model="createForm.username" placeholder="登录名" />
        </el-form-item>
        <el-form-item label="初始密码" required>
          <el-input v-model="createForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="分配角色">
          <el-tag>{{ pendingRole?.role_name }}</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">开通并分配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.hr-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hr-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.hr-head__text h2 {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
  color: #1f2d3d;
}

.hr-head__text p {
  margin: 0;
  font-size: 13px;
  color: #7b8794;
}

.hr-head__count {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #5f6b76;
}

.hr-head__count span {
  padding: 4px 10px;
  border-radius: 999px;
  background: #e3f5f3;
}

.hr-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 14px;
  align-items: start;
}

.hr-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  background: #fff;
  border: 1px solid #e8ecef;
  border-radius: 12px;
}

.hr-panel__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2d3d;
}

.hr-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 10px 0 14px;
  padding: 10px 12px;
  border: 1px solid #eef1f4;
  border-radius: 8px;
  background: #f7f9fc;
  font-weight: 400;
}

.hr-filter-keyword {
  width: 260px;
  flex: none;
}

.hr-filter-org {
  width: 320px;
  flex: none;
}

.hr-filters__count {
  margin-left: auto;
  font-size: 13px;
  color: #7a8794;
}

.hint {
  font-size: 12px;
  font-weight: 400;
  color: #98a2ad;
}

.person-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 250px);
  min-height: 120px;
  overflow: auto;
  padding-right: 2px;
}

.person-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #e8ecef;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.person-card.is-inactive {
  background: #fafbfc;
  opacity: 0.72;
}

.person-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.person-card:hover {
  border-color: #9fd9d4;
  background: #f7fdfc;
}

.person-card.is-selected {
  border-color: #0abab5;
  box-shadow: 0 0 0 2px rgba(10, 186, 181, 0.12);
}

.person-card.is-drop {
  border-style: dashed;
  border-color: #0abab5;
  background: #fdf6e3;
}

.person-avatar {
  width: 38px;
  height: 38px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #e3f5f3;
  color: #0a8f8b;
  font-weight: 600;
}

.person-main {
  flex: 1;
  min-width: 0;
}

.person-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2d3d;
}

.person-no {
  margin-left: 6px;
  font-size: 12px;
  font-weight: 400;
  color: #98a2ad;
}

.person-dept {
  margin-top: 2px;
  font-size: 12px;
  color: #7b8794;
}

.person-roles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.muted {
  font-size: 12px;
  color: #98a2ad;
}

.role-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 250px);
  overflow: auto;
}

.role-card {
  padding: 10px 12px;
  border: 1px solid #efe6cc;
  border-radius: 10px;
  background: #fdf6e3;
  cursor: grab;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.role-card:hover {
  border-color: #0abab5;
}

.role-card.is-active {
  border-color: #0abab5;
  box-shadow: 0 0 0 2px rgba(10, 186, 181, 0.14);
}

.role-name {
  font-size: 13px;
  font-weight: 600;
  color: #1f2d3d;
}

.role-code {
  margin-left: 6px;
  font-size: 11px;
  font-weight: 400;
  color: #a39a80;
}

.role-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #7b8794;
}

.role-meta {
  margin-top: 6px;
  font-size: 11px;
  color: #a39a80;
}

@media (max-width: 1100px) {
  .hr-body {
    grid-template-columns: minmax(0, 1fr);
  }

  .person-list,
  .role-list {
    max-height: none;
  }
}
</style>

<style>
/* 组织下拉浮层由 teleport 挂到 body，需全局样式才能放大行高与可视高度 */
.hr-org-popper .el-select-dropdown__wrap {
  max-height: 420px;
}

.hr-org-popper .el-tree-node__content {
  height: 34px;
}
</style>
