#!/usr/bin/env python3
"""自检蒸馏产出的 Skill 是否符合规范。

用法:
    python validate_output.py <skill 目录>

返回 0 表示无错误（可能有警告），1 表示有错误。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}
MAX_BODY_LINES = 500
MAX_DESC_CHARS = 1024
MIN_DESC_CHARS = 40
# 只匹配真正的占位标记，不匹配「清掉占位符」这类在讲占位符的正文
PLACEHOLDER_RE = r"\[TODO|\[待填写|\[待补|\[占位|TODO:|FIXME:"

# 产出红线：不出现机构标识与版权信息。
# 只抓「硬痕迹」——URL、邮箱、电话、版权符号，这些不会出现在讲解规则的正文里，
# 因此不会误伤「不要提及官网」这类规则陈述。机构名由人工自检兜底。
# 注意：技术产品名和「DeepSeek 官方 API」这类说法是允许的，不在此列。
SOURCE_ARTIFACT_RE = re.compile(
    r"https?://[\w./?=&%#+-]+|www\.[\w.-]+|[\w.+-]+@[\w-]+\.[\w.]+|\b400-\d{3}-\d{4}\b|©|®|™"
)


def strip_code(text: str) -> str:
    """去掉围栏代码块和行内代码，避免把「讲解占位符的示例」误判成占位符。"""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def check(skill_dir: Path):
    errors: list = []
    warnings: list = []
    notes: list = []

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir} 下没有 SKILL.md"], [], []
    content = skill_md.read_text(encoding="utf-8")

    if not content.startswith("---"):
        return ["SKILL.md 开头没有 YAML frontmatter"], [], []

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if not match:
        return ["frontmatter 格式不对（缺少收尾的 ---）"], [], []

    try:
        import yaml
    except ImportError:
        return ["缺少 pyyaml，无法校验 frontmatter（pip install pyyaml）"], [], []

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return [f"frontmatter YAML 解析失败: {exc}"], [], []
    if not isinstance(meta, dict):
        return ["frontmatter 必须是键值对"], [], []

    # ---- frontmatter 字段 ----
    extra = set(meta) - ALLOWED_KEYS
    if extra:
        errors.append(
            f"frontmatter 有不该有的字段: {', '.join(sorted(extra))}；"
            f"只允许 {', '.join(sorted(ALLOWED_KEYS))}"
        )

    name = meta.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("缺少 name（或不是字符串）")
    else:
        name = name.strip()
        if not re.fullmatch(r"[a-z0-9-]+", name):
            errors.append(f"name「{name}」必须只含小写字母、数字、连字符")
        elif name.startswith("-") or name.endswith("-") or "--" in name:
            errors.append(f"name「{name}」不能以连字符开头/结尾，也不能有连续连字符")
        if len(name) > 64:
            errors.append(f"name 太长（{len(name)} 字符，上限 64）")
        if name != skill_dir.name:
            warnings.append(f"name「{name}」与目录名「{skill_dir.name}」不一致")

    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("缺少 description（或不是字符串）")
    else:
        description = description.strip()
        if len(description) > MAX_DESC_CHARS:
            errors.append(f"description 太长（{len(description)} 字符，上限 {MAX_DESC_CHARS}）")
        if "<" in description or ">" in description:
            errors.append("description 不能包含尖括号 < >")
        if len(description) < MIN_DESC_CHARS:
            warnings.append(f"description 只有 {len(description)} 字符，很可能没写清触发场景")
        if not re.search(r"当|时|使用|场景|触发|用于", description):
            warnings.append(
                "description 里看不到触发条件（如「当用户……时使用」），"
                "可能导致该触发时不触发"
            )
        if re.search(r"待填写|TODO|FIXME", description):
            warnings.append("description 还是存根占位内容，必须替换成真实描述")

    # ---- 正文 ----
    body = content[match.end():]
    body_lines = body.splitlines()
    if len(body_lines) > MAX_BODY_LINES:
        warnings.append(
            f"正文 {len(body_lines)} 行，超过 {MAX_BODY_LINES} 行建议下沉到 references/"
        )
    scan = strip_code(body)
    if re.search(PLACEHOLDER_RE, scan):
        warnings.append("正文里还残留 TODO / 占位符，交付前应清掉")
    if re.search(r"详见原文|参见原文档|如上文所述", scan):
        warnings.append("正文里出现指向原文档的表述，产物应该能独立使用")

    # ---- 内部引用链接 ----
    for target in re.findall(r"\]\(([^)\s]+)\)", body):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#", 1)[0]
        if clean and not (skill_dir / clean).exists():
            errors.append(f"引用的文件不存在: {target}")

    # ---- references/ 体检 ----
    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        refs = sorted(refs_dir.rglob("*.md"))
        for ref in refs:
            lines = ref.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > 100 and not any(
                line.lstrip().startswith("#") for line in lines[:25]
            ):
                warnings.append(f"{ref.relative_to(skill_dir)} 超过 100 行但开头没有标题/目录")
        notes.append(f"references/ 下 {len(refs)} 个文件")

    # ---- scripts/ 体检 ----
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        scripts = [p for p in scripts_dir.rglob("*") if p.is_file()]
        notes.append(f"scripts/ 下 {len(scripts)} 个文件")

    for heavy in ("assets",):
        if (skill_dir / heavy).is_dir():
            notes.append(f"{heavy}/ 已创建")

    # ---- 收集全部文本（正文 + references），供下面几项检查用 ----
    targets = [("SKILL.md", body)]
    if refs_dir.is_dir():
        for ref in sorted(refs_dir.rglob("*.md")):
            targets.append(
                (str(ref.relative_to(skill_dir)), ref.read_text(encoding="utf-8", errors="replace"))
            )
    corpus = "\n".join(strip_code(text) for _, text in targets)

    # ---- 教学 Skill 专项 ----
    is_teaching = bool(re.search(r"老师|讲师|教学|学员|课程地图", scan))
    if not is_teaching:
        # 不静默跳过 —— 让人知道这一段没跑
        notes.append(
            "未检测到教学特征词（老师/讲师/教学/学员/课程地图），"
            "已跳过教学专项检查；若这确实是教学 Skill，请检查正文措辞"
        )
    if is_teaching:
        if not re.search(r"教学流程|上课|讲课", scan):
            warnings.append("教学 Skill 里没看到明确的教学流程")
        if not re.search(r"检查点|讲.{0,6}问.{0,6}确认|复盘", scan):
            warnings.append("教学 Skill 里没看到检查点/确认环节，学员学到什么程度算会无法判定")

        # ① 检查点必须是现成的选择题
        if not re.search(r"（单选|（多选|（判断|单选题|多选题|判断题", corpus):
            warnings.append(
                "没找到任何选择题（题干后标（单选）/（多选）/（判断））—— "
                "检查点默认要写成现成的选择题，不是「你来说说 X」这种开放问法"
            )

        # ② 涉及动手的课程必须有示范模式
        if not re.search(r"示范", scan):
            warnings.append(
                "SKILL.md 里没写「示范模式」—— 课程一旦涉及写代码 / 建文件 / 配环境，"
                "老师会退化成只用嘴描述"
            )

        # ③ 实战作业要分讲述类 / 动手类
        if not re.search(r"讲述类|动手类", corpus):
            warnings.append(
                "没看到「讲述类 / 动手类」的作业分类 —— 实战作业要按类型给选项"
                "（讲述类可看示例 / 跳过，动手类必须完成）"
            )

        # ④ 课程地图
        course_map = skill_dir / "references" / "course-map.md"
        if not course_map.is_file() and not re.search(r"课程地图", scan):
            warnings.append("教学 Skill 缺课程地图（references/course-map.md），先修依赖会丢失")
        elif course_map.is_file():
            map_text = course_map.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"先修|依赖|前置", map_text):
                warnings.append("课程地图里没有先修依赖，学员会跳着学然后卡死")
            if not re.search(r"检查点|验收|完成标准", map_text):
                warnings.append("课程地图里没有检查点，无法判定学员是否学会")
        notes.append("已按教学 Skill 检查")

    # ---- 来源与标识（品牌 / 官方 / 联系方式）----
    for label, text in targets:
        # 先剥离代码块与行内代码，避免把「讲规则的正文」本身误判成来源标识
        hit = SOURCE_ARTIFACT_RE.search(strip_code(text))
        if hit:
            warnings.append(
                f"{label} 里出现来源标识「{hit.group(0)[:40]}」"
                "—— 产物不应带机构名/官网/联系方式"
            )

    return errors, warnings, notes


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    if len(sys.argv) != 2:
        print("用法: python validate_output.py <skill 目录>")
        return 1

    skill_dir = Path(sys.argv[1])
    if not skill_dir.is_dir():
        print(f"❌ 目录不存在: {skill_dir}")
        return 1

    errors, warnings, notes = check(skill_dir)

    for item in notes:
        print(f"ℹ️  {item}")
    for item in warnings:
        print(f"⚠️  {item}")
    for item in errors:
        print(f"❌ {item}")

    if errors:
        print(f"\n❌ 未通过：{len(errors)} 个错误、{len(warnings)} 个警告")
        return 1

    status = f"{len(warnings)} 个警告" if warnings else "无警告"
    print(f"\n✅ 结构检查通过（{status}）")
    print("\n还差四步人工自检（详见 SKILL.md Step 5）：")
    print("  1. 能讲吗 —— 随机抽 3 个知识点，不看原文档讲一遍；讲不出来就是提炼不够")
    print("  2. 能判吗 —— 检查点是不是现成的选择题（题干 + 选项 + 答案 + 为什么）")
    print("  3. 干净吗 —— 有没有残留机构名、官网、热线、版权字样（技术产品名要留）")
    print("  4. 触发测试 —— 写 3 条提问：正常请求 / 边缘情况 / 不应触发")
    print("\n最后给交付报告：老师 skill 在哪、怎么开始第一课、3 条测试提问是什么")
    return 0


if __name__ == "__main__":
    sys.exit(main())
