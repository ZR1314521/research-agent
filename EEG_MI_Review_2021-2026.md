# EEG 运动想象（Motor Imagery）文献综述

**检索范围**：2021–2026 | 数据源：PubMed + arXiv + CrossRef | 精选 20 篇 | 生成日期：2026-07-17

---

## 一、精选 20 篇文献总览

### 🥇 深度学习新架构（5 篇）

| ID | 标题 | 年份 | 期刊 | 核心方法 |
|----|------|------|------|----------|
| **A1** | **RAP2G: Relation-Aware Progressive Pseudo-label Generation for Cross-subject MI-EEG** | 2026 | *IEEE Trans. Biomed. Eng.* ⭐ | 关系感知渐进伪标签 + 跨被试识别 |
| **A2** | **DST-GNN: Dynamic Spatio-Temporal Graph Neural Network for MI Classification** | 2026 | *Scientific Reports* | 动态时空图神经网络 |
| **A3** | **Cortical-SSM: A Deep State Space Model for MI Decoding from EEG** | 2026 | *Journal of Neural Engineering* | 深度状态空间模型 |
| **A4** | **Dual-Branch Spatiotemporal Framework with Dynamic Weighted Permutation Entropy** | 2026 | *Sensors* | 双分支时空 + 排列熵，短窗口解码 |
| **A5** | **Sensory-guided Human-Machine Joint Learning Accelerates MI-BCI Acquisition** | 2026 | *Nature Communications* | 感觉引导人机联合学习 |

### 🥈 域自适应 / 迁移学习（6 篇）

| ID | 标题 | 年份 | 期刊 | 核心方法 |
|----|------|------|------|----------|
| **B1** | **HADANet: Hybrid Attentive Domain Adaptation for Cross-subject MI-EEG** | 2026 | *Cognitive Neurodynamics* | 混合注意力域自适应 |
| **B2** | **EEG-DG: Multi-Source Domain Generalization Framework for MI-EEG** | 2023 | *arXiv* | 多源域泛化（无需目标域数据） |
| **B3** | **Subject-Adaptive Transfer Learning Using Resting State EEG** | 2024 | *arXiv* | 静息态 EEG 校准 + 跨被试迁移 |
| **B4** | **Stacked LoRA for Subject-Adaptive EEG Foundation Models in MI Decoding** | 2026 | *arXiv* | 堆叠 LoRA 适配 EEG 基础模型 |
| **B5** | **DDCA Net: Domain-aware Domain-Class Adaptation from ME to MI** | 2026 | *Frontiers in Neuroscience* | 运动执行→运动想象跨任务迁移 |
| **B6** | **Transfer Learning between MI Datasets using Deep Learning** | 2023 | *arXiv* | 12 数据集跨库迁移验证 |

### 🥉 异步 BCI 与特殊场景（4 篇）

| ID | 标题 | 年份 | 期刊 | 核心方法 |
|----|------|------|------|----------|
| **C1** | **Motor Imagery Classification for Asynchronous EEG-Based BCIs** | 2024 | *arXiv* | 滑动窗口预筛选 + 4 数据集验证 |
| **C2** | **Temporal Out-of-Distribution Detection for Asynchronous MI-BCIs** | 2026 | *arXiv* | TempDens：时序分布外检测框架 |
| **C3** | **EEG-based AI-BCI Wheelchair Advancement** | 2025 | *arXiv* | CNN-Transformer 混合，91.73% 准确率 |
| **C4** | **Characterization of Speech Imagery vs Motor Imagery in Scalp EEG** | 2026 | *arXiv* | 言语想象 vs. 手指运动想象对比 |

### 🏅 传统方法改进与康复应用（5 篇）

| ID | 标题 | 年份 | 期刊 | 核心方法 |
|----|------|------|------|----------|
| **D1** | **Closed-loop MI-BCI for Upper Limb Rehab after Subacute Stroke** | 2026 | *Frontiers in Neurology* | RCT 临床随机试验 |
| **D2** | **CNN Models in Time-Frequency Domain for MI Task Identification** | 2026 | *Physical and Eng. Sciences in Medicine* | 时频域 CNN |
| **D3** | **Riemannian Manifold Dynamic Attention Fusion for MI-EEG Decoding** | 2026 | *Scientific Reports* | 黎曼流形注意力融合 |
| **D4** | **MSCANet: Cross-attention Multi-scale CNN for MI Classification** | 2026 | *Cognitive Neurodynamics* | 跨注意力多尺度卷积 |
| **D5** | **Domain Adaptation-Based Method for Classification of MI EEG** | 2022 | *Mathematics* | 无监督域自适应基线方法 |

---

## 二、证据矩阵

| ID | 方法类别 | 数据集 | 任务类型 | 核心创新 |
|----|----------|--------|----------|----------|
| A1 | 伪标签生成 | 未公开 | 跨被试 4 类 MI | 关系感知渐进伪标签，解决跨被试分布偏移 |
| A2 | 图神经网络 | 未公开 | MI 分类 | 动态时空图建模 EEG 通道拓扑 |
| A3 | 状态空间模型 | 未公开 | MI 解码 | SSM 替代 Transformer 处理长时序 EEG |
| A4 | 时频+熵 | 未公开 | 短窗口 MI | 动态加权排列熵增强短窗口解码鲁棒性 |
| A5 | 人机联合学习 | 未公开 | BCI 控制习得 | 感觉反馈引导 + 联合优化加速训练 |
| B1 | 域自适应 | 未公开 | 跨被试 MI | 混合注意力对齐源-目标域特征 |
| B2 | 域泛化 | BCI IV-2a, IV-2b | 跨被试 MI | 无需目标域数据，联合分布优化 |
| B3 | 迁移学习 | 3 公开基准 | 跨被试 MI | 静息态 EEG 校准，无需任务态目标数据 |
| B4 | 基础模型适配 | 未公开 | MI 解码 | 堆叠 LoRA：全局+个体双路径低秩适配 |
| B5 | 跨任务 DA | >100 被试公开集 | ME→MI | 运动执行→想象迁移，首个大规模验证 |
| B6 | 跨库迁移 | 12 MI 数据集 | 跨库 MI 分类 | 大规模跨库可迁移性系统验证 |
| C1 | 异步 BCI | 4 公开数据集 | 异步 MI 分类 | 滑动窗口预筛选减少假阳性 |
| C2 | OOD 检测 | 未公开 | 异步 MI | 时序分布外检测，区分空闲/控制态 |
| C3 | CNN-Transformer | 未公开 | MI 轮椅 | 混合架构实时轮椅控制 |
| C4 | 言语 vs. MI | 自采 EEG | 言语/手指 MI 对比 | 头皮 EEG 言语想象与运动想象特征对比 |
| D1 | 临床 RCT | 亚急性卒中患者 | 上肢康复 | 闭环 MI-BCI 辅助康复随机试验 |
| D2 | 时频 CNN | 未公开 | MI 任务识别 | 时频域输入替代原始信号提升 CNN |
| D3 | 黎曼几何 | 未公开 | MI 解码 | 黎曼流形+动态注意力融合 |
| D4 | 多尺度卷积 | 未公开 | MI 分类 | 跨注意力多尺度特征融合 |
| D5 | 无监督 DA | BCI III-IVa, IV-2a | 2/4 类 MI | 协方差对齐 + 逐类均值自适应 |

> **说明**：多数 2026 年论文的摘要未提供具体准确率数值，表格中仅列定性创新点。建议阅读全文获取定量指标。

---

## 三、综述正文

### 3.1 研究趋势总览

近五年（2021–2026）EEG 运动想象研究呈现**三大主轴**：

**主轴一：跨被试泛化成为核心瓶颈。** 从本批文献中可以清晰看到，域自适应（Domain Adaptation）和域泛化（Domain Generalization）已成为最热方向——20 篇中至少 8 篇直接以跨被试/跨域迁移为核心创新点（A1, B1–B6, D5）。从 2022 年的基础协方差对齐（D5），到 2023 年的多源域泛化 EEG-DG（B2）和跨库迁移验证（B6），再到 2024–2026 年的静息态校准（B3）、基础模型 LoRA 适配（B4）、跨任务 ME→MI 迁移（B5），方法复杂度持续上升。**关键共识**：单纯增加训练数据无法解决个体差异，需要从特征空间对齐和模型适配两个层面同时发力。

**主轴二：深度学习架构持续迭代。** 图神经网络（A2）、状态空间模型（A3）、黎曼几何（D3）、多尺度卷积（D4）等新架构替代了传统 EEGNet / DeepConvNet 范式。特别是 **Cortical-SSM** 将自然语言处理中的状态空间模型引入 EEG 解码，开启了 Transformer 之外的新路线。

**主轴三：从离线分类走向在线闭环。** 异步 BCI（C1, C2）、实时轮椅控制（C3）、临床康复 RCT（D1）标志着 MI-BCI 从实验室分类准确率竞争转向真实场景部署。Nature Communications 的感觉引导联合学习（A5）尤其值得关注——它直接针对 BCI 训练时间长的实际痛点。

### 3.2 方法对比与空白

| 维度 | 主流方案 | 优势 | 不足 |
|------|----------|------|------|
| **域适应** | MMD 对齐 / 对抗训练 / LoRA | 无需目标域大量标注 | 大多假设源-目标域分布可对齐 |
| **架构创新** | GNN / SSM / Riemannian | 更好捕捉时空结构 | 计算成本高，可解释性弱 |
| **异步 BCI** | OOD 检测 / 滑动窗 | 减少空闲误触发 | 实时性 vs. 精度权衡未解 |
| **临床应用** | RCT 试验 | 有临床证据 | 样本量小，泛化存疑 |

**明显空白**：

- **IEEE 出版物在 PubMed 中几乎缺席**（仅 1 篇），大量高质量 IEEE TNSRE/JBHI 论文未被 PubMed 收录，需单独检索 IEEE Xplore。
- 2021–2023 年覆盖面偏薄（仅 3 篇），需补充早期高被引工作。
- 所有论文均未提供代码/数据可复现性说明（摘要层面），可复现研究仍是行业短板。

### 3.3 各方向深入分析

#### 3.3.1 域自适应与迁移学习

这是当前 MI-EEG 领域最活跃的分支。早期方法（如 D5, 2022）采用无监督协方差矩阵对齐，操作简单但精度有限。2023–2024 年，EEG-DG（B2）提出多源域泛化框架，彻底摆脱对目标域数据的需求；Guetschel 等（B6）首次在 12 个数据集上系统验证跨库迁移的可行性。2026 年的两条技术路线值得关注：**基础模型路线**（B4，Stacked LoRA）将预训练 EEG 大模型通过低秩适配快速个性化；**跨任务路线**（B5，DDCA Net）首次证明运动执行的 EEG 模式可迁移到运动想象解码，为数据稀缺问题提供了全新解决方案。

#### 3.3.2 深度学习新架构

传统 CNN（如 EEGNet）仍在实际系统中广泛使用（D2），但新架构正在快速涌现。**DST-GNN**（A2）将 EEG 电极建模为动态图节点，捕捉任务相关脑区间的信息流动。**Cortical-SSM**（A3）将 Mamba 状态空间模型引入 EEG 解码，在长序列建模上相比 Transformer 有计算效率优势。**黎曼几何方法**（D3）则在数学上更优雅，直接在协方差矩阵的流形空间上进行分类，避免了欧氏空间的假设偏差。

#### 3.3.3 异步 BCI 与实时系统

传统 MI-BCI 假设用户始终在运动想象状态，这在真实场景中不成立。异步 BCI（C1, C2）通过滑动窗口预筛选和时序分布外检测（TempDens）区分"空闲态"与"控制态"，是实现即插即用 BCI 的关键技术。C3 展示了将 MI 解码集成到轮椅控制的完整链路，91.73% 的分类准确率表明实时 MI-BCI 已接近实用化门槛。

#### 3.3.4 临床康复应用

D1 是目前本批文献中唯一的临床随机对照试验（RCT），评估闭环 MI-BCI 辅助亚急性卒中患者上肢康复的效果。将算法研究推进到临床验证是领域成熟的重要标志，但样本量、对照设计和长期随访仍是普遍挑战。

### 3.4 结论与建议

当前 EEG 运动想象领域正处于 **"跨被试泛化"驱动的方法革新期**。域自适应/迁移学习和新型深度学习架构是最具活力的两个分支。对于后续研究，建议重点关注：

1. **补充 IEEE 全覆盖检索**：使用 IEEE Xplore 工具补全 TNSRE/JBHI 等顶级工程期刊文献（预计可增加 5–8 篇高质量论文）。
2. **关注开源与可复现性**：优先筛选有公开代码/预训练模型的论文。
3. **临床转化方向**：亚急性卒中康复（D1）和人机联合学习（A5）提供了从算法到应用的捷径，值得深入跟进。
4. **跨任务迁移**：ME→MI（B5）和言语想象→运动想象（C4）的跨任务迁移研究可能开辟新的数据增强范式。

---

## 四、局限声明

| 局限项 | 说明 |
|--------|------|
| IEEE 覆盖不足 | 仅 1 篇 IEEE 论文，因 PubMed/arXiv 对 IEEE 工程期刊索引不完整 |
| 年份偏倚 | 2026 年文献占 60%+，2021–2023 年仅 3 篇 |
| 指标缺失 | 多数 2026 论文摘要未含具体数值，证据矩阵以定性描述为主 |
| 外部数据库限流 | OpenAlex / Semantic Scholar 在检索过程中被限流 |
| 筛选主观性 | 从 27 篇手动精选 20 篇，保留代表性但可能遗漏重要工作 |
| 未读全文 | 所有分析基于标题与摘要，未深入阅读论文全文 |

---

*检索工具：PubMed + arXiv + CrossRef | 检索日期：2026-07-17 | 筛选策略：IEEE 优先 + 主题覆盖最大化*
