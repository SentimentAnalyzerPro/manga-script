import os
import json
import datetime
import urllib.request

# ── DeepSeek API 配置 ────────────────────────────────────────────
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
SAVE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 景别衔接规则（写入 Prompt 的核心内容）──────────────────────
SHOT_RULES = """
【专业景别衔接规则 - 必须严格遵守】

景别分级（从大到小）：远景 > 全景 > 中景 > 近景 > 特写

口诀一 - 相邻景别不硬切：
  相邻片段的景别不能只差一级，必须隔一级衔接。
  合规示例：远景→中景、全景→近景、中景→特写
  违规示例：远景→全景、全景→中景、近景→特写

口诀二 - 两极镜头不硬切：
  远景和特写跨度极大，中间必须加过渡景别（如远景→中景→特写）。
  例外：悬疑片或追求视觉冲击的场景可故意打破，但需标注"故意打破"。

口诀三 - 景别切换隔一别：
  上个片段是中景时，下个片段必须隔一级（接全景/远景，或接近景/特写）。

机位原则：
  30度原则：连续拍同一主体时，相邻镜头机位角度差必须 ≥30°，且 ≤180°（超过180°会越轴）。
  动作匹配：一个动作拆为"起势"和"落势"，前镜头保留起势后半段，后镜头接落势前半段。

时长控制：每个镜头时长尽量不超过3秒，通过改变景别和角度丰富画面。
"""

# ── 函数1：环境检查 ─────────────────────────────────────────────
def check_environment():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("错误：未找到 DEEPSEEK_API_KEY 环境变量")
        print("请在终端运行：setx DEEPSEEK_API_KEY \"你的Key\"，然后重启终端")
        exit(1)

# ── 调用 DeepSeek 的通用函数 ────────────────────────────────────
def call_deepseek(prompt):
    """向 DeepSeek API 发送请求，返回生成的文本"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    data = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()

# ── 函数2：收集用户输入 ─────────────────────────────────────────
def get_novel_input():
    print("\n========== AI 漫剧视频提示词生成器（即梦专属版）==========\n")
    print("请粘贴小说文本（粘贴完成后，在新行单独输入 END 并回车）：")

    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    novel_text = "\n".join(lines).strip()

    if not novel_text:
        print("错误：小说文本不能为空")
        exit(1)

    print(f"\n已接收文本，共 {len(novel_text)} 字")

    style = input("\n视觉风格（现代都市/中国古风/赛博朋克/奇幻，直接回车默认[现代都市]）：").strip()
    if not style:
        style = "现代都市"

    count_input = input("片段数量（直接回车自动估算，建议3-12）：").strip()
    if count_input.isdigit():
        clip_count = max(3, min(12, int(count_input)))
    else:
        clip_count = max(3, min(12, len(novel_text) // 250))
    print(f"将生成 {clip_count} 个视频片段")

    return {
        "novel_text": novel_text,
        "style": style,
        "clip_count": clip_count,
    }

# ── 函数3：第一步调用 - 分析小说 ───────────────────────────────
def analyze_novel(novel_text, style):
    prompt = f"""你是一位专业的影视制作人，擅长将文学文本转化为视觉化内容。

请阅读以下小说文本，用 JSON 格式提取关键信息：

【小说文本】
{novel_text}

输出要求（严格 JSON 格式，不要添加任何其他文字）：
{{
  "characters": [
    {{"name": "角色名", "appearance": "外貌关键词（发色/体型/气质等）", "personality": "性格标签", "outfit": "服装描述"}}
  ],
  "scenes": [
    {{"location": "地点名", "environment": "环境描述（光线/天气/氛围）", "time": "时间段"}}
  ],
  "story_beats": ["片段1的一句话情节概括", "片段2...", "..."],
  "overall_mood": "整体情绪基调（如：紧张压抑、温情治愈、热血燃烧）",
  "suggested_clips": {{"count": 3, "reason": "理由"}}
}}

story_beats 的数量请根据故事节奏合理划分，生成 {style} 风格下的分析。"""

    raw = call_deepseek(prompt)

    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return {"raw_analysis": raw}

# ── 函数4：构建核心 Prompt ──────────────────────────────────────
def build_video_prompt(novel_text, analysis, user_prefs):
    style = user_prefs["style"]
    clip_count = user_prefs["clip_count"]

    if isinstance(analysis, dict) and "characters" in analysis:
        chars = analysis["characters"]
        chars_str = "\n".join(
            f"  - {c['name']}：{c.get('appearance','')}，{c.get('personality','')}，服装：{c.get('outfit','')}"
            for c in chars
        )
        mood = analysis.get("overall_mood", "未知")
        beats = analysis.get("story_beats", [])
        beats_str = "\n".join(f"  {i+1}. {b}" for i, b in enumerate(beats))
    else:
        chars_str = "见原文"
        mood = "见原文"
        beats_str = "见原文"

    prompt = f"""你是一位专业的即梦AI视频导演，精通即梦插件的提示词写作规范。

{SHOT_RULES}

【任务】
将以下小说内容转化为 {clip_count} 个视频片段的提示词，视觉风格为"{style}"。
所有提示词使用中文，不需要英文。

【原始小说】
{novel_text}

【小说分析】
角色信息：
{chars_str}

整体情绪基调：{mood}

情节节点：
{beats_str}

【即梦提示词公式】
镜头动态 + 主体动作 + 场景环境 + 光影风格
（镜头动态必须放在最前面，即梦对开头的镜头词权重最高）

【输出格式 - 每个片段严格按此格式，不得增减字段】

========== 片段 N ==========
【对应情节】这个片段对应的故事内容（一句话）
【景别衔接验证】上一片段景别 → 本片段景别（说明是否合规，首片段写"首片段"）

【镜头】景别 + 运镜方式，时长 X 秒（≤3秒）
【机位】角度描述（与上镜头的角度差，需≥30°）

【画面提示词】
（按"镜头动态+主体动作+场景环境+光影风格"顺序，具体描述物理细节，避免"很美""很帅"等抽象词）

【起始状态】片段开始时人物和场景的状态（配合即梦首尾帧功能）
【结束状态】片段结束时人物和场景的状态

【情绪节奏】情绪 / 快/中/慢节奏
【台词】有则写台词内容，无则写"无"
【音效提示】环境音、动作音等（供剪辑参考）

【负向提示】模糊、画面变形、人体结构异常、手指扭曲、低画质、水印、文字
==============================

【示例（现代都市风格，供参考格式）】

========== 片段 1 ==========
【对应情节】沈念站在卧室门口，发现傅沉舟的秘密
【景别衔接验证】首片段，无需验证

【镜头】全景，固定机位缓慢推进，时长 3 秒
【机位】正面平视 0°

【画面提示词】
缓慢推镜头，沈念站在半开的卧室门口，手扶门框，
目光落向房间深处，表情从平静转为愕然，
卧室内光线昏暗，只有台灯投下暖黄光晕，
电影质感，高对比度，冷暖光对比，丁达尔效应

【起始状态】沈念站在门口，手扶门框，表情平静
【结束状态】沈念表情凝固，身体微微后倾

【情绪节奏】震惊压抑 / 慢节奏
【台词】无
【音效提示】安静环境音、轻微喘息声

【负向提示】模糊、画面变形、人体结构异常、手指扭曲、低画质、水印、文字
==============================

========== 片段 2 ==========
【对应情节】沈念看清照片内容，情绪爆发
【景别衔接验证】上一片段：全景 → 本片段：特写 ✓（隔一级中景，合规）

【镜头】特写，快速跟随手部甩动，时长 2 秒
【机位】正面偏上 15°（与上镜头正面差 15°，动作匹配剪辑优先）

【画面提示词】
快速跟随运镜，沈念的手将一沓照片用力甩出，
手腕细链轻微抖动，照片在空中翻转散开，
部分照片掠过镜头边缘，背景是虚化的傅沉舟惊愕面孔，
高对比度，冷暖光交织，戏剧性侧光

【起始状态】沈念手握照片，手臂抬起蓄力
【结束状态】照片全部飞散，手臂甩向身侧

【情绪节奏】愤怒爆发 / 快节奏
【台词】无
【音效提示】照片散落声、急促呼吸声

【负向提示】模糊、画面变形、人体结构异常、手指扭曲、低画质、水印、文字
==============================

【注意事项】
1. 每个片段时长 ≤3 秒
2. 相邻片段景别必须隔一级，两极镜头（远景↔特写）之间必须加过渡
3. 相邻片段机位角度差必须 ≥30° 且 ≤180°
4. 画面提示词只描述具体视觉元素，禁止写配乐、字幕等非画面内容
5. 禁止使用"很美""很帅""震撼"等抽象词，改用具体光影描述
6. 现在请为上方小说生成 {clip_count} 个片段，从片段1开始，风格为"{style}"
"""
    return prompt

# ── 函数5：第二步调用 DeepSeek - 生成视频提示词 ─────────────────
def generate_video_prompts(prompt, clip_count):
    return call_deepseek(prompt)

# ── 函数6：格式化最终输出 ───────────────────────────────────────
def format_output(raw_result, user_prefs, novel_text):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"生成时间：{now}\n"
        f"原文字数：{len(novel_text)} 字 | "
        f"片段数：{user_prefs['clip_count']} | "
        f"风格：{user_prefs['style']}\n"
        + "=" * 50 + "\n\n"
    )
    footer = (
        "\n" + "=" * 50 + "\n"
        "提示词生成完毕。\n"
        "使用建议：\n"
        "  - 将【画面提示词】直接复制粘贴到即梦插件的提示词输入框\n"
        "  - 将【负向提示】复制到即梦的负向提示词输入框\n"
        "  - 【起始状态】和【结束状态】配合即梦的首尾帧控制功能使用\n"
        "  - 【音效提示】供剪映剪辑时参考\n"
    )
    return header + raw_result + footer

# ── 函数7：保存文件 ─────────────────────────────────────────────
def save_to_file(content):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_prompts_{timestamp}.txt"
    filepath = os.path.join(SAVE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath

# ── 主流程 ──────────────────────────────────────────────────────
def main():
    check_environment()

    user_prefs = get_novel_input()

    print("\n[1/3] 正在分析小说内容...")
    analysis = analyze_novel(user_prefs["novel_text"], user_prefs["style"])

    print("[2/3] 正在生成即梦视频提示词（景别衔接规则已启用）...")
    prompt = build_video_prompt(user_prefs["novel_text"], analysis, user_prefs)
    raw_result = generate_video_prompts(prompt, user_prefs["clip_count"])

    print("[3/3] 正在整理并保存...\n")
    final_content = format_output(raw_result, user_prefs, user_prefs["novel_text"])
    filepath = save_to_file(final_content)

    print(final_content)
    print(f"文件已保存至：{filepath}")

if __name__ == "__main__":
    main()
