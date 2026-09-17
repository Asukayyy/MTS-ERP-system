<script setup lang="ts">
import { ref } from 'vue'

import { getInventoryHealth } from '@/api/inventory'
import { getPlanningHealth } from '@/api/planning'
import { getProcurementHealth } from '@/api/procurement'
import { getSalesHealth } from '@/api/sales'
import { getSystemHealth } from '@/api/system'
import type { HealthData } from '@/types/api'

interface ModuleCard {
  name: string
  path: string
  english: string
  summary: string
}

const modules: ModuleCard[] = [
  {
    name: '系统与基础信息管理',
    path: '/system',
    english: 'System',
    summary: '产品、物料、BOM、工艺路线、组织人员、用户角色权限',
  },
  {
    name: '销售管理',
    path: '/sales',
    english: 'Sales',
    summary: '客户、销售预测、销售订单、销售发货',
  },
  {
    name: '计划管理',
    path: '/planning',
    english: 'Planning',
    summary: 'MPS、MRP、生产作业计划、派工单、领料单',
  },
  {
    name: '采购管理',
    path: '/procurement',
    english: 'Procurement',
    summary: '供应商、采购计划、采购订单、到货登记',
  },
  {
    name: '库存管理',
    path: '/inventory',
    english: 'Inventory',
    summary: '仓库库位、出入库、移库盘点、实时库存',
  },
]

const checking = ref(false)
const checkResult = ref('')
const checkOk = ref(false)

/** 调用五个模块的占位健康检查接口，验证前后端连通性 */
async function checkBackend() {
  checking.value = true
  checkResult.value = ''
  checkOk.value = false

  try {
    const results: HealthData[] = await Promise.all([
      getSystemHealth(),
      getSalesHealth(),
      getPlanningHealth(),
      getProcurementHealth(),
      getInventoryHealth(),
    ])

    checkOk.value = results.every((item) => item.status === 'up')
    checkResult.value = results.map((item) => `${item.module}: ${item.status}`).join('  |  ')
  } catch (error) {
    checkResult.value = `后端未连通：${(error as Error).message}`
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <div class="dashboard">
    <el-alert
      class="dashboard__notice"
      type="warning"
      :closable="false"
      title="当前仓库只完成基础工程框架"
      description="五个模块均为占位页面，具体 ERP 业务功能尚未实现。"
    />

    <el-row :gutter="16">
      <el-col v-for="item in modules" :key="item.path" :xs="24" :sm="12" :lg="8">
        <el-card class="dashboard__card" shadow="never" @click="$router.push(item.path)">
          <template #header>
            <div class="dashboard__card-header">
              <span>{{ item.name }}</span>
              <el-tag size="small" type="info">{{ item.english }}</el-tag>
            </div>
          </template>
          <p class="dashboard__card-summary">{{ item.summary }}</p>
          <el-tag size="small" type="warning" effect="plain">功能开发中</el-tag>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="dashboard__check" shadow="never">
      <template #header>
        <span>前后端连通性自检</span>
      </template>

      <el-button type="primary" :loading="checking" @click="checkBackend">
        调用五个模块的 health 接口
      </el-button>

      <el-alert
        v-if="checkResult"
        class="dashboard__check-result"
        :type="checkOk ? 'success' : 'error'"
        :closable="false"
        :title="checkResult"
      />
    </el-card>
  </div>
</template>

<style scoped>
.dashboard__notice {
  margin-bottom: 16px;
}

.dashboard__card {
  margin-bottom: 16px;
  cursor: pointer;
}

.dashboard__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.dashboard__card-summary {
  min-height: 40px;
  margin: 0 0 12px;
  color: #606266;
}

.dashboard__check-result {
  margin-top: 16px;
}
</style>
