from bertopic import BERTopic
from collections import Counter
import numpy as np
from typing import List, Dict, Any
import logging
from src.analysis.models import AnalyzedMessage

logger = logging.getLogger(__name__)

class TopicDivergenceAnalyzer:
    def __init__(self):
        # Initialize BERTopic with appropriate settings for chat messages
        self.topic_model = BERTopic(
            embedding_model="all-MiniLM-L6-v2",
            min_topic_size=2,  # Small since individual chats may be short
            nr_topics="auto",
            verbose=False
        )
    
    def analyze_chat(self, messages: List[AnalyzedMessage]) -> dict:
        """
        Fit topic model on chat messages and compute divergence metrics.
        """
        if not messages:
            return self._empty_result()
            
        filtered_messages = [m for m in messages if m.content and m.content.strip()]
        texts = [m.content for m in filtered_messages]
        
        # BERTopic needs a reasonable amount of data
        if len(texts) < 5:
            logger.debug("Not enough messages for topic modeling")
            return self._empty_result()
            
        try:
            # Fit model
            topics, _ = self.topic_model.fit_transform(texts)
            
            # Get topic info
            topic_info = self.topic_model.get_topic_info()
            topic_labels = {
                row['Topic']: row['Name'] 
                for _, row in topic_info.iterrows()
            }
            
            metrics = self._compute_metrics(topics)
            segments = self.extract_segments(filtered_messages, topics)
            
            return {
                'topics': topics,
                'topic_labels': topic_labels,
                'metrics': metrics,
                'segments': segments
            }
            
        except Exception as e:
            logger.error(f"Topic modeling failed: {e}")
            return self._empty_result()
    
    def _compute_metrics(self, topics: List[int]) -> dict:
        num_topics = len(set(topics)) - (1 if -1 in topics else 0) # Exclude outlier topic -1
        
        # Topic entropy
        entropy = self.compute_topic_entropy(topics)
        
        # Transition rate
        transitions = 0
        if len(topics) > 1:
            for i in range(1, len(topics)):
                if topics[i] != topics[i-1]:
                    transitions += 1
            transition_rate = transitions / (len(topics) - 1)
        else:
            transition_rate = 0.0
            
        # Dominant topic ratio
        counts = Counter(topics)
        # Remove outlier topic -1 from consideration for dominant topic if possible
        valid_topics = [t for t in topics if t != -1]
        if valid_topics:
            valid_counts = Counter(valid_topics)
            most_common = valid_counts.most_common(1)
            dominant_ratio = most_common[0][1] / len(valid_topics)
        else:
             dominant_ratio = 0.0 if not topics else 1.0 # If all are outliers
             
        return {
            'num_topics': num_topics,
            'topic_entropy': entropy,
            'transition_rate': transition_rate,
            'dominant_topic_ratio': dominant_ratio
        }
    
    def compute_topic_entropy(self, topics: List[int]) -> float:
        """Shannon entropy of topic distribution."""
        if not topics:
            return 0.0
        counts = Counter(topics)
        total = len(topics)
        probs = [count / total for count in counts.values()]
        return -sum(p * np.log2(p) for p in probs if p > 0)
    
    def extract_segments(self, messages: List[AnalyzedMessage], topics: List[int]) -> List[dict]:
        """
        Group contiguous messages with same topic into segments.
        """
        segments = []
        if not topics:
            return segments
            
        current_topic = topics[0]
        start_idx = 0
        
        # We need to map back to original message indices since we might have filtered empty messages
        # But here we assume 1:1 mapping for simplicity given how analyze_chat extracts texts
        # Ideally we should pass indices or filter beforehand consistently.
        # For now, let's assume `messages` and `topics` are aligned in length.
        # Note: analyze_chat filtered empty messages, so topics length might be < messages length.
        # This is a potential bug. I should filter messages first.
        
        # Let's align them in `analyze_chat` properly, or here.
        # I'll update `analyze_chat` to pass filtered messages to `extract_segments`.
        
        for i, topic in enumerate(topics):
            if topic != current_topic:
                segments.append({
                    'start_idx': start_idx,
                    'end_idx': i - 1,
                    'topic': current_topic
                })
                current_topic = topic
                start_idx = i
        
        # Last segment
        segments.append({
            'start_idx': start_idx,
            'end_idx': len(topics) - 1,
            'topic': current_topic
        })
        
        return segments

    def _empty_result(self):
        return {
            'topics': [],
            'topic_labels': {},
            'metrics': {
                'num_topics': 0,
                'topic_entropy': 0.0,
                'transition_rate': 0.0,
                'dominant_topic_ratio': 1.0
            },
            'segments': []
        }
