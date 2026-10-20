# 阶段 6B 僵尸 AI 审查与改造报告

> 时间：2026-10-20 08:40
> 仓库：`D:\Game\GAMEdev\ZombieExtraction`，分支 `master`，HEAD `2adf37b`
> 备份：`.workbuddy/backups/20261020-0835/`（5 个文件改造前快照）

---

## 1. 现状审查

### 实际架构（读完代码确认，不是照抄报告）

```
Core（纯 C#，无 UnityEngine 依赖）
  ZombieConfig        数值：速度/血量/攻击/视距/记忆/反应/搜索
  ZombieState         状态镜像：血量、攻击冷却、是否在攻击距离、位置与朝向镜像
  ZombieRules         每 tick：攻击冷却递减、InAttackRange
  ZombieBrain         脑子：Activity + 最后已知位置 + 各计时器
  ZombieBrainRules    状态转移（Tick / HearNoise / GetSearchPoint）
  ZombieSensesRules   视野扇形（只算角度，不管遮挡）
  NoiseEvent/Rules    噪音数据 + 枪声半径公式 + 能否听见
Gameplay
  ZombieMotor         NavMeshAgent 移动 + 视觉三步判定 + 听觉接入 + 攻击结算
  ZombieSpawner       数量维持 + 出生点吸附导航网格
  NoiseSystem         噪音环形缓存（拉取式，非事件）
  ZombieSensesDebug   纯 Gizmos 可视化
```

**结论：架构是健康的，不需要重写。** 职责边界清楚：Core 回答"该不该打 / 看没看见 / 听没听见"，Gameplay 回答"怎么走 / 射线打到什么 / 声音在哪"。

### 报告与真实代码的差异

| 报告里的说法 | 真实情况 |
|---|---|
| 报告写"6A 能给搜"（已修正） | 搜刮/拾取/背包**完全不存在**，属阶段 7 |
| 报告说感知"代码完成" | 属实，但**从未通过编译与实机验证** |
| 报告列了 4 个坑 | 属实，但其中 3 个是同一个根因（老组件新字段读零值）的不同表现 |

### 查出的真实问题（有代码证据）

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| 1 | `LastKnown` 一个字段混用"看到的位置"和"听到的位置" | `ZombieBrain` 只有 `LastKnownX/Z`；`Tick` 与 `HearNoise` 都写它 | 中（信息不诚实） |
| 2 | 搜索只有"到点 + 原地等 N 秒" | `Tick` 的 `Search` 分支只递减 `SearchLeft` | 高（用户明确要求改进） |
| 3 | 搜索**没有总时长上限**，靠 `TimeSinceSeen` 兜底；而 `HearNoise` 每 tick 把 `TimeSinceSeen` 归零 | `HearNoise` 里 `next.TimeSinceSeen = 0f` | 高（可能无限搜索） |
| 4 | `HearNoise` 会打断 `Alert` | 只对 `Chase`/`Attack` 早退，`Alert` 漏了 → 反应延迟被反复重置 | 中 |
| 5 | 搜索时朝向死盯记忆点，没有"观察"动作 | `UpdateFacing` 里 Search 分支固定 `DirectionTo(LastKnown)` | 低（观感） |
| 6 | 环顾点没有可达性保证 | 原实现根本没有环顾点 | — |

### 暂时没有足够证据的问题

- `Physics.Linecast` 在多只僵尸叠在一起时会不会互相挡视线：理论上会（判定 `hitT != target` 就返回 false），但没实测，属于**合理但可能过严**的行为，保留。
- 连发武器把 `NoiseSystem` 的 12 条缓存刷满：因为射击位置几乎相同，实测影响应可忽略，未改。

---

## 2. 保留清单（没动，而且理由明确）

| 保留项 | 原因 |
|---|---|
| `NavMeshAgent` 寻路 + `MaybeRecoverToNavMesh` 兜底 | 已通过实机验证，重写风险远大于收益 |
| `Freeze()` 里 `_agent.enabled = false` | 这是"撤离后僵尸还在挪"的唯一正确修法 |
| `NoiseSystem` 的"环形缓存 + 拉取" | 避开事件订阅的生命周期问题，噪音量小，够用 |
| 枪声半径公式 `base + modifiers[]` | 用户明确的数值设计，加法 + 修正项数组便于扩展 |
| 视觉三步判定（距离 → 扇形 → 射线） | 结构正确，只是参数基准曾算错（已修） |
| `EnsureStyles` 式"新字段属性兜底" | 这是项目级纪律，保留并继续使用 |
| `ZombieSensesRules` 不碰遮挡 | 规则层不该知道墙在哪，分工正确 |

---

## 3. 修改清单

### `Core/ZombieBrain.cs`（76 → 109 行）

- 新增枚举 `ZombieKnowledgeSource`（`None` / `Seen` / `Heard`）
- 新增字段：`KnownSource`、`SearchStep`、`SearchTotalLeft`
- 语义调整：`SearchLeft` = **当前搜索点**的剩余观察时间；`SearchArrived` = 是否到达当前点

### `Core/ZombieConfig.cs`（67 → 84 行）

- 新增：`SearchPointCount`（默认 3）、`SearchRadius`（4 米）、`SearchTotalSeconds`（15 秒）
- `SearchSeconds` 语义改为"**每个搜索点**的观察时长"，默认 3 → **1.5 秒**
- 全部走可选参数，旧调用一行不改

### `Core/ZombieBrainRules.cs`（199 → 299 行，重写状态机主体）

- `Tick`：参数 `arrivedAtLastKnown` → `arrivedAtSearchPoint`（语义更准）
- 视觉确认时**清空搜索进度**（`SearchStep=0`、`SearchTotalLeft=0`）→ 重新发现目标立刻放弃旧搜索计划
- 搜索拆成三个私有方法：`BeginSearch`（进入）、`TickSearch`（推进）、`GiveUp`（放弃）
- **新增 `GetSearchPoint()`**：纯数学算第 N 个搜索点（第 0 个 = 最后已知位置；之后是半径 4 米的固定方位环顾点）
- `HearNoise`：**`Alert` 时也不被声音打断**；把线索标记为 `Heard`；同一位置（1 米内）不重开搜索
- 新增 `DescribeSource()`（调试用中文名）

### `Gameplay/ZombieMotor.cs`（688 → 792 行）

- 新增 Inspector 参数 3 个（`searchPointCount` / `searchRadius` / `searchTotalSeconds`），全部属性兜底
- 新增 `ResolveSearchPoint()`：把 Core 算出的搜索点用 `NavMesh.SamplePosition` **吸附到可行走区域**，失败则退回最后已知位置；按 `SearchStep` 缓存，同一步不重复采样
- `StepOneTick`：`arrived` 改为判断"是否到达**当前搜索点**"
- `DriveAgent`：Search 状态去当前搜索点，Chase 状态去最后已知位置
- `UpdateFacing`：到点后**左右摆头观察**（±55°、90°/s），而不是死盯一个方向
- 新增 4 个只读属性供调试：`KnownSource` / `SearchStep` / `SearchPointPosition` / `HasSearchPoint`

### `Gameplay/ZombieSensesDebug.cs`（197 → 220 行）

- 新增青色搜索点可视化（线 + 小球）
- 头顶状态文字加"线索来源"和"第几个搜索点"
- 「打印当前感知状态」菜单输出补上来源/搜索步/搜索点

---

## 4. 删除或重写清单

| 对象 | 处理 | 证据 |
|---|---|---|
| `ZombieBrainRules.Tick` 的 `Search` 分支 | **重写**（不是删除整个状态机） | 原实现只有"递减一个计时器"，无法承载多点搜索；状态集合与转移关系保留 |
| `arrivedAtLastKnown` 参数 | **重命名 + 语义扩展** | 现在判断的是"当前搜索点"，不只是最后已知点 |

**没有删除任何脚本、Prefab、场景或配置。** `HealthPickup.cs` 虽然是已弃用的旧脚本，但不在本次任务范围，未动。

---

## 5. 行为改进（本次实际做到的）

### 5.1 信息诚实：视觉与听觉不再混为一谈

| 信息类型 | 存放位置 | 可信度 |
|---|---|---|
| 玩家真实位置 | `target.position`（只用于距离/射线/伤害） | 不作为记忆 |
| 视觉确认的位置 | `LastKnownX/Z` + `KnownSource = Seen` | 高（可以追） |
| 噪音位置 | `LastKnownX/Z` + `KnownSource = Heard` | 低（只能调查） |
| 搜索推测点 | `GetSearchPoint()` 算出，**不写回记忆** | 仅导航目标 |

### 5.2 搜索从"站桩"变成"有限多点搜索"

```
跟丢
  ↓
前往最后已知位置（第 0 点）
  ↓ 到达
原地摆头观察 1.5 秒
  ↓
去第 1 个环顾点（半径 4 米，正北）→ 观察 1.5 秒
  ↓
第 2 个（东）→ 第 3 个（南）
  ↓ 全部搜完 或 总时长超过 15 秒
放弃 → 回待机（清空记忆）
```

- 环顾点由 **固定方位 + 固定顺序** 生成（不用随机数）→ 可预测、可调试
- 每个点都过一遍 `NavMesh.SamplePosition`，**不会为了搜索而穿墙**
- 目标不可达时退回最后已知位置，不硬钻
- **重新看到玩家 → 立即作废搜索进度，恢复追击**

### 5.3 修掉"反应延迟被声音反复重置"

原来 `Alert` 状态下听到脚步会走 `HearNoise` → 重置 `ReactionLeft` + 改目标，表现为"玩家一晃动僵尸永远反应不完"。现在 `Alert` 与 `Chase`/`Attack` 一样，**声音不能打断**。

### 5.4 搜索有明确终止条件

| 终止条件 | 触发 |
|---|---|
| 搜完所有点位 | `SearchStep > SearchPointCount` |
| 总时长超时 | `SearchTotalLeft <= 0`（15 秒硬上限） |
| 记忆过期 | `TimeSinceSeen > MemorySeconds`（5 秒没有新线索） |
| 重新看到玩家 | 视觉确认 → 直接转 Alert/Chase |

---

## 6. 验证结果（分开记录，不混为一谈）

| 验证类型 | 结果 | 说明 |
|---|---|---|
| **静态检查** | ✅ 通过 | 5 个文件括号平衡、引号配平、新增成员声明与调用点全部核对；`ZombieBrainRules` 8 个方法定义/调用数正确 |
| **Unity 编译** | ❌ **未执行** | 编辑器正在运行，命令行 `csc` 被安全策略拦截。**这意味着可能存在编译错误，必须在编辑器里确认** |
| **自动化测试** | ❌ 未执行 | 项目没有测试框架，本次也没有为 AI 新建（用户要求不为测试列表造假测试） |
| **Unity 实机行为** | ❌ **未执行** | 无法操作编辑器，需要你按第 7 节手动验证 |

**因此本次交付的是"代码级完成 + 静态检查通过"，不是"已验证可用"。**

---

## 7. 手动验证清单（直接在编辑器里做）

先决条件：编译通过（Console 无红字）、模板僵尸挂着 `ZombieSensesDebug`、场景视图开着 Gizmos。

| # | 操作 | 期望 |
|---|---|---|
| 1 | 正面走进它 25 米、视野内 | 约 0.35 秒后 → **察觉** → **追击**，红线连上 |
| 2 | 站它正后方 5 米不动 | **不转头、不追击**，黄扇形不朝你 |
| 3 | 躲 `Cover`（2 米高）后面不动 | 不发现你；橙线（记忆）不该更新到你的新位置 |
| 4 | 隔 `Wall` 生成一只 | 出生朝向不朝你，不追 |
| 5 | 25 米外开枪 | 状态从待机 → **搜索**，橙线指向**枪声位置**，它走过去 |
| 6 | 在它 8 米内冲刺跑过 | 同样被引过去（脚步 8 米） |
| 7 | 让它看见你 → 绕墙跑掉 → 停下不动 | 它走到你**最后被看见的位置**，不会跟着你的新位置转 |
| 8 | 到达后观察 | 头顶显示「搜索 / 第 0 个点」，**头会左右摆动**；然后依次去 3 个青色环顾点 |
| 9 | 搜索中重新出现在它视野 | 立刻转「察觉 → 追击」，青色搜索点消失 |
| 10 | 搜索中在别处开枪 | 橙线跳到枪声位置，重新开始搜索（不会原地打转） |
| 11 | 让它搜满 15 秒不出现 | 自动回「待机」，记忆清空 |
| 12 | 连发扫射 | 状态稳定，不会来回抽搐 |
| 13 | 撤离成功 | 所有僵尸立刻定格（移动、攻击都停） |
| 14 | 多只同时追 | 各自独立判断，不会全部同时知道你的精确位置 |

**出问题时最快的排查手段**：选中僵尸 → 组件 ⋮ → 「打印当前感知状态到 Console」，会输出状态、线索来源、是否看到、搜索步、眼睛位置、搜索点坐标。

---

## 8. 已知问题与假设

| 类型 | 内容 |
|---|---|
| **未验证** | 编译是否通过；行为是否符合上表 —— 这是最大的未知 |
| **设计取舍** | 环顾点是**固定方位**（正北起顺时针），多次搜索会显得有规律。想更自然以后可以给每个僵尸一个固定的起始角偏移 |
| **设计取舍** | 玩家**持续跑动**时，每次脚步都会重置 `SearchTotalLeft`（因为位置变了 → `BeginSearch`）。这会让"无限追声"成为可能 —— 这是刻意的（听见就该追），但如果觉得太黏人可以给噪音加"同类去重时间窗" |
| **潜在副作用** | `HearNoise` 现在不打断 `Alert`。若玩家在僵尸刚察觉时躲起来，僵尸会先愣完 0.35 秒再转搜索，观感上"反应慢半拍" —— 符合僵尸设定 |
| **未处理** | 多只僵尸同时挡在射线上会互相屏蔽视线（`hitT != target` 即判失败）。理论上合理，但拥挤时可能让僵尸"集体失明"，未实测 |
| **未处理** | 搜索点若全部落在墙内（比如玩家死在极窄角落），会退化为"在最后已知点反复观察" —— 有总时长兜底，不会卡死 |

---

## 9. 后续路线

| 时机 | 内容 | 为什么现在不做 |
|---|---|---|
| **最近** | 编译 + 实机验证本文第 7 节 | 基础没验证，不做新东西 |
| 验证之后 | 6B 第四步：玻璃 / 撬锁铁门（发 `NoiseKind.Impact`） | 会复用现有噪音系统，成本低 |
| 之后 | 铁丝网"看得见走不过"行为（速查卡 §3.26） | 需要专用 Layer + `NavMesh.Raycast`，是独立设计 |
| 有美术之后 | 个体差异（视觉/听觉/记忆/转身速度不同） | 参数已全部在 `ZombieConfig`，只要加"僵尸类型"配置即可，不用改逻辑 |
| 有音频系统（阶段 10） | 发现叫声、脚步、搜索时的低吼 | 需要音频系统，现在接了也听不见 |
| 阶段 9 之后 | 尸潮 / 遭遇节奏导演 | 必须是独立高层系统，当前 `ZombieMotor` 只管自己，不会阻碍它 |

---

## 10. Git 状态

**未提交任何改动**（按你的要求不擅自提交）。

```
当前分支：master
HEAD：2adf37b（阶段6B-2: 僵尸状态机 + 记忆）

本轮的改动（相对 HEAD）：
  修改：Core/ZombieBrain.cs
        Core/ZombieBrainRules.cs
        Core/ZombieConfig.cs
        Core/ZombieState.cs
        Core/ZombieRules.cs
        Gameplay/ZombieMotor.cs
        Gameplay/ZombieSensesDebug.cs
        Gameplay/PlayerMotor.cs
        Gameplay/WeaponController.cs
        Gameplay/WeaponSlotDefinition.cs
  新增：Core/NoiseEvent.cs
        Core/NoiseRules.cs
        Core/ZombieSensesRules.cs
        Gameplay/NoiseSystem.cs
        Gameplay/ZombieSensesDebug.cs
        （以及各自的 .meta）
```

**建议的提交说明**（等你验证后再提交）：

```
阶段6B-3: 僵尸感知（视觉120°+视线遮挡+听觉噪音）+ 有限多点搜索

感知：
- 视觉三步判定：距离 → 视野扇形（用平滑后的实际朝向）→ Physics.Linecast 遮挡
- 眼睛高度从脚底算（1.5 米），不再从胶囊中心算（那样会变成 2.5 米，2 米掩体失效）
- sightMask 读到 0 时按 Everything 处理（LayerMask 的 0 = Nothing 会让遮挡完全失效）
- 听觉：NoiseSystem 环形缓存 + 拉取式查询；枪声半径 = noiseExposure + noiseModifiers[]
- disableHearing（false = 听得到），避免新 bool 在老组件上读成 false 静默关闭功能

状态机与搜索：
- 区分线索来源 Seen / Heard，玩家真实位置只在视觉确认时写入记忆
- 搜索改为有限多点：最后已知点 → 3 个环顾点（半径 4 米，固定方位，NavMesh 采样校正）
- 每点观察 1.5 秒，到点后左右摆头；总时长 15 秒硬上限；搜完或超时明确放弃
- 修复：HearNoise 不再打断 Alert（否则反应延迟被脚步反复重置）
- 视觉重新发现目标时作废搜索进度，避免继续执行旧搜索计划

可视化：
- ZombieSensesDebug：绿圆/黄扇形/红线/橙线/青色搜索点；头顶显示状态+线索来源+搜索步

验证：静态检查通过；编译与实机待验证
```

---

## 附：一句话总结

**架构没坏，坏的是"信息怎么用"。** 这次把"看到的位置"和"听到的位置"分开、把搜索从"站桩计时"改成"有依据的有限搜索"，同时让每一步终止条件都明确 —— 僵尸依然会笨，但它的笨现在是有理由的笨。
