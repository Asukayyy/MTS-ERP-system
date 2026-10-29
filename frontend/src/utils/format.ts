/** 库存数量一律按整数展示：后端返回 "200.0000" 形式，统一去掉小数部分 */
export function fmtQty(value: number | string | null | undefined): string {
  const n = Number(value ?? 0)
  return Number.isFinite(n) ? n.toFixed(0) : '0'
}
