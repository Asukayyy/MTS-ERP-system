<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { changePassword, listPersonnel } from '@/api/system'
import RemoteSelect from '@/components/common/RemoteSelect.vue'
import { useCurrentOperator } from '@/composables/useCurrentOperator'
import { useAppStore } from '@/stores/modules/app'
import type { RemoteOption } from '@/types/erp'
import { clearAuth, getAuth } from '@/utils/auth'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const { currentOperator, clearOperator, setOperator } = useCurrentOperator()

/** 已加载过的选项 id -> 文案，用于选中时回填姓名（RemoteSelect 的 change 只给出 id） */
const optionLabels = new Map<number, string>()

/** 复用系统人员接口，与库存各页面"操作人"下拉框保持一致 */
async function loadOperatorOptions(keyword: string): Promise<RemoteOption[]> {
  const data = await listPersonnel({ keyword, page: 1, page_size: 50 })
  const options = data.items.map((item) => ({ id: item.id, label: `${item.employee_no} ${item.person_name}` }))
  options.forEach((option) => optionLabels.set(option.id, option.label))
  // 刷新后当前操作人可能不在首屏列表内，补进选项以便下拉框正确回显姓名
  const current = currentOperator.value
  if (!keyword && current && !options.some((option) => option.id === current.id)) {
    options.unshift({ id: current.id, label: current.name || `操作人 #${current.id}` })
  }
  return options
}

function onOperatorChange(value: number | undefined): void {
  if (value === undefined) {
    clearOperator()
    return
  }
  setOperator({ id: value, name: optionLabels.get(value) ?? '' })
}

const loginUser = ref(getAuth())

function logout(): void {
  clearAuth()
  loginUser.value = null
  ElMessage.success('已退出登录')
  router.replace('/login')
}

// ---------------- 修改密码 ----------------
const pwdVisible = ref(false)
const pwdSubmitting = ref(false)
const pwdFormRef = ref<FormInstance>()
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })

const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度需为 6~64 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        callback(value === pwdForm.new_password ? undefined : new Error('两次输入的新密码不一致'))
      },
      trigger: 'blur',
    },
  ],
}

function openPasswordDialog(): void {
  Object.assign(pwdForm, { old_password: '', new_password: '', confirm: '' })
  pwdFormRef.value?.clearValidate()
  pwdVisible.value = true
}

async function submitPassword(): Promise<void> {
  const valid = await pwdFormRef.value?.validate().catch(() => false)
  if (!valid) return
  pwdSubmitting.value = true
  try {
    await changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    ElMessage.success('密码已修改，下次登录请使用新密码')
    pwdVisible.value = false
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    pwdSubmitting.value = false
  }
}
</script>

<template>
  <div class="app-header">
    <el-button link type="primary" @click="appStore.toggleSidebar()">
      {{ appStore.sidebarCollapsed ? '展开菜单' : '收起菜单' }}
    </el-button>

    <span class="app-header__title">{{ route.meta.title ?? '' }}</span>

    <div class="app-header__right">
      <span class="app-header__operator-label">当前操作人</span>
      <RemoteSelect
        :model-value="currentOperator?.id ?? undefined"
        :loader="loadOperatorOptions"
        placeholder="请选择当前操作人"
        style="width: 220px"
        @change="onOperatorChange"
      />
      <template v-if="loginUser">
        <span class="app-header__role">
          {{ (loginUser.roles ?? []).map((item) => item.role_name).filter(Boolean).join('、') || '未分配角色' }}
        </span>
        <span class="app-header__user">{{ loginUser.user.display_name || loginUser.user.username }}</span>
        <el-button link type="primary" @click="openPasswordDialog">修改密码</el-button>
        <el-button link type="danger" @click="logout">退出</el-button>
      </template>
      <el-tag v-else type="info" effect="plain">未登录</el-tag>
    </div>

    <el-dialog v-model="pwdVisible" title="修改密码" width="420px">
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="6~64 位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSubmitting" @click="submitPassword">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 0 16px;
}

.app-header__title {
  font-size: 15px;
  font-weight: 600;
}

.app-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.app-header__operator-label {
  font-size: 13px;
  color: #606266;
}

.app-header__role {
  color: #909399;
  font-size: 12px;
}

.app-header__user {
  font-weight: 600;
}
</style>
