# doc-flow PPT 设计方案（深色主题）

## 概述

为 doc-flow 项目创建网页版 PPT 演示文稿，采用 LangGraph 官网深色主题风格。

## 技术方案

- **实现方式**：纯 HTML/CSS，无 JS 框架依赖（仅少量原生 JS）
- **翻页机制**：CSS `scroll-snap-type: y mandatory`，每页 100vh
- **键盘导航**：JS 监听 ArrowUp/ArrowDown/Space/PageUp/PageDown，`scrollIntoView({ behavior: 'smooth' })`
- **字体加载**：Google Fonts — JetBrains Mono（离线时回退 system-ui）
- **动画触发**：IntersectionObserver 检测页面进入视口，添加 `.visible` class 触发 CSS 动画
- **目标视口**：桌面端优先（min-width 1024px），不做移动端适配
- **交付物**：单个 HTML 文件（CSS/JS 内联），存放于 `presentation/index.html`

## 视觉规范

### 色彩

| 用途 | 色值 |
|------|------|
| 背景 | `#030710` |
| 主高亮 | `#7fc8ff` |
| 次高亮 | `#006ddd` |
| 正文 | `rgba(255,255,255,0.85)` |
| 辅助文字 | `rgba(255,255,255,0.5)` |
| 卡片背景 | `rgba(255,255,255,0.05)` + `backdrop-filter: blur(10px)` |

### 字体

- **主字体**：JetBrains Mono（Google Fonts）
- **中文回退**：system-ui, "PingFang SC", "Microsoft YaHei"
- **标题**：2.5–3rem, weight 700
- **正文**：1.1–1.3rem, weight 400

### 视觉元素

- 标题文字带蓝色 `text-shadow: 0 0 20px rgba(127,200,255,0.4)` 发光
- 卡片使用玻璃态（glassmorphism）：半透明背景 + blur + 1px 半透明边框
- 页面底部固定页码指示器（圆点），当前页高亮为 `#7fc8ff`，其余 `rgba(255,255,255,0.3)`，可点击跳转
- CSS `@keyframes fadeInUp` 渐入动画（0.6s ease-out），由 IntersectionObserver 触发

## 页面结构（9页）

### 第1页 — 封面

- "doc-flow" 大标题，蓝色发光效果
- 副标题：「智能 API 文档问答与生成系统」
- 底部：Powered by LangGraph

### 第2页 — 项目简介

三张玻璃态卡片横排：
- **智能文档问答**：基于 RAG 的精准检索与回答
- **自动文档生成**：ReAct 工具循环驱动的文档创建
- **意图识别路由**：自动理解用户需求并分流处理

### 第3页 — 痛点一：文档缺失

左右分栏布局（50/50）：
- **左侧（问题）**：研发不爱写文档，文档更新不及时
- **右侧（方案）**：自动扫描代码生成文档，保持实时同步
- 左右用不同背景色区分（问题侧偏暗，方案侧带蓝色渐变边框）

### 第4页 — 痛点二：日常问题排查

左右分栏布局（50/50）：
- **左侧（场景）**：接口报错排查、功能细节询问
- **右侧（方案）**：智能问答快速定位问题根源
- 同痛点一的视觉风格

### 第5页 — 核心技术栈

三个技术卡片居中排列（纯文字 + emoji 图标，无外部图片）：
- **LangGraph**：智能编排框架
- **ChromaDB**：向量数据库
- **Chainlit**：对话界面框架

### 第6页 — 迭代方向一：知识体系扩展

三个要点：
- 核心定时任务文档化
- 消费者订阅服务梳理
- 多项目关联知识图谱

### 第7页 — 迭代方向二：多用户支持

两个要点：
- 多用户使用场景与权限隔离
- 会话保存与历史检索

### 第8页 — 迭代方向三：问答模块优化

四个要点：
- 分层知识加载（全局概览 + 精准细节）
- 项目级知识库管理
- 全局记忆设计，记录优质回答
- 重复问题快速响应

### 第9页 — 结尾

- "Thank You" 发光标题
- doc-flow — 让文档自己写自己
