from sentence_transformers import SentenceTransformer
import numpy as np
from scipy.spatial.distance import cosine
from typing import List, Dict, Any, Optional
from src.analysis.models import AnalyzedMessage

class EmbeddingDriftAnalyzer:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
    
    def embed(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True)
    
    def embed_messages(self, messages: List[str]) -> np.ndarray:
        """Embed multiple messages and return mean embedding."""
        if not messages:
            # Return zero vector of appropriate size (MiniLM is 384)
            # We can get dimension from model
            return np.zeros(self.model.get_sentence_embedding_dimension())
            
        embeddings = self.model.encode(messages, normalize_embeddings=True)
        if len(embeddings.shape) == 1:
            return embeddings
        return np.mean(embeddings, axis=0)
    
    def compute_drift_curve(
        self, 
        messages: List[AnalyzedMessage],
        anchor_window: int = 3,  # Use first N messages as anchor
        rolling_window: int = 1   # Compare each message individually
    ) -> dict:
        """
        Compute divergence scores for each message relative to the anchor.
        
        Returns:
            {
                'anchor_embedding': np.ndarray,
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
        if not messages:
            return {
                'anchor_embedding': None,
                'drift_scores': [],
                'metrics': {
                    'max_drift': 0.0,
                    'mean_drift': 0.0,
                    'drift_velocity': 0.0,
                    'final_drift': 0.0,
                    'return_count': 0
                }
            }
            
        # Get text content
        texts = [m.content for m in messages if m.content and m.content.strip()]
        if not texts:
             return {
                'anchor_embedding': None,
                'drift_scores': [],
                'metrics': {
                    'max_drift': 0.0,
                    'mean_drift': 0.0,
                    'drift_velocity': 0.0,
                    'final_drift': 0.0,
                    'return_count': 0
                }
            }
            
        # Compute embeddings for all messages
        # We process all texts at once for efficiency
        all_embeddings = self.model.encode(texts, normalize_embeddings=True)
        
        # Calculate anchor from first N messages
        anchor_texts_count = min(len(texts), anchor_window)
        anchor_embedding = np.mean(all_embeddings[:anchor_texts_count], axis=0)
        
        # Calculate drift scores
        drift_scores = []
        for emb in all_embeddings:
            # Cosine distance is 1 - cosine_similarity
            # distance ranges from 0 (identical) to 2 (opposite)
            # usually we want 0 to 1 for semantic drift (where 1 is orthogonal/unrelated)
            score = cosine(anchor_embedding, emb)
            drift_scores.append(score)
            
        # Compute metrics
        scores_array = np.array(drift_scores)
        max_drift = float(np.max(scores_array))
        mean_drift = float(np.mean(scores_array))
        final_drift = float(drift_scores[-1])
        
        # Drift velocity (derivative)
        if len(drift_scores) > 1:
            velocity = np.diff(scores_array)
            drift_velocity = float(np.mean(np.abs(velocity)))
        else:
            drift_velocity = 0.0
            
        # Return count (simple implementation: crossing threshold downwards)
        # Assuming high drift is > 0.5 and low is < 0.3
        return_count = 0
        is_high = False
        for score in drift_scores:
            if score > 0.5:
                is_high = True
            elif score < 0.3 and is_high:
                return_count += 1
                is_high = False
                
        return {
            'anchor_embedding': anchor_embedding,
            'drift_scores': drift_scores,
            'metrics': {
                'max_drift': max_drift,
                'mean_drift': mean_drift,
                'drift_velocity': drift_velocity,
                'final_drift': final_drift,
                'return_count': return_count,
            }
        }
    
    def detect_changepoints(
        self,
        drift_scores: List[float],
        threshold: float = 0.3,
        min_segment_length: int = 2
    ) -> List[int]:
        """
        Detect indices where significant topic shifts occur.
        """
        changepoints = []
        if not drift_scores:
            return changepoints
            
        # Simple threshold detection
        # We look for sustained drift above threshold
        
        in_drift = False
        drift_start_idx = -1
        
        for i, score in enumerate(drift_scores):
            if score > threshold:
                if not in_drift:
                    in_drift = True
                    drift_start_idx = i
            else:
                if in_drift:
                    # Drift ended
                    duration = i - drift_start_idx
                    if duration >= min_segment_length:
                        changepoints.append(drift_start_idx)
                    in_drift = False
        
        # Check if we ended in drift
        if in_drift and (len(drift_scores) - drift_start_idx >= min_segment_length):
            changepoints.append(drift_start_idx)
            
        return changepoints
