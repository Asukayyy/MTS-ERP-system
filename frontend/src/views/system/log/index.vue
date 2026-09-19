<script setup lang="ts">
import { onMounted } from 'vue'

import { listOperationLogs } from '@/api/system'
import { usePagedTable } from '@/composables/usePagedTable'
import type { OperationLog } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<
    OperationLog,
    { module: string; action: string; target_type: string; target_id: number | undefined }
  >((params) => listOperationLogs(params), {
    module: '',
    action: '',
    target_type: '',
    target_id: undefined,
  })

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">操作日志</span>
        </div>
      </template>

      <el-form class="filter-bar" :inline="true" @submit.prevent>
        <el-form-item label="模块">
          <el-select v-model="query.module" clearable placeholder="全部" style="width: 140px">
            <el-option label="system" value="system" />
            <el-option label="sales" value="sales" />
            <el-option label="planning" value="planning" />
            <el-option label="procurement" value="procurement" />
            <el-option label="inventory" value="inventory" />
          </el-select>
        </el-form-item>
        <el-form-item label="动作">
          <el-select v-model="query.action" clearable placeholder="全部" style="width: 130px">
            <el-option label="CREATE" value="CREATE" />
            <el-option label="UPDATE" value="UPDATE" />
            <el-option label="STATUS" value="STATUS" />
            <el-option label="DELETE" value="DELETE" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标类型">
          <el-input v-model="query.target_type" placeholder="如 sys_material" clearable style="width: 170px" />
        </el-form-item>
        <el-form-item label="目标ID">
          <el-input-number v-model="query.target_id" :min="0" :controls="false" style="width: 120px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border size="small">
        <el-table-column label="时间" prop="created_at" min-width="180" />
        <el-table-column label="模块" prop="module" width="110" />
        <el-table-column label="动作" prop="action" width="110" />
        <el-table-column label="目标类型" prop="target_type" min-width="150" />
        <el-table-column label="目标ID" prop="target_id" width="90" align="right" />
        <el-table-column label="操作人ID" prop="operator_id" width="100" align="right" />
        <el-table-column label="详情" prop="detail" min-width="240" show-overflow-tooltip />
        <template #empty>暂无操作日志</template>
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
  </div>
</template>