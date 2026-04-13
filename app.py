import streamlit as st
import os
import json
import datetime
import urllib.request

# ── 页面配置 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 漫剧视频提示词生成器",
    page_icon="🎬",
    layout="wide"
)

# ── DeepSeek API 配置 ────────────────────────────────────────────
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# ── 景别衔接规则 ────────────────────────────────────────────────
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
  30度原则：连续拍同一主体时，相邻镜头机位角度差必须 ≥30°，且 ≤180°。
  动作匹配：一个动作拆为"起势"和"落势"，前镜头保留起势后半段，后镜头接落势前半段。

时长控制：每个镜头时长尽量不超过3秒。
"""

# ── 调用 DeepSeek ───────────────────────────────────────────────
def call_deepseek(prompt, api_key):
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

# ── 分析小说 ────────────────────────────────────────────────────
def analyze_novel(novel_text, style, api_key):
    prompt = f"""你是一位专业的影视制作人，擅长将文学文本转化为视觉化内容。

请阅读以下小说文本，用 JSON 格式提取关键信息：

【小说文本】
{novel_text}

输出要求（严格 JSON 格式，不要添加任何其他文字）：
{{
  "characters": [
    {{"name": "角色名", "appearance": "外貌关键词", "personality": "性格标签", "outfit": "服装描述"}}
  ],
  "scenes": [
    {{"location": "地点名", "environment": "环境描述", "time": "时间段"}}
  ],
  "story_beats": ["片段1的一句话情节概括", "片段2..."],
  "overall_mood": "整体情绪基调",
  "suggested_clips": {{"count": 3, "reason": "理由"}}
}}

story_beats 的数量请根据故事节奏合理划分，生成 {style} 风格下的分析。"""

    raw = call_deepseek(prompt, api_key)
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return {"raw_analysis": raw}

# ── 生成视频提示词 ──────────────────────────────────────────────
def generate_prompts(novel_text, analysis, style, clip_count, api_key):
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
所有提示词使用中文。

【原始小说】
{novel_text}

【小说分析】
角色信息：
{chars_str}

整体情绪基调：{mood}

情节节点：
{beats_str}

【输出格式 - 每个片段严格按此格式】

========== 片段 N ==========
【对应情节】一句话概括
【景别衔接验证】上一片段景别 → 本片段景别（合规说明）

【镜头】景别 + 运镜方式，时长 X 秒（≤3秒）
【机位】角度描述（与上镜头角度差≥30°）

【画面提示词】
（镜头动态+主体动作+场景环境+光影风格，具体描述物理细节）

【起始状态】片段开始时的状态
【结束状态】片段结束时的状态

【情绪节奏】情绪 / 节奏
【台词】有则写，无则写"无"
【音效提示】环境音、动作音

【负向提示】模糊、画面变形、人体结构异常、手指扭曲、低画质、水印、文字
==============================

注意：
1. 每个片段时长 ≤3 秒
2. 相邻片段景别必须隔一级
3. 机位角度差 ≥30° 且 ≤180°
4. 只描述具体视觉元素，禁止抽象词
5. 现在请生成 {clip_count} 个片段，风格为"{style}"
"""
    return call_deepseek(prompt, api_key)

# ── 主界面 ──────────────────────────────────────────────────────
st.title("🎬 AI 漫剧视频提示词生成器")
st.caption("专为即梦插件优化 · 严格遵守景别衔接规则")

st.divider()

# 左右两栏布局
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("输入设置")

    # API Key 输入（部署到云上时用这里输入，本地也可以用环境变量）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "DeepSeek API Key",
            type="password",
            placeholder="sk-xxxxxxxx",
            help="输入你的 DeepSeek API Key，不会被保存"
        )

    novel_text = st.text_area(
        "粘贴小说文本",
        height=250,
        placeholder="在这里粘贴你的小说内容，支持几十字到几千字..."
    )

    col1, col2 = st.columns(2)
    with col1:
        style = st.selectbox(
            "视觉风格",
            ["现代都市", "中国古风", "赛博朋克", "奇幻", "民国", "悬疑惊悚"]
        )
    with col2:
        auto_count = max(3, min(12, len(novel_text) // 250)) if novel_text else 5
        clip_count = st.slider("片段数量", min_value=3, max_value=12, value=auto_count)

    generate_btn = st.button("🚀 生成提示词", type="primary", use_container_width=True)

with col_right:
    st.subheader("生成结果")

    if generate_btn:
        if not api_key:
            st.error("请先输入 DeepSeek API Key")
        elif not novel_text.strip():
            st.error("请先输入小说文本")
        else:
            with st.spinner("第一步：正在分析小说内容..."):
                analysis = analyze_novel(novel_text, style, api_key)

            with st.spinner("第二步：正在生成视频提示词..."):
                result = generate_prompts(novel_text, analysis, style, clip_count, api_key)

            st.success("生成完毕！")

            # 显示结果
            st.text_area("提示词内容（可直接复制）", value=result, height=500)

            # 下载按钮
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📥 下载 TXT 文件",
                data=result.encode("utf-8"),
                file_name=f"video_prompts_{now}.txt",
                mime="text/plain",
                use_container_width=True
            )
    else:
        st.info("填写左侧信息后，点击「生成提示词」按钮")
        st.markdown("""
**使用说明：**
1. 粘贴小说文本
2. 选择视觉风格和片段数量
3. 点击生成
4. 将【画面提示词】复制到即梦插件
5. 将【负向提示】复制到即梦负向输入框
6. 【起始/结束状态】配合即梦首尾帧功能使用
        """)
