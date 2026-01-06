"""
Approach 3: LLM-as-Judge for Topic Divergence.

Uses Claude to classify each message's relationship to the conversation anchor,
providing high-quality semantic understanding of topic changes.
"""
import json
import logging
import os
from typing import List, Dict, Any, Optional

from .models import MessageRelation, MessageClassification

logger = logging.getLogger(__name__)


class LLMDivergenceAnalyzer:
    """
    Analyzes topic divergence using Claude as a judge.
    
    For each message, Claude classifies:
    - How the message relates to the original topic
    - Relevance score (0-10)
    - Whether it should start a new segment
    
    This provides the highest quality analysis but is slower and
    costs API usage. Best used for detailed analysis or ensemble.
    
    Attributes
    ----------
    model : str
        Claude model to use
    max_context_messages : int
        Maximum recent messages to include as context
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_context_messages: int = 10,
    ):
        """
        Initialize the LLM divergence analyzer.
        
        Parameters
        ----------
        model : str
            Claude model to use. Default is claude-sonnet-4 for good
            balance of quality and cost.
        max_context_messages : int
            Maximum messages to include in context window.
        """
        self.model = model
        self.max_context_messages = max_context_messages
        self._client = None
    
    @property
    def client(self):
        """Lazy load the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except ImportError:
                raise ImportError(
                    "anthropic is required for LLM-based analysis. "
                    "Install with: pip install anthropic"
                )
        return self._client
    
    def _format_conversation(
        self,
        messages: List[Dict[str, str]],
        include_indices: bool = True,
    ) -> str:
        """
        Format conversation for prompt.
        
        Parameters
        ----------
        messages : List[Dict[str, str]]
            Messages with 'role' and 'text' keys
        include_indices : bool
            Whether to include message indices
            
        Returns
        -------
        str
            Formatted conversation
        """
        lines = []
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unknown').upper()
            text = msg.get('text', '')
            
            # Truncate very long messages
            if len(text) > 1000:
                text = text[:1000] + "..."
            
            if include_indices:
                lines.append(f"[{i}] {role}: {text}")
            else:
                lines.append(f"{role}: {text}")
        
        return "\n\n".join(lines)
    
    def classify_message(
        self,
        conversation_so_far: List[Dict[str, str]],
        current_message: Dict[str, str],
        original_anchor: str,
        message_idx: int,
    ) -> MessageClassification:
        """
        Classify how a message relates to the conversation.
        
        Parameters
        ----------
        conversation_so_far : List[Dict[str, str]]
            Previous messages (will be trimmed to max_context_messages)
        current_message : Dict[str, str]
            Message to classify
        original_anchor : str
            Summary or first message representing the original topic
        message_idx : int
            Index of the current message
            
        Returns
        -------
        MessageClassification
            Classification result
        """
        # Trim context to recent messages
        context = conversation_so_far[-self.max_context_messages:]
        
        prompt = f"""Analyze how this message relates to the conversation's original topic.

Original topic/question:
{original_anchor}

Conversation so far:
{self._format_conversation(context)}

Current message to classify:
{current_message.get('role', 'USER').upper()}: {current_message.get('text', '')}

Classify this message as one of:
- CONTINUING: Directly addressing the original topic
- CLARIFYING: Asking for clarification to better address the topic
- DRILLING: Going deeper into a subtopic (still related, but narrower)
- BRANCHING: Starting a new, different topic
- TANGENT: Brief aside, likely to return
- CONCLUDING: Wrapping up the current topic
- RETURNING: Coming back to a previous topic after a departure

Also provide:
1. A relevance score (0-10) for how relevant this is to the original topic
2. Whether this message should start a new segment (true/false)
3. Brief reasoning (1-2 sentences)

Respond in JSON format only, no other text:
{{
    "relation": "...",
    "relevance_score": X,
    "suggested_segment_break": true/false,
    "reasoning": "..."
}}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse response
            content = response.content[0].text.strip()
            
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            result = json.loads(content)
            
            # Map relation string to enum
            relation_str = result.get("relation", "CONTINUING").upper()
            try:
                relation = MessageRelation(relation_str.lower())
            except ValueError:
                relation = MessageRelation.CONTINUING
            
            return MessageClassification(
                message_idx=message_idx,
                relation=relation,
                relevance_score=float(result.get("relevance_score", 5)),
                suggested_segment_break=bool(result.get("suggested_segment_break", False)),
                reasoning=result.get("reasoning", ""),
            )
            
        except Exception as e:
            logger.warning("LLM classification failed for message %d: %s", message_idx, e)
            # Return neutral classification on error
            return MessageClassification(
                message_idx=message_idx,
                relation=MessageRelation.CONTINUING,
                relevance_score=5.0,
                suggested_segment_break=False,
                reasoning=f"Classification error: {str(e)}",
            )
    
    def analyze_full_chat(
        self,
        messages: List[Dict[str, str]],
        anchor_summary: Optional[str] = None,
        batch_size: int = 5,
    ) -> Dict[str, Any]:
        """
        Analyze entire chat and return classifications and metrics.
        
        Parameters
        ----------
        messages : List[Dict[str, str]]
            All messages in the chat
        anchor_summary : str, optional
            Summary of the original topic. If not provided, uses first message.
        batch_size : int
            Number of messages to analyze per API call (for batching)
            
        Returns
        -------
        dict
            {
                'classifications': list[MessageClassification],
                'metrics': {
                    'mean_relevance': float,
                    'branch_count': int,
                    'tangent_count': int,
                    'drill_count': int,
                },
                'suggested_changepoints': list[int],
            }
        """
        if not messages:
            return {
                'classifications': [],
                'metrics': {
                    'mean_relevance': 10.0,
                    'branch_count': 0,
                    'tangent_count': 0,
                    'drill_count': 0,
                },
                'suggested_changepoints': [],
            }
        
        # Use first user message as anchor if not provided
        if anchor_summary is None:
            for msg in messages:
                if msg.get('role') == 'user' and msg.get('text'):
                    anchor_summary = msg['text'][:500]  # Truncate if long
                    break
            if anchor_summary is None:
                anchor_summary = messages[0].get('text', '')[:500]
        
        # Analyze each message (could batch in future for efficiency)
        classifications = []
        
        for i, msg in enumerate(messages):
            if i == 0:
                # First message is always the anchor
                classifications.append(MessageClassification(
                    message_idx=0,
                    relation=MessageRelation.CONTINUING,
                    relevance_score=10.0,
                    suggested_segment_break=False,
                    reasoning="First message defines the anchor topic.",
                ))
                continue
            
            # Classify this message
            classification = self.classify_message(
                conversation_so_far=messages[:i],
                current_message=msg,
                original_anchor=anchor_summary,
                message_idx=i,
            )
            classifications.append(classification)
        
        # Compute metrics
        relevance_scores = [c.relevance_score for c in classifications]
        mean_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 10.0
        
        branch_count = sum(1 for c in classifications if c.relation == MessageRelation.BRANCHING)
        tangent_count = sum(1 for c in classifications if c.relation == MessageRelation.TANGENT)
        drill_count = sum(1 for c in classifications if c.relation == MessageRelation.DRILLING)
        
        # Get suggested changepoints
        suggested_changepoints = [
            c.message_idx for c in classifications
            if c.suggested_segment_break
        ]
        
        return {
            'classifications': classifications,
            'metrics': {
                'mean_relevance': mean_relevance,
                'branch_count': branch_count,
                'tangent_count': tangent_count,
                'drill_count': drill_count,
            },
            'suggested_changepoints': suggested_changepoints,
        }
    
    def analyze_batch(
        self,
        messages: List[Dict[str, str]],
        anchor_summary: str,
        start_idx: int = 0,
    ) -> List[MessageClassification]:
        """
        Analyze a batch of messages in a single API call.
        
        More efficient than individual calls for long conversations.
        
        Parameters
        ----------
        messages : List[Dict[str, str]]
            Messages to analyze
        anchor_summary : str
            Original topic summary
        start_idx : int
            Starting index for message numbering
            
        Returns
        -------
        list[MessageClassification]
            Classifications for each message
        """
        if not messages:
            return []
        
        prompt = f"""Analyze how each of these messages relates to the conversation's original topic.

Original topic:
{anchor_summary}

Messages to analyze:
{self._format_conversation(messages, include_indices=True)}

For EACH message, classify as one of:
- CONTINUING: Directly addressing the original topic
- CLARIFYING: Asking for clarification
- DRILLING: Going deeper into a subtopic
- BRANCHING: Starting a new topic
- TANGENT: Brief aside
- CONCLUDING: Wrapping up
- RETURNING: Coming back to earlier topic

Respond with a JSON array, one object per message:
[
    {{
        "index": 0,
        "relation": "...",
        "relevance_score": X,
        "suggested_segment_break": true/false,
        "reasoning": "..."
    }},
    ...
]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.content[0].text.strip()
            
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            results = json.loads(content)
            
            classifications = []
            for i, result in enumerate(results):
                relation_str = result.get("relation", "CONTINUING").upper()
                try:
                    relation = MessageRelation(relation_str.lower())
                except ValueError:
                    relation = MessageRelation.CONTINUING
                
                classifications.append(MessageClassification(
                    message_idx=start_idx + i,
                    relation=relation,
                    relevance_score=float(result.get("relevance_score", 5)),
                    suggested_segment_break=bool(result.get("suggested_segment_break", False)),
                    reasoning=result.get("reasoning", ""),
                ))
            
            return classifications
            
        except Exception as e:
            logger.error("Batch analysis failed: %s", e)
            # Return neutral classifications
            return [
                MessageClassification(
                    message_idx=start_idx + i,
                    relation=MessageRelation.CONTINUING,
                    relevance_score=5.0,
                    suggested_segment_break=False,
                    reasoning=f"Batch analysis error: {str(e)}",
                )
                for i in range(len(messages))
            ]
    
    def generate_segment_summary(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """
        Generate a summary for a conversation segment.
        
        Useful for creating topic labels and for cross-chat matching.
        
        Parameters
        ----------
        messages : List[Dict[str, str]]
            Messages in the segment
            
        Returns
        -------
        str
            1-2 sentence summary of the segment
        """
        prompt = f"""Summarize the main topic of this conversation segment in 1-2 sentences.
Focus on WHAT is being discussed, not HOW.

Conversation:
{self._format_conversation(messages, include_indices=False)}

Summary (1-2 sentences only):"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.error("Summary generation failed: %s", e)
            # Return first user message as fallback
            for msg in messages:
                if msg.get('role') == 'user' and msg.get('text'):
                    return msg['text'][:200]
            return "Unknown topic"
