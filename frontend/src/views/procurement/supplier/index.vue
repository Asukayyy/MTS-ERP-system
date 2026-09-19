<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createSupplier, listSuppliers, setSupplierStatus, updateSupplier } from '@/api/procurement'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Supplier } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Supplier, { keyword: string; status: string }>((params) => listSuppliers(params), {
    keyword: '',
    status: '',
  })

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<{
  supplier_code: string
  supplier_name: string
  contact_person: string
  phone: string
  email: string
  address: string
  remark: string
}>({
  supplier_code: '',
  supplier_name: '',
  contact_person: '',
  phone: '',
  email: '',
  address: '',
  remark: '',
})

const rules: FormRules = {
  supplier_code: [{ required: true, message: '请输入供应商编码', trigger: 'blur' }],
  supplier_name: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }],
}

function openCreate(): void {
  editingId.value = null
  Object.assign(form, {
    supplier_code: '',
    supplier_name: '',
    contact_person: '',
    phone: '',
    email: '',
    address: '',
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: Supplier): void {
  editingId.value = row.id
  Object.assign(form, {
    supplier_code: row.supplier_code,
    supplier_name: row.supplier_name,
    contact_person: row.contact_person ?? '',
    phone: row.phone ?? '',
    email: row.email ?? '',
    address: row.address ?? '',
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  const payload = {
    supplier_code: form.supplier_code,
    supplier_name: form.supplier_name,
    contact_person: form.contact_person || null,
    phone: form.phone || null,
    email: form.email || null,
    address: form.address || null,
    remark: form.remark || null,
  }
  try {
    if (editingId.value === null) {
      await createSupplier(payload)
      ElMessage.success('供应商已新增')
    } else {
      await updateSupplier(editingId.value, payload)
      ElMessage.success('供应商已更新')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: Supplier): Promise<void> {
  const next = row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'
  try {
    await setSupplierStatus(row.id, next)
    ElMessage.success(next === 'ACTIVE' ? '供应商已启用' : '供应商已停用')
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
          <span class="page-title">供应商</span>
          <span class="table-toolbar__spacer" />
          <el-button type="primary" @click="openCreate">新增供应商</el-button>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="关键词">
          <el-input v-model="query.keyword" placeholder="编码 / 名称 / 联系人" clearable style="width: 220px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="INACTIVE" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="供应商编码" prop="supplier_code" min-width="130" />
        <el-table-column label="供应商名称" prop="supplier_name" min-width="180" />
        <el-table-column label="联系人" prop="contact_person" min-width="100" />
        <el-table-column label="联系电话" prop="phone" min-width="130" />
        <el-table-column label="邮箱" prop="email" min-width="160" />
        <el-table-column label="地址" prop="address" min-width="180" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.status === 'ACTIVE' ? 'danger' : 'success'" @click="toggleStatus(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无供应商数据</template>
      </el-table>

      <div class="pager">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="changePage"
          @size-change="changeSize"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId === null ? '新增供应商' : '编辑供应商'" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="供应商编码" prop="supplier_code">
          <el-input v-model="form.supplier_code" placeholder="如 SUP0001" />
        </el-form-item>
        <el-form-item label="供应商名称" prop="supplier_name">
          <el-input v-model="form.supplier_name" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="form.contact_person" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.address" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>