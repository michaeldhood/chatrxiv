"""
Module for generating summaries of chat conversations.

Provides utilities to create concise summaries including:
- Initial query/topic
- Message statistics (count, word count)
- Key topics extracted from the conversation
"""
import re
from typing import Dict, Any, List, Optional
from collections import Counter
import logging

logger = logging.getLogger(__name__)

# Common stop words to filter out when extracting topics
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare', 'ought',
    'used', 'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
    'she', 'we', 'they', 'what', 'which', 'who', 'whom', 'when', 'where',
    'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
    'than', 'too', 'very', 'just', 'also', 'now', 'here', 'there', 'then',
    'once', 'if', 'my', 'your', 'his', 'her', 'our', 'their', 'me', 'him',
    'us', 'them', 'any', 'about', 'into', 'through', 'during', 'before',
    'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under',
    'again', 'further', 'because', 'while', 'although', 'though', 'unless',
    'until', 'like', 'want', 'make', 'get', 'got', 'use', 'using', 'please',
    'help', 'thanks', 'thank', 'hi', 'hello', 'hey', 'yes', 'no', 'ok', 'okay',
    'sure', 'well', 'right', 'let', 'lets', "let's", 'see', 'know', 'think',
    'something', 'anything', 'everything', 'nothing', 'someone', 'anyone',
    'everyone', 'noone', 'nobody', 'thing', 'way', 'time', 'first', 'new',
    'one', 'two', 'three'
}


def extract_topics(text: str, max_topics: int = 5) -> List[str]:
    """
    Extract key topics/keywords from text using word frequency analysis.
    
    Args:
        text: The text to analyze
        max_topics: Maximum number of topics to return
        
    Returns:
        List of extracted topic keywords
    """
    if not text:
        return []
    
    # Tokenize: extract words, normalize to lowercase
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]*\b', text.lower())
    
    # Filter out stop words and very short words
    filtered_words = [
        word for word in words 
        if word not in STOP_WORDS and len(word) > 2
    ]
    
    # Count word frequencies
    word_counts = Counter(filtered_words)
    
    # Get most common words
    topics = [word for word, _ in word_counts.most_common(max_topics)]
    
    return topics


def truncate_text(text: str, max_length: int = 150) -> str:
    """
    Truncate text to a maximum length, adding ellipsis if truncated.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        
    Returns:
        Truncated text
    """
    if not text:
        return ""
    
    # Clean up whitespace
    text = ' '.join(text.split())
    
    if len(text) <= max_length:
        return text
    
    # Find a good break point (end of word or sentence)
    truncated = text[:max_length]
    
    # Try to break at sentence end
    last_period = truncated.rfind('.')
    last_question = truncated.rfind('?')
    last_break = max(last_period, last_question)
    
    if last_break > max_length * 0.6:  # Only use if it's not too short
        return truncated[:last_break + 1]
    
    # Otherwise break at word boundary
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + '...'
    
    return truncated + '...'


def generate_chat_summary(messages: List[Dict[str, Any]], title: str = "") -> Dict[str, Any]:
    """
    Generate a summary for a chat conversation.
    
    Args:
        messages: List of message dictionaries with 'type' and 'content' keys
        title: Optional chat title
        
    Returns:
        Dictionary containing summary information:
        - initial_query: The first user message (truncated)
        - message_count: Total number of messages
        - user_messages: Count of user messages
        - ai_messages: Count of AI messages
        - word_count: Approximate total word count
        - topics: List of extracted topic keywords
        - title: The chat title
    """
    if not messages:
        return {
            'initial_query': '',
            'message_count': 0,
            'user_messages': 0,
            'ai_messages': 0,
            'word_count': 0,
            'topics': [],
            'title': title or 'Empty Chat'
        }
    
    # Categorize messages
    user_messages = []
    ai_messages = []
    all_text = []
    
    for msg in messages:
        msg_type = str(msg.get('type', '')).lower()
        content = msg.get('content', '') or ''
        
        all_text.append(content)
        
        if msg_type in ('user', 'human'):
            user_messages.append(content)
        elif msg_type in ('ai', 'assistant', 'bot'):
            ai_messages.append(content)
    
    # Get initial query (first user message)
    initial_query = ''
    if user_messages:
        initial_query = truncate_text(user_messages[0], max_length=200)
    
    # Calculate word count
    combined_text = ' '.join(all_text)
    word_count = len(combined_text.split())
    
    # Extract topics from all text
    topics = extract_topics(combined_text, max_topics=5)
    
    return {
        'initial_query': initial_query,
        'message_count': len(messages),
        'user_messages': len(user_messages),
        'ai_messages': len(ai_messages),
        'word_count': word_count,
        'topics': topics,
        'title': title or 'Untitled Chat'
    }


def format_summary_markdown(summary: Dict[str, Any]) -> str:
    """
    Format a chat summary as a markdown block.
    
    Args:
        summary: Summary dictionary from generate_chat_summary()
        
    Returns:
        Formatted markdown string
    """
    lines = [
        '> **Chat Summary**',
        '>',
    ]
    
    # Initial query
    if summary.get('initial_query'):
        lines.append(f"> 💬 *\"{summary['initial_query']}\"*")
        lines.append('>')
    
    # Statistics
    stats_parts = []
    if summary.get('message_count', 0) > 0:
        stats_parts.append(f"**{summary['message_count']}** messages")
    if summary.get('user_messages', 0) > 0:
        stats_parts.append(f"({summary['user_messages']} user, {summary['ai_messages']} AI)")
    if summary.get('word_count', 0) > 0:
        stats_parts.append(f"~{summary['word_count']} words")
    
    if stats_parts:
        lines.append(f"> 📊 {' '.join(stats_parts)}")
    
    # Topics
    if summary.get('topics'):
        topic_str = ', '.join(f'`{t}`' for t in summary['topics'])
        lines.append(f"> 🏷️ Topics: {topic_str}")
    
    lines.append('')  # Empty line after summary block
    
    return '\n'.join(lines)


def format_summary_plain(summary: Dict[str, Any]) -> str:
    """
    Format a chat summary as plain text for console display.
    
    Args:
        summary: Summary dictionary from generate_chat_summary()
        
    Returns:
        Formatted plain text string
    """
    lines = [
        '╭─────────────────────────────────────────────────────────────────╮',
        '│                        CHAT SUMMARY                            │',
        '├─────────────────────────────────────────────────────────────────┤',
    ]
    
    # Title
    title = summary.get('title', 'Untitled Chat')
    lines.append(f'│  📄 {title[:60]:<60}│')
    
    # Initial query
    if summary.get('initial_query'):
        query = summary['initial_query']
        # Split long queries across multiple lines
        while query:
            chunk = query[:58]
            query = query[58:]
            if chunk:
                lines.append(f'│  💬 "{chunk}"{"" if not query else "":<{57-len(chunk)}}│')
    
    # Statistics
    msg_count = summary.get('message_count', 0)
    user_count = summary.get('user_messages', 0)
    ai_count = summary.get('ai_messages', 0)
    word_count = summary.get('word_count', 0)
    
    stats = f'{msg_count} messages ({user_count} user, {ai_count} AI) • ~{word_count} words'
    lines.append(f'│  📊 {stats:<60}│')
    
    # Topics
    if summary.get('topics'):
        topics_str = ', '.join(summary['topics'][:5])
        lines.append(f'│  🏷️  Topics: {topics_str:<51}│')
    
    lines.append('╰─────────────────────────────────────────────────────────────────╯')
    lines.append('')
    
    return '\n'.join(lines)
