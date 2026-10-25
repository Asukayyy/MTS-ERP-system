<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElTree } from 'element-plus'

import { getOrganizationTree, listPersonnel } from '@/api/system'
import StatusTag from '@/components/common/StatusTag.vue'
import { usePagedTable } from '@/composables/usePagedTable'
import type { Organization, Personnel } from '@/types/erp'

const { loading, rows, total, page, pageSize, query, load, search, reset, changePage, changeSize } =
  usePagedTable<Personnel, { keyword: string; org_id: number | undefined; status: string }>(
    (params) => listPersonnel(params),
    { keyword: '', org_id: undefined, status: '' },
  )

// ---- 左侧组织树：按组织逐层下钻查看员工 ----
const orgTree = ref<Organization[]>([])
const orgTreeRef = ref<InstanceType<typeof ElTree>>()
const expandedOrgIds = computed(() => orgTree.value.map((item) => item.id))

async function loadOrgTree(): Promise<void> {
  try {
    orgTree.value = await getOrganizationTree()
  } catch {
    orgTree.value = []
  }
}

function onOrgClick(org: Organization): void {
  query.org_id = org.id
  search()
}

function clearOrgFilter(): void {
  query.org_id = undefined
  orgTreeRef.value?.setCurrentKey(null)
  search()
}

function resetFilter(): void {
  reset()
  orgTreeRef.value?.setCurrentKey(null)
}

function genderLabel(value?: string | null): string {
  if (value === 'MALE') return '男'
  if (value === 'FEMALE') return '女'
  return '—'
}

onMounted(() => {
  load()
  loadOrgTree()
})
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span class="page-title">员工</span>
          <span class="table-toolbar__hint">员工档案由人事部维护，此处仅供查询</span>
          <span class="table-toolbar__spacer" />
        </div>
      </template>

      <div class="personnel-body">
        <aside class="org-tree">
          <div class="org-tree__title">组织架构</div>
          <el-tree
            ref="orgTreeRef"
            :data="orgTree"
            node-key="id"
            :props="{ label: 'org_name', children: 'children' }"
            :default-expanded-keys="expandedOrgIds"
            highlight-current
            :indent="18"
            @node-click="onOrgClick"
          >
            <template #default="{ data }">
              <span class="org-tree__node">
                <span>{{ data.org_name }}</span>
                <span class="org-tree__code">{{ data.org_code }}</span>
              </span>
            </template>
          </el-tree>
          <el-button link type="primary" class="org-tree__all" @click="clearOrgFilter">
            查看全部员工
          </el-button>
        </aside>

        <div class="personnel-main">
          <el-form class="filter-bar" :inline="true" @submit.prevent>
            <el-form-item label="关键字">
              <el-input
                v-model="query.keyword"
                placeholder="工号 / 姓名"
                clearable
                style="width: 180px"
                @keyup.enter="search"
              />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="query.status" clearable placeholder="全部" style="width: 120px">
                <el-option label="启用" value="ACTIVE" />
                <el-option label="停用" value="INACTIVE" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="search">查询</el-button>
              <el-button @click="resetFilter">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="loading" :data="rows" border size="small">
            <el-table-column label="工号" prop="employee_no" min-width="120" />
            <el-table-column label="姓名" prop="person_name" min-width="120" />
            <el-table-column label="性别" width="80">
              <template #default="{ row }">{{ genderLabel(row.gender) }}</template>
            </el-table-column>
            <el-table-column label="组织ID" prop="org_id" width="100" align="right" />
            <el-table-column label="岗位" prop="position" min-width="120" />
            <el-table-column label="电话" prop="phone" min-width="130" />
            <el-table-column label="邮箱" prop="email" min-width="180" show-overflow-tooltip />
            <el-table-column label="入职日期" prop="hire_date" width="120" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <template #empty>暂无员工数据</template>
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
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.personnel-body {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.org-tree {
  width: 230px;
  flex: none;
  max-height: calc(100vh - 260px);
  overflow: auto;
  padding-right: 12px;
  border-right: 1px solid #eef1f4;
}

.org-tree__title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2d3d;
}

.org-tree__node {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 13px;
}

.org-tree__code {
  font-size: 11px;
  color: #98a2ad;
}

.org-tree__all {
  margin-top: 8px;
}

.personnel-main {
  flex: 1;
  min-width: 0;
}

.table-toolbar__hint {
  margin-left: 12px;
  font-size: 12px;
  color: #98a2ad;
}

@media (max-width: 1100px) {
  .personnel-body {
    flex-direction: column;
  }

  .org-tree {
    width: 100%;
    max-height: 240px;
    padding-right: 0;
    border-right: none;
    border-bottom: 1px solid #eef1f4;
    padding-bottom: 8px;
  }
}
</style>
