from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


@dataclass
class ResearchIntent:
    task_types: list[str] = field(default_factory=list)
    topic: str = ""
    query: str = ""
    must_include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    venues: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    output_path: str = ""
    year_from: int | None = None
    year_to: int | None = None
    limit: int | None = None
    rounds: int = 3
    max_requests_per_source: int = 2
    sort_by: str = ""
    no_network: bool = False
    requires_confirmation: bool = False
    scope: str = ""
    transform_ops: list[str] = field(default_factory=list)
    keep_columns: list[str] = field(default_factory=list)
    reply: str = ""
    raw: str = ""

    def has(self, task_type: str) -> bool:
        return task_type in self.task_types

    def add(self, task_type: str) -> None:
        if task_type not in self.task_types:
            self.task_types.append(task_type)


class IntentParser:
    VENUES = [
        "IEEE",
        "Nature",
        "Science",
        "Cell",
        "ACM",
        "Elsevier",
        "Springer",
        "PNAS",
        "NEJM",
        "BMJ",
    ]
    SOURCE_MAP = {
        "openalex": "openalex",
        "open alex": "openalex",
        "pubmed": "pubmed",
        "semantic scholar": "semantic_scholar",
        "semanticscholar": "semantic_scholar",
        "arxiv": "arxiv",
    }
    STYLE_MAP = {
        "gb/t": "gbt7714-numeric",
        "gbt": "gbt7714-numeric",
        "7714": "gbt7714-numeric",
        "ieee": "ieee",
        "nature": "nature",
        "apa": "apa",
        "science": "science",
        "cell": "cell",
    }
    LATIN_STOPWORDS = {
        "a",
        "about",
        "all",
        "and",
        "article",
        "articles",
        "best",
        "find",
        "for",
        "from",
        "help",
        "latest",
        "literature",
        "paper",
        "papers",
        "recent",
        "review",
        "search",
        "study",
        "the",
        "to",
        "using",
        "with",
        "word",
        "year",
        "years",
    }

    def parse(self, text: str, artifacts: dict[str, str] | None = None) -> ResearchIntent:
        artifacts = artifacts or {}
        intent = ResearchIntent(raw=text)
        lowered = text.lower().strip()
        intent.files = self._paths(text)
        intent.output_path = self._output_path(text)
        intent.year_from, intent.year_to = self._years(text)
        intent.limit = self._limit(text)
        intent.venues = self._venues(text)
        intent.sources = self._sources(lowered)
        intent.styles = self._styles(lowered)
        intent.no_network = bool(re.search(r"不要联网|不联网|本地|只用我上传|只依据我上传", text))
        intent.requires_confirmation = bool(re.search(r"确认后|先给我看|先给候选|先给框架|不要先写|我确认", text))
        intent.sort_by = "citation_count" if re.search(r"高被引|引用|cited|citation", lowered) else ""
        intent.scope = "uploaded" if re.search(r"只依据我上传|只用我上传|上传资料|不要联网", text) else ""
        intent.must_include = self._must_include(text)
        intent.exclude = self._exclude(text)
        intent.transform_ops = self._transform_ops(text)
        intent.keep_columns = self._keep_columns(text)

        if self._is_quality_question(text):
            intent.add("quality_audit")
        if self._is_workflow_control(text):
            intent.add("workflow_control")
        if self._is_file_upload(text, intent.files):
            intent.add("file_upload")
        if self._is_rag(text):
            intent.add("rag")
        if self._is_data_transform(text):
            intent.add("data_transform")
        if self._is_docx(text):
            intent.add("docx")
        if self._is_document_summary(text, intent.files):
            intent.add("document_summary")
        if self._is_reference(text):
            intent.add("references")
        if self._is_data_analysis(text):
            intent.add("data_analysis")
        if self._is_screening(text, artifacts):
            intent.add("screen")
        if self._is_search(text):
            intent.add("literature_search")
        if self._is_matrix(text, artifacts):
            intent.add("matrix")
        if self._is_review(text):
            intent.add("review")
        if self._is_paper_writing(text):
            intent.add("paper_writing")
        if self._is_humanize(text):
            intent.add("humanize")
        if self._is_visual(text):
            intent.add("visual")

        intent.query = self._query(text, intent)
        intent.topic = intent.query
        self._apply_defaults(intent, artifacts)
        return intent

    def _apply_defaults(self, intent: ResearchIntent, artifacts: dict[str, str]) -> None:
        if intent.has("literature_search") and not intent.year_from and re.search(r"最新|近|最近|别太老", intent.raw):
            current = time.localtime().tm_year
            intent.year_from, intent.year_to = current - 2, current
        if intent.has("literature_search") and not intent.limit:
            intent.limit = 10 if re.search(r"几篇|一些|点", intent.raw) else 12
        if intent.has("literature_search") and intent.no_network and not artifacts:
            intent.reply = "你要求不要联网，但当前会话没有可用上传资料。请先导入资料，或允许公开学术源检索。"
        if intent.has("literature_search") and re.search(r"最好|最好的", intent.raw) and not intent.sort_by:
            intent.reply = "“最好”可以按高被引、顶刊或主题相关度排序。请指定一个标准，或说“按高被引”。"
        if intent.has("literature_search") and re.search(r"最新|别太老", intent.raw) and not intent.query:
            intent.reply = "我可以默认检索近 3 年公开文献。请补充研究主题，例如“抑郁症 EEG”。"

    def _is_search(self, text: str) -> bool:
        if re.search(r"找|搜|检索|查找|推荐|有哪些|search|find", text, re.IGNORECASE) and re.search(r"论文|文献|paper|literature", text, re.IGNORECASE):
            return True
        return bool(re.search(r"找|搜|检索|查找", text) and re.search(r"最新|最好|别太老|近", text))

    def _is_screening(self, text: str, artifacts: dict[str, str]) -> bool:
        return bool(
            artifacts.get("active_papers")
            and re.search(r"必须|同时含|排除|不要|只要|边缘|筛|删掉|不相关|保留|纳入", text)
            and re.search(r"cnn|eeg|mdd|alzheimer|综述|预印本|文献|论文|review|preprint", text, re.IGNORECASE)
        )

    def _is_matrix(self, text: str, artifacts: dict[str, str]) -> bool:
        return bool(
            artifacts.get("active_papers")
            and re.search(r"大概|讲什么|逐篇|每篇|总结|摘要|介绍|创新点|为什么纳入|方法|数据集|指标|局限|做表|矩阵", text)
        )

    def _is_review(self, text: str) -> bool:
        return bool(re.search(r"综述|大纲|框架|related\s+work|review", text, re.IGNORECASE))

    def _is_paper_writing(self, text: str) -> bool:
        return bool(re.search(r"写.*(?:引言|论文|方法|结果|讨论|related\s+work)|paper\s+(?:section|draft)", text, re.IGNORECASE))

    def _is_humanize(self, text: str) -> bool:
        return bool(re.search(r"太像\s*ai|去\s*ai|润色|自然一点|humanize", text, re.IGNORECASE))

    def _is_reference(self, text: str) -> bool:
        return bool(re.search(r"参考文献|引文|引用格式|gb/?t|gbt|7714|bibtex|\bris\b|citation|doi|页码", text, re.IGNORECASE))

    def _is_data_analysis(self, text: str) -> bool:
        return bool(re.search(r"统计|异常值|趋势|实验数据|数据分析|accuracy|loss|按组|分组|analy[sz]e", text, re.IGNORECASE))

    def _is_data_transform(self, text: str) -> bool:
        return bool(re.search(r"归一化|标准化|筛掉缺失|删除缺失|只保留|保留这些列|转换|另存\s*csv|normalize|standardize", text, re.IGNORECASE))

    def _is_docx(self, text: str) -> bool:
        return bool(re.search(r"word|docx|转\s*word|保存为\s*word|导出.*文档|新建.*\.docx|创建.*\.docx|建个.*\.docx", text, re.IGNORECASE))

    def _is_document_summary(self, text: str, files: list[str]) -> bool:
        return bool(
            any(path.lower().endswith((".docx", ".md", ".markdown")) for path in files)
            and re.search(r"解释|讲了什么|总结|概述|摘要|说明|summari[sz]e|explain", text, re.IGNORECASE)
        )

    def _is_file_upload(self, text: str, files: list[str]) -> bool:
        return bool(files and re.search(r"上传|导入|读取|添加文件|我这有|用这个", text))

    def _is_rag(self, text: str) -> bool:
        without_paths = re.sub(r"[A-Za-z]:\\[^\s\"“”']+", " ", text)
        return bool(re.search(r"\brag\b|知识库|向量检索|只依据|给出处|不要.*编|上传资料回答|本地资料", without_paths, re.IGNORECASE))

    def _is_workflow_control(self, text: str) -> bool:
        return bool(re.search(r"暂停|继续|恢复|从.*重跑|目标.*改|不要重新联网|接着|上次任务|checkpoint|resume|pause|status", text, re.IGNORECASE))

    def _is_quality_question(self, text: str) -> bool:
        return bool(re.search(r"为什么没找到|请求了几次|哪个接口|哪个源|为什么停|失败原因|怎么停|调用了几次|日志|追责", text))

    def _is_visual(self, text: str) -> bool:
        return bool(re.search(r"流程图|架构图|框架图|概念图|图示|visual", text, re.IGNORECASE))

    def _years(self, text: str) -> tuple[int | None, int | None]:
        current = time.localtime().tm_year
        match = re.search(r"(20\d{2})\s*(?:-|至|到|~)\s*(20\d{2})", text)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = re.search(r"(?:近|最近|这)?\s*([一二两三四五六七八九十]|\d{1,2})\s*年", text)
        if match:
            raw = match.group(1)
            count = int(raw) if raw.isdigit() else CHINESE_NUMBERS.get(raw, 3)
            return current - max(1, count) + 1, current
        match = re.search(r"(20\d{2})\s*年", text)
        return (int(match.group(1)), current) if match else (None, None)

    def _limit(self, text: str) -> int | None:
        match = re.search(r"(?:前|找|要|共|至少|先给)?\s*(\d{1,2})\s*(?:篇|papers?)", text, re.IGNORECASE)
        if match:
            return max(1, min(50, int(match.group(1))))
        chinese = re.search(r"(?:前|找|要|共|至少|先给)?\s*([一二两三四五六七八九十])\s*篇", text)
        if chinese:
            return CHINESE_NUMBERS.get(chinese.group(1), None)
        return None

    def _venues(self, text: str) -> list[str]:
        return [venue for venue in self.VENUES if re.search(rf"\b{re.escape(venue)}\b", text, re.IGNORECASE)]

    def _sources(self, lowered: str) -> list[str]:
        explicit = []
        for marker, source in self.SOURCE_MAP.items():
            if marker in lowered and source not in explicit:
                explicit.append(source)
        return explicit

    def _styles(self, lowered: str) -> list[str]:
        styles = []
        for marker, style in self.STYLE_MAP.items():
            if marker in lowered and style not in styles:
                styles.append(style)
        return styles

    def _paths(self, text: str) -> list[str]:
        paths = []
        for value in re.findall(r"[\"“”']([^\"“”']+\.[A-Za-z0-9]{1,6})[\"“”']", text):
            paths.append(value)
        paths.extend(re.findall(r"@([^\s]+)", text))
        return list(dict.fromkeys(paths))

    def _output_path(self, text: str) -> str:
        quoted = re.search(r"(?:保存|输出|另存|导出)(?:在|到|至|为)?\s*[\"“”']([^\"“”']+\.[A-Za-z0-9]{1,6})[\"“”']", text)
        if quoted:
            return quoted.group(1).strip()
        unquoted = re.search(r"(?:保存|输出|另存|导出)(?:在|到|至|为)?\s*([A-Za-z]:\\[^\n\r\"“”']+\.[A-Za-z0-9]{1,6})", text)
        if unquoted:
            return unquoted.group(1).strip()
        return ""

    def _must_include(self, text: str) -> list[str]:
        result: list[str] = []
        match = re.search(r"必须(?:同时)?含\s*([^，。；;]+)", text, re.IGNORECASE)
        if match:
            result.extend(re.findall(r"[A-Za-z][A-Za-z0-9+/-]*|[\u4e00-\u9fff]{2,}", match.group(1)))
        for marker, value in (("抑郁", "MDD"), ("脑电", "EEG")):
            if marker in text and value not in result:
                result.append(value)
        for value in re.findall(r"\b(CNN|EEG|MDD|BCI|Transformer|LSTM)\b", text, re.IGNORECASE):
            normalized = value.upper() if value.lower() not in {"transformer"} else "Transformer"
            if normalized not in result:
                result.append(normalized)
        return result

    def _exclude(self, text: str) -> list[str]:
        result: list[str] = []
        for match in re.finditer(r"(?:排除|不要|不包括|去掉)\s*([^，。；;]+)", text, re.IGNORECASE):
            result.extend(re.findall(r"[A-Za-z][A-Za-z0-9+/-]*|[\u4e00-\u9fff]{2,}", match.group(1)))
        if "预印本" in text and "preprint" not in result:
            result.append("preprint")
        if "综述" in text and "review" not in [item.lower() for item in result]:
            result.append("review")
        return list(dict.fromkeys(result))

    def _transform_ops(self, text: str) -> list[str]:
        ops = []
        if re.search(r"归一化|normalize", text, re.IGNORECASE):
            ops.append("normalize")
        if re.search(r"标准化|standardize", text, re.IGNORECASE):
            ops.append("standardize")
        if re.search(r"筛掉缺失|删除缺失|drop\s*missing", text, re.IGNORECASE):
            ops.append("drop_missing")
        if re.search(r"只保留|保留这些列|keep\s+columns", text, re.IGNORECASE):
            ops.append("keep_columns")
        return ops

    def _keep_columns(self, text: str) -> list[str]:
        match = re.search(r"(?:只保留|保留这些列)\s*([^，。；;]+)", text)
        if not match:
            return []
        return [item.strip(" `") for item in re.split(r"[,，\s]+", match.group(1)) if item.strip(" `")]

    def _query(self, text: str, intent: ResearchIntent) -> str:
        before_save = re.split(r"保存(?:在|到|为)|输出(?:到|至)|另存", text, maxsplit=1)[0]
        latin = re.findall(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+./-]*", before_save)
        terms = []
        venue_lowers = {venue.lower() for venue in self.VENUES}
        source_lowers = set(self.SOURCE_MAP)
        for token in latin:
            lower = token.lower()
            if lower in self.LATIN_STOPWORDS or lower in venue_lowers or lower in source_lowers or re.fullmatch(r"20\d{2}", token):
                continue
            if lower in self.STYLE_MAP:
                continue
            terms.append(token)
        if "抑郁" in text and not any(item.lower() in {"mdd", "depression", "depressive"} for item in terms):
            terms.extend(["depression", "MDD"])
        if "脑电" in text and not any(item.lower() == "eeg" for item in terms):
            terms.append("EEG")
        if terms:
            return " ".join(dict.fromkeys(terms))
        cleaned = re.sub(
            r"(?:请|帮我|你能|能否|找下|找|查找|搜索|检索|近|最近|最新|别太老|这|相关的?|论文|文献|吗|一下|给我|最好|几篇|点|的)",
            " ",
            before_save,
        )
        cleaned = re.sub(r"\d+\s*年", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip(" ，,。")
