import anthropic
import json
import logging
from typing import List, Dict, Any
from src.analysis.models import AnalyzedMessage, MessageRelation

logger = logging.getLogger(__name__)

class LLMDivergenceAnalyzer:
    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        try:
            self.client = anthropic.Anthropic()
        except Exception as e:
            logger.warning(f"Anthropic client initialization failed: {e}. LLM analysis will be disabled.")
            self.client = None
        self.model = model
    
    def classify_message(
        self,
        conversation_so_far: List[AnalyzedMessage],
        current_message: AnalyzedMessage,
        original_anchor: str
    ) -> dict:
        """
        Classify how the current message relates to the conversation.
        """
        if not self.client:
            return {
                'relation': MessageRelation.CONTINUING,
                'relevance_score': 10.0,
                'suggested_segment_break': False,
                'reasoning': "LLM not available"
            }
            
        prompt = f"""Analyze how this message relates to the conversation's original topic.

Original topic/question:
{original_anchor}

Conversation so far (last 10 messages):
{self._format_conversation(conversation_so_far[-10:])}

Current message to classify:
[{current_message.role.upper()}]: {current_message.content}

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
3. Brief reasoning

Respond in JSON format:
{{
    "relation": "...",
    "relevance_score": X,
    "suggested_segment_break": true/false,
    "reasoning": "..."
}}"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.content[0].text
            # Simple JSON extraction
            json_str = content[content.find('{'):content.rfind('}')+1]
            result = json.loads(json_str)
            
            return {
                'relation': MessageRelation(result['relation'].lower()),
                'relevance_score': float(result['relevance_score']),
                'suggested_segment_break': bool(result['suggested_segment_break']),
                'reasoning': result['reasoning']
            }
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return {
                'relation': MessageRelation.CONTINUING,
                'relevance_score': 5.0,
                'suggested_segment_break': False,
                'reasoning': f"Error: {e}"
            }
    
    def analyze_full_chat(self, messages: List[AnalyzedMessage]) -> dict:
        """
        Analyze entire chat.
        """
        if not messages:
            return {}
            
        # Determine anchor from first user message
        original_anchor = "Unknown topic"
        for m in messages:
            if m.role == 'user':
                original_anchor = m.content[:500] # Truncate
                break
                
        results = []
        conversation_so_far = []
        
        for msg in messages:
            # Skip system messages or very short ones if needed, but for now classify all
            result = self.classify_message(conversation_so_far, msg, original_anchor)
            results.append({
                'message_id': msg.id,
                **result
            })
            conversation_so_far.append(msg)
            
        return {'message_analysis': results}

    def _format_conversation(self, messages: List[AnalyzedMessage]) -> str:
        return "\n".join([f"[{m.role.upper()}]: {m.content[:200]}..." for m in messages])
