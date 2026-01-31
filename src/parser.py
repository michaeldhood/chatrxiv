"""
Module for parsing and converting Cursor chat data to various formats.
"""
import os
import json
from typing import List, Dict, Any, Optional
import pandas as pd
from pathlib import Path
import logging

from src.tagger import TagManager
from src.summarizer import generate_chat_summary, format_summary_markdown

logger = logging.getLogger(__name__)

def parse_chat_json(file_path: str, tag_manager: Optional[TagManager] = None) -> pd.DataFrame:
    """
    Parse a Cursor chat JSON file and convert it to a DataFrame.
    
    Args:
        file_path: Path to the JSON file containing chat data
        tag_manager: Optional TagManager instance for auto-tagging
        
    Returns:
        DataFrame containing structured chat data with tags column if tag_manager provided
        
    Raises:
        FileNotFoundError: If the specified file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
        KeyError: If the expected data structure isn't found
    """
    # Read the JSON file
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Find the chat data in the JSON structure
    chat_data = None
    for item in data:
        item_data = item.get('data')
        if isinstance(item_data, dict) and 'tabs' in item_data:
            chat_data = item_data['tabs']
            break
    
    if chat_data is None:
        raise KeyError("Could not find chat data in the JSON file")
    
    # List to store all bubble data
    rows = []
    
    # Iterate through each tab
    for tab in chat_data:
        tab_id = tab.get('tabId', '')
        chat_title = tab.get('chatTitle', 'Untitled Chat')
        
        # Iterate through bubbles
        for bubble in tab.get('bubbles', []):
            row = {
                'tabId': tab_id,
                'chatTitle': chat_title,
                'type': bubble.get('type'),
                'messageType': bubble.get('messageType'),
                'id': bubble.get('id'),
                'requestId': bubble.get('requestId'),
                'text': bubble.get('text'),
                'rawText': bubble.get('rawText'),
                'modelType': bubble.get('modelType'),  # This will only exist for AI responses
                'hasCodeBlock': bubble.get('hasCodeBlock', False),  # This will only exist for AI responses
                'timestamp': bubble.get('timestamp')
            }
            rows.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Add auto-tagging if tag_manager is provided
    if tag_manager:
        tags_column = []
        for _, row in df.iterrows():
            # Combine text from user and AI messages for better tagging
            content = str(row.get('text', '')) + ' ' + str(row.get('rawText', ''))
            auto_tags = tag_manager.auto_tag(content)
            
            # Store tags for this message
            tags_column.append(list(auto_tags))
            
            # Also add tags to the chat (identified by tabId)
            if auto_tags and row.get('tabId'):
                existing_tags = tag_manager.get_tags(row['tabId'])
                new_tags = list(auto_tags - set(existing_tags))
                if new_tags:
                    tag_manager.add_tags(row['tabId'], new_tags)
        
        df['tags'] = tags_column
    
    return df


def export_chats_to_markdown(chats_data: List[Dict[str, Any]], output_dir: str = '.', include_summary: bool = True) -> List[str]:
    """
    Export chat data to markdown files.
    
    Args:
        chats_data: A list of chat data dictionaries, each containing 'id', 'title', and 'messages'
        output_dir: Directory where markdown files will be saved
        include_summary: Whether to include a summary block at the top of each file
    
    Returns:
        List of generated file paths
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        output_path.mkdir(parents=True, exist_ok=True)
    
    generated_files = []
    
    for chat in chats_data:
        # Create filename based on chat ID
        workspace_id = Path(output_dir).name if output_dir != '.' else ''
        filename = f"chat_{workspace_id}_{chat['id']}.md"
        filepath = output_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            # Write chat title
            f.write(f"# {chat['title']}\n\n")
            
            # Generate and write summary if requested
            if include_summary:
                summary = generate_chat_summary(chat['messages'], chat['title'])
                summary_md = format_summary_markdown(summary)
                f.write(f"{summary_md}\n")
            
            # Write each message
            for message in chat['messages']:
                role = message.get('type', 'Unknown')
                content = message.get('content', '')
                f.write(f"## {role}\n\n{content}\n\n")
        
        generated_files.append(str(filepath))
        logger.info("Exported chat to %s", filepath)
    
    return generated_files


def convert_df_to_markdown(df: pd.DataFrame, output_dir: str = '.') -> List[str]:
    """
    Convert a DataFrame of chat messages to markdown files.
    
    Args:
        df: DataFrame with chat messages
        output_dir: Directory where markdown files will be saved
    
    Returns:
        List of generated file paths
    """
    # Group the DataFrame by tabId and chatTitle
    grouped = df.groupby(['tabId', 'chatTitle'])
    
    chats_data = []
    
    for (tab_id, chat_title), group in grouped:
        messages = []
        
        # Convert each row to a message format
        for _, row in group.iterrows():
            message = {
                'type': row['type'],
                'content': row['text'] or row['rawText'] or ''
            }
            messages.append(message)
        
        chats_data.append({
            'id': tab_id,
            'title': chat_title,
            'messages': messages
        })
    
    return export_chats_to_markdown(chats_data, output_dir)


def export_to_csv(df: pd.DataFrame, output_file: str) -> str:
    """
    Export a DataFrame to a CSV file.
    
    Args:
        df: DataFrame to export
        output_file: Path to the output CSV file
        
    Returns:
        Path to the created CSV file
    """
    df.to_csv(output_file, index=False)
    logger.info("Exported data to %s", output_file)
    return output_file
