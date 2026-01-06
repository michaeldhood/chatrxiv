"""
Approach 2: Topic Modeling with BERTopic.

Extracts discrete topics from conversation messages and measures
topic entropy and transitions to detect divergence.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import numpy as np

logger = logging.getLogger(__name__)

# Lazy import for BERTopic
_topic_model = None


class TopicDivergenceAnalyzer:
    """
    Analyzes topic divergence using BERTopic.
    
    Fits a topic model on conversation messages and computes:
    - Number of distinct topics
    - Topic entropy (higher = more divergent)
    - Transition rate (how often topics change)
    - Dominant topic ratio (concentration in primary topic)
    
    Attributes
    ----------
    embedding_model : str
        Name of the embedding model for BERTopic
    min_topic_size : int
        Minimum messages to form a topic
    """
    
    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        min_topic_size: int = 2,
    ):
        """
        Initialize the topic divergence analyzer.
        
        Parameters
        ----------
        embedding_model : str
            Sentence transformer model for embeddings
        min_topic_size : int
            Minimum messages needed to form a distinct topic.
            Set low (2) for short conversations.
        """
        self.embedding_model = embedding_model
        self.min_topic_size = min_topic_size
        self._model = None
    
    def _get_model(self):
        """
        Create a BERTopic model instance.
        
        Creates a new model each time since BERTopic models are
        typically fit per-conversation.
        """
        try:
            from bertopic import BERTopic
        except ImportError:
            raise ImportError(
                "bertopic is required for topic modeling analysis. "
                "Install with: pip install bertopic"
            )
        
        # Configure for small document sets (individual conversations)
        model = BERTopic(
            embedding_model=self.embedding_model,
            min_topic_size=self.min_topic_size,
            nr_topics="auto",
            calculate_probabilities=True,
            verbose=False,
        )
        
        return model
    
    def analyze_chat(
        self,
        message_texts: List[str],
        roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fit topic model on chat messages and compute divergence metrics.
        
        Parameters
        ----------
        message_texts : List[str]
            List of message texts in chronological order
        roles : List[str], optional
            Message roles ('user', 'assistant') - for potential weighting
            
        Returns
        -------
        dict
            {
                'topics': list[int],  # Topic ID per message (-1 = outlier)
                'topic_labels': dict[int, str],  # Topic ID -> label
                'topic_probabilities': np.ndarray,  # Prob distribution per message
                'metrics': {
                    'num_topics': int,
                    'topic_entropy': float,
                    'transition_rate': float,
                    'dominant_topic_ratio': float,
                },
                'segments': list[dict]  # Contiguous topic segments
            }
        """
        if not message_texts or len(message_texts) < 2:
            return self._empty_result()
        
        # Filter out very short or empty messages
        valid_messages = []
        valid_indices = []
        for i, text in enumerate(message_texts):
            if text and len(text.strip()) > 10:
                valid_messages.append(text)
                valid_indices.append(i)
        
        if len(valid_messages) < self.min_topic_size:
            return self._empty_result(len(message_texts))
        
        try:
            # Fit topic model
            model = self._get_model()
            topics, probs = model.fit_transform(valid_messages)
            
            # Map topics back to original indices
            full_topics = [-1] * len(message_texts)
            for idx, topic in zip(valid_indices, topics):
                full_topics[idx] = topic
            
            # Get topic info
            topic_info = model.get_topic_info()
            topic_labels = {}
            for _, row in topic_info.iterrows():
                topic_id = row['Topic']
                if topic_id != -1:  # Skip outlier topic
                    # Get top words for label
                    topic_words = model.get_topic(topic_id)
                    if topic_words:
                        label = ", ".join([word for word, _ in topic_words[:3]])
                        topic_labels[topic_id] = label
            
            # Compute metrics
            metrics = self._compute_metrics(full_topics)
            
            # Extract segments
            segments = self._extract_segments(full_topics)
            
            return {
                'topics': full_topics,
                'topic_labels': topic_labels,
                'topic_probabilities': probs if probs is not None else None,
                'metrics': metrics,
                'segments': segments,
            }
            
        except Exception as e:
            logger.warning("BERTopic analysis failed: %s. Using fallback.", e)
            return self._fallback_analysis(message_texts)
    
    def _empty_result(self, num_messages: int = 0) -> Dict[str, Any]:
        """Return empty result for edge cases."""
        return {
            'topics': [0] * num_messages if num_messages else [],
            'topic_labels': {0: "main topic"},
            'topic_probabilities': None,
            'metrics': {
                'num_topics': 1,
                'topic_entropy': 0.0,
                'transition_rate': 0.0,
                'dominant_topic_ratio': 1.0,
            },
            'segments': [{
                'topic_id': 0,
                'start_idx': 0,
                'end_idx': num_messages - 1 if num_messages > 0 else 0,
                'label': "main topic",
            }] if num_messages > 0 else [],
        }
    
    def _fallback_analysis(self, message_texts: List[str]) -> Dict[str, Any]:
        """
        Fallback analysis when BERTopic fails.
        
        Uses simple heuristics based on message similarity.
        """
        from .embedding_drift import EmbeddingDriftAnalyzer
        
        try:
            analyzer = EmbeddingDriftAnalyzer()
            drift_result = analyzer.compute_drift_curve(message_texts)
            
            # Use drift to estimate topic changes
            drift_scores = drift_result['drift_scores']
            
            # Assign pseudo-topics based on drift thresholds
            topics = []
            current_topic = 0
            for i, score in enumerate(drift_scores):
                if i > 0 and score > 0.3 and drift_scores[i-1] < 0.25:
                    current_topic += 1
                topics.append(current_topic)
            
            # Compute metrics from pseudo-topics
            metrics = self._compute_metrics(topics)
            segments = self._extract_segments(topics)
            
            return {
                'topics': topics,
                'topic_labels': {i: f"topic_{i}" for i in range(current_topic + 1)},
                'topic_probabilities': None,
                'metrics': metrics,
                'segments': segments,
            }
            
        except Exception as e:
            logger.error("Fallback analysis also failed: %s", e)
            return self._empty_result(len(message_texts))
    
    def _compute_metrics(self, topics: List[int]) -> Dict[str, Any]:
        """
        Compute summary metrics from topic assignments.
        
        Parameters
        ----------
        topics : List[int]
            Topic ID per message
            
        Returns
        -------
        dict
            Topic metrics
        """
        # Filter out outliers (-1) for counting
        valid_topics = [t for t in topics if t != -1]
        
        if not valid_topics:
            return {
                'num_topics': 1,
                'topic_entropy': 0.0,
                'transition_rate': 0.0,
                'dominant_topic_ratio': 1.0,
            }
        
        # Count topics
        topic_counts = Counter(valid_topics)
        num_topics = len(topic_counts)
        
        # Entropy
        entropy = self.compute_topic_entropy(valid_topics)
        
        # Transition rate
        transitions = 0
        prev_topic = None
        for topic in topics:
            if topic != -1:
                if prev_topic is not None and topic != prev_topic:
                    transitions += 1
                prev_topic = topic
        
        transition_rate = transitions / len(valid_topics) if valid_topics else 0.0
        
        # Dominant topic ratio
        if topic_counts:
            most_common = topic_counts.most_common(1)[0][1]
            dominant_ratio = most_common / len(valid_topics)
        else:
            dominant_ratio = 1.0
        
        return {
            'num_topics': num_topics,
            'topic_entropy': entropy,
            'transition_rate': transition_rate,
            'dominant_topic_ratio': dominant_ratio,
        }
    
    def compute_topic_entropy(self, topics: List[int]) -> float:
        """
        Compute Shannon entropy of topic distribution.
        
        Higher entropy = more diverse topics = more divergent.
        
        Parameters
        ----------
        topics : List[int]
            Topic assignments
            
        Returns
        -------
        float
            Shannon entropy in bits
        """
        if not topics:
            return 0.0
        
        counts = Counter(topics)
        total = len(topics)
        probs = [count / total for count in counts.values()]
        
        # Shannon entropy
        entropy = -sum(p * np.log2(p) for p in probs if p > 0)
        
        return float(entropy)
    
    def _extract_segments(self, topics: List[int]) -> List[Dict[str, Any]]:
        """
        Group contiguous messages with same topic into segments.
        
        Parameters
        ----------
        topics : List[int]
            Topic ID per message
            
        Returns
        -------
        list[dict]
            List of segment dictionaries
        """
        if not topics:
            return []
        
        segments = []
        current_segment = {
            'topic_id': topics[0],
            'start_idx': 0,
            'end_idx': 0,
        }
        
        for i in range(1, len(topics)):
            if topics[i] == current_segment['topic_id']:
                # Extend current segment
                current_segment['end_idx'] = i
            else:
                # Close current segment and start new one
                segments.append(current_segment)
                current_segment = {
                    'topic_id': topics[i],
                    'start_idx': i,
                    'end_idx': i,
                }
        
        # Don't forget the last segment
        segments.append(current_segment)
        
        return segments
    
    def get_segment_boundaries(self, topics: List[int]) -> List[int]:
        """
        Get indices where segments start (excluding index 0).
        
        Parameters
        ----------
        topics : List[int]
            Topic assignments
            
        Returns
        -------
        list[int]
            Start indices of new segments
        """
        boundaries = []
        prev_topic = topics[0] if topics else None
        
        for i in range(1, len(topics)):
            if topics[i] != prev_topic and topics[i] != -1:
                boundaries.append(i)
            if topics[i] != -1:
                prev_topic = topics[i]
        
        return boundaries
    
    def analyze_with_embeddings(
        self,
        message_texts: List[str],
        embeddings: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Analyze using pre-computed embeddings.
        
        More efficient when embeddings are already available from
        the drift analyzer.
        
        Parameters
        ----------
        message_texts : List[str]
            Message texts
        embeddings : np.ndarray
            Pre-computed embeddings
            
        Returns
        -------
        dict
            Analysis results
        """
        if len(message_texts) < self.min_topic_size:
            return self._empty_result(len(message_texts))
        
        try:
            from bertopic import BERTopic
            from sklearn.cluster import AgglomerativeClustering
            
            # Use pre-computed embeddings with BERTopic
            model = BERTopic(
                embedding_model=None,  # Don't re-embed
                min_topic_size=self.min_topic_size,
                nr_topics="auto",
                verbose=False,
            )
            
            topics, probs = model.fit_transform(message_texts, embeddings)
            
            # Get topic labels
            topic_info = model.get_topic_info()
            topic_labels = {}
            for _, row in topic_info.iterrows():
                topic_id = row['Topic']
                if topic_id != -1:
                    topic_words = model.get_topic(topic_id)
                    if topic_words:
                        label = ", ".join([word for word, _ in topic_words[:3]])
                        topic_labels[topic_id] = label
            
            metrics = self._compute_metrics(topics)
            segments = self._extract_segments(topics)
            
            return {
                'topics': topics,
                'topic_labels': topic_labels,
                'topic_probabilities': probs,
                'metrics': metrics,
                'segments': segments,
            }
            
        except Exception as e:
            logger.warning("Topic modeling with embeddings failed: %s", e)
            return self._fallback_analysis(message_texts)
