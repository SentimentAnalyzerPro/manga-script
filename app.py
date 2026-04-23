import streamlit as st
import os
import json
import datetime
import urllib.request
import urllib.error
import sqlite3

# ── 页面配置 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 漫剧提示词优化器",
    page_icon="✨",
    layout="wide"
)

# ── DeepSeek API 配置 ────────────────────────────────────────────
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# ── 数据库 ───────────────────────────────────────────────────────
DB_PATH = "history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            style TEXT,
            clip_count INTEGER,
            present_characters TEXT,
            novel_text TEXT,
            result TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_history(original, result):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO history (created_at, novel_text, result) VALUES (?, ?, ?)",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), original, result)
    )
    conn.commit()
    conn.close()

def load_history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, created_at, novel_text FROM history ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return rows

def load_history_detail(record_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, created_at, novel_text, result FROM history WHERE id = ?",
        (record_id,)
    ).fetchone()
    conn.close()
    return row

def delete_history(record_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM history WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()

init_db()

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
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        if e.code == 500:
            raise RuntimeError(f"DeepSeek 服务器内部错误（500），可能是提示词过长或服务繁忙，请稍后重试。\n详情：{body[:300]}")
        elif e.code == 401:
            raise RuntimeError("API Key 无效或已过期，请检查后重新输入。")
        elif e.code == 429:
            raise RuntimeError("请求频率超限，请稍等片刻后重试。")
        else:
            raise RuntimeError(f"API 请求失败（HTTP {e.code}）：{body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络连接失败：{e.reason}，请检查网络后重试。")

# ── 优化提示词 ──────────────────────────────────────────────────
def optimize_prompts(user_prompts, api_key):
    prompt = f"""你是一位专业的即梦AI视频导演，精通即梦插件的提示词写作规范。

{SHOT_RULES}

【用户的原始提示词】
{user_prompts}

【第一步：前期分析（只用于内部推理，不输出到最终结果）】

1. 出场人物站位分析
   - 从提示词中提取所有出场人物
   - 根据剧情/动作推断每个人物在场景中的初始站位（如：A站左侧、B站右侧、C在门口等）
   - 每个片段追踪人物是否有移动，没有明确移动的人物站位保持不变

2. 景别可见人物推断
   - 对每个片段，结合景别和人物站位，判断哪些人物会出现在画面中
   - 中景镜头：根据镜头朝向和站位，画面内所有处于景深范围内的人物都应出现（不只是互动主体）
   - 近景/特写：聚焦主体，背景人物虚化或不可见
   - 全景/远景：场景内所有人物均可见

3. 景别衔接合规性检查
   - 列出每个片段景别，检查相邻片段是否违规

4. 机位角度差检查
   - 检查相邻片段机位角度差是否≥30°且≤180°

5. 时长合规性检查
   - 纯动作/过渡：1.5～3秒；有台词：字数×0.3秒（最短2秒最长6秒）；空镜：1～2秒

【第二步：输出结果】

先输出「问题诊断」部分，简要列出每个片段存在的违规点。

然后输出「优化后提示词」，每个片段严格按照以下格式，只输出以下字段，其余分析内容不写入：

========== 片段 N ==========
【镜头】景别 + 运镜方式，时长 X.X 秒
【机位】角度描述（与上镜头角度差≥30°）
【画面提示词】
镜头动态+所有出现在画面中的人物（含非互动人物）的具体动作姿态+场景环境+光影风格，全部用物理细节描述，禁止抽象词
【情绪节奏】情绪 / 节奏
【台词】有则写具体内容并注明预计时长，无则写"无"
【负向提示】模糊、画面变形、人体结构异常、手指扭曲、低画质、水印、文字
==============================

严格注意：
1. 每个片段只输出上述6个字段，不输出其他任何字段
2. 景别违规时必须调整使其合规
3. 【画面提示词】中，中景镜头必须包含站位在镜头范围内的所有人物，不能只写互动主体
4. 人物没有明确移动时，站位与上一片段保持一致，体现在【画面提示词】的位置描述中
5. 禁止出现"充满活力""气氛紧张""令人窒息"等抽象词，改为具体动作/表情/环境描述
6. 【时长严格规定】用户原始提示词中已标注的时长必须原样保留，不得修改；只有在原始提示词完全没有写时长时，才按规则自动计算
7. 【台词严格规定】用户原始提示词中的台词内容必须原样保留，一字不改；只补充台词预计时长标注（如果缺少的话）
"""
    return call_deepseek(prompt, api_key)

# ── 主界面 ──────────────────────────────────────────────────────
st.title("✨ AI 漫剧提示词优化器")
st.caption("检查并修正景别衔接、机位角度、时长计算等规则违规")

st.divider()

tab_optimize, tab_history = st.tabs(["✍️ 优化提示词", "📋 历史记录"])

# ════════════════════════════════════════════════════════════════
# Tab 1：优化提示词
# ════════════════════════════════════════════════════════════════
with tab_optimize:
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("输入")

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            api_key = st.text_input(
                "DeepSeek API Key",
                type="password",
                placeholder="sk-xxxxxxxx",
                help="输入你的 DeepSeek API Key，不会被保存"
            )

        user_prompts = st.text_area(
            "粘贴你的提示词",
            height=450,
            placeholder="把你已经写好的分镜提示词粘贴到这里，AI 会检查景别衔接、机位角度、时长等规则并给出优化版本..."
        )

        optimize_btn = st.button("🚀 开始优化", type="primary", use_container_width=True)

        st.divider()
        with st.expander("📋 查看景别衔接规则"):
            st.markdown(SHOT_RULES)

    with col_right:
        st.subheader("优化结果")

        if optimize_btn:
            if not api_key:
                st.error("请先输入 DeepSeek API Key")
            elif not user_prompts.strip():
                st.error("请先粘贴你的提示词")
            else:
                try:
                    with st.spinner("正在检查规则并优化..."):
                        result = optimize_prompts(user_prompts, api_key)

                    save_history(user_prompts, result)
                    st.success("优化完毕！已自动保存到历史记录")

                    st.text_area("优化后的提示词（可直接复制）", value=result, height=500)

                    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="📥 下载 TXT 文件",
                        data=result.encode("utf-8"),
                        file_name=f"optimized_prompts_{now}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                except RuntimeError as e:
                    st.error(str(e))
        else:
            st.info("粘贴提示词后点击「开始优化」")
            st.markdown("""
**优化内容包括：**
1. 分析所有出场人物的初始站位，未明确移动时保持不变
2. 检测景别衔接违规并修正
3. 检查机位角度差（≥30°且≤180°）
4. 精确计算每个片段时长
5. 中景镜头补全所有站位在画面内的人物，而不只是互动主体
6. 将抽象描述改为具体视觉细节
7. 补全负向提示

**输出字段：**
【镜头】【机位】【画面提示词】【情绪节奏】【台词】【负向提示】
            """)

# ════════════════════════════════════════════════════════════════
# Tab 2：历史记录
# ════════════════════════════════════════════════════════════════
with tab_history:
    st.subheader("历史记录")

    rows = load_history()

    if not rows:
        st.info("还没有历史记录，优化后会自动保存在这里")
    else:
        if "view_id" not in st.session_state:
            st.session_state.view_id = None

        if st.session_state.view_id is not None:
            detail = load_history_detail(st.session_state.view_id)
            if detail:
                record_id, created_at, original, result = detail
                st.markdown(f"### 记录 #{record_id} · {created_at}")

                if st.button("← 返回列表"):
                    st.session_state.view_id = None
                    st.rerun()

                st.divider()
                col_orig, col_opt = st.columns(2)
                with col_orig:
                    st.markdown("**原始提示词**")
                    st.text_area("", value=original, height=400, key="orig_detail")
                with col_opt:
                    st.markdown("**优化后提示词**")
                    st.text_area("", value=result, height=400, key="opt_detail")

                st.download_button(
                    label="📥 下载优化结果",
                    data=result.encode("utf-8"),
                    file_name=f"optimized_prompts_{created_at.replace(':', '-').replace(' ', '_')}.txt",
                    mime="text/plain"
                )
        else:
            for row in rows:
                record_id, created_at, original = row
                preview = original[:50] + "..." if len(original) > 50 else original

                col_info, col_btn, col_del = st.columns([6, 1, 1])
                with col_info:
                    st.markdown(f"**#{record_id}** · {created_at}  \n_{preview}_")
                with col_btn:
                    if st.button("查看", key=f"view_{record_id}"):
                        st.session_state.view_id = record_id
                        st.rerun()
                with col_del:
                    if st.button("删除", key=f"del_{record_id}"):
                        delete_history(record_id)
                        st.rerun()

                st.divider()
