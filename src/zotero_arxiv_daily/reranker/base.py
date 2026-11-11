from abc import ABC, abstractmethod
from omegaconf import DictConfig
from ..protocol import Paper, CorpusPaper
import numpy as np
from typing import Type
class BaseReranker(ABC):
    def __init__(self, config:DictConfig):
        self.config = config

    def rerank(self, candidates:list[Paper], corpus:list[CorpusPaper]) -> list[Paper]:
        if not candidates:
            return []
        corpus = sorted(corpus,key=lambda x: x.added_date,reverse=True)
        time_decay_weight = 1 / (1 + np.log10(np.arange(len(corpus)) + 1))
        time_decay_weight: np.ndarray = time_decay_weight / time_decay_weight.sum()
        focus = self.config.reranker.get("focus") if self.config is not None else None
        topics = [str(topic).strip() for topic in focus.get("topics", [])] if focus else []
        topics = [topic for topic in topics if topic]
        references = [c.abstract for c in corpus] + topics
        candidate_texts = [f"{c.title}\n{c.abstract}" for c in candidates]
        sim = self.get_similarity_score(candidate_texts, references)
        assert sim.shape == (len(candidates), len(references))
        zotero_scores = (sim[:, :len(corpus)] * time_decay_weight).sum(axis=1)
        if topics:
            focus_weight = float(focus.get("weight", 0.8))
            if not 0 <= focus_weight <= 1:
                raise ValueError("reranker.focus.weight must be between 0 and 1")
            focus_scores = sim[:, len(corpus):].max(axis=1)
            scores = (focus_weight * focus_scores + (1 - focus_weight) * zotero_scores) * 10
        else:
            scores = zotero_scores * 10
        for s,c in zip(scores,candidates):
            c.score = s
        candidates = sorted(candidates,key=lambda x: x.score,reverse=True)
        return candidates
    
    @abstractmethod
    def get_similarity_score(self, s1:list[str], s2:list[str]) -> np.ndarray:
        raise NotImplementedError

registered_rerankers = {}

def register_reranker(name:str):
    def decorator(cls):
        registered_rerankers[name] = cls
        return cls
    return decorator

def get_reranker_cls(name:str) -> Type[BaseReranker]:
    if name not in registered_rerankers:
        raise ValueError(f"Reranker {name} not found")
    return registered_rerankers[name]
