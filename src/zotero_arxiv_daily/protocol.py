from dataclasses import dataclass
from typing import Optional, TypeVar
from datetime import datetime
import re
import tiktoken
from openai import OpenAI
from loguru import logger
import json
RawPaperItem = TypeVar('RawPaperItem')


def _request_llm(openai_client: OpenAI, llm_params: dict, messages: list[dict]) -> str:
    api_mode = llm_params.get("api_mode", "chat_completion")
    generation_kwargs = dict(llm_params.get("generation_kwargs", {}))

    if api_mode == "chat_completion":
        response = openai_client.chat.completions.create(
            messages=messages,
            **generation_kwargs,
        )
        return response.choices[0].message.content

    if api_mode == "response":
        max_tokens = generation_kwargs.pop("max_tokens", None)
        if max_tokens is not None and "max_output_tokens" not in generation_kwargs:
            generation_kwargs["max_output_tokens"] = max_tokens
        response = openai_client.responses.create(
            input=messages,
            **generation_kwargs,
        )
        return response.output_text

    raise ValueError(
        f"Unsupported llm.api_mode: {api_mode}. "
        "Expected 'chat_completion' or 'response'."
    )


@dataclass
class Paper:
    source: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    pdf_url: Optional[str] = None
    full_text: Optional[str] = None
    tldr: Optional[str] = None
    affiliations: Optional[list[str]] = None
    score: Optional[float] = None
    reading_card: Optional[dict[str, str]] = None

    def _generate_tldr_with_llm(self, openai_client:OpenAI,llm_params:dict) -> str:
        lang = llm_params.get('language', 'English')
        prompt = f"Given the following information of a paper, generate a one-sentence TLDR summary in {lang}:\n\n"
        if self.title:
            prompt += f"Title:\n {self.title}\n\n"

        if self.abstract:
            prompt += f"Abstract: {self.abstract}\n\n"

        if self.full_text:
            prompt += f"Preview of main content:\n {self.full_text}\n\n"

        if not self.full_text and not self.abstract:
            logger.warning(f"Neither full text nor abstract is provided for {self.url}")
            return "Failed to generate TLDR. Neither full text nor abstract is provided"
        
        # use gpt-4o tokenizer for estimation
        enc = tiktoken.encoding_for_model("gpt-4o")
        prompt_tokens = enc.encode(prompt)
        prompt_tokens = prompt_tokens[:4000]  # truncate to 4000 tokens
        prompt = enc.decode(prompt_tokens)
        
        tldr = _request_llm(
            openai_client,
            llm_params,
            [
                {
                    "role": "system",
                    "content": f"You are an assistant who perfectly summarizes scientific paper, and gives the core idea of the paper to the user. Your answer should be in {lang}.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return tldr
    
    def generate_tldr(self, openai_client:OpenAI,llm_params:dict) -> str:
        try:
            tldr = self._generate_tldr_with_llm(openai_client,llm_params)
            self.tldr = tldr
            return tldr
        except Exception as e:
            logger.warning(f"Failed to generate tldr of {self.url}: {e}")
            tldr = self.abstract
            self.tldr = tldr
            return tldr

    def generate_reading_card(self, openai_client: OpenAI, llm_params: dict) -> dict[str, str]:
        """Create a short, evidence-bound card for the Obsidian dashboard."""
        basis = "提取正文" if self.full_text else "仅摘要"
        empty = {
            "basis": basis,
            "problem": "暂无可靠信息",
            "method": "暂无可靠信息",
            "results": "暂无可靠信息",
            "relevance": "暂无可靠信息",
            "limitations": "暂无可靠信息",
        }
        if not self.full_text and not self.abstract:
            self.reading_card = empty
            return empty

        text = f"标题：{self.title}\n\n摘要：{self.abstract or '无'}\n\n"
        if self.full_text:
            text += f"提取到的正文：\n{self.full_text}"
        enc = tiktoken.encoding_for_model("gpt-4o")
        tokens = enc.encode(text)
        if self.full_text and len(tokens) > 12000:
            basis = "正文节选"
            empty["basis"] = basis
        text = enc.decode(tokens[:12000])
        prompt = (
            "请根据下面的论文内容，用中文写一张五分钟能读完的阅读卡。"
            "只使用给出的内容，不能补造实验结果、数字或结论。"
            "如果只给摘要，results 只能报告摘要明确给出的结果，limitations 要指出缺少全文。"
            "如果给出的是提取正文的截断片段，不能假称读过完整论文。"
            "返回且只返回 JSON 对象，字段恰好是 problem、method、results、relevance、limitations。"
            "每项 1–3 句。relevance 只讨论它与 RAG evaluation、retrieval noise/robustness 或 LLM agents 的具体联系；"
            "联系弱就直说。limitations 写论文自身限制以及当前材料无法核实的地方。\n\n"
            + text
        )
        try:
            raw = _request_llm(openai_client, llm_params, [
                {"role": "system", "content": "你是谨慎的 NLP 论文阅读助手。只输出有效 JSON。"},
                {"role": "user", "content": prompt},
            ])
            raw = raw.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
            parsed = json.loads(raw)
            card = {key: str(parsed.get(key, empty[key])).strip() or empty[key]
                    for key in ("problem", "method", "results", "relevance", "limitations")}
            card["basis"] = basis
            self.reading_card = card
            return card
        except Exception as exc:
            logger.warning(f"Failed to generate reading card of {self.url}: {exc}")
            self.reading_card = empty
            return empty

    def _generate_affiliations_with_llm(self, openai_client:OpenAI,llm_params:dict) -> Optional[list[str]]:
        if self.full_text is not None:
            prompt = f"Given the beginning of a paper, extract the affiliations of the authors in a python list format, which is sorted by the author order. If there is no affiliation found, return an empty list '[]':\n\n{self.full_text}"
            # use gpt-4o tokenizer for estimation
            enc = tiktoken.encoding_for_model("gpt-4o")
            prompt_tokens = enc.encode(prompt)
            prompt_tokens = prompt_tokens[:2000]  # truncate to 2000 tokens
            prompt = enc.decode(prompt_tokens)
            affiliations = _request_llm(
                openai_client,
                llm_params,
                [
                    {
                        "role": "system",
                        "content": "You are an assistant who perfectly extracts affiliations of authors from a paper. You should return a python list of affiliations sorted by the author order, like [\"TsingHua University\",\"Peking University\"]. If an affiliation is consisted of multi-level affiliations, like 'Department of Computer Science, TsingHua University', you should return the top-level affiliation 'TsingHua University' only. Do not contain duplicated affiliations. If there is no affiliation found, you should return an empty list [ ]. You should only return the final list of affiliations, and do not return any intermediate results.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            affiliations = re.search(r'\[.*?\]', affiliations, flags=re.DOTALL).group(0)
            affiliations = json.loads(affiliations)
            affiliations = list(set(affiliations))
            affiliations = [str(a) for a in affiliations]

            return affiliations
    
    def generate_affiliations(self, openai_client:OpenAI,llm_params:dict) -> Optional[list[str]]:
        try:
            affiliations = self._generate_affiliations_with_llm(openai_client,llm_params)
            self.affiliations = affiliations
            return affiliations
        except Exception as e:
            logger.warning(f"Failed to generate affiliations of {self.url}: {e}")
            self.affiliations = None
            return None
@dataclass
class CorpusPaper:
    title: str
    abstract: str
    added_date: datetime
    paths: list[str]
