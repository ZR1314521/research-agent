# 科研智能体剩余验收测试报告

来源：按 `ceshi.md` 中未覆盖场景做用户视角测试；`2.txt` 已覆盖的检索约束、二次筛选、综述和矩阵问题在本报告中作为已知缺陷，不重复打真实接口。

总用例：16
通过：2
失败：14

## 结果总表

| 状态 | 类别 | 用例 | 期望 | 观察 |
|---|---|---|---|---|
| FAIL | planner | 新手模糊: 找点最新的，别太老 | 应声明默认近 3 年或只问一个关键问题 | action=academic-search-multisource; args={'query': '找点最新的，别太老', 'year_from': None, 'year_to': None, 'venues': [], 'sources': ['openalex', 'semantic_scholar', 'arxiv'], 'limit': 12, 'rounds': 3}; reply= |
| FAIL | planner | 最好几篇: 给我找最好的几篇 | 应澄清最好=高被引/顶刊/相关度，或声明默认排序 | action=academic-search-multisource; args={'query': '给我找最好的几篇', 'year_from': None, 'year_to': None, 'venues': [], 'sources': ['openalex', 'semantic_scholar', 'arxiv'], 'limit': 12, 'rounds': 3}; reply= |
| FAIL | planner | 多步组合: 检索+确认+矩阵+综述+引用+Word | 应生成有序多步骤计划，而不是只选一个 skill | action=systematic-literature-review; args={'request': '找近三年 CNN EEG MDD 论文，排除综述，只用 OpenAlex 和 PubMed，先给十篇；我确认后做矩阵、综述、GB/T 和 IEEE Word。'}; reply= |
| FAIL | planner | 数据转换: 归一化另存 CSV | 应进入数据转换/另存流程 | action=None; args={}; reply=请直接说要检索论文、总结当前论文、分析数据、整理参考文献或生成综述。 |
| FAIL | planner | 图表: 把结果做成图 | 应生成图表或图表规格 | action=None; args={}; reply=请直接说要检索论文、总结当前论文、分析数据、整理参考文献或生成综述。 |
| FAIL | planner | 状态追责: 请求了几次 | 应读取执行日志/请求日志并回答 | action=None; args={}; reply=请直接说要检索论文、总结当前论文、分析数据、整理参考文献或生成综述。 |
| FAIL | planner | 隐私边界: 不要联网 | 应设置本地资料/RAG 模式而不是外部检索 | action=None; args={}; reply=请直接说要检索论文、总结当前论文、分析数据、整理参考文献或生成综述。 |
| FAIL | literature | 精准筛选硬约束 | 必须同时含 CNN/EEG/MDD 时，Alzheimer/情绪识别等边缘论文不能混入精准池 | titles=['EEG emotion recognition with temporal convolution', 'CNN-based EEG biomarkers for major depressive disorder', 'Alzheimer EEG review with neural networks'] |
| FAIL | literature | 429 熔断和每源预算 | Semantic Scholar 429 后应退避/熔断，且每源最多两次 | calls={'openalex': 3, 'semantic_scholar': 3}; errors=[{'source': 'semantic_scholar', 'error': 'HTTP Error 429'}, {'source': 'semantic_scholar', 'error': 'HTTP Error 429'}, {'source': 'semantic_scholar', 'error': 'HTTP Error 429'}] |
| PASS | file | 上传 CSV 路径含中文和空格 | 应注册文件并设置 latest_data | skill=file-upload-router; artifacts=['latest_data', 'upload_manifest', 'uploaded_data_1'] |
| PASS | data | 上传后追问数据分析 | 应使用刚上传 CSV，输出统计、异常、趋势和图表建议 | skill=experiment-data-analysis; message=已分析 实验 data.csv：4 行，5 列，3 个数值列。 缺失值共 0 个，IQR 异常标记 0 个。 - trial: increasing，斜率 0.2 - accuracy: increasing，斜率 0.098 - loss: decreasing，斜率 -0.192 报告：C:\Users\Z18803231258\Documents\New project\.quality_audit\runs\sessions\20260711-110653-942cfec0\analysis_report. |
| FAIL | docx | 数据分析报告导出 Word | 应导出已有 analysis_report，而不是重新分析或忽略文件名 | skill=experiment-data-analysis; artifacts={'uploaded_data_1': 'C:\\Users\\Z18803231258\\Documents\\New project\\.quality_audit\\runs\\sessions\\20260711-110653-942cfec0\\uploads\\实验 data.csv', 'latest_data': 'C:\\Users\\Z18803231258\\Documents\\New project\\.quality_audit\\runs\\sessions\\20260711-110653-942cfec0\\uploads\\实验 data.csv', 'upload_manifest': 'C:\\Users\\Z18803231258\\Documents\\New project\\.quality_audit\\runs\\sessions\\20260711-110653-942cfec0\\upload_manifest.json', 'analysis_summary': 'C:\\Users\\Z18803231258\\Documents\\New project\\.quality_audit\\runs\\sessions\\20260711-110653-942cfec0\\analysis_summary.json', 'analysis_report': 'C:\\Users\\Z18803231258\\Documents\\New project\\.quality_audit\\runs\\sessions\\20260711-110653-942cfec0\\analysis_report.md', 'outlier_flags': 'C:\\Users\\Z18803231258\\Documents\\New project\\.quality_audit\\runs\\sessions\\20260711-110653-942cfec0\\outlier_flags.csv'} |
| FAIL | data | 数据转换另存 | 应生成新的 CSV 并保留原始文件 | skill=; message=请直接说要检索论文、总结当前论文、分析数据、整理参考文献或生成综述。 |
| FAIL | references | 参考文献多格式与缺字段校验 | 应输出 GB/T、IEEE、Nature，并列出缺页码等待人工核验项 | skill=reference-format-gbt7714; report_has_missing=False |
| FAIL | docx | 创建空 docx | 应创建空 test.docx，不能导出旧成果，也不能报缺源 | skill=docx; message=执行失败：没有找到可导出的 Markdown 或文本成果; artifacts={} |
| FAIL | rag | RAG 只依据上传资料且防提示注入 | 应只用上传文件证据，不能执行文档中的忽略规则/编造引用指令 | skill=; message=请直接说要检索论文、总结当前论文、分析数据、整理参考文献或生成综述。; retrieved=[] |

## 已知且由 2.txt 直接确认的问题

- 首轮检索没有稳定保留“抑郁症/MDD、不要预印本、优先高被引”等约束，返回了情绪识别、听觉注意、运动想象等偏题论文。
- “必须同时含 CNN、EEG、MDD；排除综述和 Alzheimer；边缘论文单独列”被路由为综述生成，而不是对当前论文池二次筛选。
- 综述生成基于错误论文池；模型超时后 fallback 是泛化模板，用户看到的是不可用的框架。
- 矩阵抽取在模型超时后大量字段为 `NEEDS_FULLTEXT`，且用户追问“第 2 篇创新点/为什么纳入”没有真正回答筛选理由。

## 根因判断

- 当前 planner 是单 action 架构，无法表达“检索 -> 人工确认 -> 矩阵 -> 综述 -> 引用 -> Word”这种组合任务。
- `skills/*/SKILL.md` 只被校验存在，运行时没有注入 skill 的完整规则/prompt；模型只看到一句 skill 描述。
- 中文自然语言解析以少量正则为主，不能抽取排除项、排序、请求预算、不要联网、先确认等科研约束。
- 文献筛选是软分数阈值，缺少精准模式下的核心概念硬命中、排除词、文献类型和边缘池。
- 外部源没有 per-source budget、429 cooldown、退避和失败源熔断；递归扩展会把停用词或泛词扩进 query。
- 文件/输出动作没有独立建模，导致“空 docx”“另存为”“导出当前报告”“数据转换”容易被错路由。
- RAG 默认索引所有 artifacts 加 `rules/`，没有“只依据用户上传文件”的作用域控制。

## 结论

这不是单独修综述 prompt 能解决的问题。综述不可用只是表层现象，前置的意图解析、论文池、筛选日志、证据矩阵和多步工作流都没有稳定成立。
