<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  /** 状态值（后端枚举字符串） */
  status?: string | null
  /** 状态域，用于区分同名字段的语义（业务单据 / 启用状态 / 供应类型等） */
  kind?: 'doc' | 'record' | 'materialType' | 'supply' | 'txn' | 'source' | 'quality'
}>()

/** 状态中文名 */
const LABELS: Record<string, string> = {
  // 单据状态
  DRAFT: '草稿',
  CONFIRMED: '已确认',
  RELEASED: '已下达',
  IN_PROGRESS: '执行中',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
  // 启用状态
  ACTIVE: '启用',
  INACTIVE: '停用',
  // 物料类型
  RAW: '原材料',
  PURCHASED: '采购件',
  SEMI: '半成品',
  FINISHED: '成品',
  // 供应类型
  MAKE: '自制',
  BUY: '采购',
  // 库存流水类型
  IN: '入库',
  OUT: '出库',
  TRANSFER_IN: '移库入库',
  TRANSFER_OUT: '移库出库',
  ADJUST: '盘点调整',
  // 来源类型
  SALES: '销售',
  STOCKFILL: '补库',
  MPS: 'MPS',
  MRP: 'MRP',
  REORDER: '采购补库',
  PRODUCTION: '生产补库',
  MANUAL: '手工',
  PURCHASE_RECEIPT: '采购到货',
  PRODUCTION_COMPLETION: '生产完工',
  MATERIAL_REQUISITION: '生产领料',
  SALES_SHIPMENT: '销售发货',
  SALES_RETURN: '销售退货',
  TRANSFER: '移库',
  STOCKTAKE: '盘点',
  // 质量状态
  QUALIFIED: '合格',
  DEFECTIVE: '不良',
  SCRAP: '报废',
}

/** 状态标签配色 */
const TYPES: Record<string, 'success' | 'info' | 'warning' | 'danger' | 'primary'> = {
  DRAFT: 'info',
  CONFIRMED: 'primary',
  RELEASED: 'warning',
  IN_PROGRESS: 'warning',
  COMPLETED: 'success',
  CANCELLED: 'danger',
  ACTIVE: 'success',
  INACTIVE: 'info',
  MAKE: 'warning',
  BUY: 'primary',
  IN: 'success',
  OUT: 'warning',
  TRANSFER_IN: 'success',
  TRANSFER_OUT: 'warning',
  ADJUST: 'danger',
  QUALIFIED: 'success',
  DEFECTIVE: 'warning',
  SCRAP: 'danger',
  REORDER: 'primary',
  PRODUCTION: 'warning',
}

const label = computed(() => (props.status ? LABELS[props.status] ?? props.status : '-'))
const tagType = computed(() => (props.status ? TYPES[props.status] ?? 'info' : 'info'))
</script>

<template>
  <el-tag :type="tagType" size="small" effect="light">{{ label }}</el-tag>
</template>