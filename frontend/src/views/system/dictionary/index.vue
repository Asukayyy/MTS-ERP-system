<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  addDictionaryItem,
  createDictionary,
  deleteDictionaryItem,
  listDictionaries,
  updateDictionary,
  updateDictionaryItem,
} from '@/api/system'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Dictionary, DictionaryItem } from '@/types/erp'

const loading = ref(false)
const dictionaries = ref<Dictionary[]>([])
const selectedId = ref<number | null>(null)

const selectedDict = computed(
  () => dictionaries.value.find((item) => item.id === selectedId.value) ?? null,
)

async function load(): Promise<void> {
  loading.value = true
  try {
    dictionaries.value = await listDictionaries()
    if (dictionaries.value.length && selectedId.value === null) {
      selectedId.value = dictionaries.value[0].id
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function selectDict(row: Dictionary): void {
  selectedId.value = row.id
}

// ---------------- 字典头 ----------------
const dictDialogVisible = ref(false)
const dictSubmitting = ref(false)
const editingDictId = ref<number | null>(null)
const dictFormRef = ref<FormInstance>()
const dictForm = reactive({ dict_code: '', dict_name: '', status: 'ACTIVE', remark: '' })

const dictRules: FormRules = {
  dict_code: [{ required: true, message: '请输入字典编码', trigger: 'blur' }],
  dict_name: [{ required: true, message: '请输入字典名称', trigger: 'blur' }],
}

function openCreateDict(): void {
  editingDictId.value = null
  Object.assign(dictForm, { dict_code: '', dict_name: '', status: 'ACTIVE', remark: '' })
  dictDialogVisible.value = true
}

function openEditDict(row: Dictionary): void {
  editingDictId.value = row.id
  Object.assign(dictForm, {
    dict_code: row.dict_code,
    dict_name: row.dict_name,
    status: row.status,
    remark: row.remark ?? '',
  })
  dictDialogVisible.value = true
}

async function submitDict(): Promise<void> {
  const valid = await dictFormRef.value?.validate().catch(() => false)
  if (!valid) return
  dictSubmitting.value = true
  try {
    if (editingDictId.value === null) {
      await createDictionary({
        dict_code: dictForm.dict_code,
        dict_name: dictForm.dict_name,
        status: dictForm.status,
        remark: dictForm.remark || null,
      })
      ElMessage.success('字典已新增')
    } else {
      await updateDictionary(editingDictId.value, {
        dict_name: dictForm.dict_name,
        status: dictForm.status,
        remark: dictForm.remark || null,
      })
      ElMessage.success('字典已修改')
    }
    dictDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    dictSubmitting.value = false
  }
}

// ---------------- 字典项 ----------------
const itemDialogVisible = ref(false)
const itemSubmitting = ref(false)
const editingItemId = ref<number | null>(null)
const itemFormRef = ref<FormInstance>()
const itemForm = reactive({
  item_code: '',
  item_name: '',
  item_value: '',
  sort_no: 0,
  status: 'ACTIVE',
})

const itemRules: FormRules = {
  item_code: [{ required: true, message: '请输入字典项编码', trigger: 'blur' }],
  item_name: [{ required: true, message: '请输入字典项名称', trigger: 'blur' }],
}

function openCreateItem(): void {
  if (selectedId.value === null) {
    ElMessage.warning('请先选择字典')
    return
  }
  editingItemId.value = null
  Object.assign(itemForm, { item_code: '', item_name: '', item_value: '', sort_no: 0, status: 'ACTIVE' })
  itemDialogVisible.value = true
}

function openEditItem(row: DictionaryItem): void {
  editingItemId.value = row.id
  Object.assign(itemForm, {
    item_code: row.item_code,
    item_name: row.item_name,
    item_value: row.item_value ?? '',
    sort_no: row.sort_no,
    status: row.status,
  })
  itemDialogVisible.value = true
}

async function submitItem(): Promise<void> {
  const valid = await itemFormRef.value?.validate().catch(() => false)
  if (!valid) return
  if (selectedId.value === null) return
  itemSubmitting.value = true
  try {
    if (editingItemId.value === null) {
      await addDictionaryItem(selectedId.value, {
        item_code: itemForm.item_code,
        item_name: itemForm.item_name,
        item_value: itemForm.item_value || null,
        sort_no: itemForm.sort_no,
        status: itemForm.status,
      })
      ElMessage.success('字典项已新增')
    } else {
      await updateDictionaryItem(editingItemId.value, {
        item_name: itemForm.item_name,
        item_value: itemForm.item_value || null,
        sort_no: itemForm.sort_no,
        status: itemForm.status,
      })
      ElMessage.success('字典项已修改')
    }
    itemDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    itemSubmitting.value = false
  }
}

async function removeItem(row: DictionaryItem): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除字典项「${row.item_name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDictionaryItem(row.id)
    ElMessage.success('字典项已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-row :gutter="12">
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>
            <div class="table-toolbar">
              <span class="page-title">公共字典</span>
              <span class="table-toolbar__spacer" />
              <el-button type="primary" @click="openCreateDict">新增字典</el-button>
            </div>
          </template>
          <el-table
            v-loading="loading"
            :data="dictionaries"
            border
            size="small"
            highlight-current-row
            :current-row-key="selectedId"
            row-key="id"
            @row-click="selectDict"
          >
            <el-table-column label="字典编码" prop="dict_code" min-width="140" />
            <el-table-column label="字典名称" prop="dict_name" min-width="140" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <el-table-column label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click.stop="openEditDict(row)">编辑</el-button>
              </template>
            </el-table-column>
            <template #empty>暂无字典数据</template>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="table-toolbar">
              <span class="page-title">
                字典项{{ selectedDict ? ` · ${selectedDict.dict_name}` : '' }}
              </span>
              <span class="table-toolbar__spacer" />
              <el-button type="primary" :disabled="!selectedDict" @click="openCreateItem">新增字典项</el-button>
            </div>
          </template>
          <el-table :data="selectedDict?.items ?? []" border size="small">
            <el-table-column label="编码" prop="item_code" min-width="130" />
            <el-table-column label="名称" prop="item_name" min-width="130" />
            <el-table-column label="值" prop="item_value" min-width="120" />
            <el-table-column label="排序" prop="sort_no" width="80" align="right" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEditItem(row)">编辑</el-button>
                <el-button link type="danger" @click="removeItem(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>请选择字典后查看字典项</template>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="dictDialogVisible" :title="editingDictId === null ? '新增字典' : '修改字典'" width="520px">
      <el-form ref="dictFormRef" :model="dictForm" :rules="dictRules" label-width="90px">
        <el-form-item label="字典编码" prop="dict_code">
          <el-input v-model="dictForm.dict_code" :disabled="editingDictId !== null" />
        </el-form-item>
        <el-form-item label="字典名称" prop="dict_name">
          <el-input v-model="dictForm.dict_name" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="dictForm.status" style="width: 100%">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="INACTIVE" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dictForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dictDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="dictSubmitting" @click="submitDict">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="itemDialogVisible" :title="editingItemId === null ? '新增字典项' : '修改字典项'" width="520px">
      <el-form ref="itemFormRef" :model="itemForm" :rules="itemRules" label-width="110px">
        <el-form-item label="字典项编码" prop="item_code">
          <el-input v-model="itemForm.item_code" :disabled="editingItemId !== null" />
        </el-form-item>
        <el-form-item label="字典项名称" prop="item_name">
          <el-input v-model="itemForm.item_name" />
        </el-form-item>
        <el-form-item label="字典项值">
          <el-input v-model="itemForm.item_value" />
        </el-form-item>
        <el-form-item label="排序号">
          <el-input-number v-model="itemForm.sort_no" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="itemForm.status" style="width: 100%">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="INACTIVE" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="itemSubmitting" @click="submitItem">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>