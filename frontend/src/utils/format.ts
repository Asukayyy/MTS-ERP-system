/** 库存数量一律按整数展示：后端返回 "200.0000" 形式，统一去掉小数部分 */
export function fmtQty(value: number | string | null | undefined): string {
  const n = Number(value ?? 0)
  return Number.isFinite(n) ? n.toFixed(0) : '0'
}

interface SupplierScoreLike {
  supplier_code: string
  supplier_name: string
  is_primary?: boolean
  quality_score?: number | string | null
  delivery_score?: number | string | null
  price_score?: number | string | null
  total_score?: number | string | null
}

/** 供应商下拉选项标签：主供应商置顶标记 + 各项得分，作为选择主供应商的参考 */
export function supplierOptionLabel(s: SupplierScoreLike): string {
  const base = `${s.supplier_code} ${s.supplier_name}`
  const primary = s.is_primary ? '★主供 ' : ''
  if (s.total_score === null || s.total_score === undefined) {
    return `${primary}${base} ｜ 暂无评价`
  }
  const f = (v: number | string | null | undefined) => Number(v ?? 0).toFixed(0)
  return `${primary}${base} ｜ 综合${f(s.total_score)} 交期${f(s.delivery_score)} 质量${f(s.quality_score)} 价格${f(s.price_score)}`
}
