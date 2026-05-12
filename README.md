# 校园心理健康智能评估与干预平台（示例项目）

基于《校园心理健康智能评估》的前后端分离示例，适合课程作业、毕设展示与二次开发。

**三人分工（与当前代码一致）**：见 [分工说明.md](./分工说明.md)。  
**初级阶段（开发内容、目标、计划、技术、分工总览）**：见 [项目初级阶段规划.md](./项目初级阶段规划.md)。

## 技术栈

- **后端**：Python 3 + FastAPI + SQLAlchemy + MySQL（PyMySQL）
- **AI**：默认 **Ollama（本机免费）** 用于测评长文点评与「心灵树洞」对话；可选配置 **DeepSeek（云端）**（`LLM_PROVIDER=auto` 或 `deepseek`）
- **安全**：bcrypt 密码哈希、JWT（Bearer）鉴权、环境变量管理敏感配置
- **前端**：**Vue 3.5**（组合式 API `<script setup>`）+ **Vite 6** + **Vue Router 4** + **Pinia 3**（学生 / 管理员登录态）+ **Element Plus** + **Tailwind CSS v4** + **Axios** + **ECharts**（统计页与数据大屏）

接口前缀：`/api/v1/`；本地联调时前端将 `/api` 代理到后端 **8002** 端口；`@` 别名指向 `src/`。

## 环境要求

| 组件    | 建议版本           | 说明                                                                |
| ------- | ------------------ | ------------------------------------------------------------------- |
| Python  | 3.10+（推荐 3.11） | 后端运行环境                                                        |
| Node.js | 18+                | 前端构建与开发服务器                                                |
| MySQL   | 5.7+ / 8.0         | 存储用户、测评、预约、资源等                                        |
| Ollama  | 最新版             | 可选；不装则测评 AI 点评会回退规则模板，心灵树洞需配置云端或 Ollama |

## 快速开始（本地开发）

1. **安装并启动 MySQL**，创建数据库（库名默认 `campus_mental`）。
2. **启动后端**（见下文「后端运行」）：`uvicorn` 监听 `http://127.0.0.1:8002`。
3. **启动前端**：`npm run dev`，浏览器打开 `http://127.0.0.1:5173`。
4. （可选）安装 **Ollama** 并 `ollama pull` 对应模型，以便测评与树洞使用 AI。

## 目录结构

```text
test/
  README.md
  backend/
    main.py              # FastAPI 入口、路由、数据模型、种子数据
    config.py            # 环境变量与数据库 URL
    security.py          # JWT、密码哈希
    llm_client.py        # DeepSeek / Ollama 统一调用与提示词
    requirements.txt
    .env.example         # 复制为 .env 后修改
    migrations/          # 可选 SQL（旧库补列等）
  frontend/
    vite.config.js       # 开发代理 /api → 127.0.0.1:8002
    package.json
    src/
      api/               # Axios 实例与拦截器
      stores/            # Pinia：studentAuth、adminAuth、theme
      router/            # 路由与守卫
      views/             # 页面（测评、树洞、管理端统计与大屏等）
      components/        # 如 ThemeToggle
      assets/main.css    # Tailwind 与全局样式
```

## 后端运行

### 1. 准备数据库

在 MySQL 中创建空库（字符集建议 `utf8mb4`）：

```sql
CREATE DATABASE IF NOT EXISTS campus_mental
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

确保账号可远程或本机登录，并记下 **用户名、密码、端口**（默认 `3306`）。

### 2. Python 虚拟环境（推荐）

**Windows（PowerShell）**

```powershell
cd test\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**

```bash
cd test/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

将 `backend/.env.example` 复制为 **`backend/.env`**，按实际环境修改。常用项如下：

| 变量                      | 说明                                                                                     |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `DB_USER` / `DB_PASSWORD` | MySQL 账号密码                                                                           |
| `DB_HOST`                 | 默认 `127.0.0.1`；远程数据库填 IP 或域名                                                 |
| `DB_PORT`                 | 默认 `3306`；若 MySQL 映射到本机 **3307**（例如 Docker）则改为 `3307`                    |
| `DB_NAME`                 | 默认 `campus_mental`                                                                     |
| `JWT_SECRET`              | 生产环境务必改为**长随机字符串**                                                         |
| `CORS_ORIGINS`            | 生产环境填前端地址，多个用英文逗号分隔，如 `http://localhost:5173,http://127.0.0.1:5173` |
| `LLM_PROVIDER`            | `ollama`（默认）/ `auto` / `deepseek`                                                    |
| `OLLAMA_BASE_URL`         | 默认 `http://127.0.0.1:11434`                                                            |
| `OLLAMA_MODEL`            | 须与 `ollama list` 一致，如 `qwen2.5:7b`                                                 |
| `DEEPSEEK_API_KEY`        | 使用云端时填写                                                                           |

更多 AI 调参与加速相关变量见下文「AI 生成速度」及 `.env.example` 内注释。

### 4. 启动服务

**开发模式（热重载，默认端口 8002，与前端 Vite 代理一致）**

```bash
cd test/backend
uvicorn main:app --reload --host 127.0.0.1 --port 8002
```

也可使用项目内入口（等价于上面一行）：

```bash
python main.py
```

（`main.py` 末尾以 **8002** 启动，无 `--reload`。开发时更推荐 `uvicorn ... --reload`。）

**监听所有网卡（局域网其它设备访问调试时）**

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

此时请将前端 `vite.config.js` 里 `proxy.target` 改为可达的后端地址，并在 `CORS_ORIGINS` 中加入对应前端 origin。

### 5. 验证后端

| 地址                                | 说明                       |
| ----------------------------------- | -------------------------- |
| http://127.0.0.1:8002/docs          | Swagger / OpenAPI 交互文档 |
| http://127.0.0.1:8002/api/v1/health | 健康检查（含数据库连通性） |

首次成功启动后，若表为空，会自动写入 **PHQ-9 / SCL-90 演示题** 与 **心理资源** 种子数据（资源按标题去重增量补充）。

### 6. 后端常见问题

- **无法连接 MySQL**：检查 `DB_HOST`、`DB_PORT`、`DB_PASSWORD` 是否与 MySQL 一致；本机防火墙是否放行端口。
- **Windows 上 `localhost` 连库异常**：`config` 中已倾向 `127.0.0.1`，与 `localhost` 走 IPv6 的问题可参考 `.env.example` 注释。
- **Ollama 502 / 超时**：确认 `ollama list` 中模型名与 `OLLAMA_MODEL` 完全一致；显存不足可换 `qwen2.5:3b`；代理软件勿劫持 `127.0.0.1`（可设 `NO_PROXY`）。
- **旧库缺列**：若曾手动建表，可执行 `migrations/` 下 SQL 为 `evaluation_result` 等补列。

### 管理员账号

管理员为 `user` 表中 `role = 'admin'` 的用户。

**方式一：受控自助注册（推荐演示/首次部署）**

1. 在 `backend/.env` 设置 **`ADMIN_REGISTER_SECRET`** 为一段足够长的随机字符串（勿提交到公开仓库）。
2. 重启后端，打开 **管理员登录页**，点击「受控注册管理员」，填写用户名、密码与**注册密钥**（与 `.env` 中一致）。
3. 注册成功后用该账号登录。未配置 `ADMIN_REGISTER_SECRET` 或密钥错误时，接口返回 403。

**方式二：手工写入数据库**

若库中尚无管理员，可在 MySQL 中插入一条（密码可与学生端一致为明文，登录时兼容校验；**新注册用户密码一律为 bcrypt 哈希**）：

```sql
INSERT INTO user (username, password, role, create_time)
VALUES ('admin', '你的密码', 'admin', NOW());
```

生产环境建议将管理员密码也改为 bcrypt 哈希，可在后端目录执行：

```bash
python -c "from passlib.context import CryptContext; c=CryptContext(schemes=['bcrypt'],deprecated='auto'); print(c.hash('你的强密码'))"
```

将输出替换进 `user.password` 字段。

### 数据库表与种子数据

- 应用启动时会 `create_all` 创建缺失表；种子逻辑见上文。
- 若 `user.password` 列为 `VARCHAR(50)` 等较短类型，建议改为 `VARCHAR(255)` 以容纳 bcrypt。
- 若旧库已有 `evaluation_result` 但无 `ai_generated` 列，可执行 `backend/migrations/001_add_evaluation_result_ai_generated.sql`。

### AI 与 Ollama（后端侧摘要）

- **免费与本机（推荐演示）**
  - 安装 [Ollama](https://ollama.com)，执行 `ollama pull qwen2.5:7b`（或 `.env` 中其它模型名）。
  - `LLM_PROVIDER=ollama`，或 `auto` 且**不填** `DEEPSEEK_API_KEY`，将走 Ollama。
  - 后端与 Ollama 默认同机 `http://127.0.0.1:11434`。

- **云端 DeepSeek（可选）**
  - 在 [DeepSeek 开放平台](https://platform.deepseek.com/) 创建 `DEEPSEEK_API_KEY`。
  - `LLM_PROVIDER=auto` 且配置密钥时优先 DeepSeek；失败可回退 Ollama（若已安装）。

## 前端运行

```bash
cd test/frontend
npm install
npm run dev
```

- 默认访问：**http://127.0.0.1:5173/**
- 开发时接口经 Vite 代理到 **http://127.0.0.1:8002**，请先启动后端。
- 生产静态资源：`npm run build`，产物在 `frontend/dist`，可由 Nginx 等托管并反向代理 `/api` 到后端。

前端已集成 **Tailwind CSS v4**；顶栏与登录等页可切换 **深色 / 浅色** 主题（`localStorage` 键 `campus_theme`，与 Element Plus 深色变量联动）。

## 主要 API 分组（详见 /docs）

- **学生**：`/api/v1/user/*` 注册、登录、重置密码
- **测评**：`/api/v1/evaluation/*` 题目、提交结果、历史
- **AI**：`/api/v1/ai/chat` 心灵树洞（整段返回）；`/api/v1/ai/chat/stream` **SSE 流式**（前端树洞页使用）；公开配置等
- **资源 / 预约**：`/api/v1/resource/*`、`/api/v1/appointment/*`
- **管理端**：`/api/v1/admin/*` 登录、统计、导出 CSV 等

统一响应结构与健康检查见 Swagger **http://127.0.0.1:8002/docs**。

## 功能概览

### 学生端

- 注册 / 登录 / 忘记密码（新密码 ≥6 位）
- JWT 登录态；测评、个人中心、预约等接口需携带 `Authorization: Bearer <token>`
- **PHQ-9** 与 **SCL-90（演示）** 测评；提交后可由 **Ollama / DeepSeek** 生成长文点评（失败时用规则模板）
- 个人中心、**心灵树洞** 多轮对话、咨询预约、**心理资源库**（文章与音频）

### 管理端

- 管理员独立 JWT；统计图表、数据大屏、测评记录与 **导出 CSV**

### 前端体验

- 中文界面；Pinia 管理会话；路由守卫与 Axios 401 处理
- 心灵树洞等长请求在前端代理层已设较长超时（开发环境）

## AI 生成速度（测评点评 / 心灵树洞）

影响耗时的因素包括：**模型大小**、**GPU/CPU**、**max_tokens**、**上下文长度**。可在 `backend/.env` 调节（详见 `.env.example`）：

| 变量                                | 作用                                  |
| ----------------------------------- | ------------------------------------- |
| `OLLAMA_MODEL`                      | 如 `qwen2.5:3b` 通常比 `7b` 更快      |
| `LLM_EVAL_MAX_TOKENS`               | 测评长文上限，调小可加快              |
| `LLM_CHAT_MAX_TOKENS`               | 树洞单轮上限，调小可加快              |
| `LLM_TIMEOUT_SEC`                   | 请求超时秒数                          |
| `OLLAMA_NUM_CTX`                    | 仅 Ollama；限制上下文有时加快 prefill |
| `LLM_PROVIDER` / `DEEPSEEK_API_KEY` | 本机 CPU 慢时云端常更快               |

首次加载模型可能明显慢于后续请求。流式输出（SSE）需额外开发以改善首字等待。

## 安全与配置说明

- **切勿**将含真实密码的 `.env` 提交到版本库。
- 生产环境请设置强随机 `JWT_SECRET`，并用 `CORS_ORIGINS` 限制前端来源；与 `allow_credentials` 配合时不要使用 `*`。
- 旧数据若为明文密码，登录仍可使用；新注册与重置密码后为 bcrypt 存储。

## 后续可扩展方向

- 接入真实 SCL-90 全量题目与常模解释
- 预约时段容量、咨询师角色与通知（邮件 / 站内信）
- 前端路由懒加载、ECharts 按需引入以进一步优化性能
