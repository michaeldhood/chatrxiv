import uuid
from typing import List, Dict, Any
import numpy as np
import logging

from src.analysis.models import AnalyzedMessage, Segment, AnalyzedChat, DivergenceReport
from src.analysis.embedding import EmbeddingDriftAnalyzer
from src.analysis.topic import TopicDivergenceAnalyzer
from src.analysis.llm import LLMDivergenceAnalyzer

logger = logging.getLogger(__name__)

class ConversationSegmenter:
    def __init__(self):
        self.embedding_analyzer = EmbeddingDriftAnalyzer()
        self.topic_analyzer = TopicDivergenceAnalyzer()
        self.llm_analyzer = LLMDivergenceAnalyzer()
    
    def segment_chat(
        self,
        chat: AnalyzedChat,
        drift_threshold: float = 0.35,
        min_segment_messages: int = 3
    ) -> List[Segment]:
        """
        Detect segment boundaries using ensemble of approaches.
        """
        messages = chat.messages
        if not messages:
            return []
            
        # 1. Embedding Drift
        embedding_metrics = self.embedding_analyzer.compute_drift_curve(messages)
        drift_scores = embedding_metrics.get('drift_scores', [])
        drift_changepoints = self.embedding_analyzer.detect_changepoints(drift_scores, threshold=drift_threshold)
        
        # 2. Topic Modeling
        topic_result = self.topic_analyzer.analyze_chat(messages)
        topic_segments = topic_result.get('segments', [])
        topic_boundaries = [s['start_idx'] for s in topic_segments if s['start_idx'] > 0]
        
        # 3. LLM Analysis (Optional/Expensive - maybe only near potential boundaries or sparsely)
        # For now, we'll assume we run it fully if available, as per "Use LLM liberally"
        llm_result = self.llm_analyzer.analyze_full_chat(messages)
        llm_boundaries = []
        if llm_result:
            for i, res in enumerate(llm_result.get('message_analysis', [])):
                if res.get('suggested_segment_break'):
                    llm_boundaries.append(i)
        
        # 4. Combine signals
        # We start with 0 as implicit boundary
        boundaries = {0}
        
        # Voting system
        # We consider a message index a boundary if 2+ methods agree, or LLM is confident
        # We scan through messages
        
        candidates = set(drift_changepoints) | set(topic_boundaries) | set(llm_boundaries)
        
        for idx in sorted(list(candidates)):
            score = 0
            if idx in drift_changepoints: score += 1
            if idx in topic_boundaries: score += 1
            if idx in llm_boundaries: score += 2 # Stronger signal
            
            if score >= 2:
                boundaries.add(idx)
                
        sorted_boundaries = sorted(list(boundaries))
        
        # Create segments
        segments = []
        for i in range(len(sorted_boundaries)):
            start_idx = sorted_boundaries[i]
            end_idx = sorted_boundaries[i+1] - 1 if i < len(sorted_boundaries) - 1 else len(messages) - 1
            
            # Skip short segments unless explicitly forced by LLM
            if (end_idx - start_idx + 1) < min_segment_messages and start_idx not in llm_boundaries and len(sorted_boundaries) > 1:
                # Merge with previous if possible, or skip
                # Actually simpler to just define it and let downstream handle it, or merge now.
                # Let's keep it simple for now.
                pass

            # Calculate anchor embedding for this segment
            # We can reuse embeddings from drift analyzer if we cache them, but for now re-embed or just take start
            # EmbeddingDriftAnalyzer re-computes, we might want to refactor to pass embeddings
            # For efficiency, we'll just take the embedding of the first message of segment if available
            segment_msgs = messages[start_idx:end_idx+1]
            segment_texts = [m.content for m in segment_msgs if m.content]
            anchor_emb = self.embedding_analyzer.embed_messages(segment_texts[:3]) # First 3 as anchor
            
            segment = Segment(
                id=str(uuid.uuid4()),
                chat_id=chat.id,
                start_message_idx=start_idx,
                end_message_idx=end_idx,
                anchor_embedding=anchor_emb,
                summary=f"Segment {i+1}", # Placeholder, should use LLM to summarize
                topic_label=None,
                parent_segment_id=None, # To be determined by hierarchy analysis
                divergence_score=0.0 # Placeholder
            )
            segments.append(segment)
            
        return segments
    
    def compute_divergence_score(self, chat: AnalyzedChat) -> Dict[str, Any]:
        """
        Compute overall divergence score for the chat.
        """
        messages = chat.messages
        
        embedding_metrics = self.embedding_analyzer.compute_drift_curve(messages)
        topic_result = self.topic_analyzer.analyze_chat(messages)
        topic_metrics = topic_result.get('metrics', {})
        
        mean_drift = embedding_metrics['metrics']['mean_drift']
        topic_entropy = topic_metrics.get('topic_entropy', 0.0)
        dominant_ratio = topic_metrics.get('dominant_topic_ratio', 1.0)
        
        # Composite score
        # drift is 0-1 (approx, cosine distance can be 0-2 but usually 0-1 for positive vectors)
        # entropy can be > 1. Normalize by log(num_messages)? or just clamp.
        # dominant_ratio is 0-1.
        
        normalized_entropy = min(topic_entropy / 3.0, 1.0) # Heuristic
        
        composite = (
            0.4 * mean_drift +
            0.3 * normalized_entropy +
            0.3 * (1 - dominant_ratio)
        )
        
        composite = min(max(composite, 0.0), 1.0)
        
        return {
            'composite_score': composite,
            'embedding_metrics': embedding_metrics['metrics'],
            'topic_metrics': topic_metrics,
            'interpretation': self._interpret_score(composite)
        }
    
    def _interpret_score(self, score: float) -> str:
        if score < 0.2:
            return "Highly focused - single topic throughout"
        elif score < 0.4:
            return "Mostly focused with minor tangents"
        elif score < 0.6:
            return "Moderate divergence - multiple related topics"
        elif score < 0.8:
            return "Significant divergence - distinct topic branches"
        else:
            return "Highly divergent - consider splitting into child chats"

    def find_best_link_target(
        self,
        source_chat: AnalyzedChat, 
        target_chat: AnalyzedChat
    ) -> Dict[str, Any]:
        """
        Find which segment in target_chat best matches source_chat's topic.
        """
        if not source_chat.segments:
             return None
             
        source_anchor = source_chat.segments[0].anchor_embedding
        if source_anchor is None:
            return None
            
        best_match = None
        best_score = -1.0
        
        from scipy.spatial.distance import cosine
        
        for segment in target_chat.segments:
            if segment.anchor_embedding is None:
                continue
            
            # cosine returns distance (0=same), we want similarity (1=same)
            # But earlier I noted embedding model returns normalized vectors.
            # distance is 1 - dot_product if normalized.
            # So similarity = 1 - distance.
            dist = cosine(source_anchor, segment.anchor_embedding)
            score = 1.0 - dist
            
            if score > best_score:
                best_score = score
                best_match = segment
        
        if best_match:
            return {
                'target_segment_id': best_match.id,
                'similarity_score': float(best_score),
                'link_type': 'related' # simplified inference
            }
        return None
