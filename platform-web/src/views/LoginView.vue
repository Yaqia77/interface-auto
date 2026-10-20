<script setup lang="ts">
/**
 * 登录页：用户名 + 密码，成功后按 redirect 回跳。
 * 默认账号由后端首次启动播种（admin/tl/qa/dev/viewer），生产部署需改密。
 */
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { login } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const submitting = ref(false);

const form = reactive({ username: "", password: "" });
const formRef = ref();
const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

async function submit() {
  const ok = await formRef.value?.validate().catch(() => false);
  if (!ok) return;
  submitting.value = true;
  try {
    const user = await login(form.username.trim(), form.password);
    ElMessage.success(`欢迎回来，${user.display_name || user.username}`);
    const redirect = (route.query.redirect as string) || "/dashboard";
    router.replace(redirect);
  } catch {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="always">
      <div class="login-logo">● Interface Auto 测试平台</div>
      <div class="login-sub">Excel 驱动接口自动化 · 企业级测试管理与执行</div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent="submit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" clearable autofocus @keyup.enter="submit" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="submitting" @click="submit">登 录</el-button>
      </el-form>

      <el-alert type="info" :closable="false" class="login-tip">
        <div>默认角色账号（首次启动播种，生产请立即改密）：</div>
        <div class="mono">admin/admin123 · tl/tl123 · qa/qa123 · dev/dev123 · viewer/viewer123</div>
      </el-alert>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2b3e 0%, #2c405c 55%, #409eff 100%);
}
.login-card { width: 400px; border-radius: 10px; padding: 8px 12px; }
.login-logo { font-size: 18px; font-weight: 600; color: #1f2b3e; text-align: center; }
.login-sub { font-size: 12px; color: #909399; text-align: center; margin: 8px 0 22px; }
.login-btn { width: 100%; margin-top: 4px; }
.login-tip { margin-top: 18px; font-size: 12px; line-height: 1.7; }
.mono { font-family: Consolas, Monaco, monospace; word-break: break-all; }
</style>
