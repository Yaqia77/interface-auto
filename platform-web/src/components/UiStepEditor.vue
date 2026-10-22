<script setup lang="ts">
/**
 * UI 步骤编辑器：动作下拉（中文标签来自后端 /api/ui-cases/meta 的 actions 字典）
 * + 定位器输入 + 取值输入（可插入 {{变量}} chip）+ 步骤备注。
 * 是否需要定位器/取值由动作字典 need_locator/need_value 驱动，与后端校验同源；
 * 本组件只做编辑与结构化，最终合法性仍由后端落盘那一刻校验兜底。
 */
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { UiActionMeta, UiStep } from "../types";

const props = defineProps<{
  modelValue: UiStep[];
  actions: UiActionMeta[];
  variables?: string[];
}>();
const emit = defineEmits<{ (e: "update:modelValue", v: UiStep[]): void }>();

/** 编辑态行：value 一律以字符串承载（12 个动作的取值均为文本/路径），保存时透传字符串 */
interface StepRow {
  action: string;
  locator: string;
  value: string;
  desc: string;
}

const metaOf = (action: string) => props.actions.find((a) => a.action === action);
const needLocator = (action: string) => metaOf(action)?.need_locator ?? false;
const needValue = (action: string) => metaOf(action)?.need_value ?? false;
const isExpect = (action: string) => action.startsWith("expect_");

const LOC_PH = "定位器，如 #username / css=.btn / xpath=//div / role=button,name=登录";
const VAL_PH = "取值，支持 {{变量}} 引用";

const toRow = (s: UiStep): StepRow => ({
  action: s.action ?? "",
  locator: s.locator == null ? "" : String(s.locator),
  value: s.value == null ? "" : String(s.value),
  desc: s.desc ?? "",
});

/** 行 → 提交结构：仅带该动作需要的字段，空的可选项省略（与后端 _validate_step 口径一致） */
const toStep = (r: StepRow): UiStep => {
  const s: UiStep = { action: r.action };
  const loc = r.locator.trim();
  if (loc) s.locator = loc;
  const val = r.value;
  if (needValue(r.action)) s.value = val.trim();
  else if (val.trim()) s.value = val.trim();
  if (r.desc.trim()) s.desc = r.desc.trim();
  return s;
};

const rows = reactive<StepRow[]>([]);

// 外部模型 → 内部行：仅在结构真正变化时同步，避免回填触发写入循环
watch(
  () => props.modelValue,
  (v) => {
    const next = (v ?? []).map(toRow);
    if (JSON.stringify(next) !== JSON.stringify(rows)) rows.splice(0, rows.length, ...next);
  },
  { immediate: true, deep: true }
);

// 内部行 → 外部模型
watch(rows, () => emit("update:modelValue", rows.map(toStep)), { deep: true });

function addStep() {
  rows.push({ action: "goto", locator: "", value: "", desc: "" });
}
function removeStep(i: number) {
  rows.splice(i, 1);
}
function moveStep(i: number, dir: -1 | 1) {
  const j = i + dir;
  if (j < 0 || j >= rows.length) return;
  const t = rows[i];
  rows[i] = rows[j];
  rows[j] = t;
}

// 变量 chip 插入：先聚焦某步取值框，再点变量标签把 {{name}} 追加进去
const focusRow = ref(-1);
function insertVar(name: string) {
  if (focusRow.value < 0 || focusRow.value >= rows.length) {
    ElMessage.warning("请先点击某一步的取值框，再点变量标签插入");
    return;
  }
  rows[focusRow.value].value += `{{${name}}}`;
}

// 变量 chip 展示文本：在脚本里拼接，避免模板 {{ }} 字面量干扰解析
const varChip = (v: string) => "{{" + v + "}}";
</script>

<template>
  <div class="ui-step-editor">
    <div v-for="(r, i) in rows" :key="i" class="step-card">
      <div class="step-head">
        <span class="step-no">{{ i + 1 }}</span>
        <el-select v-model="r.action" placeholder="选择动作" style="width: 180px" size="default">
          <el-option v-for="a in actions" :key="a.action" :value="a.action" :label="`${a.desc}（${a.action}）`">
            <span class="opt-key">{{ a.desc }}</span>
            <span class="opt-val mono">{{ a.action }}</span>
          </el-option>
        </el-select>
        <span v-if="isExpect(r.action)" class="expect-tag">断言：期望值不满足即该步失败并中断</span>
        <div class="step-ops">
          <el-button text size="small" :disabled="i === 0" @click="moveStep(i, -1)">↑</el-button>
          <el-button text size="small" :disabled="i === rows.length - 1" @click="moveStep(i, 1)">↓</el-button>
          <el-button text size="small" type="danger" @click="removeStep(i)">✕ 删除</el-button>
        </div>
      </div>

      <div class="step-body">
        <el-input
          v-if="needLocator(r.action) || r.locator"
          v-model="r.locator"
          :placeholder="LOC_PH"
          class="mono"
          clearable
        >
          <template #prepend>定位器</template>
        </el-input>
        <el-input
          v-if="needValue(r.action) || r.value"
          v-model="r.value"
          :placeholder="VAL_PH"
          class="mono"
          @focus="focusRow = i"
        >
          <template #prepend>取值</template>
        </el-input>
        <el-input v-model="r.desc" placeholder="步骤备注（选填，仅展示用）" clearable>
          <template #prepend>备注</template>
        </el-input>
      </div>
    </div>

    <el-button size="small" type="primary" plain @click="addStep">＋ 添加步骤</el-button>

    <div class="hint" style="margin: 10px 0 0">
      定位器前缀：<span class="mono">css=</span>（默认，可省略）/ <span class="mono">xpath=</span> /
      <span class="mono">text=</span> / <span class="mono">role=button,name=登录</span>；
      <span class="mono">goto</span> 的取值填相对路径（自动拼环境 base_url）或完整 URL。
    </div>
    <div v-if="variables?.length" class="var-chips">
      <span class="hint" style="margin:0;line-height:22px">点变量插入到聚焦的取值框：</span>
      <el-tag v-for="v in variables" :key="v" size="small" class="var-chip" @click="insertVar(v)">{{ varChip(v) }}</el-tag>
    </div>
  </div>
</template>

<style scoped>
.ui-step-editor { display: flex; flex-direction: column; gap: 10px; }
.step-card { border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px 12px; background: #fafbfc; }
.step-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.step-no { flex: 0 0 auto; width: 22px; height: 22px; line-height: 22px; text-align: center; border-radius: 50%; background: #409eff; color: #fff; font-size: 12px; }
.step-ops { margin-left: auto; display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.expect-tag { color: #e6a23c; font-size: 12px; }
.step-body { display: flex; flex-direction: column; gap: 8px; }
.mono { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.hint { color: #909399; font-size: 12px; }
.opt-key { float: left; }
.opt-val { float: right; color: #a0a4a8; margin-left: 16px; }
.var-chips { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.var-chip { cursor: pointer; font-family: Consolas, Monaco, monospace; }
</style>
