import streamlit as st
from pathlib import Path
from datetime import datetime, timedelta
import socket
import io
import os
import tempfile
import json
import re
from urllib.parse import quote, urlencode, parse_qs, urlparse

import pandas as pd
import streamlit.components.v1 as components
import plotly.express as px

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request
import requests
from openai import OpenAI as OpenAIClient

# streamlit-audiorecorder 依赖 pydub，而 pydub 在部分 Python 版本上需要额外安装 audioop-lts
try:
    from audiorecorder import audiorecorder  # type: ignore

    AUDIORECORDER_AVAILABLE = True
    AUDIORECORDER_IMPORT_ERROR = None
except Exception as e:
    AUDIORECORDER_AVAILABLE = False
    AUDIORECORDER_IMPORT_ERROR = e

st.set_page_config(page_title="我的AI智能日程")

st.title("我的AI智能日程")

st.subheader("Google 登录")

def _get_lan_ip():
    """获取本机局域网 IP，便于手机访问同一台电脑上的应用。"""
    if "_cached_lan_ip" not in st.session_state:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            try:
                s.connect(("8.8.8.8", 80))
                st.session_state._cached_lan_ip = s.getsockname()[0]
            finally:
                s.close()
        except OSError:
            st.session_state._cached_lan_ip = None
        except Exception:
            st.session_state._cached_lan_ip = None
    return st.session_state._cached_lan_ip

with st.expander("📱 在 iOS / 手机端使用本应用", expanded=False):
    try:
        lan_ip = _get_lan_ip()
        if lan_ip:
            st.markdown(f"**本机局域网 IP：** `{lan_ip}`")
            st.markdown(f"在手机 Safari 中打开：**http://{lan_ip}:8501**")
        else:
            st.markdown("在电脑上运行 `ipconfig`（Windows）或 `ifconfig`（Mac/Linux）查看本机 IP，然后在手机浏览器打开 **http://你的IP:8501**。")
        st.markdown("---")
        st.markdown("**步骤：**")
        st.markdown("1. 手机和电脑连接**同一 WiFi**。")
        st.markdown("2. 在电脑上**只运行一个** Streamlit 进程（避免端口冲突）。")
        st.markdown("3. 在 iPhone 上打开 **Safari**，地址栏输入上面的链接（如 `http://192.168.1.100:8501`）。")
        st.markdown("4. **首次使用**：务必在**电脑浏览器**打开同一地址并点「登录 Google」完成授权（在手机点登录会占用端口且授权页在电脑上弹出）；授权会保存到本机，之后手机刷新即可共用。")
        st.markdown("5. 若手机端需录音复盘，请在 Safari 中允许麦克风权限。")
        st.markdown("---")
        st.markdown("**手机显示「无法访问此网站」时（多为 Windows 防火墙拦截）：**")
        st.markdown("1. 在电脑上按 `Win + R`，输入 `wf.msc` 回车，打开 **高级安全 Windows 防火墙**。")
        st.markdown("2. 左侧点 **入站规则** → 右侧点 **新建规则**。")
        st.markdown("3. 选 **端口** → 下一步 → 选 **TCP**，特定本地端口填 **8501**（若启动时用了其它端口如 8502 则填该端口）→ 下一步。")
        st.markdown("4. 选 **允许连接** → 下一步 → 三个选项全勾选（域/专用/公用）→ 下一步 → 名称填 **Streamlit** → 完成。")
        st.markdown("5. 手机与电脑连**同一 WiFi**，在手机 Safari 地址栏输入 **http://本机IP:8501** 再试。")
        st.caption("若仍无法访问：确认手机和电脑在同一网络；若曾改过 Streamlit 端口，请用实际端口号。")
        st.markdown("---")
        st.markdown("**☁️ 想用手机直接打开网址、不依赖电脑？** 可将应用部署到云端（如 Streamlit Community Cloud），部署后手机浏览器输入应用地址即可使用。详见项目中的 **DEPLOY.md**。")
    except Exception as e:
        st.caption("本机 IP 获取失败，请在电脑上运行 ipconfig 查看 IP，再在手机浏览器打开 http://你的IP:8501")

# Calendar / Tasks 读写权限（写权限用于在应用内添加、编辑、删除并同步到 Google）
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]
OAUTH_LOCAL_PORT = 8765
# 端口被占用时依次尝试的备用端口（需在 Google 控制台“已获授权的重定向 URI”中一并添加）
OAUTH_PORTS_TO_TRY = [8765, 8766, 8767, 8768, 8769]

# 放宽 OAuth scope 校验：若 Google 返回的 scope 与请求不完全一致（如仅返回基础资料），仍接受 token，
# 避免 "Scope has changed" 报错导致无法登录；若之后日历/任务接口 403，再提示用户重新授权并勾选全部权限
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
GOOGLE_API_TIMEOUT_SECONDS = 20

# 云端部署：路径含 /mount/src 视为 Streamlit Cloud；或显式设置 CLOUD_DEPLOY / STREAMLIT_APP_URL
_app_dir = Path(__file__).resolve().parent
IS_CLOUD_DEPLOY = (
    "/mount/src" in str(_app_dir)
    or os.environ.get("CLOUD_DEPLOY", "").lower() in ("1", "true", "yes")
    or bool(os.environ.get("STREAMLIT_APP_URL"))
)

def _read_secret_str(key: str) -> str:
    """从 st.secrets 读取字符串（兼容不同实现），取不到则返回空字符串。"""
    v = None
    try:
        v = st.secrets[key]
    except Exception:
        v = None
    if not v:
        try:
            v = st.secrets.get(key)
        except TypeError:
            try:
                v = st.secrets.get(key, None)
            except Exception:
                v = None
        except Exception:
            v = None
    if not v:
        try:
            v = getattr(st.secrets, key)
        except Exception:
            v = None
    return str(v).strip() if v is not None else ""


# 云端应用地址（Secrets 根级键在 Cloud 上可能不暴露，优先从 [google] 段内读 streamlit_app_url）
_def_url = os.environ.get("STREAMLIT_APP_URL", "").strip()
if not _def_url:
    for key in ("STREAMLIT_APP_URL", "streamlit_app_url"):
        _def_url = _read_secret_str(key)
        if _def_url:
            break
if not _def_url:
    try:
        g = st.secrets.get("google") or getattr(st.secrets, "google", None)
        if g is not None:
            for k in ("streamlit_app_url", "STREAMLIT_APP_URL"):
                v = g.get(k) if isinstance(g, dict) else getattr(g, k, None)
                if v:
                    _def_url = str(v).strip()
                    break
    except Exception:
        pass
STREAMLIT_APP_URL = (_def_url or "").rstrip("/")
app_dir = _app_dir
OAUTH_STATE_DIR = Path(tempfile.gettempdir()) / "myaiplanner_oauth"

# 仅用于排查云端 Secrets 读取（?debug=1，不输出敏感值）
if st.query_params.get("debug") == "1":
    with st.expander("🔧 部署调试（不含敏感值）", expanded=True):
        st.write("IS_CLOUD_DEPLOY:", IS_CLOUD_DEPLOY)
        st.write("app_dir:", str(app_dir))
        st.write("STREAMLIT_APP_URL 已读到:", bool(STREAMLIT_APP_URL), "，长度:", len(STREAMLIT_APP_URL))
        try:
            keys = list(st.secrets.keys())
            st.write("st.secrets 根级 keys:", keys)
        except Exception as e:
            st.write("st.secrets.keys() 失败:", type(e).__name__)

# OpenAI 官方 API 模型与超时
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo")
OPENAI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "120"))

if "google_credentials" not in st.session_state:
    st.session_state.google_credentials = None

GOOGLE_TOKEN_PATH = app_dir / "google_token.json"


def _get_google_client_config_cloud():
    """云端从 secrets 或环境变量读取 Google OAuth 客户端配置（Web 应用类型）。"""
    def _from_obj(s):
        if s is None:
            return None
        cid = s.get("client_id", None) if isinstance(s, dict) else getattr(s, "client_id", None)
        csec = s.get("client_secret", None) if isinstance(s, dict) else getattr(s, "client_secret", None)
        if cid and csec:
            return {"client_id": str(cid).strip(), "client_secret": str(csec).strip()}
        if isinstance(s, dict) and s.get("web"):
            return _from_obj(s["web"])
        return None

    try:
        if getattr(st.secrets, "get", None):
            out = _from_obj(st.secrets.get("google", {}))
            if out:
                return out
        if hasattr(st.secrets, "google"):
            out = _from_obj(st.secrets.google)
            if out:
                return out
    except Exception:
        pass
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    csec = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if cid and csec:
        return {"client_id": cid, "client_secret": csec}
    return None


# ---------- 云端部署：处理 Google 回调 ----------
if IS_CLOUD_DEPLOY and STREAMLIT_APP_URL:
    _code = st.query_params.get("code")
    _state = st.query_params.get("state")
    if _code and _state:
        _state_file = OAUTH_STATE_DIR / f"{_state}.json"
        try:
            OAUTH_STATE_DIR.mkdir(parents=True, exist_ok=True)
            if _state_file.exists():
                with open(_state_file, "r", encoding="utf-8") as f:
                    _saved = json.load(f)
                _config = _get_google_client_config_cloud()
                if _config and _saved.get("code_verifier") is not None:
                    _redirect_uri = f"{STREAMLIT_APP_URL}/"
                    _client_config = {
                        "installed": {
                            "client_id": _config["client_id"],
                            "client_secret": _config["client_secret"],
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": [_redirect_uri],
                        }
                    }
                    _flow = InstalledAppFlow.from_client_config(
                        _client_config, scopes=SCOPES, redirect_uri=_redirect_uri
                    )
                    _flow.oauth2session._state = _state
                    _flow.oauth2session._code_verifier = _saved["code_verifier"]
                    _flow.code_verifier = _saved["code_verifier"]  # Flow.fetch_token 通过 self.code_verifier 传给 token 请求
                    _qs = urlencode(dict(st.query_params)) if st.query_params else ""
                    _current_url = f"{STREAMLIT_APP_URL}/?{_qs}" if _qs else f"{STREAMLIT_APP_URL}/"
                    _flow.fetch_token(authorization_response=_current_url)
                    st.session_state.google_credentials = _flow.credentials
                    _state_file.unlink(missing_ok=True)
                else:
                    st.error("云端登录状态已过期，请重新点击「登录 Google」。")
            else:
                st.warning("未找到对应的授权状态，请重新点击「登录 Google」。")
        except Exception as e:
            st.error("云端 Google 登录回调处理失败，请重试。")
            st.exception(e)
        # 清除 URL 中的 code/state，避免刷新时重复处理
        if st.session_state.get("google_credentials"):
            st.query_params.clear()
            st.rerun()

# 启动时尝试从本地文件加载已保存的授权，免去每次重启都重新登录（仅本机）
if not st.session_state.google_credentials and not IS_CLOUD_DEPLOY and GOOGLE_TOKEN_PATH.exists():
    try:
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), SCOPES)
        if creds and creds.refresh_token:
            if creds.expired:
                creds.refresh(Request())
            st.session_state.google_credentials = creds
    except Exception:
        pass

login_button = st.button("登录 Google")
if login_button:
    candidate_paths = [app_dir / "client_secret.json", app_dir / "client_secret.json.json"]
    client_secret_path = next((p for p in candidate_paths if p.exists()), None)
    cloud_cfg = _get_google_client_config_cloud()

    # ---------- 无本地文件时：优先用云端（Secrets + STREAMLIT_APP_URL）----------
    if client_secret_path is None:
        if cloud_cfg and STREAMLIT_APP_URL:
            config = cloud_cfg
            redirect_uri = f"{STREAMLIT_APP_URL}/"
            client_config = {
                "installed": {
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            }
            try:
                flow = InstalledAppFlow.from_client_config(
                    client_config, scopes=SCOPES, redirect_uri=redirect_uri
                )
                auth_url, state = flow.authorization_url(prompt="consent")
                # code_verifier 在 Flow 上（google_auth_oauthlib），不在 oauth2session._code_verifier
                code_verifier = getattr(flow, "code_verifier", None) or getattr(
                    flow.oauth2session, "_code_verifier", None
                )
                if not code_verifier:
                    st.error("无法生成授权状态，请稍后重试。")
                    st.stop()
                OAUTH_STATE_DIR.mkdir(parents=True, exist_ok=True)
                state_file = OAUTH_STATE_DIR / f"{state}.json"
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump({"code_verifier": code_verifier}, f)
                st.info("请点击下方按钮前往 Google 完成授权，授权后将自动返回本应用。")
                st.link_button("前往 Google 授权", auth_url, type="primary")
                st.caption(f"回调地址（请在 Google 控制台添加）：{redirect_uri}")
            except Exception as e:
                st.error("发起云端登录失败")
                st.exception(e)
            st.stop()
        if cloud_cfg and not STREAMLIT_APP_URL:
            st.error(
                "**云端部署**：已检测到 Secrets 中的 [google]，但缺少 **STREAMLIT_APP_URL**。\n\n"
                "请在 **Settings** → **Secrets** 的 TOML 里增加一行（与 [google] 同级）：\n\n"
                "`STREAMLIT_APP_URL = \"https://my-ai-planner-test-4odzlhb4.streamlit.app\"`\n\n"
                "保存后 **Reboot app**，再试登录。"
            )
            st.stop()
        st.error(
            "找不到 Google OAuth 客户端密钥文件。\n\n"
            "**Streamlit Cloud**：请在 Settings → Secrets 中添加 `[google]` 的 client_id、client_secret，"
            "以及根级键 `STREAMLIT_APP_URL = \"你的应用地址\"`（如 https://xxx.streamlit.app）。"
        )
        st.code(f"app.py 目录: {app_dir}\n已尝试: " + ", ".join(str(p) for p in candidate_paths))
        st.stop()

    # ---------- 本机：有 client_secret.json，用本地回调服务器 ----------

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_path),
        scopes=SCOPES,
    )
    st.info(
        "即将打开浏览器进行 Google 授权。\n\n"
        "若在 Google Cloud Console 使用“Web 应用”类型，请把以下回调地址都加入“已获授权的重定向 URI”：\n"
        + "、".join(f"http://localhost:{p}/" for p in OAUTH_PORTS_TO_TRY)
    )
    creds = None
    last_err = None
    for port in OAUTH_PORTS_TO_TRY:
        try:
            creds = flow.run_local_server(port=port, prompt="consent")
            break
        except OSError as e:
            if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) in (98, 10048):
                last_err = e
                continue
            raise
        except requests.exceptions.SSLError as e:
            last_err = e
            st.error(
                "与 Google 服务器交换登录凭据时发生 **SSL 错误**（连接被中断或遭代理/防火墙干扰）。\n\n"
                "**请依次尝试：**\n"
                "1. 若本机设置了 **HTTP/HTTPS 代理**：在运行 Streamlit 的终端里先取消代理再启动，例如：\n"
                "   `set HTTP_PROXY=` 与 `set HTTPS_PROXY=`（CMD）或关闭系统/浏览器代理。\n"
                "2. 若使用 **VPN**：改用「全局」或可访问 Google 的节点后，重新点击「登录 Google」再试。\n"
                "3. 关闭 **杀毒/企业 SSL 检测**（若存在）后重试。\n"
                "4. 过几分钟后再次点击「登录 Google」完成授权（有时为网络波动）。"
            )
            st.exception(e)
            st.stop()
    if creds is None and last_err is not None:
        st.error(
            f"OAuth 回调端口 {OAUTH_PORTS_TO_TRY} 均被占用（WinError 10048）。"
            "请关闭占用这些端口的程序，或在任务管理器中结束残留的 python 进程后重试。"
        )
        st.exception(last_err)
        st.stop()
    assert creds is not None
    st.session_state.google_credentials = creds
    try:
        with open(GOOGLE_TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    except Exception:
        pass

creds = st.session_state.google_credentials

if creds and isinstance(creds, Credentials):
    st.success("登录成功！")
    if not IS_CLOUD_DEPLOY and GOOGLE_TOKEN_PATH.exists():
        st.caption("已使用本地保存的授权，重启 Streamlit 无需重新登录。")
    if IS_CLOUD_DEPLOY:
        st.caption("云端模式：本会话内保持登录；新设备或新浏览器需重新登录。")
    st.caption("若无法在侧边栏添加/删除日程或任务，请点「清除本地授权并重新登录」以获取写权限。")
    if st.sidebar.button("清除本地授权并重新登录"):
        if not IS_CLOUD_DEPLOY:
            try:
                GOOGLE_TOKEN_PATH.unlink(missing_ok=True)
            except Exception:
                pass
        st.session_state.google_credentials = None
        st.rerun()
    session = AuthorizedSession(creds)

    # 计算今天 0 点到明天 0 点的时间范围（使用本地时区）
    now = datetime.now().astimezone()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    def fetch_today_calendar_events():
        resp = session.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            params={
                "timeMin": start_of_day.isoformat(),
                "timeMax": end_of_day.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            },
            timeout=GOOGLE_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])

    def fetch_calendar_colors():
        try:
            resp = session.get(
                "https://www.googleapis.com/calendar/v3/colors",
                timeout=GOOGLE_API_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("event") or {}
        except Exception:
            return {}

    # Google 日历事件 colorId 常用名称（用于 AI 分析时的标签）
    EVENT_COLOR_ID_TO_LABEL = {
        "1": "薰衣草",
        "2": "鼠尾草",
        "3": "葡萄",
        "4": "蓝莓",
        "5": "罗勒",
        "6": "番茄",
        "7": "火烈鸟",
        "8": "香蕉",
        "9": "橘子",
        "10": "孔雀",
        "11": "石墨",
    }

    def fetch_task_lists():
        resp = session.get(
            "https://tasks.googleapis.com/tasks/v1/users/@me/lists",
            params={"maxResults": 100},
            timeout=GOOGLE_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json().get("items", []) or []

    def fetch_tasks(list_id):
        resp = session.get(
            f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks",
            params={
                "showCompleted": "true",
                "maxResults": 100,
            },
            timeout=GOOGLE_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json().get("items", []) or []

    def get_primary_calendar_id():
        resp = session.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            timeout=GOOGLE_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        for item in (resp.json().get("items") or []):
            if item.get("primary"):
                return item.get("id")
        return "primary"

    events = []
    task_lists_with_tasks = []  # [{ "id", "title", "tasks": [...] }]
    primary_calendar_id = None

    # ------- 侧边栏：嵌入日历 + 今日安排 + 快捷编辑 -------
    with st.sidebar:
        st.header("📅 今日安排")

        # 嵌入完整 Google Calendar 界面（需本机已登录 Google）
        try:
            primary_calendar_id = get_primary_calendar_id()
            embed_src = "https://calendar.google.com/calendar/embed?src=" + quote(primary_calendar_id, safe="")
            with st.expander("📆 打开完整 Google 日历", expanded=False):
                components.iframe(embed_src, height=400)
        except Exception:
            primary_calendar_id = "primary"

        try:
            events = fetch_today_calendar_events()
            event_colors = fetch_calendar_colors()
            st.subheader("今天的日程 (Google Calendar)")
            if not events:
                st.write("今天没有日程。")
            else:
                for i, event in enumerate(events):
                    start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
                    summary = event.get("summary", "(无标题)")
                    cid = event.get("colorId")
                    bg_hex = None
                    if cid and isinstance(event_colors.get(cid), dict):
                        bg_hex = event_colors[cid].get("background")
                    if not bg_hex and cid:
                        bg_hex = "#a4bdfc"  # 默认淡蓝
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        if bg_hex:
                            st.markdown(
                                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{bg_hex};margin-right:6px;vertical-align:middle;"></span>'
                                f" **{start}** | {summary}",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.write(f"- {start}  |  {summary}")
                    with col2:
                        ev_id = event.get("id") or ""
                        if ev_id and st.button("删", key=f"del_ev_{i}"):
                            try:
                                session.delete(
                                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{ev_id}",
                                    timeout=GOOGLE_API_TIMEOUT_SECONDS,
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
            with st.expander("➕ 添加日程（同步到 Google Calendar）"):
                add_title = st.text_input("日程标题", key="new_ev_title")
                _today = datetime.now().astimezone().strftime("%Y-%m-%d")
                add_start_str = st.text_input("开始日期 (YYYY-MM-DD)", value=_today, key="new_ev_start", placeholder="2026-03-06")
                add_st_str = st.text_input("开始时间 (HH:MM)", value="09:00", key="new_ev_st", placeholder="09:00")
                add_end_str = st.text_input("结束日期 (YYYY-MM-DD)", value=_today, key="new_ev_end", placeholder="2026-03-06")
                add_et_str = st.text_input("结束时间 (HH:MM)", value="10:00", key="new_ev_et", placeholder="10:00")
                color_options = ["（无）"] + [f"{k} - {v}" for k, v in EVENT_COLOR_ID_TO_LABEL.items()]
                add_color_choice = st.selectbox("颜色标签", color_options, key="new_ev_color")
                add_color_id = None
                if add_color_choice and add_color_choice != "（无）":
                    add_color_id = add_color_choice.split(" - ")[0].strip()
                if st.button("创建日程"):
                    if not add_title:
                        st.warning("请填写标题")
                    else:
                        try:
                            add_start = datetime.strptime(add_start_str.strip(), "%Y-%m-%d").date()
                            add_st = datetime.strptime(add_st_str.strip(), "%H:%M").time()
                            add_end = datetime.strptime(add_end_str.strip(), "%Y-%m-%d").date()
                            add_et = datetime.strptime(add_et_str.strip(), "%H:%M").time()
                            tz = datetime.now().astimezone().tzinfo
                            start_dt = datetime.combine(add_start, add_st).replace(tzinfo=tz).isoformat()
                            end_dt = datetime.combine(add_end, add_et).replace(tzinfo=tz).isoformat()
                            body = {
                                "summary": add_title,
                                "start": {"dateTime": start_dt},
                                "end": {"dateTime": end_dt},
                            }
                            if add_color_id:
                                body["colorId"] = add_color_id
                            session.post(
                                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                                json=body,
                                timeout=GOOGLE_API_TIMEOUT_SECONDS,
                            )
                            st.success("已同步到 Google Calendar")
                            st.rerun()
                        except ValueError as e:
                            st.warning("日期或时间格式有误，请使用 开始/结束日期 YYYY-MM-DD、时间 HH:MM")
                        except Exception as e:
                            st.error(str(e))
        except (requests.Timeout, TimeoutError, socket.timeout, OSError) as e:
            st.error("获取 Google Calendar 日程超时/网络连接失败。")
            st.caption("如果你的网络需要代理，请在终端设置 HTTP(S)_PROXY 后再启动 Streamlit。")
            st.exception(e)
        except requests.HTTPError as e:
            st.error("获取 Google Calendar 日程失败（HTTP 错误）。")
            st.caption("常见原因：未启用 Calendar API、授权范围不足、或账号无日历权限。")
            st.exception(e)
        except Exception as e:
            st.error("获取 Google Calendar 日程失败（其他错误）。")
            st.exception(e)

        try:
            raw_lists = fetch_task_lists()
            if not raw_lists:
                raw_lists = [{"id": "@default", "title": "默认"}]
            task_lists_with_tasks = []
            for tl in raw_lists:
                list_id = tl.get("id") or "@default"
                list_title = tl.get("title") or "未命名列表"
                try:
                    task_list = fetch_tasks(list_id)
                except Exception:
                    task_list = []
                task_lists_with_tasks.append({"id": list_id, "title": list_title, "tasks": task_list})

            st.subheader("我的任务 (Google Tasks)")
            if not any(g["tasks"] for g in task_lists_with_tasks):
                st.write("当前任务列表为空。")
            else:
                for g in task_lists_with_tasks:
                    if not g["tasks"]:
                        continue
                    st.caption(f"📁 {g['title']}")
                    for j, task in enumerate(g["tasks"]):
                        title = task.get("title", "(无标题任务)")
                        status = task.get("status", "needsAction")
                        task_id = task.get("id")
                        list_id = g["id"]
                        completed = status == "completed"
                        row_key = f"{list_id}_{task_id}_{j}"
                        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                        with col1:
                            st.write(f"{'✅' if completed else '⏳'} {title}")
                        with col2:
                            if task_id:
                                new_status = "completed" if not completed else "needsAction"
                                if st.button("✓" if not completed else "↩", key=f"task_toggle_{row_key}"):
                                    try:
                                        session.patch(
                                            f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks/{task_id}",
                                            json={"status": new_status},
                                            timeout=GOOGLE_API_TIMEOUT_SECONDS,
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))
                        with col3:
                            if task_id and st.button("删", key=f"del_task_{row_key}"):
                                try:
                                    session.delete(
                                        f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks/{task_id}",
                                        timeout=GOOGLE_API_TIMEOUT_SECONDS,
                                    )
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                        with col4:
                            if task_id:
                                with st.popover("编辑"):
                                    edit_title = st.text_input("标题", value=title, key=f"edit_title_{row_key}")
                                    edit_notes = st.text_area("备注", value=task.get("notes") or "", key=f"edit_notes_{row_key}", height=80)
                                    due_val = task.get("due")
                                    edit_due_str = ""
                                    if due_val:
                                        try:
                                            d = datetime.fromisoformat(due_val.replace("Z", "+00:00")).date()
                                            edit_due_str = d.isoformat()
                                        except Exception:
                                            edit_due_str = ""
                                    # 用 text_input 避免 date_input 在 Streamlit 反序列化时 ISO 与 %Y/%m/%d 冲突（手机端转写并复盘报错）
                                    edit_due_text = st.text_input("截止日期 (YYYY-MM-DD)", value=edit_due_str, key=f"edit_due_{row_key}", placeholder="2026-03-06")
                                    if st.button("保存", key=f"save_task_{row_key}"):
                                        try:
                                            patch_body = {"title": edit_title}
                                            if edit_notes is not None:
                                                patch_body["notes"] = edit_notes
                                            if edit_due_text and edit_due_text.strip():
                                                patch_body["due"] = edit_due_text.strip() + "T00:00:00.000Z"
                                            session.patch(
                                                f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks/{task_id}",
                                                json=patch_body,
                                                timeout=GOOGLE_API_TIMEOUT_SECONDS,
                                            )
                                            st.success("已更新")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))
            with st.expander("➕ 添加任务（同步到 Google Tasks）"):
                list_options = [(g["title"], g["id"]) for g in task_lists_with_tasks]
                add_to_list_idx = st.selectbox(
                    "添加到列表",
                    range(len(list_options)),
                    format_func=lambda i: list_options[i][0],
                    key="add_task_list",
                )
                add_to_list_id = list_options[add_to_list_idx][1]
                new_task_title = st.text_input("任务标题", key="new_task_title")
                if st.button("创建任务"):
                    if not new_task_title:
                        st.warning("请填写标题")
                    else:
                        try:
                            session.post(
                                f"https://tasks.googleapis.com/tasks/v1/lists/{add_to_list_id}/tasks",
                                json={"title": new_task_title},
                                timeout=GOOGLE_API_TIMEOUT_SECONDS,
                            )
                            st.success("已同步到 Google Tasks")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
        except (requests.Timeout, TimeoutError, socket.timeout, OSError) as e:
            st.error("获取 Google Tasks 任务超时/网络连接失败。")
            st.caption("如果你的网络需要代理，请在终端设置 HTTP(S)_PROXY 后再启动 Streamlit。")
            st.exception(e)
        except requests.HTTPError as e:
            st.error("获取 Google Tasks 任务失败（HTTP 错误）。")
            st.caption("常见原因：未启用 Tasks API、授权范围不足。")
            st.exception(e)
        except Exception as e:
            st.error("获取 Google Tasks 任务失败（其他错误）。")
            st.exception(e)

    # ------- 主区域：语音复盘（仅使用 OpenAI 官方 API） -------
    st.subheader("语音复盘")

    if not AUDIORECORDER_AVAILABLE:
        st.error("录音组件加载失败：缺少音频依赖。")
        st.caption(
            "请在已激活的虚拟环境中执行：`python -m pip install audioop-lts`，然后重启 Streamlit。"
        )
        st.exception(AUDIORECORDER_IMPORT_ERROR)
        st.stop()

    openai_api_key = None
    try:
        _k = st.secrets.get("OPENAI_API_KEY")  # type: ignore[attr-defined]
        openai_api_key = (_k or "").strip() or None
    except Exception:
        openai_api_key = None
    if not openai_api_key:
        openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or None

    with st.expander("配置 OpenAI API Key", expanded=not openai_api_key):
        st.write("使用 OpenAI 官方 API。请将 Key 放在环境变量 `OPENAI_API_KEY` 或下方输入（勿写入代码以防泄露）。")
        openai_input = st.text_input("OpenAI API Key", type="password", value=openai_api_key or "")
        if openai_input:
            openai_api_key = openai_input.strip()
        transcribe_model = st.text_input("语音转写模型", value=OPENAI_TRANSCRIBE_MODEL)
        chat_model = st.text_input("复盘分析模型", value=OPENAI_CHAT_MODEL)
        if openai_api_key and st.button("在页面内验证 Key（请求 api.openai.com）"):
            try:
                r = requests.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_api_key.strip()}"},
                    timeout=10,
                )
                if r.status_code == 200:
                    st.success(f"验证成功，状态码 200。当前 Key 前 12 位：{openai_api_key[:12]}…")
                else:
                    st.error(f"验证失败，状态码 {r.status_code}。请检查 Key 或到 platform.openai.com 重新创建。")
            except Exception as e:
                st.error("请求失败（网络或超时）。")
                st.exception(e)

    # 打字输入 + 语音输入 并行
    st.caption("可只填其一，或同时使用：下方文字会与语音转写合并后一起用于复盘。")
    typed_input = st.text_area(
        "文字输入（可选，与下方录音可同时使用）",
        height=120,
        placeholder="在此输入今日复盘文字…",
        key="typed_review_input",
    )

    audio = audiorecorder("开始录音", "停止录音")
    if audio is not None and len(audio) > 0:
        wav_buf = io.BytesIO()
        audio.export(wav_buf, format="wav")
        wav_bytes = wav_buf.getvalue()
        st.audio(wav_bytes, format="audio/wav")

    if "voice_transcript" not in st.session_state:
        st.session_state.voice_transcript = ""
    if "review_reply" not in st.session_state:
        st.session_state.review_reply = ""
    if "gantt_data" not in st.session_state:
        st.session_state.gantt_data = None

    if st.button("转写并复盘", type="primary"):
        if not openai_api_key:
            st.error("请先在「配置 OpenAI API Key」中填写你的 OpenAI 官方 API Key。")
            st.stop()

        typed_text = (typed_input or "").strip()
        has_audio = audio is not None and len(audio) > 0

        if not typed_text and not has_audio:
            st.error("请先输入文字或录制语音（或两者都填）。")
            st.stop()

        # 强制使用 OpenAI 官方地址，避免环境变量 OPENAI_BASE_URL 指向中转导致 401
        oa_client = OpenAIClient(
            api_key=openai_api_key,
            base_url="https://api.openai.com/v1",
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
        )

        # 1) 若有录音：语音 -> 文字，再与打字内容合并
        if has_audio:
            with st.spinner("正在转写语音..."):
                try:
                    transcription = oa_client.audio.transcriptions.create(
                        model=transcribe_model,
                        file=("recording.wav", wav_bytes, "audio/wav"),
                        response_format="text",
                        language="zh",
                    )
                    transcript_text = (getattr(transcription, "text", None) or str(transcription)).strip()
                except Exception as e:
                    st.error("语音转写失败。")
                    st.exception(e)
                    st.stop()
            if typed_text:
                combined = typed_text + "\n\n【语音转写】\n" + transcript_text
            else:
                combined = transcript_text
        else:
            combined = typed_text

        st.session_state.voice_transcript = combined
        st.text_area("本次复盘内容（文字+语音转写）", value=st.session_state.voice_transcript, height=180, key="show_combined")

        # 2) 组合 Prompt -> 复盘分析（含日历颜色标签与任务分组/备注/截止）
        def format_events_for_prompt(evts):
            lines = []
            for e in evts or []:
                start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
                end = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date")
                summary = e.get("summary", "(无标题)")
                cid = e.get("colorId")
                tag = EVENT_COLOR_ID_TO_LABEL.get(cid, cid or "无") if cid else "无"
                lines.append(f"- {start} ~ {end} | {summary} [颜色/标签: {tag}]")
            return "\n".join(lines) if lines else "- （今天没有日程）"

        def format_tasks_for_prompt(groups):
            lines = []
            for g in groups or []:
                list_title = g.get("title", "未命名列表")
                for t in g.get("tasks") or []:
                    title = t.get("title", "(无标题任务)")
                    status = t.get("status", "needsAction")
                    due = t.get("due") or ""
                    notes = (t.get("notes") or "").strip()
                    parts = [f"[{list_title}] [{status}] {title}"]
                    if due:
                        parts.append(f"截止: {due}")
                    if notes:
                        parts.append(f"备注: {notes[:200]}{'…' if len(notes) > 200 else ''}")
                    lines.append("- " + " | ".join(parts))
            return "\n".join(lines) if lines else "- （任务列表为空）"

        prompt = f"""你是一名严格但友好的日程复盘教练。

今天日期：{start_of_day.date().isoformat()}

## 今天的日历（Google Calendar，含颜色/标签，分析时请考虑标签含义）
{format_events_for_prompt(events)}

## 今天的任务（Google Tasks，按列表分组；含截止与备注，分析时请考虑）
{format_tasks_for_prompt(task_lists_with_tasks)}

## 我的复盘内容（文字+语音转写）
{st.session_state.voice_transcript}

请按以下两部分的格式回复：

【第一部分：分析文字】
1) 我今天完成了哪些关键事项（按影响力排序）
2) 哪些计划未完成/被打断，可能原因是什么
3) 明天最重要的 3 件事（可执行、可衡量）
4) 给我一个改进建议（尽量具体）

【第二部分：甘特图数据】
在分析文字之后，必须紧跟一行：---GANTT_JSON---
然后是一段合法的 JSON 数组，用于任务进度甘特图。每个元素包含且仅包含以下四个字段（字段名必须与下列完全一致）：
- "任务名"：字符串
- "开始日期"：字符串，格式 YYYY-MM-DD
- "结束日期"：字符串，格式 YYYY-MM-DD
- "完成百分比"：0～100 的整数

请根据上述日历、任务和复盘内容，推断并生成 3～10 条任务（可包含今日日程与任务中的事项，以及你建议的明日事项），每条都要有合理的开始/结束日期和完成百分比。只输出一个 JSON 数组，不要其他说明。示例：
---GANTT_JSON---
[{{"任务名": "完成周报", "开始日期": "2025-03-03", "结束日期": "2025-03-05", "完成百分比": 100}}, {{"任务名": "项目方案", "开始日期": "2025-03-05", "结束日期": "2025-03-10", "完成百分比": 40}}]
"""

        # 3) 复盘分析（OpenAI Chat 官方）
        with st.spinner("AI 正在分析你的进度..."):
            try:
                resp = oa_client.chat.completions.create(
                    model=chat_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                )
                raw = (resp.choices[0].message.content or "").strip()
                # 拆出分析文字与甘特图 JSON
                gantt_marker = "---GANTT_JSON---"
                if gantt_marker in raw:
                    text_part, json_part = raw.split(gantt_marker, 1)
                    st.session_state.review_reply = text_part.strip()
                    json_part = json_part.strip()
                    # 去掉可能的 markdown 代码块包裹
                    if json_part.startswith("```"):
                        json_part = re.sub(r"^```\w*\n?", "", json_part)
                        json_part = re.sub(r"\n?```\s*$", "", json_part)
                    try:
                        st.session_state.gantt_data = json.loads(json_part)
                        if not isinstance(st.session_state.gantt_data, list):
                            st.session_state.gantt_data = None
                    except Exception:
                        st.session_state.gantt_data = None
                else:
                    st.session_state.review_reply = raw
                    st.session_state.gantt_data = None
            except Exception as e:
                err_msg = str(e).lower()
                if "401" in err_msg or "invalid" in err_msg or "令牌" in str(e) or "authentication" in err_msg:
                    st.error("API Key 无效或未通过验证（401）。请检查：1) 在 platform.openai.com 确认 Key 未撤销、无多余空格 2) 若使用代理/中转，确认 Key 与接口匹配。")
                else:
                    st.error("复盘分析失败。")
                st.exception(e)
                st.stop()

    if st.session_state.get("review_reply"):
        st.subheader("AI 复盘结果")
        st.write(st.session_state.review_reply)

    gantt_data = st.session_state.get("gantt_data")
    if gantt_data and isinstance(gantt_data, list) and len(gantt_data) > 0:
        st.subheader("任务进度甘特图")
        rows = []
        for item in gantt_data:
            if not isinstance(item, dict):
                continue
            name = item.get("任务名") or item.get("task_name") or "未命名"
            start_s = item.get("开始日期") or item.get("start_date") or ""
            end_s = item.get("结束日期") or item.get("end_date") or ""
            pct = item.get("完成百分比", item.get("completion", 0))
            try:
                pct = int(pct) if pct is not None else 0
            except (TypeError, ValueError):
                pct = 0
            if not start_s or not end_s:
                continue
            try:
                start_d = pd.to_datetime(start_s)
                end_d = pd.to_datetime(end_s)
                if end_d <= start_d:
                    end_d = start_d + pd.Timedelta(days=1)
            except Exception:
                continue
            rows.append({"Task": name, "Start": start_d, "Finish": end_d, "完成百分比": max(0, min(100, pct))})
        if rows:
            df = pd.DataFrame(rows)
            fig = px.timeline(
                df, x_start="Start", x_end="Finish", y="Task",
                color="完成百分比", color_continuous_scale="Blues",
                title="根据本次复盘生成的任务进度",
            )
            fig.update_yaxes(autorange="reversed")
            fig.update_layout(height=max(300, 60 * len(rows)), margin=dict(l=10, r=10, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("本次回复中未解析到有效的甘特图数据。")
    elif st.session_state.get("review_reply"):
        st.caption("本次复盘未返回甘特图数据，或格式解析失败。")


