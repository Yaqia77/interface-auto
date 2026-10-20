<script setup lang="ts">
/**
 * 用户管理（仅 admin 可见/可访问）：账号增删改 + 角色分配 + 启停 + 重置密码。
 * 角色权限矩阵由后端 authz.PERMISSIONS 定义，本页只做只读展示。
 */
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import { currentUser } from "../stores/auth";
import type { UserInfo } from "../types";

const users = ref<UserInfo[]>([]);
const loading = ref(false);

const ROLE_OPTIONS = [
  { value: "admin", label: "管理员 Admin" },
  { value: "tl", label: "测试负责人 TL" },
  { value: "qa", label: "测试工程师 QA" },
  { value: "dev", label: "开发 Dev" },
  { value: "viewer", label: "只读访客 Viewer" },
];
const roleName = (r: string) => ROLE_OPTIONS.find((o) => o.value === r)?.label ?? r;

/** 角色权限矩阵说明（与设计文档一致，前端静态展示） */
const PERM_MATRIX: Record<string, string[]> = {
  admin: ["全部权限（含用户管理）"],
  tl: ["用例/场景/执行/报告删除", "环境·凭证·通知·定时任务管理"],
  qa: ["用例编辑与导入", "场景管理", "触发执行"],
  dev: ["只读查看 + 触发执行"],
  viewer: ["全站只读"],
};

async function load() {
  loading.value = true;
  try {
    users.value = await api.listUsers();
  } finally {
    loading.value = false;
  }
}
onMounted(load);

/* ---------- 新建/编辑 ---------- */
const dialog = ref(false);
const mode = ref<"create" | "edit">("create");
const saving = ref(false);
const editTarget = ref("");
const form = reactive({ username: "", password: "", display_name: "", role: "qa", enabled: true });

function openCreate() {
  mode.value = "create";
  editTarget.value = "";
  Object.assign(form, { username: "", password: "", display_name: "", role: "qa", enabled: true });
  dialog.value = true;
}

function openEdit(u: UserInfo) {
  mode.value = "edit";
  editTarget.value = u.username;
  Object.assign(form, {
    username: u.username, password: "", display_name: u.display_name,
    role: u.role, enabled: u.enabled,
  });
  dialog.value = true;
}

async function save() {
  if (!form.username.trim()) {
    ElMessage.warning("用户名不能为空");
    return;
  }
  saving.value = true;
  try {
    if (mode.value === "create") {
      if (form.password.length < 6) {
        ElMessage.warning("密码至少 6 位");
        saving.value = false;
        return;
      }
      await api.createUser({
        username: form.username.trim(), password: form.password,
        display_name: form.display_name, role: form.role,
      });
      ElMessage.success("用户已创建");
    } else {
      const body: Record<string, unknown> = {
        display_name: form.display_name, role: form.role, enabled: form.enabled,
      };
      if (form.password) body.password = form.password;
      await api.updateUser(editTarget.value, body);
      ElMessage.success("用户已更新");
    }
    dialog.value = false;
    load();
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false;
  }
}

async function remove(u: UserInfo) {
  try {
    await ElMessageBox.confirm(
      `确认删除用户「${u.display_name || u.username}」？`, "删除用户",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
    await api.deleteUser(u.username);
    ElMessage.success("已删除");
    load();
  } catch { /* 取消或拦截器已提示 */ }
}

const isSelf = (u: UserInfo) => u.username === currentUser.value?.username;
const dialogTitle = computed(() => (mode.value === "create" ? "新建用户" : `编辑用户：${editTarget.value}`));
</script>

<template>
  <div>
    <div class="page-header">
      <span class="page-title">共 {{ users.length }} 个账号 · 权限矩阵见右侧说明</span>
      <el-button type="primary" @click="openCreate">+ 新建用户</el-button>
    </div>

    <el-row :gutter="12">
      <el-col :span="17">
        <el-table v-loading="loading" :data="users" size="small" border>
          <el-table-column label="用户名" min-width="120">
            <template #default="{ row }">
              <span class="mono">{{ row.username }}</span>
              <el-tag v-if="isSelf(row)" size="small" type="success" effect="plain" style="margin-left: 6px">当前</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="display_name" label="姓名" min-width="120" />
          <el-table-column label="角色" width="140">
            <template #default="{ row }">
              <el-tag size="small" :type="row.role === 'admin' ? 'danger' : 'info'">{{ row.role_name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.enabled ? 'success' : 'warning'">
                {{ row.enabled ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="150">
            <template #default="{ row }">{{ (row.updated_at ?? "").replace("T", " ").slice(0, 16) || "—" }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" text type="danger" :disabled="isSelf(row) || row.username === 'admin'" @click="remove(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-col>

      <el-col :span="7">
        <el-card shadow="never" class="perm-card">
          <template #header><b>角色权限矩阵</b></template>
          <div v-for="r in ROLE_OPTIONS" :key="r.value" class="perm-row">
            <el-tag size="small" :type="r.value === 'admin' ? 'danger' : 'info'" effect="plain">{{ r.label }}</el-tag>
            <ul>
              <li v-for="p in PERM_MATRIX[r.value]" :key="p">{{ p }}</li>
            </ul>
          </div>
          <el-alert type="warning" :closable="false" style="margin-top: 10px">
            默认账号密码为初始化播种值，生产部署请立即重置。
          </el-alert>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="dialog" :title="dialogTitle" width="460px">
      <el-form label-width="88px" @submit.prevent>
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" :disabled="mode === 'edit'" placeholder="登录账号，如 zhangsan" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.display_name" placeholder="显示名（可选）" maxlength="30" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="mode === 'edit' ? '重置密码' : '密码'" :required="mode === 'create'">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="mode === 'edit' ? '留空表示不修改' : '至少 6 位'"
          />
        </el-form-item>
        <el-form-item v-if="mode === 'edit'" label="启用">
          <el-switch v-model="form.enabled" :disabled="isSelf({ username: form.username } as UserInfo)" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.page-title { font-size: 13px; color: #909399; }
.mono { font-family: Consolas, Monaco, monospace; }
.perm-card { font-size: 12px; }
.perm-row { margin-bottom: 10px; }
.perm-row ul { margin: 6px 0 0; padding-left: 18px; color: #606266; line-height: 1.7; }
</style>
