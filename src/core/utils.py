"""
Utility functions for chat processing.
"""
import re
from typing import Tuple


def count_words(text: str) -> int:
    """
    Count words in a text string.
    
    Parameters
    ----
    text : str
        Text to count words in
        
    Returns
    ----
    int
        Word count
    """
    if not text or not isinstance(text, str):
        return 0
    
    # Remove extra whitespace and split on whitespace
    words = re.findall(r'\S+', text)
    return len(words)


def calculate_chat_word_count(messages) -> int:
    """
    Calculate total word count for a chat from its messages.
    
    Parameters
    ----
    messages : List[Message]
        List of messages in the chat
        
    Returns
    ----
    int
        Total word count across all messages
    """
    total_words = 0
    for msg in messages:
        # Count words from both text and rich_text fields
        total_words += count_words(msg.text or "")
        total_words += count_words(msg.rich_text or "")
    return total_words


def word_count_to_tshirt_size(word_count: int) -> str:
    """
    Convert word count to t-shirt size indication.
    
    T-shirt sizes:
    - XS: 0-100 words
    - S: 101-500 words
    - M: 501-2000 words
    - L: 2001-5000 words
    - XL: 5001-10000 words
    - XXL: 10001+ words
    
    Parameters
    ----
    word_count : int
        Total word count
        
    Returns
    ----
    str
        T-shirt size (XS, S, M, L, XL, XXL)
    """
    if word_count == 0:
        return "XS"
    elif word_count <= 100:
        return "XS"
    elif word_count <= 500:
        return "S"
    elif word_count <= 2000:
        return "M"
    elif word_count <= 5000:
        return "L"
    elif word_count <= 10000:
        return "XL"
    else:
        return "XXL"
