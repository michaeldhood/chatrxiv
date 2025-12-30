"""
Topic Statement Generator Service

Generates concise topic statements for chat conversations using AI APIs.
Supports multiple providers (OpenAI, Anthropic) with fallback to simple heuristics.
"""
import os
import logging
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)


class TopicStatementGenerator:
    """
    Generates topic statements for chat conversations.
    
    Uses AI APIs (OpenAI, Anthropic) to generate concise summaries of what
    a chat conversation is about. Falls back to simple heuristics if API
    is unavailable.
    """
    
    def __init__(self, provider: str = "heuristic", api_key: Optional[str] = None):
        """
        Initialize topic statement generator.
        
        Parameters
        ----
        provider : str
            AI provider to use: "openai", "anthropic", or "heuristic"
        api_key : str, optional
            API key for the provider. If None, reads from environment variables.
        """
        self.provider = provider.lower()
        self.api_key = api_key
        
        if self.provider == "openai":
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                logger.warning("OPENAI_API_KEY not set, falling back to heuristic method")
                self.provider = "heuristic"
        elif self.provider == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not self.api_key:
                logger.warning("ANTHROPIC_API_KEY not set, falling back to heuristic method")
                self.provider = "heuristic"
        else:
            self.provider = "heuristic"
    
    def generate(self, messages: List[Dict[str, Any]], title: Optional[str] = None,
                 max_length: int = 100) -> str:
        """
        Generate a topic statement for a chat conversation.
        
        Parameters
        ----
        messages : List[Dict[str, Any]]
            List of message dictionaries with 'role' and 'text' fields
        title : str, optional
            Existing chat title for context
        max_length : int
            Maximum length of the topic statement in characters
            
        Returns
        ----
        str
            Generated topic statement
        """
        if not messages:
            return "Empty conversation"
        
        # Filter to only user and assistant messages with text
        text_messages = []
        for msg in messages:
            role = msg.get("role", "")
            text = msg.get("text", "") or msg.get("rich_text", "")
            if text and role in ("user", "assistant"):
                text_messages.append({"role": role, "text": text})
        
        if not text_messages:
            return "No text content"
        
        # Use appropriate generation method
        if self.provider == "openai":
            return self._generate_openai(text_messages, title, max_length)
        elif self.provider == "anthropic":
            return self._generate_anthropic(text_messages, title, max_length)
        else:
            return self._generate_heuristic(text_messages, title, max_length)
    
    def _generate_openai(self, messages: List[Dict[str, Any]], title: Optional[str],
                        max_length: int) -> str:
        """Generate topic statement using OpenAI API."""
        try:
            import openai
            
            # Build conversation context
            conversation_text = self._build_conversation_text(messages)
            
            # Create prompt
            prompt = f"""Generate a concise topic statement (max {max_length} characters) that summarizes what this conversation is about.

Chat title: {title or "Untitled"}

Conversation:
{conversation_text}

Topic statement:"""
            
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Fast and cost-effective
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates concise topic statements for chat conversations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.3,
            )
            
            topic = response.choices[0].message.content.strip()
            # Truncate if needed
            if len(topic) > max_length:
                topic = topic[:max_length-3] + "..."
            return topic
            
        except ImportError:
            logger.warning("openai package not installed, falling back to heuristic")
            return self._generate_heuristic(messages, title, max_length)
        except Exception as e:
            logger.error("Error generating topic statement with OpenAI: %s", e)
            return self._generate_heuristic(messages, title, max_length)
    
    def _generate_anthropic(self, messages: List[Dict[str, Any]], title: Optional[str],
                           max_length: int) -> str:
        """Generate topic statement using Anthropic API."""
        try:
            import anthropic
            
            # Build conversation context
            conversation_text = self._build_conversation_text(messages)
            
            # Create prompt
            prompt = f"""Generate a concise topic statement (max {max_length} characters) that summarizes what this conversation is about.

Chat title: {title or "Untitled"}

Conversation:
{conversation_text}

Topic statement:"""
            
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model="claude-3-haiku-20240307",  # Fast and cost-effective
                max_tokens=50,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            
            topic = response.content[0].text.strip()
            # Truncate if needed
            if len(topic) > max_length:
                topic = topic[:max_length-3] + "..."
            return topic
            
        except ImportError:
            logger.warning("anthropic package not installed, falling back to heuristic")
            return self._generate_heuristic(messages, title, max_length)
        except Exception as e:
            logger.error("Error generating topic statement with Anthropic: %s", e)
            return self._generate_heuristic(messages, title, max_length)
    
    def _generate_heuristic(self, messages: List[Dict[str, Any]], title: Optional[str],
                          max_length: int) -> str:
        """
        Generate topic statement using simple heuristics.
        
        This is a fallback method that doesn't require API access.
        It extracts key information from the first user message and title.
        """
        # Use title if available and reasonable
        if title and title != "Untitled Chat" and len(title) <= max_length:
            return title
        
        # Extract from first user message
        first_user_msg = None
        for msg in messages:
            if msg.get("role") == "user":
                first_user_msg = msg.get("text", "") or msg.get("rich_text", "")
                break
        
        if first_user_msg:
            # Take first sentence or first N characters
            # Remove common prefixes
            text = first_user_msg.strip()
            
            # Remove common prefixes
            prefixes = ["can you", "could you", "please", "help me", "i need", "i want"]
            text_lower = text.lower()
            for prefix in prefixes:
                if text_lower.startswith(prefix):
                    text = text[len(prefix):].strip()
                    # Remove leading punctuation
                    while text and text[0] in ",.!?:":
                        text = text[1:].strip()
                    break
            
            # Extract first sentence or truncate
            sentences = text.split(". ")
            if sentences:
                topic = sentences[0]
                if not topic.endswith(".") and len(sentences) == 1:
                    # No period found, try to find natural break
                    if len(topic) > max_length:
                        # Truncate at word boundary
                        words = topic.split()
                        topic = ""
                        for word in words:
                            if len(topic) + len(word) + 1 <= max_length - 3:
                                topic += (" " + word) if topic else word
                            else:
                                break
                        topic += "..."
                else:
                    topic = sentences[0] + "."
                
                if len(topic) > max_length:
                    topic = topic[:max_length-3] + "..."
                
                return topic
        
        # Fallback
        return "Chat conversation"
    
    def _build_conversation_text(self, messages: List[Dict[str, Any]], max_messages: int = 10) -> str:
        """
        Build conversation text for AI prompt.
        
        Parameters
        ----
        messages : List[Dict[str, Any]]
            List of messages
        max_messages : int
            Maximum number of messages to include
            
        Returns
        ----
        str
            Formatted conversation text
        """
        # Take first few messages to keep prompt short
        selected_messages = messages[:max_messages]
        
        lines = []
        for msg in selected_messages:
            role = msg.get("role", "unknown")
            text = msg.get("text", "") or msg.get("rich_text", "")
            # Truncate long messages
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(f"{role.capitalize()}: {text}")
        
        if len(messages) > max_messages:
            lines.append(f"... ({len(messages) - max_messages} more messages)")
        
        return "\n".join(lines)
    
    def update_chat_topic(self, db, chat_id: int) -> Optional[str]:
        """
        Generate and update topic statement for a chat in the database.
        
        Parameters
        ----
        db : ChatDatabase
            Database instance
        chat_id : int
            Chat ID
            
        Returns
        ----
        str, optional
            Generated topic statement, or None if generation failed
        """
        # Get chat data
        chat_data = db.get_chat(chat_id)
        if not chat_data:
            logger.warning("Chat %d not found", chat_id)
            return None
        
        # Generate topic statement
        topic = self.generate(
            messages=chat_data.get("messages", []),
            title=chat_data.get("title"),
        )
        
        # Update database
        success = db.update_topic_statement(chat_id, topic)
        if not success:
            logger.warning("Failed to update topic statement for chat %d", chat_id)
            return None
        
        logger.info("Generated topic statement for chat %d: %s", chat_id, topic)
        return topic
