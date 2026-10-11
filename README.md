# distilling-docs-into-teaching-skills

把一份课程资料，蒸馏成一个**能上课的 Claude Code Skill** —— 不是一个「回答关于这门课的提问」的知识库，而是一个会讲解、会提问、会检查理解、会布置练习的老师。

给它 PDF / Word / 图片，它产出 `SKILL.md` + `course-map.md` + 各阶段讲解要点与现成题库。

---

## 它解决什么问题

Claude 本身知道很多，但**「知道」和「会教」是两回事**：

| 直接把资料丢给 Claude | 用它蒸馏出的老师 |
|---|---|
| 一口气全讲完，你不知道自己会没会 | 每个知识点停下来，出一道选择题 |
| 问「理解了吗」，你只能回「懂了」 | 干扰项踩中典型误解 —— 选错才有信息 |
| 讲代码只用嘴描述 | 在编辑器里真的做出来，你看得见 diff |
| 不知道先学什么 | 有**先修依赖图**，不会跳着学然后卡死 |
| 没有练习，看完就忘 | 每小节配实战任务，点评精确到用了哪个知识点 |

---

## 快速开始

### 1. 安装

```bash
# 放到全局 skills 目录（任何项目都能用）
git clone https://github.com/fanchangxin9-cyber/distilling-docs-into-teaching-skills ~/.claude/skills/distilling-docs-into-teaching-skills

# 装依赖
pip install -r ~/.claude/skills/distilling-docs-into-teaching-skills/requirements.txt
```

> Windows 下 `~/.claude/skills` 是 `C:\Users\<你的用户名>\.claude\skills`。

### 2. 用

在 Claude Code 里直接说：

> 把 `D:\课程\人工智能基础.pdf` 做成一个教学 skill

它会走六步：

```
Step 1  清点输入（列文件清单、确定产物放哪）
Step 2  解析成干净文本（乱码 / 扫描件自动识别）
Step 3  教学分析 —— 四个问题，产出方案给你过目 ← 会停下来等你确认
Step 4  生成老师 Skill
Step 5  自检（结构 + 教学专项 + 触发测试）
Step 6  用起来 → 反馈 → 回来改
```

---

## 产出的老师长什么样

```
你的课程老师/
├── SKILL.md                  老师人设 + 教学六段流程 + 三套机制
└── references/
    ├── course-map.md         阶段 / 先修依赖 / 检查点 / 实战任务
    └── stage-N.md            各阶段知识点 + 讲解要点 + 现成选择题
```

### 教学六段流程（每次上课固定走）

> 定目标 → 摸底 → 排路线 → 逐点讲授（**讲 → 问 → 确认**）→ 小节实战 → 复盘

### 检查点默认出选择题，按考点选题型

| 题型 | 什么时候用 |
|------|-----------|
| **判断题** | 验证一个明确认知点，或戳破一个典型误解 |
| **单选题** | 概念辨析、有唯一正确答案 |
| **多选题** | 考「记不记得全」—— 漏选本身就是信息 |

每道题的干扰项都对应一个**学员真会犯的误解**。没有误解，就出不出好题。

### 示范模式（涉及动手的课程）

写代码 / 建文件 / 配环境时，老师**不用嘴描述，直接在编辑器里做**：

> **说**（动哪个文件、改成什么、为什么）→ **做**（一次只动一个文件）→ **看**（让学员看 diff）→ **跑**（原样展示输出和报错）

节奏是 **老师做一段 → 学员跟一段**，不一路做到底。报错不替他修好，而是教他读报错。

### 实战作业按类型给选项

- **讲述类**（用自然语言分析、拆解）→ 三选一：`A. 我自己做` / `B. 先看个例子` / `C. 跳过`
- **动手类**（写代码、改文件）→ **必须完成，不给跳过** —— 看别人敲一遍和自己敲一遍是两回事

---

## 目录结构

```
.
├── SKILL.md                          主流程（六步）
├── requirements.txt
├── scripts/
│   ├── convert_to_markdown.py        PDF / Word / 图片 → markdown
│   ├── init_skill.py                 建教学 Skill 骨架
│   └── validate_output.py            产物结构 + 教学专项自检
└── references/
    ├── teaching-skill-template.md    ⭐ 教学 Skill 标准结构（核心）
    ├── distillation-rules.md         留什么、丢什么、怎么抽象
    ├── skill-authoring.md            SKILL.md 写作规范
    └── parsing-notes.md              各类文档解析的坑
```

### 两个值得单独说的技术点

**中文 PDF 乱码自动识别** —— 有些 PDF 有文字层，但嵌入字体缺少 ToUnicode 映射，抽出来全是错码（看起来是字，读起来是 `*eòe¢H:AIöã—`）。脚本会检测可疑字符占比，超过阈值就**整页渲染成图片走视觉阅读**，而不是硬洗乱码。

**自检是硬门槛** —— `validate_output.py` 会强制检查产物有没有：现成选择题的检查点、示范模式、作业分类、课程地图与先修依赖。不满足就报警告。**规范不靠文档里写几行字，靠脚本卡。**

---

## 依赖

- Python 3.9+
- `pymupdf` —— 读 PDF 与页面渲染
- `python-docx` —— 读 Word
- `pyyaml` —— 校验 frontmatter

详见 [`requirements.txt`](requirements.txt)。

---

## 相关仓库

- **[ai-agent-dev-teacher](https://github.com/fanchangxin9-cyber/ai-agent-dev-teacher)** —— 用本工具蒸馏出的一个真实产出示例（一门 AI 应用开发课的老师）。

---

## 许可证

[Apache License 2.0](LICENSE)。

本作品派生自 `qiuzhi-skill-creator`（Apache 2.0），后者派生自 Anthropic 的 `skill-creator`。
相对上游的改动清单见 [NOTICE](NOTICE)。
