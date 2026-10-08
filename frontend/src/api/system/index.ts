import { del, get, patch, post, put } from '@/utils/request'
import type { HealthData, PageData } from '@/types/api'
import type {
  Bom,
  BomItem,
  BomTreeNode,
  Dictionary,
  DictionaryItem,
  LoginResult,
  Material,
  MaterialPayload,
  OperationLog,
  Organization,
  Permission,
  Personnel,
  Role,
  Routing,
  RoutingOperation,
  SystemStats,
  User,
} from '@/types/erp'

/** system 模块接口（基础信息 / 系统管理），统一前缀 /api/v1/system */

/** 占位健康检查，用于验证前后端连通性 */
export function getSystemHealth(): Promise<HealthData> {
  return get<HealthData>('/system/health')
}

/** 系统基础数据统计 */
export function getSystemStats(): Promise<SystemStats> {
  return get<SystemStats>('/system/stats')
}

// ---------------- 物料 ----------------

export function listMaterials(params: Record<string, unknown> = {}): Promise<PageData<Material>> {
  return get<PageData<Material>>('/system/materials', params)
}

export function getMaterial(id: number): Promise<Material> {
  return get<Material>(`/system/materials/${id}`)
}

export function createMaterial(payload: MaterialPayload): Promise<Material> {
  return post<Material>('/system/materials', payload)
}

export function updateMaterial(id: number, payload: MaterialPayload): Promise<Material> {
  return put<Material>(`/system/materials/${id}`, payload)
}

/** 物料启用 / 停用（PATCH） */
export function setMaterialStatus(id: number, status: string): Promise<Material> {
  return patch<Material>(`/system/materials/${id}/status`, { status })
}

// ---------------- BOM ----------------

export function listBoms(params: Record<string, unknown> = {}): Promise<PageData<Bom>> {
  return get<PageData<Bom>>('/system/boms', params)
}

export function createBom(payload: Record<string, unknown>): Promise<Bom> {
  return post<Bom>('/system/boms', payload)
}

export function getBomTree(materialId: number, maxLevel = 10): Promise<BomTreeNode[]> {
  return get<BomTreeNode[]>('/system/boms/tree', { material_id: materialId, max_level: maxLevel })
}

export function getBom(id: number): Promise<Bom> {
  return get<Bom>(`/system/boms/${id}`)
}

export function updateBom(id: number, payload: Record<string, unknown>): Promise<Bom> {
  return put<Bom>(`/system/boms/${id}`, payload)
}

export function deleteBom(id: number): Promise<null> {
  return del<null>(`/system/boms/${id}`)
}

/** 激活指定 BOM 版本（同物料其它版本置非激活） */
export function activateBom(id: number): Promise<Bom> {
  return post<Bom>(`/system/boms/${id}/activate`)
}

export function setBomStatus(id: number, status: string): Promise<Bom> {
  return patch<Bom>(`/system/boms/${id}/status`, { status })
}

export function addBomItem(bomId: number, payload: Record<string, unknown>): Promise<BomItem> {
  return post<BomItem>(`/system/boms/${bomId}/items`, payload)
}

export function updateBomItem(itemId: number, payload: Record<string, unknown>): Promise<BomItem> {
  return put<BomItem>(`/system/bom-items/${itemId}`, payload)
}

export function deleteBomItem(itemId: number): Promise<null> {
  return del<null>(`/system/bom-items/${itemId}`)
}

// ---------------- 工艺路线 ----------------

export function listRoutings(params: Record<string, unknown> = {}): Promise<PageData<Routing>> {
  return get<PageData<Routing>>('/system/routings', params)
}

export function createRouting(payload: Record<string, unknown>): Promise<Routing> {
  return post<Routing>('/system/routings', payload)
}

export function getRouting(id: number): Promise<Routing> {
  return get<Routing>(`/system/routings/${id}`)
}

export function updateRouting(id: number, payload: Record<string, unknown>): Promise<Routing> {
  return put<Routing>(`/system/routings/${id}`, payload)
}

export function setRoutingStatus(id: number, status: string): Promise<Routing> {
  return patch<Routing>(`/system/routings/${id}/status`, { status })
}

export function addRoutingOperation(
  routingId: number,
  payload: Record<string, unknown>,
): Promise<RoutingOperation> {
  return post<RoutingOperation>(`/system/routings/${routingId}/operations`, payload)
}

export function updateRoutingOperation(
  operationId: number,
  payload: Record<string, unknown>,
): Promise<RoutingOperation> {
  return put<RoutingOperation>(`/system/routing-operations/${operationId}`, payload)
}

export function deleteRoutingOperation(operationId: number): Promise<null> {
  return del<null>(`/system/routing-operations/${operationId}`)
}

// ---------------- 组织 ----------------

export function getOrganizationTree(): Promise<Organization[]> {
  return get<Organization[]>('/system/organizations')
}

export function listOrganizationsFlat(): Promise<Organization[]> {
  return get<Organization[]>('/system/organizations/flat')
}

export function createOrganization(payload: Record<string, unknown>): Promise<Organization> {
  return post<Organization>('/system/organizations', payload)
}

export function updateOrganization(id: number, payload: Record<string, unknown>): Promise<Organization> {
  return put<Organization>(`/system/organizations/${id}`, payload)
}

export function setOrganizationStatus(id: number, status: string): Promise<Organization> {
  return patch<Organization>(`/system/organizations/${id}/status`, { status })
}

// ---------------- 人员 ----------------

export function listPersonnel(params: Record<string, unknown> = {}): Promise<PageData<Personnel>> {
  return get<PageData<Personnel>>('/system/personnel', params)
}

export function createPersonnel(payload: Record<string, unknown>): Promise<Personnel> {
  return post<Personnel>('/system/personnel', payload)
}

export function updatePersonnel(id: number, payload: Record<string, unknown>): Promise<Personnel> {
  return put<Personnel>(`/system/personnel/${id}`, payload)
}

export function setPersonnelStatus(id: number, status: string): Promise<Personnel> {
  return patch<Personnel>(`/system/personnel/${id}/status`, { status })
}

// ---------------- 字典 ----------------

export function listDictionaries(): Promise<Dictionary[]> {
  return get<Dictionary[]>('/system/dictionaries')
}

export function createDictionary(payload: Record<string, unknown>): Promise<Dictionary> {
  return post<Dictionary>('/system/dictionaries', payload)
}

export function updateDictionary(id: number, payload: Record<string, unknown>): Promise<Dictionary> {
  return put<Dictionary>(`/system/dictionaries/${id}`, payload)
}

export function addDictionaryItem(dictId: number, payload: Record<string, unknown>): Promise<DictionaryItem> {
  return post<DictionaryItem>(`/system/dictionaries/${dictId}/items`, payload)
}

export function updateDictionaryItem(itemId: number, payload: Record<string, unknown>): Promise<DictionaryItem> {
  return put<DictionaryItem>(`/system/dictionary-items/${itemId}`, payload)
}

export function deleteDictionaryItem(itemId: number): Promise<null> {
  return del<null>(`/system/dictionary-items/${itemId}`)
}

// ---------------- 用户 / 角色 / 权限 ----------------

export function listUsers(params: Record<string, unknown> = {}): Promise<PageData<User>> {
  return get<PageData<User>>('/system/users', params)
}

export function createUser(payload: Record<string, unknown>): Promise<User> {
  return post<User>('/system/users', payload)
}

export function updateUser(id: number, payload: Record<string, unknown>): Promise<User> {
  return put<User>(`/system/users/${id}`, payload)
}

export function setUserStatus(id: number, status: string): Promise<User> {
  return patch<User>(`/system/users/${id}/status`, { status })
}

export function setUserRoles(id: number, roleIds: number[]): Promise<User> {
  return post<User>(`/system/users/${id}/roles`, { role_ids: roleIds })
}

export function listRoles(status?: string): Promise<Role[]> {
  return get<Role[]>('/system/roles', status ? { status } : {})
}

export function createRole(payload: Record<string, unknown>): Promise<Role> {
  return post<Role>('/system/roles', payload)
}

export function updateRole(id: number, payload: Record<string, unknown>): Promise<Role> {
  return put<Role>(`/system/roles/${id}`, payload)
}

export function setRolePermissions(id: number, permissionIds: number[]): Promise<Role> {
  return post<Role>(`/system/roles/${id}/permissions`, { permission_ids: permissionIds })
}

export function getPermissionTree(): Promise<Permission[]> {
  return get<Permission[]>('/system/permissions')
}

export function createPermission(payload: Record<string, unknown>): Promise<Permission> {
  return post<Permission>('/system/permissions', payload)
}

export function updatePermission(id: number, payload: Record<string, unknown>): Promise<Permission> {
  return put<Permission>(`/system/permissions/${id}`, payload)
}

// ---------------- 登录 / 注册 / 日志 ----------------

export function login(payload: { username: string; password: string }): Promise<LoginResult> {
  return post<LoginResult>('/system/auth/login', payload)
}

/** 注册页可选的九种身份角色 */
export function listRegisterRoles(): Promise<Role[]> {
  return get<Role[]>('/system/auth/register-roles')
}

/** 注册账号：选择部门 + 选择一种身份（九选一），工号留空自动生成 */
export function register(payload: {
  username: string
  password: string
  display_name: string
  org_id: number
  employee_no?: string
  role_ids: number[]
}): Promise<User> {
  return post<User>('/system/auth/register', payload)
}

export function listOperationLogs(params: Record<string, unknown> = {}): Promise<PageData<OperationLog>> {
  return get<PageData<OperationLog>>('/system/operation-logs', params)
}