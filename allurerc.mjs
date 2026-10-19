export default {
  name: "interface-auto 接口自动化测试报告",
  plugins: {
    awesome: {
      options: {
        reportLanguage: "zh",   // 报告 UI 默认中文
        singleFile: true,       // 生成单文件 HTML，便于 Jenkins 归档与直接打开
      },
    },
  },
};
