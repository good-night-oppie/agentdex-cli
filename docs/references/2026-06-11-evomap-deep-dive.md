---
title: "EvoMap.ai deep-dive dossier (adversarially verified)"
status: active
owner: "@EdwardTang"
created: 2026-06-11
updated: 2026-06-11
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
---

# EvoMap.ai 深度拆解档案（Final Dossier）

日期：2026-06-11 ｜ 受众：Good Night Oppie CTO ｜ 证据基线：evomap.ai 站点抓取、GitHub/npm（EvoMap org）、Superlinear Academy 原帖 + 2h 访谈、本地 vendored 源码 `/home/admin/gh/agentdex-cli/vendor/aaop/evomap-evolver`（commit 49f38a8c）、公网扫描（2026-06-11）。**所有结论已经对抗性核查；核查修正优先于原始 collector 判断。**

---

## 1. 一句话本质

**EvoMap 是一家深圳 venture-funded 创业公司（AutoGame，<20 人，张昊阳/seikiko 创办）做的「agent 经验资产化 + 中心化共享经济」：客户端 evolver 把 agent 运行日志蒸馏成 ~200–570 token 的 JSON「Gene」并在下次任务注入 prompt，平台端用积分经济激励上传、用 GDI 启发式打分、用 hub 中心化控制分发——整套「自然选择」叙事之下，不存在任何 paired-run 因果测量。**

剥掉营销后的三层皮：

- **技术层**：一个 prompt generator + 反馈环（README 自述 "a prompt generator, not a code patcher"），不碰权重，不打 patch——in-context 的 prompt-library 策展，创始人的「Agent 时代的 LoRA」是营销修辞。
- **商业层**：SaaS 订阅（$0/$20/$100）+ 不可兑现的积分经济 + 30% marketplace 抽佣（evomap.ai/pricing、/economics）。
- **叙事层**：前腾讯游戏策划的 worldbuilding——AI 议会、双螺旋宣言、圆桌十二骑士、8–9 套隐藏主题皮肤。是刻意的产品美学，不是 load-bearing 功能。

它对你最重要的一点：**这是 Gene Mesh 那个被否掉的 MVP 被别人真实造出来之后的样子，而它恰好把「measurement problem as product」的空白衬托得更清楚了**（详见 §6）。

---

## 2. 产品解剖

### 2.1 实际 ship 了什么

| 表面 | 实物 | 证据 |
|---|---|---|
| evolver CLI | npm `@evomap/evolver` v1.89.3（npm 包 2026-03-09 创建、87 个版本；GitHub repo 2026-02-01 创建、84 个 release，release 序列从 v1.66.0/2026-04-16 起；最新 2026-06-10）。Node.js，GPL-3.0-or-later | npm dist-tags + GitHub（核查修正确认） |
| 周边生态 | **不止 CLI 一个 artifact**（核查修正）：org 公开 25 repos——gep-mcp-server、gep-sdk-js、atp-sdk-js、skill2gep、payment-gateway、Cursor/Claude Code/Codex 官方插件 | github.com/EvoMap |
| 平台 | evomap.ai：market（Assets/Recipes/Services/Skills）、wiki（四区：Getting Started/Governance/Guides/Reference）、pricing、economics、atp、arena/bounties/leaderboard | 站点抓取 |
| Hub 后端 | **无公开代码**——GDI 评分、validator 共识聚合、积分结算全部 server-side，不可审计 | 全网未见 hub repo |

**关键修正（核查推翻了 collector 的「客户端可审计」结论）**：CLI 本身也不可独立审计——172 个 src 文件中 50 个（~5.6MB，约占 src 字节 73–85%，取决于树快照）是 javascript-obfuscator 输出，**整个核心引擎**（evolve.js、selector.js、prompt.js 324KB、mutation.js、solidify.js、a2aProtocol.js 736KB、deviceId.js、envFingerprint.js、hubReview.js、crypto.js）在 npm 和 GitHub main 上都是混淆态。可读的只有脚手架：config、schemas、asset store、hook adapters、sanitize、sandboxExecutor。**「客户端可审计 vs 服务端黑箱」的二分是假的——不透明一直延伸到客户端内部。**

### 2.2 一次安装其实是三个产品

1. **本地进化环**：扫 `./memory/` 日志 → 选 Gene/Capsule（`<workspace>/.evolver/gep/{genes.json,capsules.json,events.jsonl}`）→ 输出 GEP prompt（默认上限 24,000 字符，`src/config.js:152`）→ 记 EvolutionEvent。
2. **localhost Proxy（127.0.0.1:19820）**：既是 hub mailbox，又是完整的 Anthropic `/v1/messages` 兼容 LLM gateway——按 cheap/mid/expensive tier 改写 model ID（`@aws-sdk/client-bedrock-runtime` 是 **hard dependency**），并把 token 用量计量进 `Capsule.derivation_tokens`（basis:"measured"）。**启用时 evolver 坐在 agent 的 LLM 流量路径里。**
3. **Hub 联网态**：6 分钟 heartbeat；**validator 角色默认 ON**（你的机器在 sandbox 里跑陌生人的 validation commands 换积分）；hub 可推 `force_update`（degit 下载覆盖 + `process.exit(78)` 重启）和 feature flags；自动向 GitHub 提 issue 默认 ON；ATP buy/orders/verify 的 agent 商业闭环。

**重要修正（推翻 collector 的「offline 声明不可验证」）**：offline gate 是**明文可读且成立的**——`src/proxy/index.js:223-229` 与 `lifecycle/manager.js:359` 直接 gate 在 `process.env.A2A_HUB_URL` 上；未设置时打印 `"[proxy] No A2A_HUB_URL set, running in offline/local mode"`，hello/heartbeat/sync 都不会启动。`resolveHubUrl()` 的 evomap.ai 编译期默认值只在已有 URL 介入时解析，不强制联网。README 的「不设 env = 离线」在 Proxy 连接层成立。（a2aProtocol.js 等仍混淆，daemon 深层路径未做动态验证——见 §8。）

### 2.3 Gene 生命周期（用户视角，本地可验证的一半）

```
信号提取（keyword regex：log_error / test_failure / recurring_error…）
  → selector 优先复用既有 Gene/Capsule，无匹配则 fall through 到 mutation（生成新 gene）
  → 策略预设分配 repair/optimize/innovate/explore 比例
      （zh README 四 intent 表是真实引擎；EN README 还停在三 intent 旧表——doc drift）
  → solidify 执行 gene 的 validation commands
      （代码层已收紧为 node-only allowlist，GHSA-jxh8-jh77-xh6g 之后；README 仍写 node/npm/npx——又一处 doc drift）
  → 自动退役：4 次尝试 best success ≤0.15 / 连续 8 次 inert（issue #562）/ epigenetic boost ≤ −0.3
  → broadcast 资格：score ≥0.7 + success_streak ≥2；hub publish ≥0.78
  → hub 侧 quarantine → --validated 晋升 → GDI 评分 → 上架
```

全部阈值在 `src/config.js` 逐项核实。**修正两处**：(a) schema 字段名是 `signals_match`/`constraints`，官网营销文案写的 `trigger`/`guard` 是 paraphrase；(b) hub-validator sandbox 在**全新临时目录**中执行并清理，不是 git-stash 回滚（本地 solidify 路径文档写有 `EVOLVER_ROLLBACK_MODE=stash`，但核查未确认该机制实际形态——**低置信**）。

### 2.4 营销 vs 现实的自相矛盾（产品级诊断）

| 对外说法 | 同一公司的另一处说法 |
|---|---|
| 创始人原帖：「全程没有人工审核，只有算力的自然选择」 | /market：「所有上架资产通过多维 AI review（GDI）」，仅 52.8% 提交达标 |
| README：「does NOT automatically edit your source code」 | SKILL.md:79：「Evolution is not optional. Adapt or die… autonomously writes improvements」 |
| /market：1.1K assets、1.1M total calls | 同页「9.7M calls today」；访谈称 4 天 12 万资产；4 月报道称 1.38M 资产/46M calls——**跨度三个数量级，全部自报** |
| README badge「8.5k stars」 | 硬编码静态 shields.io badge（脚本刷新）；恰好与真实 star 数接近，是表演手法而非造假 |

### 2.5 UX 与定价

- 接入 = hooks（Claude Code 的 SessionStart/UserPromptSubmit/PostToolUse/Stop；Cursor/Codex/Kiro/opencode；OpenClaw 原生）+ `curl -s https://evomap.ai/skill.md` 让 agent 自己读指令注册——**prompt-injection 形状的 onboarding**。
- Alpha 期激活码 gating（创始人在 Superlinear 评论区手发 20 个码）；6 月现状未知。
- 定价：Free $0 / Premium $20 / Ultra $100；积分**明确不可兑现**（创始人拒绝发币、拒 USDC、拒法币结算），但 /atp 页又写「funds escrowed on-chain」——未解矛盾。
- Recipes & Organisms（「compose genes into recipes, express as temporary organisms」）只有一句话 + CLI 里一个 `recipe build/reuse` stub，**无 spec，纯 roadmap**。

---

## 3. 技术内核：paper 机制 vs repo 现实

### 3.1 Gene 的真实形态（已核实，schema v1.6.0）

`src/gep/schemas/gene.js`：category ∈ {repair, optimize, innovate, explore}、`signals_match`（多语言 regex，`error|错误|异常|エラー|오류`）、`strategy`（步骤串）、`validation`（命令串）、`constraints`（max_files=20、forbidden_paths）、学习字段（epigenetic_marks/learning_history/anti_patterns），以及可选 `routing_hint`（模型 tier 路由）与 `tool_policy`（工具 allow/deny）——后两者由注释里精确到行号引用的**未公开 Rust runtime「EvoX agent-core」**消费。证明存在第二条产品线：gene 直接 gate 模型路由和工具权限。

### 3.2 Token 经济学：paper 数字挑了低端

paper（arXiv 2604.15097）说 ~230 token 的 compact Gene 胜过 ~2,500 token 的 documentation Skill。本地实测 `assets/gep/genes.seed.json` 的 11 个 seed genes：**208–573 token**（chars/4）。~230 只对应最小的 gene，最大的是其 2.5 倍。compact-beats-verbose 的排序仍可能成立，但 headline 数字是 cherry-pick。真正的 context 预算在 prompt 层（24,000 字符 cap），不在单 gene。

### 3.3 核心弱点：它从不测量 gene 是否「有用」

这是整份档案最重要的技术结论，全部一手核实：

- 喂给整个 selection/promotion/经济栈的 outcome 信号是一个**两点启发式**：session-end hook 算 `score = hasErrors ? 0.3 : 0.8`（`src/adapters/scripts/evolver-session-end.js:281`）。
- validation commands 只检查「没弄坏」，从不检查「比 counterfactual 更好」。
- 晋升 broadcast 只要 **n=2** 个 ≥0.7 的 streak——在近二值的 proxy 指标上，n=2 对区分「有用 gene / 无作为 gene / baseline 方差」的统计功效约等于零。
- 全 codebase 没有 control arm、没有 paired comparison、没有方差估计。
- hub 侧 GDI（intrinsic 35% / usage 30% / social 20% / freshness 15%）是人气合成分，不是 causal lift。

**Issue #562 是这一切的 in-repo 实证**：v1.88.2 之前，零产出的 `stable_no_error` 被当作 Bayesian success（0.6）计入，一个什么都不做的 gene 后验爬到 p≈0.997、在 `--loop` 中被选中 **99.7%** 的周期、持续数周——靠事故发现，不是靠测量发现。修复（inert 分类 + 连续 8 次封禁）只补了症状；0.3/0.8 的打分模型原封未动。`test/issue562InertGeneBan.test.js` 公开可查。**一个把整个选择经济跑在 do-nothing gene 上数周的系统，就是「measurement problem as product」论题的活体展示。**

### 3.4 Paper 与代码无法对账（by construction）

- paper 应描述的科学核心（selection 数学、mutation 算子、prompt 模板）恰好全在混淆集里——4,590 trials、CritPt 9.1%→18.57% / 17.7%→27.14% 的声明**无法与 shipped engine 建立任何机制连接**。
- paper 是 vendor 自published：创始人张昊阳是第三作者，无 affiliation，标注 "Technical Report"，v1 提交于 2026-04-16——**Hermes/Nous 指控 + MIT→GPL relicense 的次日**；未找到任何独立引用；流通几乎全靠 EvoMap 自家 README/blog。
- 评测 harness 从未发布。公开 commit 历史从 247 压缩到 3。
- GPL-3.0 与「core modules distributed in obfuscated form to protect intellectual property」（README:559 原文）直接冲突于 GPL「preferred form for modification」要求。

### 3.5 必须给的 honest credit（这让批评更锋利而非更温和）

可读的 15% 工程质量异常扎实：165 个 node:test 回归测试逐个钉在编号事故上（#562、22 天卡死周期、GHSA sandbox 收紧）、sandboxExecutor 的 node-only allowlist + eval-flag 封锁、sanitize.js 约 25 种 secret 模式 + 反向 env-value 泄漏扫描、link(2) 原子锁/oom_score_adj 级别的 daemon 加固。**这个团队有能力做严谨工程——gene 效用测量的缺席是设计选择（增长/经济优先），不是能力问题。**

剩余不可审计面：selector/mutation/prompt 数学、a2aProtocol 的 wire-auth、deviceId/envFingerprint 实际采集什么、sanitize 是否在每条出站路径被调用。注意：**env fingerprint 正是他们回应「py3.10 vs 3.12/glibc 怎么复现」这一社区质疑的承重机制，而它恰好混淆**。

---

## 4. GTM 解剖

### 4.1 Superlinear 路径（核查确认）

- **grapeot 连接是幻象**：路径走的是课代表立正（孙煜征），不是 grapeot（王琰）。后者全网零 commit、零投资、零背书记录（私下关系无法完全排除，但公开面为零）。任何把 EvoMap 当「grapeot-adjacent」的内部 framing 应删除。
- **同日两帖漏斗**（2026-02-25）：立正的 2h 访谈（《从渣女AI到万机之神》，52 赞/16 评）供叙事与背书 → 创始人 pitch 帖（25 赞/33 评）转化——评论区大半是带具体痛点的激活码请求；2-28 创始人精确投放 20 个「Superlinear 可用」邀请码。Alpha + 激活码 + 「创世节点」招募 + 飞书核心群 = 教科书级 scarcity-gated 信徒社区 GTM，gated 社区兼任 lead qualification。
- 无正式商业关系记录（投资/分成）——目前看是编辑性推广 + 会员专属福利。

### 4.2 社区即开发环

创始人自述工作流：泡在所有用户群 → 「赛博精神病」核心信徒群收反馈 → 10–20 分钟进 vibe-coding 窗口 → **直接在生产环境 coding**，单日 163 commits / 18 个版本（自报，未验证）。同一循环在 Superlinear 帖里现场可见：成员 Sun 提分层企业 marketplace，创始人当场拒绝「太重了」。代价同样可见：对最尖锐批评者（Tianyi HAN 的 crypto 换皮论 + 复现性质疑）的回应是**开启评论审核**，不是给出 verification story。

### 4.3 飞轮力学

- **供给侧**：积分付费拉上传（publish +20、reuse 0–12 按 GDI、validation report +10–30）；validator 默认 ON = 节点捐算力；capsule 强制带 env_fingerprint。
- **分发侧**：agent-to-agent GTM——让 agent 读 skill.md 自注册、声称 AI 账号自己发帖推广 Evolver、「AI 信息交换是人类的 15–20 倍」。
- **起点神话**：ClawHub 3 天 36k 下载、被无故下架、$1,000 勒索、2-14 中文开发者被批量封号——全部出自创始人单一来源叙述（**低置信**），但它解释了 pivot 动机：自建协议与平台。
- **市场理论**：他们相信 agent 经验层是流动性 land-grab、定标准者赢（「记忆孤岛」「one agent learns, a million inherit」「定协议是全球性的事」）。Hermes/Nous 之战是这一信念的推论：若护城河是「成为协议」，西方实验室无 attribution 地 ship 相似 primitives 就是存亡问题——这解释了不成比例的反应（license 翻转 + 混淆 + 次日自发 arXiv paper）。

### 4.4 地理瘸腿与轨迹

接受度几乎全在中文平台（知乎两极、V2EX、cnblogs、雷锋网）；西方 organic traction ≈ 零（HN 唯一一帖是他们自己的指控文，2 分 0 评论；无 Reddit 线程）。Superlinear 帖创始人 3-4 后沉默，4-16 「已经两个月了不知道 evomap 如何了」无人回——但工程持续活着（v1.89.3 / 2026-06-10）。**解读为「社区动能转移到飞书群/X/站内」与「衰退」均可能——中置信。**

---

## 5. 竞争格局

### 5.1 对位图

| 对手 | EvoMap 的态度 | 实际关系 |
|---|---|---|
| **mem0 / Letta** | 仅收录于自家 awesome-agent-evolution 列表 | 正交：单 agent 记忆深度 vs 跨 agent 传播。EvoMap 自己的话：「Hermes optimizes for depth within one agent's lifetime. EvoMap optimizes for propagation across agents and teams」 |
| **claude-reflect / Tessl / Zep** | **全部材料中从未出现** | 任何对比必须由我们第一手构建——这本身是定位机会 |
| **Nous Hermes Agent** | 唯一公开宣战对象（2026-04-15 指控「结构同构抄袭」；Nous 官号回「Delete your account」后删；Teknium 称从未听说过此人）| 即便同情方报道也承认无逐字代码抄袭；指控基于概率性「structural isomorphism」。**⚠ 命名撞车：此 Hermes 是 Nous 的产品，与 agentdex-cli 的 Hermes gateway runtime 无关——任何公开比较必须开头消歧，否则读起来像被告在回应** |

### 5.2 vs agentdex：Seed 与 Gene 同属不同种

| 维度 | adx Seed（EvolutionCard） | EvoMap Gene |
|---|---|---|
| 体积 | 紧凑，confidence + provenance | 紧凑（208–573 tok），category + confidence + learning_history |
| **激活** | 无 trigger | `signals_match` regex 触发 |
| **执行** | 无 | `strategy` 步骤 + `validation` 可执行命令 + blast-radius 约束 |
| **生命周期** | 无（M5/M7-open，无消费环路） | ban/promotion 全套阈值 + routing_hint/tool_policy 运行时消费 |
| **测量** | 这正是我们的轴：frozen TaskCard + hard/soft oracle + Pareto verdict | **0.3/0.8 启发式，n=2 晋升，无 control arm** |

一句话：**Gene 是 control object，Seed 是 measurement artifact。EvoMap 缺我们的器官（causal 测量），我们缺它的器官（control-orientation + 消费环路）。** 它没有 TaskCard 等价物（信号刮自可变日志，无 frozen input 纪律）；它的「一人学习百万继承」把一个未测量的 per-gene 效应乘到全网——方差复合，从未被估计。paper abstract 自己点了题：「the core problem… is how to encode experience as a compact, **control-oriented**, evolution-ready object」——恰好命名了 Seed 缺的维度。

---

## 6. 对 Good Night Oppie 的含义

### 6.1 对 Gene Mesh 否决的校验

- **Kill-shot #2（CISO/trust 销售不可达）→ 强化**。EvoMap 就是那个被造出来的 federated-seeds 网络，而信任账单当众到期：85% src 字节混淆 + GPL 冲突、device-fingerprint 节点身份、hub 可推代码的 force_update、validator 默认跑陌生命令（含真实 RCE advisory GHSA-jxh8-jh77-xh6g）、cnblogs 警告、欧洲 CTO 紧急叫停、西方零接受。Kill 成立，且现在有了具名的反面教材。
- **Kill-shot #1（规模化质量退化）→ 方向性佐证，勿过度引用**。52.8% 达标率、质押互验反作弊、知乎指出的 content-addressing 抢注激励、inert-gene 漂移——是「网络噪声需要重度治安」的旁证，不是 FedTextGrad 聚合退化的同机制复现（中置信）。
- **不重启 Gene Mesh**：需求信号不可用（自报指标跨三个数量级互斥）。真实需求存在（8.5k stars、九合创投天使、中文社区真实拉力），但结构性反对（trust、噪声）不被需求证据触动。否决文档里的 salvage——「seeds-not-data 隐私结构、single-tenant 形态」——恰好是 EvoMap **不是**的东西（中心化 hub + 指纹节点），salvage 变得更强。

### 6.2 对 Delta-Meter 空白的校验

**最强外部验证**：一个融了数百万美元的 gene 经济体，核心打分是 `hasErrors ? 0.3 : 0.8`，曾在 do-nothing gene 上跑了数周的选择经济（#562）。「卖测量问题，不卖改进」的论题从未得到过更好的展品。同时它也暴露我们自己的缺口：paper 的 compact/control-oriented 发现（即便是 vendor research）对 Seed 设计是个便宜可证伪的设计论据——Seed 缺 control-orientation 是真缺口。

### 6.3 三个具体选项（含工作量）

**Option 1 — Borrow：M7 learned seeds 嫁接 Gene 生命周期（~1–2 周）**
给 Seed（或 SeedSelector sidecar）加：(a) 激活 trigger 字段（signals_match 风格）；(b) promotion/ban 簿记，用 EvoMap 实战调出的常数做先验（ban：4 次尝试 best ≤0.15、连续 8 次 inert；promote：score ≥0.7 + streak 2）；(c) **inert ≠ success** 的 outcome 分类——#562 的 bug class 是免费学费。来源全部是可读 schemas/config/tests（clean-room 事实借用，不碰 GPL 实现代码）；插入点 `packages/agentdex_engine/.../expedition.py` 选择环。**在 ADR 中显式引用 EvoMap/evolver 与 arXiv 2604.15097**（对方的诉讼模式正是「相似设计 + 换词 + 零 attribution」）。

**Option 2 — Compete：Delta-Meter 首个 demo = gene/seed-toggle paired expedition（~1–2 周）**
同一 frozen TaskCard 跑 {agent} vs {agent + 注入策略 artifact}，hard+soft oracle 出带 CI 的 delta 报告。两个子打法：(a) 在我们 substrate 上复现 paper 的 compact-gene（~230 tok）vs doc-skill（~2,500 tok）对比——同时验证产品和审计这领域唯一的 paper；(b) 离线测他们 11 个公开 seed genes（vendored `assets/gep/genes.seed.json`，无 hub 账号、无 SDK、无指纹）。**默认走 quiet 版**（以 Tessl/claude-reflect artifacts 为对象，不点名 EvoMap）——公开版「我们测了 EvoMap 的 genes，X% 无可测效应」注意力高但会招来 Nous 同款待遇。

**Option 3 — Schema lift + 定位武器化（~数天）**
(a) `env_fingerprint` → ResultCard（让跨 baseline 比较对环境偏斜诚实，同时正面回应 Tianyi HAN 式复现质疑）；(b) `blast_radius {files, lines}` → 廉价结构量级指标；(c) `derivation_tokens` 的 basis:"measured" 纪律映射到现有 BridgeResponse cost/tokens 契约。同时把 **#562 写成 Delta-Meter 的 canonical case study**：「融资的 gene 经济平台，selector 99.7% 周期选中无作为 gene 数周，因为指标把 inert 算成 success——paired-run delta 一份报告就能抓住」。可验证（回归测试公开）、不涉密、把对手最强的工程资产转化为我们产品的论据。

### 6.4 风险卫生（trivial 工作量，无条件做）

1. **Hermes 消歧**：任何提及 EvoMap 的公开物料开头声明与 Nous Hermes 无关。
2. **Attribution**：Evolver 2026-02-01 开源、adx M0–M5 完成于 2026-06-08——Seeds 时序在后、概念趋同；所有借用处引用出处（与 R6 truth-in-advertising 一致）。
3. **Vendored 树隔离**：`vendor/aaop/evomap-evolver` 是 GPL + 5.6MB 不可审计 JS——只读 move-library 材料，**永不 import/link/打包/执行**。核查已确认 proxy 层 offline gate 可读且成立，但 a2a 深层混淆，保留 deny 规则成本为零。

---

## 7. 红队意见：不把 EvoMap 当回事的最强论证

1. **所有 traction 都是自报且互斥**：1.1K vs 12 万 vs 138 万资产，同一页面 1.1M total calls 配 9.7M calls today。一家连自己指标都对不上账的公司，其「网络效应」不构成任何市场证据。
2. **「全球协议」没有西方基质**：HN 一帖 2 分 0 评（还是自家指控文）、零 Reddit、零独立学术引用。定标准的公司没有标准的采用者。
3. **paper 是带 arXiv DOI 的营销**：创始人署名、争议次日提交、无 affiliation、无 harness、无引用——用它支持任何论点（包括我们引用它否决 Gene Mesh）都要打折。
4. **产品核心不可审计，可读部分显示的是一个两点启发式**——所谓「进化」可能就是穿着生物学 lore 的噪声。#562 不是偶发 bug，是系统本质的快照。
5. **创始人模式匹配 hype cycle 而非 infra 公司**：21 天轻躁狂叙事、万机之神、半小时通过决议的 AI 议会、对批评者上评论审核、对唯一的企业级需求说「太重了」、社区 6 周内沉寂。Manus 对标是投资人话术（且经 ASR 转录，低置信）。
6. **连起源神话都不可验证**：36k 下载、$1 vs $200 的物理 benchmark（从未具名）、4 天 12 万资产——全部单一来源。
7. **结论的最强版本**：「EvoMap 是一个围着 prompt library 转的 content-marketing 飞轮；继续追踪它是拖延症。」作为竞争者——可忽略；作为需求证据——不可用；作为技术——只有可读的 15% 有价值，而那 15% 大体是常规工程。

**红队也杀不死的残余**（一段，供平衡）：CLI 工程真实且活着（v1.89.3、165 tests、事故钉死的回归）；compact-gene 假说便宜可测；#562 这类失败模式有真实教学价值。所以正确动作是 **mine it, don't track it**——一次性榨取（§6 三选项），然后 6 个月 re-check 节奏，不进入常态监控。

---

## 8. 未解之谜（+ 廉价解法）

| # | 问题 | 廉价解法 | 成本 |
|---|---|---|---|
| 1 | Hub 在 2026-06 是活是僵尸？激活码 gate 还在吗？homepage 的 `--` 计数器实值？ | headless browser 过一遍 evomap.ai 首页 + /market 列表（JS 渲染） | ~30 min |
| 2 | `@evomap/gep-sdk` / `@evomap/atp-sdk` 是否未混淆？若是，它们是比 85% 混淆客户端干净得多的 wire-protocol clean-room 参照 | `npm pack` + 翻源码 | ~30 min |
| 3 | 混淆的 daemon 路径（a2aProtocol）在 A2A_HUB_URL unset 时是否真零外联？（proxy 层 gate 已核实可读且成立；此条查 daemon 深层） | 沙箱跑 vendored CLI + tcpdump/网络捕获 | 半天 |
| 4 | 「asset」到底数什么？1.1K（上架）vs 1.38M（自报）的 1000 倍差是策展子集还是注水？ | headless /market 翻页计数 + Discord/飞书群直接问 | ~1 h |
| 5 | EvoX agent-core（gene.js 注释里精确到行号的 Rust runtime）存在吗？ | GitHub/crates.io 搜索 + watch org | ~15 min |
| 6 | paper 共同作者 Junjie Wang / Yiming Ren 是 AutoGame 员工还是外部学者？（决定 paper 是否有任何独立支腿） | LinkedIn/Google Scholar/邮箱域名查证 | ~30 min |
| 7 | 有无任何付费企业客户？（若有，「CISO 不可达」kill-shot 需减弱并重做竞争判断） | 搜索 + /careers + 招聘 JD 反推 + 访谈语料挖掘 | ~1 h |
| 8 | Borrow 选项的法律卫生：从 GPL repo 的 docs/schemas/tests 借事实与常数进 Python 惯例上安全，但鉴于对方按「结构同构」发难的前科，值不值得写一页 clean-room/attribution ADR？ | 一页 ADR，进 `docs/adr/` | ~1 h |
| 9 | 访谈里的 0.71「执行度」上传阈值是否就是 BROADCAST_SCORE_THRESHOLD=0.7？（ASR 转录，低置信；上游历史已被压缩无法考古） | 仅在公开写作引用时才需确认，否则跳过 | 0 |
| 10 | Superlinear 原帖 33 条痛点评论（跨环境依赖地狱、不可验证的「fixed it」、企业知识共享）能否作为 Delta-Meter 的 outreach 访谈对象？痛点与 frozen TaskCard + oracle 机制的映射度？ | 与 `tasks/outreach-interview-problems/` 现有语料交叉 | ~1 h |

---

**关键本地路径**：
- vendored 源码：`/home/admin/gh/agentdex-cli/vendor/aaop/evomap-evolver/`（schemas：`src/gep/schemas/{gene,capsule,protocol}.js`；常数：`src/config.js`；打分启发式：`src/adapters/scripts/evolver-session-end.js:281`；#562：`test/issue562InertGeneBan.test.js`；seed genes：`assets/gep/genes.seed.json`；offline gate：`src/proxy/index.js:223-229`）
- Gene Mesh 否决与 whitespace 基线：`/home/admin/gh/agentdex-cli/docs/references/2026-06-10-aaop-mvp-verdicts.md`
- Seed 模型（Option 1 改造对象）：`/home/admin/gh/agentdex-cli/packages/agentdex_engine/src/agentdex_engine/cards/evolution_card.py`
