import { reactive, ref } from 'vue'
import type { Ref } from 'vue'

import type { PageData } from '@/types/api'

/** 列表查询函数签名（后端分页统一 page / page_size / total / items） */
export type ListFetcher<T> = (params: Record<string, unknown>) => Promise<PageData<T>>

/**
 * 分页表格通用逻辑：查询条件 + 分页 + 加载状态。
 *
 * 各页面把真实的接口函数传进来即可，不做任何本地假数据。
 */
export function usePagedTable<T, Q extends Record<string, unknown>>(
  fetcher: ListFetcher<T>,
  initialQuery: Q,
) {
  const loading = ref(false)
  const rows = ref([]) as Ref<T[]>
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const query = reactive({ ...initialQuery }) as Q

  /** 加载当前页数据 */
  async function load(): Promise<void> {
    loading.value = true
    try {
      const data = await fetcher({
        page: page.value,
        page_size: pageSize.value,
        ...query,
      })
      rows.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  /** 条件查询：回到第一页 */
  function search(): Promise<void> {
    page.value = 1
    return load()
  }

  /** 重置查询条件 */
  function reset(): Promise<void> {
    Object.assign(query, initialQuery)
    page.value = 1
    return load()
  }

  function changePage(next: number): Promise<void> {
    page.value = next
    return load()
  }

  function changeSize(size: number): Promise<void> {
    pageSize.value = size
    page.value = 1
    return load()
  }

  return {
    loading,
    rows,
    total,
    page,
    pageSize,
    query,
    load,
    search,
    reset,
    changePage,
    changeSize,
  }
}

/** 把后端 Decimal（字符串或数字）安全转为数字，用于表格汇总等场景 */
export function toNumber(value: number | string | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const num = Number(value)
  return Number.isNaN(num) ? 0 : num
}