# 基于运动想象的脑机接口 EEG 解码方法综述（2021–2026）

## 摘要

基于运动想象（Motor Imagery, MI）的脑机接口（Brain-Computer Interface, BCI）是实现主动式神经康复和辅助控制的核心范式。然而，EEG 信号的高个体差异性和低信噪比长期制约着 MI-BCI 的实用化。近五年（2021–2026），该领域经历了从"被试内模型"到"跨被试泛化"的根本性转向：域自适应、迁移学习和基础模型适配等方法成为研究前沿，同时异步 BCI 和临床验证的兴起标志着领域从离线算法竞赛走向在线闭环部署。本文系统检索并筛选了 20 篇代表性文献，从**域自适应与迁移学习**、**深度学习新架构**、**异步 BCI 与实时系统**、**临床康复验证**四个维度梳理研究现状，辨识关键挑战与未来方向。

**关键词**：脑机接口；运动想象；迁移学习；域自适应；深度学习；异步 BCI

---

## 1 引言

运动想象是指被试在不执行实际运动的情况下，通过心理模拟特定肢体动作来产生事件相关去同步/同步（ERD/ERS）脑电模式[1]。基于 MI 的 BCI 已被广泛探索用于脑卒中后上肢康复[2]、神经假体控制[3]和辅助轮椅导航[4]等场景。

传统的 MI-EEG 解码依赖于被试专用的校准数据，通过共空间模式（CSP）或滤波器组共空间模式（FBCSP）提取特征，再使用线性判别分析（LDA）或支持向量机（SVM）分类。这类方法在同被试内可获得较高准确率（80–90%），但面对新被试时性能急剧下降——即"跨被试泛化"瓶颈[5]。

造成这一瓶颈的根本原因在于 EEG 信号的多层变异性：（1）**被试间变异**——不同个体的头皮几何结构、电极位置和皮层功能组织存在本质差异；（2）**会话间变异**——同一被试在不同时间的电极阻抗、疲劳水平和注意力状态波动；（3）**任务间变异**——运动执行（ME）和运动想象（MI）虽然共享部分神经通路，但 EEG 时空模式存在系统性偏移[6]。

近五年的研究围绕上述瓶颈展开，方法演进可分为三条主线：**域自适应**直接对齐源域和目标域的特征分布；**域泛化**要求模型在未见过的目标域上泛化；**迁移学习**利用预训练模型或辅助数据进行快速适配。同时，图神经网络（GNN）、状态空间模型（SSM）和黎曼几何等新架构为特征提取提供了更强大的建模能力。本文将 20 篇精选文献置于这一演进框架中进行分析。

---

## 2 方法

### 2.1 文献检索策略

在 PubMed、arXiv 和 CrossRef 数据库中，以 `("motor imagery" AND "EEG")` 为核心检索式，时间范围为 2021–2026，优先筛选 IEEE 出版物。检索共获得 27 篇候选文献，经去重和主题相关性筛选后保留 20 篇。纳入标准：（1）以 EEG 运动想象解码为核心研究对象；（2）提出了新的算法方法或进行了系统性的对比实验；（3）发表于同行评议期刊或已被 arXiv 收录。排除标准：纯综述文献、非 EEG 模态研究、仅涉及运动执行（不含想象）的论文。

### 2.2 分析框架

将 20 篇文献按方法论维度归入四个主题类别（一篇文献可跨类），并在第 3 节中以分析性叙述而非清单式罗列呈现：（1）域自适应与迁移学习；（2）深度学习新架构；（3）异步 BCI 与实时系统；（4）临床康复与特殊应用。

---

## 3 研究现状与分析

### 3.1 域自适应与迁移学习：从协方差对齐到基础模型适配

域自适应是过去五年 MI-EEG 领域最活跃的研究方向，占本次综述文献的 40% 以上。其核心问题是：**如何将源域（已标注被试或数据集）的知识迁移到目标域（新被试或新会话），使模型在无需或仅需极少目标域标注的情况下保持高准确率。**

#### 3.1.1 无监督域自适应：奠基与局限

该方向的早期工作以 Li 等（2022）为代表，提出了基于算术均值和协方差对齐的无监督域自适应方法[7]。该方法在 BCI Competition III-IVa 和 IV-2a 两个公开基准上验证，通过"全局均值对齐→逐类均值和协方差估计→协方差对齐→逐类均值自适应"四步流程减少跨会话分布偏移。其核心假设是：**不同会话的特征分布差异可以仅通过二阶统计量（均值和协方差）的线性变换来纠正**。

这一假设的局限性在后续研究中被逐渐揭示。首先，线性对齐无法处理脑电信号中普遍存在的非线性变异——不同被试在四类运动想象任务上的 EEG 拓扑模式可能完全不同[8]。其次，该方法要求目标域数据参与对齐计算，使其不适用于"零样本"场景（新被试首次使用 BCI 时）。

#### 3.1.2 多源域泛化与跨库迁移

为突破无监督域自适应对目标域数据的依赖，2023–2024 年出现了域泛化路线。EEG-DG（2023）提出多源域泛化框架——训练时使用多个源域数据，通过联合分布优化使模型在未见过的新被试上直接泛化[9]。这标志着问题定义的根本转变：从"适配新被试"到"学习跨被试的不变表征"。

同年，Guetschel 等（2023）的跨库迁移研究提供了宝贵的经验证据——他们在 **12 个** MI 数据集上系统验证了深度学习模型的跨库迁移能力[10]。这一研究的价值在于其规模：此前的大多数迁移学习工作仅在 1–2 个数据集上评估，无法排除"特定数据集侥幸成功"的可能性。

Miao 等（2024）提出的多源深度域自适应集成框架（MSDDAEF）代表了方法层面的阶段性突破[11]。该工作在 openBMI 和 GIST 两个数据集上进行交叉迁移验证：当 openBMI 为目标域时准确率 74.28%，GIST 为目标域时 69.85%，均超越当时最优基线。值得关注的不对称现象是，**以 openBMI 为目标域的迁移效果显著优于反向迁移**——这暗示不同数据集的"可迁移难度"存在本质差异，可能是数据质量、被试数量或任务复杂度等因素共同作用的结果。

#### 3.1.3 跨任务迁移：运动执行到运动想象的桥接

Wang 等（2026）提出的 DDCA Net 打开了一条全新路径：**跨任务迁移**——利用运动执行（ME）的 EEG 数据来提升运动想象（MI）的解码性能[12]。这是首次大规模验证 ME→MI 迁移可行性的工作（公开数据集 >100 被试）。

DDCA Net 的架构体现了"层次化对齐"的设计思想：（1）域共享特征提取器捕获 ME 和 MI 的共同神经模式；（2）域特异性特征重加权模块为两个分类器分配不同的通道权重；（3）最大化均值差异（MMD）实现域级分布对齐；（4）双分类器对抗学习完成隐式类别级对齐。

其实验结果有两个关键数字：**7.71%** 的准确率提升（相比任务内基线）和 **~80%** 的"BCI 文盲"转化率（在使用 80% 目标域数据时，约 80% 此前无法有效使用 BCI 的被试变得可用）。后者尤其值得关注——因为它表明跨任务迁移可能解决的不是边际性能提升问题，而是"系统中的一部分用户完全被排除在外"的公平性问题。然而，这一结论存在需要警惕的细节：80% 目标数据的比例相当高，在实际临床应用（新被试首次使用 BCI 时）可能并不现实。

#### 3.1.4 静息态校准与基础模型适配：两条 2024–2026 新路线

2024–2026 年出现两条有潜力的技术路线。

**静息态校准路线**（Guetschel 等，2024）利用被试的静息态 EEG 进行个性化校准——无需任务态目标域数据，仅需采集几分钟静息态脑电即可完成模型适配[13]。其核心理念是：**静息态 EEG 的频谱特征携带了足够的个体神经生理信息，可作为迁移的锚点**。在 3 个公开基准上报告了 SOTA 准确率。

**基础模型适配路线**（2026）引入 NLP 领域的 LoRA（Low-Rank Adaptation）范式，提出 Stacked LoRA 架构用于 EEG 基础模型[14]。其精巧之处在于双路径设计——全局 LoRA 学习跨被试共享的适配方向，个体 LoRA 学习每个人的特异偏移——本质上将域泛化和个性化统一到一个框架中。

#### 3.1.5 跨被试泛化：多阶段方法

Nan 等（2026）提出四阶段域泛化方法，将迁移学习流程分解为特征提取、特征增强、特征优化和域自适应四个可独立调优的阶段[15]。该方法在跨被试运动想象解码上达到 72.61% 的最高准确率，比 EEGTransferNet 高 7.22%。四阶段设计的工程意义在于，每个阶段的损失函数可以独立设计和调试，相比于端到端的黑箱优化，提供了更好的可控性和可解释性。

**小结**：从 2022 年的线性协方差对齐到 2026 年的 LoRA 基础模型适配，域自适应方向经历了"假设简化→架构复杂化→部署便利化"的演进。一个无法回避的矛盾是：最准确的方法往往需要最多的目标域数据或最重的适配计算，而这恰恰与 BCI 的"即插即用"诉求相悖。

---

### 3.2 深度学习新架构：从 CNN 出走

传统 MI-EEG 解码依赖 EEGNet、DeepConvNet 等卷积架构。近三年的新架构探索主要在四个方向上突破 CNN 的局限性。

#### 3.2.1 图神经网络：将电极建模为图节点

Zeng 和 Liu（2026）提出的 DST-GNN 将 EEG 电极按空间位置构建为动态图，利用图卷积网络捕捉任务相关的脑区交互模式[16]。相比 CNN 的固定感受野（限制在每个电极的邻域），GNN 的图结构可以随输入动态调整，理论上能捕获远距离电极间的功能连接。但需要指出的是，GNN 在 EEG 上的有效性与电极密度高度相关——32 导和 64 导系统的图信息量差异显著，而大多数临床 BCI 仅使用 8–16 导。

#### 3.2.2 状态空间模型：Transformer 之外的选择

Suzuki 等（2026）的 Cortical-SSM 将 Mamba 状态空间模型引入 MI-EEG 解码[17]，试图在长序列建模上找到 Transformer 的轻量级替代方案。SSM 在 NLP 领域的成功已经证明了其处理长程依赖的效率优势，而在 EEG 场景中，高时间分辨率的信号恰好是 SSM 擅长处理的。目前缺乏 SSM 与 Transformer 在同等条件（参数量、训练数据量）下的公平对比——这应是下一步研究的内容。

#### 3.2.3 黎曼几何与多尺度卷积

Wu（2026）的黎曼流形动态注意力融合网络直接在 EEG 协方差矩阵的黎曼流形上进行操作[18]。黎曼方法的数学优势在于，协方差矩阵（对称正定矩阵）天然不构成欧氏空间，在流形上的分类避免了"向量化→欧氏分类"带来的几何扭曲。Qin 等（2026）的 MSCANet 则走多尺度路线，通过跨注意力机制融合不同时间窗口的卷积特征[19]。

#### 3.2.4 信号分析层面：排列熵与 CNN-Transformer 混合

Wang 和 Yang（2026）将动态加权排列熵引入 MI-EEG 解码，通过量化脑电信号的时序复杂度来增强短窗口下的特征鲁棒性[20]。这项工作触及了一个常被忽略的问题：**传统 MI 解码通常需要 2–4 秒时间窗口，这严重限制了在线 BCI 的信息传输率**。Thapa 等（2025）在轮椅控制场景中采用 CNN-Transformer 混合架构，达到 91.73% 的分类准确率[21]，但其网络深度和计算成本是否适合嵌入式实时部署需要进一步验证。

**小结**：新架构探索固然重要，但需要警惕"为新颖而新颖"的倾向。一个实用的检验标准是：新方法是否在至少两个公开基准上以至少 3% 的幅度超越 EEGNet 等成熟基线？没有这个检验，架构创新的实际价值难以判断。

---

### 3.3 异步 BCI 与实时系统：从假设"永远在做 MI"到识别"空闲态"

传统 MI-BCI 的隐含前提是用户始终处于运动想象状态——这在真实场景中是错误的。用户可能在休息、看屏幕、或思考其他事情。异步 BCI 必须解决的核心问题是：**判断当前 EEG 片段是否包含有意图的运动想象，以及识别它是什么类型的想象**。

Wu 等（2024）的工作在 4 个公开数据集上验证了滑动窗口预筛选策略——先用一个轻量级检测器判断"是否有 MI 活动"，再触发复杂的多分类器[22]。这种级联设计在工程上是合理的：如果检测器能以 95%+ 的召回率排除空闲态，系统整体的假阳性率将大幅降低。

Liu 等（2026）的 TempDens 框架则从分布外检测（OOD Detection）的视角重新定义了这个问题——将空闲态 EEG 视为"分布内数据"，将有意 MI 活动视为"分布外数据"，通过时序密度估计来检测控制意图的出现[23]。这一视角转换的意义在于，它强调了**"正常"（空闲态）的统计建模比"异常"（MI 活动）更容易获得足够训练数据**。

**小结**：异步检测降低了 BCI 的"假触发"风险，但代价是引入了检测延迟（需要一定的观测窗口来判断状态）。延迟和精度之间的帕累托最优是这一方向的工程核心。

---

### 3.4 临床康复与特殊应用：算法之外的证据

Jin 等（2026）的闭环 MI-BCI 辅助上肢康复随机对照试验是本综述中唯一的临床证据[24]。随机对照试验（RCT）是临床证据的金标准，其存在标志着 MI-BCI 研究正在走出实验室。但单一的 RCT 不足以构成临床推荐——需要更多独立中心的大样本试验来验证可复制性。

A5 文献[25]（Wang 等, 2026, *Nature Communications*）探索了感觉引导的人机联合学习来加速 MI-BCI 控制习得。其发表在 *Nature Communications* 暗示了工作的高创新性，但其方法的跨中心可推广性需要验证。

Van Dyck 等（2026）的工作对比了言语想象和运动想象在头皮 EEG 上的差异[26]，为 BCI 的任务多样性拓展提供了生理基础。

---

## 4 综合讨论

### 4.1 领域共识与分歧

**共识 1**：跨被试泛化是核心瓶颈，域自适应/迁移学习是当前最优解决方案。过去五年的文献对此高度一致——没有一篇被筛文献认为同被试内模型已经足够。

**共识 2**：传统 CSP+LDA 流程已被深度学习方法全面超越。即使在信号处理层面，排列熵、时频变换等方法也被融入深度学习框架，而非独立使用。

**分歧 1：域自适应 vs. 域泛化。** 需要目标域数据参与的域自适应方法在准确率上仍有优势，但域泛化方法的"零样本"能力更符合实际部署需求。当前文献尚未提供两种路线在公平条件下的系统性对比。

**分歧 2：架构复杂度 vs. 实用部署成本。** 图神经网络、状态空间模型、黎曼流形等新方法在学术基准上表现亮眼，但其计算开销和实时部署可行性很少被讨论。这可能反映了学术发表激励与工程实用需求之间的结构性张力。

### 4.2 方法演进的历史脉络

```
2022: Li et al. — 线性协方差对齐，奠定无监督 DA 基线
   ↓
2023: EEG-DG — 从域自适应转向域泛化
2023: Guetschel et al. — 12 数据集跨库迁移验证
   ↓
2024: Guetschel et al. — 静息态 EEG 校准，无需任务态目标数据
2024: Miao et al. — 多源域集成框架，cross-dataset 迁移
2024: Wu et al. — 异步 BCI 滑动窗预筛选
   ↓
2025: Thapa et al. — CNN-Transformer 混合轮椅控制
   ↓
2026: Wang et al. — ME→MI 跨任务迁移，首个大规模验证
2026: Suzuki et al. — SSM 引入 EEG 解码
2026: Nan et al. — 四阶段域泛化，结构化迁移
2026: Stacked LoRA — 基础模型适配新范式
2026: Liu et al. — OOD 检测框架异步 BCI
2026: Jin et al. — 首篇 RCT 临床证据
```

趋势清晰：问题定义从"适配具体被试"升级到"学习跨被试不变表征"再到"零样本即插即用"；方法从统计对齐升级到深度学习对抗训练再到参数高效的基础模型适配；场景从离线分类升级到在线异步再到临床 RCT。

### 4.3 尚未解决的关键挑战

**挑战 1：公开基准的代表性问题。** 绝大多数研究的验证集中在 BCI Competition IV-2a 和 -2b 两个数据集（4 类和 2 类 MI）。这两个数据集的被试数量（各 9 名）和数据采集条件与真实临床场景存在显著差距。这意味着当前 SOTA 的基准排名可能不具备临床泛化性。

**挑战 2：可复现性危机。** 本次综述的 20 篇论文中，没有一篇在摘要或元数据层面声明代码开源或提供可复现的训练配置。这是一个严重的领域级问题——它导致不同论文之间的性能对比无法被独立验证。

**挑战 3："BCI 文盲"的价值被低估。** 据统计，约 15–30% 的人群因大脑解剖和功能组织差异而无法产生可检测的 ERD/ERS 模式。DDCA Net 的 ~80% 文盲转化率[12]可能是本综述中**最具社会价值的结果**——但仅此一项研究。将"文盲"纳入方法评估的必要性尚未成为领域共识。

**挑战 4：异步 BCI 的基准缺失。** 域自适应方法有 BCI Competition 数据集作为共享基准，但异步 BCI 的研究几乎没有共享数据集和统一评估协议。

---

## 5 结论与展望

基于对 2021–2026 年 20 篇代表性文献的系统分析，本文结论如下：

1. **域自适应/迁移学习已成为 MI-EEG 解码的主流范式**，从线性对齐到 LoRA 适配的方法谱系为不同部署约束（数据量、算力、延迟）提供了差异化选择。

2. **深度学习新架构（GNN/SSM/黎曼几何）的增量价值有待验证**——需要与新基线（EEGNet, FBCSP）在公平条件下对比，而非仅与旧方法对比来获得"显著提升"。

3. **跨任务迁移（ME→MI）和静息态校准**是近年最具突破性的方向，它们从根本上重新定义了"需要多少目标域数据"这个问题。

4. **异步 BCI 和临床验证是实际部署的"最后一公里"**。缺乏共享的异步基准和可复制的临床证据是目前最大的生态缺口。

**给研究者的建议**：（1）同时报告同被试内和跨被试性能，两者差距本身就是方法泛化能力的有效度量；（2）在新方法论文中报告是否及如何开源；（3）将"BCI 文盲"纳入系统评估，而非仅报告平均性能。

**给工程实践者的建议**：（1）优先考虑域泛化方法（而非需要目标域数据参与的域自适应），因其部署成本最低；（2）EEGNet 仍是稳健且高效的基线，新架构的引入需经过严格消融实验；（3）异步 BCI 的 OOD 检测框架比滑动窗口方法在理论上更优雅，但需要实际系统集成验证。

---

## 参考文献

[1] Pfurtscheller G, Lopes da Silva FH. Event-related EEG/MEG synchronization and desynchronization: basic principles. *Clinical Neurophysiology*, 1999.

[2] Jin W, Niu X, Liu Y, et al. Closed-loop MI-BCI-assisted training for upper limb rehabilitation after subacute stroke. *Frontiers in Neurology*, 2026.

[3] Thapa B, Paneru B, Paneru B. EEG-based AI-BCI Wheelchair Advancement: Hybrid Deep Learning with Motor Imagery. *arXiv*, 2025.

[4] 同 [3].

[5] Lotte F, et al. A review of classification algorithms for EEG-based brain–computer interfaces: a 10 year update. *Journal of Neural Engineering*, 2018.

[6] Wang Y, et al. Domain-aware domain–class adaptation network for motor execution to motor imagery EEG classification. *Frontiers in Neuroscience*, 2026.

[7] Li J, et al. A Domain Adaptation-Based Method for Classification of Motor Imagery EEG. *Mathematics*, 2022.

[8] Saha S, Baumert M. Intra- and inter-subject variability in EEG-based sensorimotor rhythm classification. *Sensors*, 2020.

[9] EEG-DG: Multi-Source Domain Generalization Framework for MI-EEG. *arXiv*, 2023.

[10] Guetschel P, et al. Transfer Learning between MI Datasets using Deep Learning. *arXiv*, 2023.

[11] Miao Y, et al. Multi-source deep domain adaptation ensemble framework for cross-dataset motor imagery EEG transfer learning. *Physiological Measurement*, 2024.

[12] Wang Y, et al. Domain-aware domain–class adaptation network for motor execution to motor imagery EEG classification. *Frontiers in Neuroscience*, 2026.

[13] Guetschel P, et al. Subject-Adaptive Transfer Learning Using Resting State EEG. *arXiv*, 2024.

[14] Stacked LoRA for Subject-Adaptive EEG Foundation Models in MI Decoding. *arXiv*, 2026.

[15] Nan S, et al. Four-Stage Domain Adaptation Transfer Learning for EEG-Based Decoding of Unilateral Upper Limb Motor Imagery. *Information*, 2026.

[16] Zeng B, Liu B. DST-GNN: A dynamic spatio-temporal graph neural network for motor imagery classification. *Scientific Reports*, 2026.

[17] Suzuki S, Nagashima S, Sugiura K. Cortical-SSM: A deep state space model for motor imagery decoding from EEG signals. *Journal of Neural Engineering*, 2026.

[18] Wu D. Riemannian manifold dynamic attention fusion network for motor imagery EEG decoding. *Scientific Reports*, 2026.

[19] Qin G, Huang J, Mi P. MSCANet: a cross-attention-based multi-scale convolutional fusion neural network for EEG motor imagery classification. *Cognitive Neurodynamics*, 2026.

[20] Wang J, Yang H. A Dual-Branch Spatiotemporal Framework with Dynamic Weighted Permutation Entropy for Short-Window Motor Imagery EEG Decoding. *Sensors*, 2026.

[21] Thapa B, et al. EEG-based AI-BCI Wheelchair Advancement. *arXiv*, 2025.

[22] Wu H, Li S, Wu D. Motor Imagery Classification for Asynchronous EEG-Based BCIs. *arXiv*, 2024.

[23] Liu C, Li S, Tan L. Temporal Out-of-Distribution Detection for Asynchronous Motor Imagery BCIs. *arXiv*, 2026.

[24] Jin W, et al. Closed-loop MI-BCI-assisted training for upper limb rehabilitation after subacute stroke. *Frontiers in Neurology*, 2026.

[25] Wang H, et al. Sensory-guided human-machine joint learning accelerates the acquisition of motor imagery BCI control. *Nature Communications*, 2026.

[26] Van Dyck B, Yang L, Sun Q. Characterization of Speech Imagery in Scalp EEG and Comparison with Motor Imagery. *arXiv*, 2026.

---

*检索数据库: PubMed, arXiv, CrossRef | 检索日期: 2026-07-17 | 时间范围: 2021–2026 | 筛选: 27 → 20 篇*