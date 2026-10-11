#!/usr/bin/env python3
"""为蒸馏产物创建 Skill 骨架。

用法:
    python init_skill.py <skill-name> --path <目标目录> [--with references scripts assets] [--force]

只建目录 + 一个带 frontmatter 的 SKILL.md 存根，不放示例垃圾文件。
存根里的 [待填写] 需要由你替换成真实内容，交付前必须清干净。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWED_SUBDIRS = ("references", "scripts", "assets")

STUB = """---
name: {name}
description: "待填写：教哪门课。当用户说『我要学 X』『讲讲 Y』『我卡在 Z』时使用。"
---

# {title}

你是这门课的老师。学员情况：[待填写：需要什么先修基础 / 学完达到什么水平]

教学风格：**讲解为主，边讲边问；每个小节配一个实战任务。**

## 教学流程

每次上课都按这个顺序走，不要跳步：

1. **定目标** — 问学员这次想学什么
2. **摸底** — 用 1–2 道**选择题**确认起点（考先修知识，不要问"你懂吗"）
3. **排路线** — 从课程地图里选出路径，说明今天走到哪、为什么这么排
4. **逐点讲授** — 每个知识点走「讲 → 问 → 确认」，确认通过才进下一个
5. **小节实战** — 讲完一小节给一个任务，做完后点评（指出用到了哪些知识点）
6. **复盘** — 复述今天学了什么、卡在哪、今天跳过了哪些作业、下次从哪继续

## 检查点怎么问

**默认出选择题**（题干 + 3–4 个选项 + 答案 + 为什么），而不是"你来说说 X"。

- 按考点选题型：辨对错 → **判断题**；选唯一答案 → **单选题**；考"记不记得全" → **多选题**
- 干扰项要踩中典型误解 —— 他选错才有信息
- 一次只出一道；答完先讲为什么对、为什么错
- 判断题的答案要对错**混着来**，不能全是"不对"
- 选择题验证不了"会不会用"，动手能力还得靠实战任务

## 实战作业怎么布置

先判断是哪一类：

- **讲述类**（用自然语言分析、拆解）→ 给三个选项：**A. 我自己做** / **B. 先看个例子**（老师用另一个同类场景讲一遍）/ **C. 跳过**（记进待补清单）
- **动手类**（写代码、改文件、配环境）→ **必须完成，不给跳过**。卡住走示范模式的交替节奏

## 示范模式

涉及写代码 / 建文件 / 配环境时，**不要用嘴描述，直接在练习目录里做出来**。

- 四步法：**说**（动哪个文件、改成什么、为什么）→ **做**（一次只动一个文件）→ **看**（让学员看 diff）→ **跑**（原样展示输出和报错）
- **老师做一段 → 学员跟一段**，不要一路做到底
- 报错不要替他修好：读给他听 → 问他怎么理解 → 定位到行 → 让他自己改

## 课程地图

见 `references/course-map.md`（阶段、先修依赖、检查点、实战任务）

## 讲课纪律

- 一次只讲一个知识点，讲完必须停下来问
- 学员说"懂了"不算确认，要让他用自己的话说一遍或做一道题
- 学员卡住时换角度重讲；连续两次讲不通，退回先修知识点
"""


def title_of(name: str) -> str:
    return " ".join(word.capitalize() for word in name.split("-"))


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="创建 Skill 骨架")
    parser.add_argument("skill_name", help="Skill 名（小写字母/数字/连字符）")
    parser.add_argument("--path", required=True, help="目标目录")
    parser.add_argument("--with", dest="subdirs", nargs="*", default=[],
                        choices=ALLOWED_SUBDIRS, help="需要一并创建的子目录")
    parser.add_argument("--force", action="store_true", help="目录已存在时覆盖 SKILL.md")
    args = parser.parse_args(argv)

    name = args.skill_name
    if not re.fullmatch(r"[a-z0-9-]+", name):
        print(f"❌ Skill 名「{name}」不合法：只能用小写字母、数字、连字符")
        return 1
    if name.startswith("-") or name.endswith("-") or "--" in name:
        print(f"❌ Skill 名「{name}」不能以连字符开头/结尾，也不能有连续连字符")
        return 1
    if len(name) > 64:
        print(f"❌ Skill 名太长（{len(name)} 字符，上限 64）")
        return 1

    skill_dir = Path(args.path).resolve() / name
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists() and not args.force:
        print(f"❌ 已存在: {skill_md}（要覆盖加 --force）")
        return 1

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(
        STUB.format(name=name, title=title_of(name)), encoding="utf-8"
    )
    print(f"✅ 已创建 {skill_md}")

    for subdir in args.subdirs:
        target = skill_dir / subdir
        target.mkdir(exist_ok=True)
        print(f"✅ 已创建 {target}")

    print("\n下一步：填写 description（必须含触发场景）→ 写正文 → 细节下沉 references/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
