"""
Approach 1: Semantic Embedding Drift Analysis.

Measures cosine distance from conversation anchor over time to detect
when conversations drift from their original topic.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Lazy import for sentence_transformers to avoid startup cost
_model = None
_model_name = None


def _get_model(model_name: str = "all-MiniLM-L6-v2"):
    """
    Lazy load the sentence transformer model.
    
    Uses global singleton to avoid repeated loading.
    """
    global _model, _model_name
    
    if _model is None or _model_name != model_name:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence transformer model: %s", model_name)
            _model = SentenceTransformer(model_name)
            _model_name = model_name
            logger.info("Model loaded successfully")
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embedding drift analysis. "
                "Install with: pip install sentence-transformers"
            )
    
    return _model


class EmbeddingDriftAnalyzer:
    """
    Analyzes topic drift using semantic embeddings.
    
    Computes embeddings for messages and measures how far the conversation
    drifts from its initial anchor over time.
    
    The anchor is computed from the first few messages (configurable)
    and drift is measured as cosine distance from this anchor.
    
    Attributes
    ----------
    model_name : str
        Name of the sentence-transformers model to use
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedding drift analyzer.
        
        Parameters
        ----------
        model_name : str
            Name of the sentence-transformers model.
            Default "all-MiniLM-L6-v2" is fast and good for general text.
            For code-heavy content, consider "all-mpnet-base-v2".
        """
        self.model_name = model_name
        self._model = None
    
    @property
    def model(self):
        """Lazy load the model."""
        if self._model is None:
            self._model = _get_model(self.model_name)
        return self._model
    
    def embed(self, text: str) -> np.ndarray:
        """
        Compute embedding for a single text.
        
        Parameters
        ----------
        text : str
            Text to embed
            
        Returns
        -------
        np.ndarray
            Normalized embedding vector
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return np.zeros(self.model.get_sentence_embedding_dimension())
        
        return self.model.encode(text, normalize_embeddings=True)
    
    def embed_messages(self, messages: List[str]) -> np.ndarray:
        """
        Embed multiple messages and return mean embedding.
        
        Parameters
        ----------
        messages : List[str]
            List of message texts
            
        Returns
        -------
        np.ndarray
            Mean embedding (normalized)
        """
        # Filter out empty messages
        non_empty = [m for m in messages if m and m.strip()]
        
        if not non_empty:
            return np.zeros(self.model.get_sentence_embedding_dimension())
        
        embeddings = self.model.encode(non_empty, normalize_embeddings=True)
        mean_embedding = np.mean(embeddings, axis=0)
        
        # Normalize the mean
        norm = np.linalg.norm(mean_embedding)
        if norm > 0:
            mean_embedding = mean_embedding / norm
        
        return mean_embedding
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        Embed a batch of texts.
        
        Parameters
        ----------
        texts : List[str]
            List of texts to embed
            
        Returns
        -------
        np.ndarray
            Array of embeddings, shape (n_texts, embedding_dim)
        """
        # Replace empty texts with placeholder to maintain indexing
        processed = [t if t and t.strip() else " " for t in texts]
        return self.model.encode(processed, normalize_embeddings=True)
    
    def compute_drift_curve(
        self,
        message_texts: List[str],
        anchor_window: int = 3,
        rolling_window: int = 1,
    ) -> Dict[str, Any]:
        """
        Compute divergence scores for each message relative to the anchor.
        
        The anchor is computed from the first `anchor_window` messages.
        Each subsequent message (or rolling window) is compared to this anchor.
        
        Parameters
        ----------
        message_texts : List[str]
            List of message texts in chronological order
        anchor_window : int
            Number of initial messages to use for anchor (default: 3)
        rolling_window : int
            Window size for computing current position (default: 1)
            Use 1 for per-message drift, larger for smoothed drift.
            
        Returns
        -------
        dict
            {
                'anchor_embedding': np.ndarray,
                'embeddings': np.ndarray,  # All message embeddings
                'drift_scores': list[float],  # 0 = identical, 1 = orthogonal
                'metrics': {
                    'max_drift': float,
                    'mean_drift': float,
                    'drift_velocity': float,
                    'final_drift': float,
                    'return_count': int,
                }
            }
        """
        if not message_texts:
            return {
                'anchor_embedding': np.zeros(384),
                'embeddings': np.array([]),
                'drift_scores': [],
                'metrics': {
                    'max_drift': 0.0,
                    'mean_drift': 0.0,
                    'drift_velocity': 0.0,
                    'final_drift': 0.0,
                    'return_count': 0,
                }
            }
        
        # Embed all messages at once for efficiency
        all_embeddings = self.embed_batch(message_texts)
        
        # Compute anchor from first N messages
        anchor_texts = message_texts[:anchor_window]
        anchor_embedding = self.embed_messages(anchor_texts)
        
        # Compute drift for each position
        drift_scores = []
        
        for i in range(len(message_texts)):
            if rolling_window == 1:
                current_embedding = all_embeddings[i]
            else:
                # Use rolling window
                start_idx = max(0, i - rolling_window + 1)
                window_embeddings = all_embeddings[start_idx:i+1]
                current_embedding = np.mean(window_embeddings, axis=0)
                norm = np.linalg.norm(current_embedding)
                if norm > 0:
                    current_embedding = current_embedding / norm
            
            # Cosine distance (1 - cosine similarity)
            similarity = np.dot(anchor_embedding, current_embedding)
            drift = 1.0 - similarity
            drift_scores.append(float(drift))
        
        # Compute metrics
        metrics = self._compute_metrics(drift_scores)
        
        return {
            'anchor_embedding': anchor_embedding,
            'embeddings': all_embeddings,
            'drift_scores': drift_scores,
            'metrics': metrics,
        }
    
    def _compute_metrics(self, drift_scores: List[float]) -> Dict[str, Any]:
        """
        Compute summary metrics from drift scores.
        
        Parameters
        ----------
        drift_scores : List[float]
            Per-message drift scores
            
        Returns
        -------
        dict
            Summary metrics
        """
        if not drift_scores:
            return {
                'max_drift': 0.0,
                'mean_drift': 0.0,
                'drift_velocity': 0.0,
                'final_drift': 0.0,
                'return_count': 0,
            }
        
        scores = np.array(drift_scores)
        
        # Basic statistics
        max_drift = float(np.max(scores))
        mean_drift = float(np.mean(scores))
        final_drift = float(scores[-1])
        
        # Drift velocity (average change between consecutive scores)
        if len(scores) > 1:
            velocity = np.mean(np.abs(np.diff(scores)))
        else:
            velocity = 0.0
        
        # Return count (times drift decreased by > 0.1 after increasing)
        return_count = 0
        if len(scores) > 2:
            for i in range(2, len(scores)):
                # Check if we had been increasing and now decreased
                prev_change = scores[i-1] - scores[i-2]
                curr_change = scores[i] - scores[i-1]
                if prev_change > 0.05 and curr_change < -0.1:
                    return_count += 1
        
        return {
            'max_drift': max_drift,
            'mean_drift': mean_drift,
            'drift_velocity': float(velocity),
            'final_drift': final_drift,
            'return_count': return_count,
        }
    
    def detect_changepoints(
        self,
        drift_scores: List[float],
        threshold: float = 0.3,
        min_segment_length: int = 2,
        return_threshold: float = 0.15,
    ) -> List[int]:
        """
        Detect indices where significant topic shifts occur.
        
        Uses a threshold + persistence approach:
        - Mark as changepoint when drift exceeds threshold
        - Require drift to persist for min_segment_length messages
        - Also detect "returns" where conversation comes back to anchor
        
        Parameters
        ----------
        drift_scores : List[float]
            Per-message drift scores from compute_drift_curve
        threshold : float
            Drift threshold for considering a potential boundary (default: 0.3)
        min_segment_length : int
            Minimum messages in a segment (default: 2)
        return_threshold : float
            Threshold for detecting returns to anchor (default: 0.15)
            
        Returns
        -------
        List[int]
            Indices where segment boundaries should be placed
            (the index is the START of a new segment)
        """
        if len(drift_scores) < min_segment_length * 2:
            return []  # Not enough messages for meaningful segmentation
        
        changepoints = []
        scores = np.array(drift_scores)
        
        # State tracking
        in_diverged_region = False
        divergence_start = 0
        last_changepoint = 0
        
        for i in range(1, len(scores)):
            # Skip if too close to last changepoint
            if i - last_changepoint < min_segment_length:
                continue
            
            prev_score = scores[i-1]
            curr_score = scores[i]
            
            # Detect divergence onset
            if not in_diverged_region and curr_score > threshold:
                # Check if this persists
                future_scores = scores[i:i+min_segment_length]
                if len(future_scores) >= min_segment_length and np.mean(future_scores) > threshold * 0.8:
                    changepoints.append(i)
                    in_diverged_region = True
                    divergence_start = i
                    last_changepoint = i
            
            # Detect return to anchor
            elif in_diverged_region and curr_score < return_threshold:
                # Check if return persists
                future_scores = scores[i:i+min_segment_length]
                if len(future_scores) >= min_segment_length and np.mean(future_scores) < return_threshold * 1.5:
                    changepoints.append(i)
                    in_diverged_region = False
                    last_changepoint = i
            
            # Detect significant jumps (sudden topic change)
            elif abs(curr_score - prev_score) > 0.2:
                # Significant change in drift
                if i - last_changepoint >= min_segment_length:
                    changepoints.append(i)
                    last_changepoint = i
                    in_diverged_region = curr_score > threshold
        
        return changepoints
    
    def analyze_chat(
        self,
        message_texts: List[str],
        anchor_window: int = 3,
        drift_threshold: float = 0.3,
        min_segment_length: int = 2,
    ) -> Dict[str, Any]:
        """
        Complete analysis of a chat conversation.
        
        Convenience method that runs compute_drift_curve and detect_changepoints.
        
        Parameters
        ----------
        message_texts : List[str]
            List of message texts
        anchor_window : int
            Messages to use for anchor
        drift_threshold : float
            Threshold for changepoint detection
        min_segment_length : int
            Minimum segment size
            
        Returns
        -------
        dict
            Complete analysis results including drift curve and changepoints
        """
        # Compute drift curve
        drift_result = self.compute_drift_curve(
            message_texts,
            anchor_window=anchor_window,
        )
        
        # Detect changepoints
        changepoints = self.detect_changepoints(
            drift_result['drift_scores'],
            threshold=drift_threshold,
            min_segment_length=min_segment_length,
        )
        
        return {
            **drift_result,
            'changepoints': changepoints,
            'num_segments': len(changepoints) + 1,
        }
    
    def compute_segment_similarity(
        self,
        segment1_texts: List[str],
        segment2_texts: List[str],
    ) -> float:
        """
        Compute similarity between two segments.
        
        Useful for cross-chat segment linking.
        
        Parameters
        ----------
        segment1_texts : List[str]
            Texts from first segment
        segment2_texts : List[str]
            Texts from second segment
            
        Returns
        -------
        float
            Cosine similarity (0-1)
        """
        emb1 = self.embed_messages(segment1_texts)
        emb2 = self.embed_messages(segment2_texts)
        
        return float(np.dot(emb1, emb2))
