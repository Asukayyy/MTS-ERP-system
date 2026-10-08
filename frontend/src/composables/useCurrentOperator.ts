import { computed, ref } from 'vue'

/** 当前操作人（用于审计：后端 created_by / updated_by / operator_id） */
export interface CurrentOperator {
  id: number
  /** 展示用姓名（形如"工号 姓名"），仅用于界面回显 */
  name: string
}

/** localStorage 持久化 key */
const STORAGE_KEY = 'bh-erp:operator_id'

/** 从 localStorage 读取，兼容 JSON 解析失败 / 只存了数字 id 的旧格式 */
function readFromStorage(): CurrentOperator | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null

    const parsed = JSON.parse(raw) as unknown

    // 兼容只存了数字 id 的情况
    if (typeof parsed === 'number') {
      return Number.isFinite(parsed) ? { id: parsed, name: '' } : null
    }

    if (parsed !== null && typeof parsed === 'object') {
      const id = Number((parsed as { id?: unknown }).id)
      if (!Number.isFinite(id)) return null
      const name = (parsed as { name?: unknown }).name
      return { id, name: typeof name === 'string' ? name : '' }
    }

    return null
  } catch {
    // JSON 解析失败或 localStorage 不可用，视为未选择
    return null
  }
}

/** 模块级单例：所有组件共享同一份当前操作人状态 */
const currentOperator = ref<CurrentOperator | null>(readFromStorage())

function persist(value: CurrentOperator | null): void {
  try {
    if (value) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // localStorage 不可用（无痕模式 / 存储被禁用）时忽略，仅影响刷新后的持久化
  }
}

/** 设置当前操作人 */
function setOperator(operator: CurrentOperator | null): void {
  currentOperator.value = operator
  persist(operator)
}

/** 清空当前操作人 */
function clearOperator(): void {
  setOperator(null)
}

/**
 * 读取当前操作人 id。
 *
 * 供请求层（non-setup 上下文）注入 operator_id 使用，无需组件实例。
 */
export function getCurrentOperatorId(): number | null {
  return currentOperator.value?.id ?? null
}

/** 当前操作人状态与设置/清空方法 */
export function useCurrentOperator() {
  const operatorId = computed(() => currentOperator.value?.id ?? null)
  const operatorName = computed(() => currentOperator.value?.name ?? '')

  return {
    currentOperator,
    operatorId,
    operatorName,
    setOperator,
    clearOperator,
  }
}
