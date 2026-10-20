# 把项目上传到 GitHub（从零开始）

> 写给完全没做过的人。每一步都写清「点哪里、填什么、看到什么算成功」。
> 生成时间：2026-10-20 16:30

---

## 0. 先弄清一件事：你有**两个**仓库

| 仓库 | 位置 | 装什么 |
|---|---|---|
| **文档仓库** | `D:\Game\GAMEdev\.git` | `Docs\`、`AGENTS.md`、`Tools\`、`.workbuddy\memory\` |
| **Unity 工程仓库** | `D:\Game\GAMEdev\ZombieExtraction\.git` | 游戏代码、场景、Prefab |

两个仓库是独立的，所以要建**两个** GitHub 仓库（不是把整个 `D:\Game` 传上去）。

> 为什么不在根目录一个仓库全包？因为 Unity 工程自带 `.git`，硬塞进去会变成"嵌套仓库"，Git 会当它是一个空壳，代码全丢。**两个仓库更干净。**

---

## 1. 注册 GitHub 账号（已有就跳到第 2 步）

1. 浏览器打开 **https://github.com**
2. 点右上角 **Sign up（注册）**
3. 依次填：邮箱 → 密码 → 用户名（用户名会出现在仓库地址里，**想好再填**，改起来麻烦）
4. 邮箱收验证码，验证
5. 完成后进入首页

> ⚠️ 国内访问 github.com 可能很慢或打不开，需要开代理（见第 9 节）。注册时也要能打开网页。

---

## 2. 建第一个仓库（放文档）

1. 登录后，点右上角 **`+`** → **New repository（新建仓库）**
2. 填写：

| 字段 | 填什么 |
|---|---|
| **Owner（所有者）** | 保持你自己的用户名 |
| **Repository name（仓库名）** | `GAMEdev-docs`（英文、短、不带空格） |
| **Description（描述）** | 可留空，或写「僵尸搜打撤 - 设计文档」 |
| **Public / Private** | 想公开选 Public，不想被别人看到选 **Private** |
| **Add a README file** | ⚠️ **不要勾** |
| **Add .gitignore** | ⚠️ **不要勾** |
| **Choose a license** | ⚠️ **不要勾** |

> **三个勾为什么都不能勾？** 勾了 GitHub 会先帮你造一个提交，你本地推送时会报 `rejected (fetch first)`，还得额外处理。**建空仓库最省事。**

3. 点绿色 **Create repository（创建仓库）**
4. 创建后页面会显示地址，形如：

```
https://github.com/你的用户名/GAMEdev-docs.git
```

**把这个地址复制下来**，下一步要用。

---

## 3. 生成访问令牌（Token）—— 这一步最容易被卡

**从 2021 年起，GitHub 不接受账号密码推送了，必须用 Token。**

1. 点右上角**头像** → **Settings（设置）**
2. 左侧菜单**拉到最下面** → **Developer settings（开发者设置）**
3. 左侧 → **Personal access tokens（个人访问令牌）** → **Tokens (classic)**
4. 右上角 **Generate new token** → **Generate new token (classic)**
5. 填写：

| 字段 | 填什么 |
|---|---|
| **Note（备注）** | `GAMEdev 推送` |
| **Expiration（有效期）** | 选 **90 days**（安全）；嫌麻烦可选 No expiration |
| **Select scopes（权限）** | ✅ **只勾最上面那个 `repo`**（勾了它会自动带上下面 5 个子项） |

6. 拉到底 → **Generate token**
7. 页面显示一串 `ghp_xxxxxxxx...` 的字符 —— **立刻复制保存到记事本**

> ⚠️ **这串字符只显示这一次**，刷新页面就看不到了。丢了只能重新生成。
> ⚠️ **它是密码**，不要发给任何人、不要写进代码、不要提交到仓库。

### 3.1 那一长串 Scope 到底勾哪个？（只看这一条）

> **口诀：只勾 `repo`，其余留空；`delete_repo` 永远别碰。**

GitHub 那个页面会列 30 多个权限项，很容易看花眼。实际只需要**最上面第一个 `repo`**。

| Scope | 勾不勾 | 干什么用的 |
|---|---|---|
| **`repo`** | ✅ **要** | 推送、拉取、读写仓库（含私有仓库）—— **唯一需要的** |
| `repo:status` | ✅ 自动带 | 勾了 `repo` 后 GitHub 自动勾上，不用管 |
| `repo_deployment` | ✅ 自动带 | 同上 |
| `public_repo` | ✅ 自动带 | 同上 |
| `repo:invite` | ✅ 自动带 | 同上 |
| `security_events` | ✅ 自动带 | 同上 |
| `workflow` | ❌ | 只有要改 GitHub Actions 工作流才需要 |
| `write:packages` / `read:packages` / `delete:packages` | ❌ | 只有要发 NuGet / npm 包才需要 |
| `admin:org` 以及它下面所有 `org` 项 | ❌ | 管理组织、团队才需要 |
| `admin:public_key` / `admin:gpg_key` / `admin:ssh_signing_key` | ❌ | 管理密钥才需要 |
| `admin:repo_hook` / `write:repo_hook` / `read:repo_hook` / `admin:org_hook` | ❌ | 配 Webhook 才需要 |
| `gist` | ❌ | 存代码片段才需要 |
| `notifications` | ❌ | 不需要 |
| `user` / `read:user` / `user:email` / `user:follow` | ❌ | 读个人资料才需要 |
| **`delete_repo`** | ❌ **绝对别勾** | ⚠️ 勾了它，Token 一旦泄露，**别人能删掉你整个仓库** |
| `discussions` / `read:discussion` | ❌ | 不需要 |
| `admin:enterprise` 及其下面所有 | ❌ | 企业功能 |
| `audit_log` / `read:audit_log` | ❌ | 不需要 |
| `codespace` / `codespace:secrets` | ❌ | 云端 IDE |
| `copilot` / `manage_billing:copilot` | ❌ | 不需要 |
| `project` / `read:project` | ❌ | 项目管理看板 |

**为什么勾这么少**：Token 就是密码，权限给多了等于把钥匙串全交出去。推送代码只需要 `repo`，多勾一项就多一分风险。

> 页面上"笔记（Note）"填 `GAMEdev 推送` 即可 —— 只是给你自己在 Token 列表里辨认用。
> "到期日（Expiration）"选 `90 days` 较安全；嫌麻烦可以选 `No expiration`，但风险更高。

---

## 4. 本地把这个仓库接上 GitHub 并推送

打开 **Git Bash**（或 PowerShell），执行：

```bash
cd /d/Game/GAMEdev
git remote add origin https://github.com/你的用户名/GAMEdev-docs.git
git push -u origin master
```

> 上面的地址换成第 2 步复制的那个。
> 我们的分支叫 `master`（不是网上常见的 `main`），这只是名字不同，不影响任何使用。

**推送时会弹窗要求登录：**

| 框 | 填什么 |
|---|---|
| 用户名 / Username | **你的 GitHub 用户名**（不是邮箱） |
| 密码 / Password | **第 3 步那个 `ghp_...` 的 Token**（不是账号密码！） |

成功后应该看到类似：

```
Enumerating objects: 14, done.
Writing objects: 100% (14/14), 68.5 KiB
To https://github.com/xxx/GAMEdev-docs.git
 * [new branch]      master -> master
branch 'master' set up to track 'origin/master'.
```

**换成中文就是：14 个文件传上去了，本地的 master 跟远程的 master 绑定了。**

> Windows 会自动把这个 Token 记在「凭据管理器 / Credential Manager」里，以后再推不用重新输。
> 想清除：控制面板 → 凭据管理器 → Windows 凭据 → 找 `git:https://github.com` → 删除。

---

## 5. 建第二个仓库（放 Unity 工程）

重复第 2 步，但：

- Repository name 填 **`ZombieExtraction`**
- 地址会变成 `https://github.com/你的用户名/ZombieExtraction.git`

然后：

```bash
cd /d/Game/GAMEdev/ZombieExtraction
git remote add origin https://github.com/你的用户名/ZombieExtraction.git
git push -u origin master
```

这次不用再输 Token（已记住）。

> ✅ 已确认：Unity 工程的 `.gitignore` 排除了 `Library/ Temp/ Logs/`，只有 **210 个文件**，推送很快。
> 如果哪天发现要传好几个 GB，说明 `.gitignore` 出问题了，**先停下来检查**，别硬传。

---

## 6. 验证成功

1. 浏览器刷新 GitHub 仓库页面 —— 能看到 `Docs/`、`AGENTS.md` 等文件 = 成功
2. 本地执行 `git status` —— 显示 `working tree clean` = 本地没有遗漏
3. 本地执行 `git remote -v` —— 能看到 `origin` 那两行 = 地址绑对了

---

## 7. 以后日常怎么用（记住这三行就够）

**改完文档（在 `D:\Game\GAMEdev`）：**

```bash
git add -A
git commit -m "更新了阶段7设计"
git push
```

**改完代码（在 `D:\Game\GAMEdev\ZombieExtraction`）：**

```bash
git add -A
git commit -m "阶段7-B：物品定义与网格算法"
git push
```

**三条命令各自的作用：**

| 命令 | 干什么 | 类比 |
|---|---|---|
| `git add -A` | 把改动放进"待提交区" | 把东西装进箱子 |
| `git commit -m "说明"` | 拍一张快照存到本地历史 | 给箱子贴标签封箱 |
| `git push` | 把本地历史传到 GitHub | 把箱子寄出去 |

> 只 `commit` 不 `push`，东西只在你电脑上（硬盘坏了还是会丢）。
> **两个仓库要分别提交、分别推送**，别只推一个。

---

## 8. 常见报错对照表

| 报错 | 原因 | 怎么办 |
|---|---|---|
| `Authentication failed` | 密码框里填了账号密码 | 填 Token（`ghp_...`） |
| `Support for password authentication was removed` | 同上 | 同上 |
| `fatal: unable to access ... 502` / `Failed to connect to github.com` | 网络/代理不通 | 见第 9 节 |
| `src refspec master does not match any` | 还没提交过 | 先 `git add -A && git commit -m "init"` |
| `rejected ... fetch first` | 远程已有内容（建仓库时勾了 README） | `git pull --rebase origin master` 后再 push |
| `remote: Permission to xxx denied` | Token 没有 `repo` 权限，或账号不对 | 重新生成 Token，勾 `repo` |
| `fatal: remote origin already exists` | 已经绑过地址 | `git remote set-url origin 新地址` |
| `file is 128.00 MB; this exceeds GitHub's file size limit` | 有超大文件 | 用 Git LFS；或从版本库移除该文件 |

---

## 9. 网络问题（你这台机器的实际情况）

**2026-10-20 实测：**

| 测试 | 结果 |
|---|---|
| 直连 `github.com` | ❌ 超时（被墙） |
| 直连 `api.github.com` | ✅ 能连（返回 403 限流，说明网络通） |
| 走环境变量代理 `127.0.0.1:63386` | ❌ **502 Bad Gateway**（代理上游不通） |

**所以：现在直接 `git push` 大概率失败。** 先解决网络：

### 方案 A：开代理客户端（最常用）

Clash / V2Ray 之类开起来，确认能打开 github.com 网页，再 push。

如果代理客户端开了但 `git` 还是不走代理，给 git 单独指定端口（**端口换成你自己客户端的**，Clash 常见 7890、V2RayN 常见 10809）：

```bash
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

取消代理：

```bash
git config --global --unset http.proxy
git config --global --unset https.proxy
```

### 方案 B：等网络好的时候再推

代码和文档已经在**本地 git** 里了，不会丢（除非硬盘坏）。可以积攒几次提交，等能上 GitHub 时一次性推。

### 方案 C：用 Gitee（国内，速度快，不用代理）

流程几乎一样（gitee.com → 新建仓库 → 推送），只是地址不同，而且 Gitee 支持账号密码。
**将来想换回 GitHub，只改 `git remote set-url` 一行即可，历史不会丢。**

### 9.1 推送超时 / 卡住不动？先怀疑代理

**实测记录（2026-10-21）**：

| 情况 | 结果 |
|---|---|
| 走代理 `127.0.0.1:63386` | ❌ 超时 / 502 |
| 直连 github.com | ✅ 200 OK |

Git 底层的 libcurl **会读 `http_proxy` / `https_proxy` 环境变量**。
如果系统里（或某个终端会话里）残留了指向失效代理的变量，`git push` 就会一直挂着直到超时。

**临时绕过（只在这次命令生效）：**

```bash
http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= git push
```

**永久检查：**

```bash
git config --global --get http.proxy    # 有值说明 git 自己在走代理
echo $http_proxy $https_proxy           # 有值说明环境变量在起作用
```

要清掉 git 自己配的代理：

```bash
git config --global --unset http.proxy
git config --global --unset https.proxy
```

### 9.2 Token 撤销后怎么继续推（推荐用 GCM，别再手写 Token）

撤销 Token 后，`git push` 会报：

```
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/...'
```

**这不是仓库坏了，只是凭据失效。** 处理方式：

1. 确认 Git for Windows 的凭据管理器在（**默认就有**，不用装）：
   ```bash
   git config --get credential.helper      # 应输出 manager
   ```
2. 清掉旧的失效凭据（Windows 凭据管理器里那条 `git:https://github.com`）：
   - 控制面板 → **凭据管理器（Credential Manager）** → **Windows 凭据**
   - 找到 `git:https://github.com` → **删除**
3. 重新 `git push` → 会**自动弹出浏览器**让你点一下登录 → 之后自动记住，**再也不用手写 Token**

> 这就是推荐做法：**Token 只在别人（或 AI）代你推送时临时用一次，日常交给自己电脑上的 GCM**。
> Token 一旦贴到聊天记录里就等于泄露，用完必须去 GitHub 删除。

---

## 10. 安全提醒（认真看）

1. **Token 等于密码**。泄露了别人能改、能删你的仓库。
2. **不要把 Token 写进任何文件**、不要贴到聊天里、不要放进代码注释。
3. 用 Windows 凭据管理器保存，不要用 `https://用户名:token@github.com/...` 这种把 Token 塞进地址的写法（会明文留在 `.git/config` 里）。
4. 定期去 Settings 里看一眼 Token 列表，不用的删掉。
5. `Private` 仓库只是别人看不到，**GitHub 官方和你的 Token 持有者仍可访问**，别放真正的密钥/密码。

---

## 11. 一页速查（贴在显示器上那种）

```
建仓库：github.com → + → New repository → 三个勾全不勾 → Create
拿令牌：头像 → Settings → Developer settings → Personal access tokens
        → Tokens (classic) → Generate → 勾 repo → 复制 ghp_...
绑定：  cd 项目目录
        git remote add origin https://github.com/用户名/仓库名.git
推送：  git push -u origin master
        （用户名 + Token 当密码）

以后：  git add -A
        git commit -m "说明"
        git push
```
