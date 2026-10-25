<script setup lang="ts">
import { ref, watch } from 'vue'

import { getBomTree, getMaterial, listMaterials } from '@/api/system'
import type { BomTreeNode, Material } from '@/types/erp'

/**
 * 按 BOM 结构逐层展开的物料选择器。
 *
 * 数据结构与 BOM 表一致：
 * - 首层列成品，展开节点后按该物料的 BOM 继续下钻；
 * - 支持直接输入物料编码 / 名称搜索，命中后可直接选中。
 */
const props = withDefaults(
  defineProps<{
    modelValue?: number | null
    placeholder?: string
    width?: string
    clearable?: boolean
  }>(),
  { modelValue: undefined, placeholder: '选择物料', width: '260px', clearable: true },
)

const emit = defineEmits<{
  'update:modelValue': [value: number | undefined]
  change: [material: Material | BomTreeNode | undefined]
}>()

const visible = ref(false)
const keyword = ref('')
const loading = ref(false)
const results = ref<Material[]>([])
const label = ref('')
let searchTimer: number | undefined

/** 外部传入 id 时补齐显示文案 */
watch(
  () => props.modelValue,
  async (value) => {
    if (!value) {
      label.value = ''
      return
    }
    if (label.value) return
    try {
      const material = await getMaterial(value)
      label.value = `${material.material_code} ${material.material_name}`
    } catch {
      label.value = ''
    }
  },
  { immediate: true },
)

/** 懒加载：首层列成品，展开后按该物料的 BOM 结构继续下钻 */
async function loadNodes(
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

function onInput(): void {
  window.clearTimeout(searchTimer)
  const kw = keyword.value.trim()
  if (!kw) {
    results.value = []
    return
  }
  searchTimer = window.setTimeout(async () => {
    loading.value = true
    try {
      results.value = (await listMaterials({ keyword: kw, page: 1, page_size: 50 })).items
    } finally {
      loading.value = false
    }
  }, 250)
}

function pick(item: {
  material_id?: number
  id?: number
  material_code: string
  material_name: string
}): void {
  const id = item.material_id ?? item.id
  if (!id) return
  label.value = `${item.material_code} ${item.material_name}`
  emit('update:modelValue', id)
  emit('change', item as Material | BomTreeNode)
  close()
}

function close(): void {
  visible.value = false
  keyword.value = ''
  results.value = []
}

function clear(): void {
  label.value = ''
  emit('update:modelValue', undefined)
  emit('change', undefined)
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="400"
    trigger="click"
    popper-class="bom-picker"
    @hide="close"
  >
    <template #reference>
      <el-input
        :model-value="label"
        :placeholder="placeholder"
        :style="{ width }"
        readonly
        clearable
        @clear="clear"
      />
    </template>
    <div class="bom-picker__panel">
      <el-input
        v-model="keyword"
        placeholder="输入物料编码 / 名称直接搜索"
        clearable
        @input="onInput"
      />
      <div v-loading="loading" class="bom-picker__list">
        <template v-if="keyword.trim()">
          <div
            v-for="item in results"
            :key="item.id"
            class="bom-picker__item"
            @click="pick(item)"
          >
            <span class="bom-picker__code">{{ item.material_code }}</span>
            <span class="bom-picker__name">{{ item.material_name }}</span>
            <span class="bom-picker__type">{{ item.material_type }}</span>
          </div>
          <div v-if="!loading && !results.length" class="bom-picker__empty">无匹配物料</div>
        </template>
        <el-tree
          v-else
          lazy
          :load="loadNodes"
          :props="{ label: 'material_name', children: 'children' }"
          node-key="material_id"
          :expand-on-click-node="false"
          @node-click="pick"
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
</template>

<style scoped>
.bom-picker__panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bom-picker__list {
  max-height: 320px;
  overflow: auto;
}

.bom-picker__item,
.bom-picker__node {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  font-size: 13px;
}

.bom-picker__item {
  cursor: pointer;
}

.bom-picker__item:hover {
  background: #f2f7ff;
}

.bom-picker__code {
  color: #5b6b7c;
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
}

.bom-picker__name {
  color: #1f2d3d;
}

.bom-picker__type {
  margin-left: auto;
  color: #98a2ad;
  font-size: 11px;
}

.bom-picker__empty {
  padding: 12px 0;
  text-align: center;
  color: #98a2ad;
  font-size: 12px;
}
</style>
