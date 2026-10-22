# 背包 / 装备 UI 重构 — 设计说明（方案定稿，代码未开工）

> **本文档状态**：2026-10-22 13:30，**全部决策已由用户拍板，代码一行未写**。
> 下一次开工时，从本文 §16「实施顺序」第一条开始，不需要重新讨论设计。
>
> **读法**：
>
> | 你想知道 | 看哪一节 |
> | --- | --- |
> | 为什么改、改成什么样 | §1、§3 |
> | 有哪些硬性约束（不许违反） | §2、§10、§11、§17 |
> | 要写哪些类 | §4、§5、§6 |
> | 怎么生成 Prefab、怎么接进场景 | §12 |
> | 怎么算做完 | §14、§16 |
> | 哪些东西故意没做 | §15、§17 |
>
> **与其它文档的关系**：本文只管"背包/装备 UI 这一块的方案"。项目级功能台账在 `项目进度总览.md`，状态快照在 `项目速查卡.md`，开发规则在 `AGENTS.md`，阶段 7 搜刮/容器设计在 `阶段7-设计说明.md`（其 §22 是阶段 7 总览）。

---

## 1. 目标与非目标

### 1.1 目标

把现有的**临时三列界面**（`InventoryUi.cs`，1552 行，纯代码构建）替换为**接近参考图的正式界面**，同时保住所有已经实机验证过的底层能力。

最终形态（分三步走，**不要一步到位**）：

1. **结构跑通**：分区正确、组件层级正确、真实数据绑定、交互正确 —— 先不追求精致
2. **视觉细化**：深色半透明面板、橙色强调、字体字号、选中高亮、槽位底色、图标
3. **动效与音效**：过渡动画、悬停/点击反馈、音效

### 1.2 非目标（本阶段明确不做）

- 不重写背包/容器/网格算法（规则在 `Core/`，一行不改语义）
- 不做容器物品化（弹挂/背包不能真的拖下来换）
- 不做地面掉落物（T 丢弃）
- 不做死亡保护、护甲减伤、健康状态机制
- 不做负重惩罚（只显示数字）
- 不迁移 HUD（血条/弹药/准星仍是 OnGUI）
- 不引入任何第三方 UI 框架

### 1.3 参考图

| 文件 | 用途 |
| --- | --- |
| `pic/QQ_1792641996134.png` | **结构图** —— 分区边界、比例、谁挨着谁、底部键位提示。以这张为准做布局 |
| `pic/ChatGPT 图像 2026年10月22日 11_55_10.png` | **质感参考** —— 暗色 + 橙色、角色模型、装备槽、双网格、右侧空态。只参考风格，不参考像素位置 |

**不要把图片当 UI 背景，也不要用裁图代替组件。** 所有分区都必须是真正可交互的 uGUI 节点。

---

## 2. 已拍板的决策（改动需重新请示）

> 编号 D1~D26。**这是本文最高优先级的一节**，实现时逐条对照。

| # | 决策 | 备注 |
| --- | --- | --- |
| D1 | 技术路线：**uGUI + Prefab**。编辑器脚本生成初始 Prefab，之后 Prefab 就是正式表现层 | 不用 UI Toolkit |
| D2 | 运行时不重建层级：**首次打开时实例化一次，之后隐藏复用** | 不做每次运行 Generate |
| D3 | Prefab 生成器**不得覆盖人工修改过**的资产；只在"不存在"时创建，另设单独的"强制覆盖"菜单 | 二次确认 |
| D4 | 不使用 `InventoryScreenPrefabSet` ScriptableObject：子 Prefab **嵌套**进 `InventoryScreen.prefab`，`InventoryScreenHost` 只序列化一个 `rootPrefab` | 避免双重配置 |
| D5 | UI 实例化到**场景级 `UIRoot`**，不挂在 Player 下面 | 老 UI 现在把 Canvas 建在 Player 下，新 UI 不重复这个错误 |
| D6 | **保留旧 UI 作回退**，切换开关初始默认**旧 UI**；用户手测通过后再改默认 | 同一时刻只允许一个界面响应输入 |
| D7 | 装备槽**真能穿脱**：头盔 / 防护服 / 近战武器，走"最小装备数据"方案 | 见 §5 |
| D8 | 装备槽尺寸**按品类**：头盔 2×2、防护服 2×2、近战 2×1 | 需编辑器校验"同品类物品尺寸与槽一致" |
| D9 | 装备槽**互相独立**：背包放不进头盔位，弹挂放不进近战位 | 由容器白名单天然保证 |
| D10 | **特殊道具槽显示撤离信号枪**，不是物品容器；信号枪**不在快捷栏重复显示** | 见 §7 |
| D11 | 弹挂 / 背包**本轮不做穿脱**：显示"已装备（固定）"，不可脱、不可换 | 见 §15 难度评估 |
| D12 | **口袋容器取消**，左下改为快捷使用栏 | 口袋资产转为隐藏 |
| D13 | **钥匙卡包本轮不显示**，预留后续入口；它和口袋都转为**隐藏资产** | 见 §9 |
| D14 | 隐藏资产的实现方式是**不实例化**（不是"实例化了但不画"） | 防止物品被塞进看不见的格子 |
| D15 | 代码里**不许出现隐藏容器的 id 硬编码**，快捷拾取顺序改为**数据驱动** | 见 §9.3 |
| D16 | 武器槽映射：1 号=`slots[0]`、2 号=`slots[1]`、3 号=`slots[2]`（禁用占位）、`slots[3]` 不显示、`slots[4]` 血包进快捷栏 | 映射集中在一个适配层 |
| D17 | **不修改 `WeaponController` 的业务行为**；只允许加只读 getter | 见 §6.3 |
| D18 | **E 键从 `Interact` 上解绑**（开容器/拾取只用 F） | 含 PlayerPrefs 覆盖迁移，见 §11.1 |
| D19 | 收益显示：**背包页只显示"本局获得"**；"本局消耗"只算不显示（后台数据） | 见 §5.5 |
| D20 | 搜索规则**完全不变**（按物品稀有度分级、中断即作废） | 见 §10 |
| D21 | 角色预览先做**占位框**（`CharacterPreviewPanel`，可替换组件），不做 RenderTexture / 预览相机 / 专用 Layer | 玩家现在没有任何可见模型 |
| D22 | 键位提示**只写真实可用的键**；R 整理背包、T 丢弃都不写 | 提示不撒谎 |
| D23 | 允许修改并保存 `Test_Graybox.unity`（加 `InventoryScreenHost`、建 `UIRoot`） | 只加必需内容，脚本可重复执行不重复创建 |
| D24 | 允许开发用"往背包塞测试物品"菜单 | 只在手动执行时生效，不改开局背包 |
| D25 | 装备重量**不能漏算**：负重 = 携行组 + 装备组 | 见 §5.4 |
| D26 | 物品/装备的正式数值由用户**后期用 JSON 逐个定义**；测试资产是占位 | 代码不写死任何物品 id |

---

## 3. 布局规格

### 3.1 画布与适配

- Canvas：`ScreenSpaceOverlay`，`sortingOrder = 100`（与旧 UI 同级，反正不同时显示）
- `CanvasScaler`：`ScaleWithScreenSize`，参考分辨率 **1920×1080**，`matchWidthOrHeight = 0.5`
- 目标分辨率：1920×1080 / 2560×1440（都是 16:9，等比放大即可）
- 非 16:9 窗口：靠锚点自适应，允许左右留白，**不允许元素重叠或裁切**

### 3.2 分区（在 1920×1080 下的目标比例）

```
┌──────────────────────────────────────────────────────────────┐
│ 顶部导航栏 56px   背包 | 任务 | 地图 | 设置        本局获得 +X │
├───────────────┬──────────────────────────┬───────────────────┤
│ 左：角色与装备 │ 中：弹挂 + 背包           │ 右：容器          │
│ ┌───────────┐ │  弹挂 4×2                │  （未开容器时空白）│
│ │角色预览    │ │  ┌────┐                  │                   │
│ │（占位）    │ │  └────┘                  │  打开容器后：      │
│ │           │ │  背包 10×6                │  标题 + 网格      │
│ └───────────┘ │  ┌──────────┐            │                   │
│ 装备槽列：     │  └──────────┘            │                   │
│  头盔/防护服   │                          │                   │
│  近战/特殊道具 │                          │                   │
│ 武器槽 ×3      │                          │                   │
├───────────────┴──────────────────────────┴───────────────────┤
│ 左下快捷栏 │ 中下角色状态（血/负重/状态位） │ 右下安全箱 2×2  │
├──────────────────────────────────────────────────────────────┤
│ 底部键位提示 32px                                             │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 硬性布局约束

1. **右侧容器区恒定占位**：只开背包时右列留空，**不得把左列/中列拉宽** —— 否则"开箱前"和"开箱后"位置不一致，操作手感全乱（这是现有行为，必须保住）。
2. **武器槽不得遮挡角色预览**：预览区与武器槽区上下分区，物理上不重叠（不是靠层级盖住）。
3. **格子大小自适应**：中列背包 10 列、右列容器最多 10 列，若超出可用宽度就**按可用宽度反算 cell**，不允许溢出裁切。
4. 左/中/右三块用**锚点**固定（左贴左、右贴右、中居中拉伸），不写死绝对坐标。
5. 同一行的三个底部面板用水平布局，互不重叠，宽度不足时优先压缩中间状态区。

> 以上是**目标比例**，不是像素铁律。阶段 B 在 Unity 里目视微调，改 Prefab 即可，不用改代码。

---

## 4. 组件清单

> 原则：**一个组件只干一件事**；数据全部来自真实系统，组件本身不存业务状态。

| 组件 | 职责 | 依赖 | **明确不做** |
| --- | --- | --- | --- |
| `InventoryScreen` | 界面总入口：开/关、注册 `InteractionMode`、Esc/Tab 路由、拖拽仲裁、持有各面板引用 | `PlayerInventory`、`ItemDatabase`、`InteractionMode` | 不判断"能不能放"（Core 判）、不自己算格子 |
| `EquipmentPanel` | 左：角色预览 + 4 个装备槽 + 3 个武器槽的容器 | `EquipmentLoadout`、`WeaponSlotUIAdapter` | 不实现护甲数值 |
| `EquipmentSlotView` | 单个装备槽：图标、空态、悬停、接受拖放 | `ItemContainer`（1 个槽 = 1 个迷你容器） | 不校验白名单（Core 校验） |
| `WeaponSlotView` | 单武器槽显示：名称、弹药、激活态、重武器视觉标记 | `WeaponSlotUIAdapter` | 不计算弹药、不切枪 |
| `WeaponSlotUIAdapter` | **唯一**把 `WeaponController` 数据翻译成 UI 语义的地方 | `WeaponController`（只读） | 不改控制器、不用反射 |
| `TacticalRigPanel` | 弹挂区：标题 + 网格 | `CarryGroup` | 不做装备/卸下 |
| `BackpackPanel` | 背包区：标题 + 网格 | `CarryGroup` | 同上 |
| `ContainerPanel` | 右列：无容器时空白；有容器时标题 + 网格 + 搜索状态 | `ContainerInstance`、`ContainerSearchDriver` | 不模拟搜索进度 |
| `QuickAccessPanel` | 左下：血包（真实数据）+ 空占位框 | `WeaponSlotUIAdapter` | 不造手雷、不造不存在的东西 |
| `CharacterStatusPanel` | 中下：生命、负重、健康状态预留区 | `PlayerHealth`、`CarryGroup`+`EquipmentLoadout` | 不显示假状态图标、不加机制 |
| `SecureContainerPanel` | 右下：安全箱 2×2 网格 | `CarryGroup` | 不加死亡保护规则 |
| `InputHintPanel` | 底部：真实可用键位 | 常量 | 不写未实现的键 |
| `CharacterPreviewPanel` | 角色预览占位（背景 + 剪影 + 文字） | 无 | 不做 RenderTexture / 相机 / Layer |
| `ItemTooltipView` | 物品悬停信息（名称、品质、尺寸、重量、价值） | `ItemDef` | 不与业务耦合 |
| `IItemCellHost` | 格子与宿主之间的交互接口（9 个方法） | — | 见 §4.1 |
| `InventoryScreenHost` | 持有 `rootPrefab`，首次打开实例化到 `UIRoot`，之后复用 | — | 不存运行时状态到资产 |

### 4.1 `IItemCellHost`（对现有代码的唯一改动点）

`ItemCellView` 现在有 **9 处**直接调用 `InventoryUi`：

```
GetIcon(string itemId)
BeginDrag(ItemCellView, Vector2)
UpdateDrag(Vector2)
EndDrag(Vector2)
SetHoveredCell(ItemCellView)
ClearHoveredCell(ItemCellView)
ShowTooltip(ItemCellView, Vector2)
HideTooltip(ItemCellView)
OnItemRightClick(ItemCellView)
```

把这 9 个签名抽成接口，`InventoryUi` 声明实现它（方法体一个字不改），新 UI 的 `InventoryScreen` 也实现它。

**为什么必须抽**：`ItemCellView` / `InventoryGridView` 是"格子与网格"的唯一实现，新旧两套界面要共用它们。复制一份等于把已经踩过 6 轮坑的拖拽逻辑再写一遍。

**注意**：
- 不能用 `[SerializeField] IItemCellHost`（Unity 不序列化接口）。现有代码全部是 `AddComponent` + `Bind(...)` 传引用，**本身就绕开了序列化**，所以不存在这个问题 —— 但**不要**为了"方便"把它改成 Inspector 字段。
- `InventoryGridView` 只是把宿主透传给格子（`view.Bind(_ui, ...)`），改动量仅 1 行类型。

---

## 5. 数据层改动（Core，纯 C#，必须配单测）

> 铁律：`Assets/Scripts/Core/` **零 `using UnityEngine`**。加任何东西都先问"这段逻辑放服务器上还能跑吗"。

### 5.1 `ItemKind` 追加 3 个值

现有 7 个：`Misc=0, Weapon=1, Ammo=2, Medical=3, Material=4, Key=5, Card=6`。

追加：`Helmet=7, BodyArmor=8, Melee=9`。

- **只在末尾追加，不改任何已有数值**（无存档系统，零迁移风险；全项目无 `switch(ItemKind)`，不会掉进 default 分支）
- 不新增"饰品/Trinket"：特殊道具槽是信号枪的只读展示位，不是物品容器

### 5.2 `ContainerRole` 追加 `Equipment`

现有：`Carried=0, MapLoot=1, Stash=2`。追加 `Equipment=3`。

**为什么**：装备容器若用 `Carried`，会被 `PlayerInventory.EnsureBuilt` 一起收进 `CarryGroup` → 按 F 快捷拾取会往头盔槽里塞东西、中列也会把装备槽当背包列出来。

**改动后必须核对的四个方向**（用户明确要求）：

| 方向 | 期望 | 怎么保证 |
| --- | --- | --- |
| 快捷拾取 | 只走 `Carried` | `PlayerInventory` 只取 `Carried`，装备组单独建 |
| 界面分类 | 装备区只列 `Equipment`，中列只列 `Carried` | 两组分开渲染，不可能重复 |
| 负重统计 | 装备 + 携行都算 | `负重 = CarryGroup.TotalWeight + EquipmentLoadout.TotalWeight`，**单测断言** |
| 物品转移 | 装备槽之间/与背包之间搬运仍走 `CanPlaceAt` / `TryTransferTo` | 全部是 `ItemContainer`，规则不分叉 |

### 5.3 `ContainerDef` / `ContainerDefinitionAsset` 追加 2 个字段

| 字段 | 类型 | 默认 | 含义 |
| --- | --- | --- | --- |
| `Hidden` | bool | `false` | **不实例化**。口袋 / 钥匙卡包设为 true |
| `QuickPickup` | bool | `true` | 是否参与 F 快捷拾取。安全箱设为 false |

两者都要写进 `ToDef()`，并在编辑器校验里给出提示。

### 5.4 `EquipmentLoadout`（新，Core）

职责：**第二个 `CarryGroup`**，装 3 个装备容器。复用现成的 `CarryGroup`（它本来就是"一组容器"的通用外壳），不新造一套。

```
EquipmentLoadout
  ├ 按 Equipment 角色的容器定义建 ItemContainer（幂等，EnsureBuilt）
  ├ Slots（已按 UiOrder 排序）
  └ TotalWeight（给负重显示用）
```

玩家侧 `PlayerInventory` 暴露 `Equipment` 属性，并在 `EnsureBuilt` 里一起建。

### 5.5 `RaidValueLedger`（新，Core）— 本局收益

#### 语义（用户例子已验证）

**相对"开局携带"的实时价值差**，不是流水账。

- 基线：开局瞬间，所有 `Carried + Equipment` 里每一条的 `(uid, 数量, 单价)`
- 只要 uid 在基线里 → 无论丢几次捡几次，**永远算 0 收益**
- 新 uid → 获得
- 基线 uid 消失或数量变少 → 消耗

#### 公式

```
获得 += Σ(当前存在且 uid 不在基线)            价值(数量 × 单价)
获得 += Σ(uid 在基线 且 当前数量 > 基线数量)   (当前 - 基线) × 单价

消耗 -= Σ(基线存在 且 当前已不存在)            基线数量 × 单价
消耗 -= Σ(基线存在 且 当前数量 < 基线数量)      (基线 - 当前) × 单价
```

#### 用例（与用户原话一致，要写成单测）

| 动作 | uid | 本局获得 | 本局消耗 |
| --- | --- | --- | --- |
| 开局带 50000 的枪，丢在地上 | 消失 | 0 | **-50000** |
| 捡回同一把 | 还在 | 0 | **0** |
| 从武器箱摸到 20000 的枪并捡起 | 新 | **+20000** | 0 |
| 开局 30 发子弹打掉 10 发 | 数量 30→20 | 0 | **-10 × 单价** |
| 上局带出、没清理背包又带进来 | 在基线里 | 0 | 0 |

#### 显示规则

- **只有"本局获得"上界面**（顶部栏右侧 `本局获得 +20,000`）
- **"本局消耗"不在任何画面显示**，只作为后台数据（将来做行为画像/分析用），仅经公开属性暴露
- 刷新时机：打开界面时 + 每次物品变动后（不要每帧重算）

### 5.6 现有 `PlayerInventory.ComputeGainsSinceRaidStart` 怎么办

它现在是**按数量**统计、只覆盖 `Carried`。新 UI 需要的是**按价值**、且覆盖装备组。

处理：保留它（不破坏现有调用），新增 `RaidValueLedger` 用同一份基线数据算价值。两者共用 `CaptureRaidStartSnapshot` 记的基线，**不要让它们各记一份**。

---

## 6. 武器槽映射

### 6.1 真实数据结构（读代码确认，非推测）

`WeaponController.slots` 默认 5 个，运行时若找不到信号枪会**追加第 6 个**：

| 下标 | 默认内容 | `enabled` | `kind` | `isHeavy` |
| --- | --- | --- | --- | --- |
| 0 | 步枪 | true | Weapon | false |
| 1 | 精确步枪 | true | Weapon | false |
| 2 | 占位 3 | **false** | Weapon | false |
| 3 | 占位 4 | **false** | Weapon | false |
| 4 | 血包 | true | Consumable | false |
| 5 | 信号枪（自动追加） | true | SignalGun | false |

### 6.2 映射表

| UI 位置 | 真实来源 | 显示 | 可点击 |
| --- | --- | --- | --- |
| 1 号位 | `slots[0]` | 名称 + 弹药 `弹匣/备弹` + 激活高亮 | 是 → `TrySwitchTo(0,false)` |
| 2 号位 | `slots[1]` | 同上 | 是 → `TrySwitchTo(1,false)` |
| 3 号位 | `slots[2]` | **「战术重武器 / 未装备」**，禁用灰 + 橙色描边 | **否**（禁用槽，不显示成可用） |
| （不显示） | `slots[3]` | 不创建节点 | — |
| 快捷栏 | `slots[4]` | 血包：名称 + **真实剩余个数** + 当前容量% | 是 → `TrySwitchTo(4,false)` |
| 特殊道具槽 | `SignalGunSlotIndex` | 信号枪：名称 + H 提示 + 选中态 + 已使用态 | 是 → 同 H 键逻辑 |

### 6.3 禁用槽不会「意外可用」（已核实）

- `TrySwitchTo` 第 449 行有 `if (!slots[index].enabled) return false;`
- `FindNextSlotWithAmmo` 第 438 行跳过禁用槽
- `GameInput.Slots` 只有 5 个（数字键 1~5 → 下标 0~4）

**所以不需要改切枪机制。** 但 UI 仍必须把 3 号位画成明确的"未装备"，不能让人误以为能按。

### 6.4 `WeaponSlotUIAdapter`（新）

**唯一允许出现 `slots[0]` / `slots[4]` 这种下标的地方。** 其他 UI 组件一律通过它拿数据：

```
WeaponSlotUIAdapter
  ├ WeaponSlotRead GetPrimary()      → { 名称, 弹匣, 备弹, 是否激活, 是否可用 }
  ├ WeaponSlotRead GetSecondary()
  ├ WeaponSlotRead GetHeavy()        → 未装备时 IsEquipped=false, DisplayName="战术重武器"
  ├ ConsumableRead GetConsumable()   → { 名称, 剩余个数(真实), 当前容量, 容量上限 }
  ├ SignalGunRead  GetSignalGun()    → { 名称, 是否激活, 是否已使用 }
  └ int ActiveSlotIndex
```

**规则**：
- 只读，不改控制器的任何状态
- 不用反射、不复制控制器内部数组
- 信号枪靠 `SignalGunSlotIndex` 识别，**不用末尾下标**
- 下标映射写死在这里，其他地方出现魔法下标视为 bug

### 6.5 为 UI 新增的两个只读接口（用户已批准）

| 文件 | 新增 | 为什么必须加 |
| --- | --- | --- |
| `WeaponController` | `public int GetConsumableKits(int slotIndex)` | `ActiveSlotCount` **只返回当前手持槽**的数量。拿着步枪时要显示"血包 ×3"根本读不到。必须返回**真实当前数量**（不是 `startCount`），非法索引/非消耗品槽返回 0，**绝不修改任何状态** |
| `SignalGun` | `public bool HasUsed => _used;` | `_used` 是 private，快捷栏与特殊道具槽都要显示"已使用"。不改 `_used` 本身权限、不改发射逻辑 |

### 6.6 快捷栏点击行为

- 血包格点击 → `TrySwitchTo(4, false)`（等价数字键 5，**只切换、不治疗**）
- 信号枪格 **不在快捷栏**（见 §7）
- 手雷格 **不存在**：E 键实际绑的是 `Interact`（和 F 同键开容器/拾取），项目没有手雷系统。**不造不存在的格子**
- 空占位框：只画框，不可点、不带假数据

---

## 7. 特殊道具槽 = 撤离信号枪

### 7.1 规则

| 项 | 规则 |
| --- | --- |
| 位置 | 左侧角色装备区，与头盔/防护服/近战**并列的第 4 个槽** |
| 内容 | 撤离信号枪（**不是背包物品**，不转成普通物品，不映射到 `slots[4]`） |
| 显示 | 名称、图标（暂缺则文字）、`H` 键提示、选中态、**已使用态（置灰 + 「已使用」）** |
| 点击 | 等价按 H：已拿着 → 收回；没拿着 → 切出。**绝不直接发射、绝不触发撤离** |
| 发射 | 仍由原系统负责：切出后**长按左键**才发射 |
| 状态来源 | `SignalGun.HasUsed`（只读） |

### 7.2 点击实现（不改控制器）

H 键的真实逻辑就是：

```
ActiveIsSignalGun ? ReturnToLastWeapon() : TrySwitchTo(SignalGunSlotIndex, false)
```

这两个方法**都是 public**，UI 原样调用即可，**不模拟按键、不加新方法、不复制状态**。

> 若将来 H 键逻辑变了（比如新增前置条件），UI 会跟着变 —— 只要它还在调这两个公开入口。

---

## 8. 快捷使用栏（左下）

| 槽 | 内容 | 数据来源 | 点击 |
| --- | --- | --- | --- |
| 1 | 血包 | `WeaponSlotUIAdapter.GetConsumable()` | 切到 `slots[4]`（不治疗） |
| 2~3 | 空占位框 | 无 | 不可点 |

**硬性要求**：
- 数量必须读**真实当前剩余**，不能用 `startCount` 冒充
- 用完后显示 0 或空态，不能留旧数字
- 切换武器后仍显示正确（因为读的是槽位数据，不是"当前手持"）
- **不放信号枪**（它在特殊道具槽，避免重复显示）

---

## 9. 容器分类与隐藏资产

### 9.1 最终分类

| 容器 | 角色 | 尺寸 | 显示位置 | 状态 |
| --- | --- | --- | --- | --- |
| `container_chestrig` 弹挂 | Carried | 4×2 | 中列上方 | 显示（已装备、固定） |
| `container_backpack` 背包 | Carried | 10×6 | 中列下方 | 显示（已装备、固定） |
| `container_safebox` 安全箱 | Carried | 2×2 | 右下 | 显示（不可快捷拾取） |
| `container_pocket` 口袋 | Carried | 1×1 | — | **隐藏**（被快捷栏取代） |
| `container_keypouch` 钥匙卡包 | Carried | 1×2 | — | **隐藏**（位置未定，预留） |
| `container_equip_helmet` 头盔槽 | Equipment | 2×2 | 左列 | 新建 |
| `container_equip_suit` 防护服槽 | Equipment | 2×2 | 左列 | 新建 |
| `container_equip_melee` 近战槽 | Equipment | 2×1 | 左列 | 新建 |

### 9.2 隐藏 = 不实例化

- `Hidden=true` 的容器**根本不会创建 `ItemContainer`**
- 于是 `GetContainer(id)` 返回 null（现有 F 拾取已容错 `continue`），**物品绝不可能被塞进看不见的格子**
- 资产文件**保留**，不物理删除；要恢复只需取消勾选 —— 这就是"预留入口"

### 9.3 必须清掉的 id 硬编码（用户明确要求）

| 文件 | 现在 | 改成 |
| --- | --- | --- |
| `PlayerInventory.pickupOrder` | 写死 `背包 / 弹挂 / 口袋` | **由数据生成**：`Carried + !Hidden + QuickPickup`，按 `UiOrder` 排 |
| `InventoryUi` 的兜底数组 | 同样写死含 `container_pocket` | 向 `PlayerInventory` 要顺序，不再自己写 id |
| `ContainerDatabase.ValidateAll` | 报错文案提到"口袋" | 去掉口袋字样，保留"必须有 container_backpack" |

**验收标准**：将来把口袋/钥匙卡包的 `.asset` 彻底删掉，代码里**不需要改任何一行**。

---

## 10. 搜索规则（完全不变）

| 规则 | 现状 | 本次是否改 |
| --- | --- | --- |
| 逐步搜索、逐步揭示 | 已实现 | ❌ 不改 |
| 单件搜索时长 | **按物品稀有度配**：白 0.9 / 绿 1.1 / 蓝 1.3 / 紫 1.6 / 金 1.9 / 红 2.5 / 彩 3.0 秒 | ❌ 不改（需求书里的"统一 3 秒"作废） |
| 中断后不保留进度 | 已实现（必须重新连续搜满） | ❌ 不改 |
| 已揭示不重新隐藏 | 已实现 | ❌ 不改 |
| 搜索时不能移动 | 已实现（`InteractionMode.SearchLike`） | ❌ 不改 |
| 世界继续运行 | 已实现 | ❌ 不改 |
| 开背包不暂停世界 | 已实现（`BackpackLike`：可移动、禁开火） | ❌ 不改 |
| 禁止 `Time.timeScale = 0` | 已遵守 | ❌ 不许引入 |

**UI 只做展示**：未知（灰块轮廓）、搜索中（放大镜/进度）、已揭示、空槽。**不得自己模拟进度**，进度必须来自 `ContainerSearchSession.Progress01`。

---

## 11. 输入与交互仲裁

### 11.1 解绑 E 键（含一个真实隐患）

- E 目前只绑在 `Interact`（`GameInput.cs:204`），全项目无其它 E 引用，也没 UI 读它的第 2 个绑定
- **隐患**：改键覆盖按**绑定下标**存进 PlayerPrefs（`zx.input.<action>`）。删掉 E 后，下标 1 会变成手柄 A 键 —— 若曾有覆盖记录，会**错位套到手柄上**
- **处理**：加一次性迁移 —— 读 `zx.input.layoutVersion`，小于当前版本就删掉 `Interact` 的覆盖键，再写新版本号；其它动作的自定义键**保留**
- 同时更新文案：`GameInput.cs` 注释里的"长按 F / E"、`ContainerInteract.cs` 头部注释的"F / E"

### 11.2 新旧 UI 不双响应

- 门面接口 `IInventoryScreen`（`IsOpen` / `OpenBackpack` / `OpenContainer` / `Close`），`InventoryUi` 与 `InventoryScreen` 都实现
- `ContainerInteract` 面向接口 + 一个 `useNewUi` 开关，**同一时刻只把输入交给其中一个**
- `InteractionMode` 仍然是谁开谁 `Push`，不允许两套同时登记

### 11.3 保持现有行为

- `Tab` 开/关背包（可移动）、`Esc` 关闭、`F` 交互、`R` 拖拽中旋转
- 搜索必须站定、受伤/移动中断搜索 —— 全部沿用 `InteractionMode` 与 `ContainerSearchDriver`
- 关闭界面时必须清掉：拖拽幽灵、悬停、Tooltip、选中态、预览框

---

## 12. Prefab 工作流

### 12.1 目录

```
Assets/Prefabs/UI/Inventory/
  InventoryScreen.prefab          ← 根（子面板以嵌套 Prefab 形式嵌入）
  Panels/
    EquipmentPanel.prefab
    WeaponSlotView.prefab
    TacticalRigPanel.prefab
    BackpackPanel.prefab
    ContainerPanel.prefab
    QuickAccessPanel.prefab
    CharacterStatusPanel.prefab
    SecureContainerPanel.prefab
    InputHintPanel.prefab
    CharacterPreviewPanel.prefab
    ItemTooltipView.prefab
```

**物品格子不做 Prefab**：`InventoryGridView` 继续用现有运行时对象池生成（每个格子 1 个 `ItemCellView` + 2 个 `Graphic`），Prefab 化没有收益还会拖慢。

### 12.2 生成器规则

菜单：`ZombieExtraction → UI → 1. 生成背包界面 Prefab`

- **只在文件不存在时创建**；已存在则跳过并打印"已存在，跳过"
- 另一个菜单 `UI → 9. 强制重建（会覆盖）` 才允许覆盖，且先弹确认
- 生成后**自动选中**根 Prefab，方便立刻看
- 幂等：重复执行不产生重复节点
- 生成器不写运行时状态、不碰场景（场景接入是另一个菜单）

### 12.3 运行时

```
InventoryScreenHost（挂 Player）
  ├ [SerializeField] GameObject rootPrefab     ← 唯一引用
  ├ 首次打开：找/建场景级 UIRoot → Instantiate(rootPrefab, uiRoot)
  └ 之后：SetActive(true/false) 复用，不重复实例化
```

- `UIRoot`：场景级空物体（不挂在 Player 下），带 `Canvas` + `CanvasScaler` + `GraphicRaycaster`
- `EventSystem` 全局唯一：复用现有"没有就建、有就把 `StandaloneInputModule` 换成 `InputSystemUIInputModule`"的逻辑，**不许两套 UI 各建一个**
- 不把运行时实例存进任何 ScriptableObject

---

## 13. 三阶段推进（用户指定的顺序）

| 阶段 | 内容 | 完成标志 |
| --- | --- | --- |
| **B 结构** | 分区、层级、锚点、尺寸、占位色块与文字；装备槽/网格能显示真实物品 | 打开界面能看到正确的分区与真实内容，拖拽可用 |
| **C 视觉** | 深色面板、橙色强调、字体字号、槽位底色、选中高亮、图标、进度表现 | 接近参考图观感（不追求像素一致） |
| **D 动效** | 开关淡入、悬停反馈、拖拽反馈、揭示动画（已有）、音效 | 手感连贯；音效需用户提供素材或授权找替代 |

**动效阶段注意**：已有的揭示动画/光晕是**逐物品**的（`ItemCellView`），不要在新界面里重写一遍。

---

## 14. 验收清单

### 14.1 我能自己验证的（会在汇报里给证据）

- [ ] 编译 `error CS` = 0
- [ ] EditMode 全量测试通过（当前 126 条，新增装备/收益用例后数量上升）
- [ ] `Core/` 仍然零 `using UnityEngine`
- [ ] 新增 Core 用例：装备白名单隔离、装备槽单件、负重合计、收益四例（§5.5 表格）
- [ ] 代码里无隐藏容器 id 硬编码（grep 验证）

### 14.2 必须你在 Unity 里看的

- [ ] 界面能打开/关闭，Tab 与 Esc 都行
- [ ] 普通开背包时右列**没有**容器内容
- [ ] 打开容器时右列出现标题 + 网格，且**左中两列位置不变**
- [ ] 搜索进度真实推进、中断后重新搜满
- [ ] 装备能拖进/拖出，白名单拒绝非法物品
- [ ] 三个武器槽显示正确，3 号位明确"未装备"且点不动
- [ ] 特殊道具槽显示信号枪，点击 = 切出，长按左键能发射
- [ ] 快捷栏血包数量真实、用完后刷新
- [ ] 角色预览占位框不与武器槽重叠
- [ ] 1920×1080 与 2560×1440 下都不重叠、不裁切

### 14.3 不能宣称的

- Prefab 的**视觉观感**只能你验收，我不会替你判"好看/正确"
- 手测项未过之前，相关功能一律写"待实机验证"，不写"已完成"

---

## 15. 已知缺口（本轮不做，已记录）

| # | 缺口 | 为什么现在不做 | 将来怎么做 |
| --- | --- | --- | --- |
| 1 | 弹挂/背包不能穿脱 | `ItemDef` 没有"容量"字段；换装要把容器内物品整体迁移并重建 `CarryGroup`，而该系统已 L4 验证，风险大于收益 | 给 `ItemDef` 加 `ContainerDefId`，容器物品化后再做 |
| 2 | 不能丢到地上（T） | 项目没有"地面掉落物"实体，要做世界物体 + 拾取交互，属玩法系统 | 单独一轮：`GroundItem` 组件 + 拾取进背包 |
| 3 | 健康状态（流血/骨折） | 完全没有该系统 | 先留空区域，机制单独设计 |
| 4 | 负重没有上限/惩罚 | 只有 `TotalWeight` 数据，没有容量上限 | 先只显示数字 |
| 5 | 护甲/头盔没有减伤 | 装备只做数据与穿脱 | 单独设计减伤公式 |
| 6 | 近战武器没有近战攻击 | 只有枪械射击 | 单独做近战系统 |
| 7 | 容器物品化 / 仓库 / 存档 / 结算入库 | 阶段 7 剩余工作 | 见 `阶段7-设计说明.md` §22 |
| 8 | 旧 UI 的 Tooltip 与新 UI 各有一份 | 抽取共享会被接口改造放大；旧 UI 退役后自然合并 | 旧 UI 删除时统一 |

---

## 16. 实施顺序（下次开工照这个走）

| # | 任务 | 交付 | 验证 |
| --- | --- | --- | --- |
| T1 | Core：`ItemKind` +3、`ContainerRole.Equipment`、`ContainerDef.Hidden/QuickPickup` | 3 个文件小改 | 编译 |
| T2 | Core：`EquipmentLoadout` + `RaidValueLedger` + 单测 | 2 新文件 + 1 测试文件 | 全量测试 |
| T3 | Gameplay：`PlayerInventory` 接装备组 + 快捷拾取改数据驱动 | 改 1 文件 | 全量测试 |
| T4 | Gameplay：`IItemCellHost` 抽取（`ItemCellView`/`InventoryGridView`/`InventoryUi`） | 改 3 文件 | 编译 + 旧 UI 回归 |
| T5 | Gameplay：`WeaponSlotUIAdapter` + 两个只读 getter | 1 新 + 2 改 | 编译 |
| T6 | Gameplay：`InventoryScreen` + 10 个面板组件 | 11 新文件 | 编译 |
| T7 | Editor：`EquipmentSetup`（3 容器 + 3 测试装备 + 尺寸校验）、测试物品菜单 | 1 新文件 | 跑菜单看 Console |
| T8 | Editor：`InventoryPrefabBuilder` + 场景接入菜单（Host + UIRoot） | 1 新文件 | **需你在 Unity 里点一次** |
| T9 | 视觉细化（阶段 C） | Prefab 调整 | 你的眼睛 |

**每完成 T1~T7 的一批，都跑一次 batchmode 编译 + 全量测试，并汇报真实数字。**

---

## 17. 明确不做（写下来防止以后"顺手做了"）

1. 不改 `ItemContainer` / `ItemStack` / `CarryGroup` 的**规则语义**
2. 不改搜索规则与搜索时长
3. 不改 `WeaponController` 的射击、切枪、换弹、自动切枪、消耗品逻辑
4. 不改信号枪的发射、使用次数、H 键逻辑
5. 不改任何 HUD（血条/弹药/准星/跳字/Toast）
6. 不加 `Time.timeScale = 0`
7. 不为了"还原参考图"新增任何游戏机制
8. 不用静态截图冒充可交互 UI
9. 不引入第三方 UI 库
10. 不在 `Core/` 里 `using UnityEngine`

---

## 18. 变更记录

| 日期 | 内容 |
| --- | --- |
| 2026-10-22 13:30 | 初版：整合 2026-10-22 全天讨论的 26 条决策、布局规格、组件清单、数据层改动、Prefab 工作流、实施顺序。**代码未开工** |
