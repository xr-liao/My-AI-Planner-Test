# 云端部署说明（手机直接通过网址打开，不依赖电脑）

部署后可在手机浏览器输入应用地址即可使用，无需电脑运行 Streamlit。

---

## 一、推荐方式：Streamlit Community Cloud（免费）

1. **准备代码仓库**
   - 将本项目推送到 **GitHub**（或 GitLab），确保根目录有 `app.py` 和 `requirements.txt`。

2. **打开 Streamlit Cloud**
   - 访问：https://share.streamlit.io/
   - 用 GitHub 账号登录，选择 **Deploy an app**。

3. **填写部署信息**
   - **Repository**：你的仓库，如 `你的用户名/MyAIPlanner`
   - **Branch**：`main` 或你的默认分支
   - **Main file path**：`app.py`
   - 点击 **Advanced settings**，在 **Secrets** 中填入（见下方「配置 Secrets」）。

4. **配置 Secrets（必填）**
   在 Streamlit Cloud 的 **Secrets** 里添加（格式为 TOML）：

   ```toml
   # Google OAuth（云端必须用「Web 应用」类型）
   [google]
   client_id = "你的客户端ID.apps.googleusercontent.com"
   client_secret = "你的客户端密钥"

   # 可选：OpenAI API Key（也可在应用内填写）
   OPENAI_API_KEY = "sk-..."
   ```

5. **设置应用 URL 环境变量**
   - 部署完成后，Streamlit 会给你一个地址，例如：`https://你的应用名-你的用户名-xxx.streamlit.app`
   - 在 Streamlit Cloud 该应用的 **Settings** → **General** → **Environment variables** 中添加：
     - 名称：`STREAMLIT_APP_URL`
     - 值：`https://你的应用名-你的用户名-xxx.streamlit.app`（与上一步实际地址一致，不要末尾斜杠）
   - 保存后重新部署一次，使环境变量生效。

6. **Google Cloud Console 配置（云端必做）**
   - 打开 [Google Cloud Console](https://console.cloud.google.com/) → 你的项目 → **凭据**。
   - 创建或编辑 **OAuth 2.0 客户端 ID**，类型选 **「Web 应用」**。
   - 在 **已获授权的重定向 URI** 中**添加一行**（与上面 `STREAMLIT_APP_URL` 一致，并带末尾斜杠）：
     - `https://你的应用名-你的用户名-xxx.streamlit.app/`
   - 保存。

7. **使用**
   - 在手机浏览器打开你的 Streamlit 应用地址。
   - 点击「登录 Google」→ 点击「前往 Google 授权」→ 在 Google 页面完成授权 → 自动跳回应用即可使用。

---

## 二、自建服务器 / 其他云（Railway、Render、自己的 VPS 等）

1. **环境变量**（必须设置）：
   - `CLOUD_DEPLOY=1` 或 `STREAMLIT_APP_URL=https://你的应用公网地址`（不要末尾斜杠）
   - `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`：若不用 Secrets 文件，可在这里配置
   - （可选）`OPENAI_API_KEY`

2. **Google 控制台**：在「Web 应用」类型 OAuth 客户端的重定向 URI 中添加：`https://你的应用公网地址/`

3. **启动命令**：`streamlit run app.py --server.port 8501 --server.address 0.0.0.0`

4. 若用 **Secrets 文件**（如 `.streamlit/secrets.toml`），格式同上方 `[google]` 与 `OPENAI_API_KEY`。

---

## 三、说明

- **云端登录**：每次在新设备或新浏览器打开需重新点「登录 Google」；同一浏览器会话内会保持登录。
- **OpenAI Key**：建议在 Secrets 中配置 `OPENAI_API_KEY`，也可在应用内「配置 OpenAI API Key」中填写。
- **录音**：手机浏览器需允许麦克风权限方可使用语音复盘。
