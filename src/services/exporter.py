"""
Export service for converting chats to various formats.
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

from src.core.db import ChatDatabase

logger = logging.getLogger(__name__)


class ChatExporter:
    """
    Exports chats to various formats (Markdown, JSON, CSV).
    """
    
    def __init__(self, db: ChatDatabase):
        """
        Initialize exporter.
        
        Parameters
        ----
        db : ChatDatabase
            Database instance
        """
        self.db = db
    
    def export_chat_markdown(self, chat_id: int, output_path: Path) -> bool:
        """
        Export a single chat to Markdown.
        
        Parameters
        ----
        chat_id : int
            Chat ID to export
        output_path : Path
            Output file path
            
        Returns
        ----
        bool
            True if successful
        """
        chat = self.db.get_chat(chat_id)
        if not chat:
            logger.error("Chat %d not found", chat_id)
            return False
        
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                # Write header
                f.write(f"# {chat['title']}\n\n")
                f.write(f"**Mode:** {chat['mode']}  \n")
                f.write(f"**Created:** {chat['created_at']}  \n")
                if chat.get('workspace_path'):
                    f.write(f"**Workspace:** {chat['workspace_path']}  \n")
                if chat.get('thinking_count', 0) > 0:
                    f.write(f"**Thinking bubbles:** {chat['thinking_count']}  \n")
                f.write("\n")
                
                # Write messages
                for msg in chat['messages']:
                    role_emoji = "👤" if msg['role'] == 'user' else "🤖"
                    f.write(f"## {role_emoji} {msg['role'].title()}\n\n")
                    
                    # Use rich_text if available, otherwise text
                    content = msg.get('rich_text') or msg.get('text', '')
                    f.write(f"{content}\n\n")
                
                # Write relevant files if any
                if chat.get('files'):
                    f.write("## 📁 Relevant Files\n\n")
                    for file_path in chat['files']:
                        f.write(f"- `{file_path}`\n")
                    f.write("\n")
            
            logger.info("Exported chat %d to %s", chat_id, output_path)
            return True
            
        except Exception as e:
            logger.error("Failed to export chat %d: %s", chat_id, e)
            return False
    
    def export_all_markdown(self, output_dir: Path) -> int:
        """
        Export all chats to Markdown files.
        
        Parameters
        ----
        output_dir : Path
            Output directory
            
        Returns
        ----
        int
            Number of chats exported
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        chats = self.db.list_chats(limit=10000)  # Get all chats
        exported = 0
        
        for chat in chats:
            filename = f"chat_{chat['id']}_{chat['composer_id'][:8]}.md"
            output_path = output_dir / filename
            
            if self.export_chat_markdown(chat['id'], output_path):
                exported += 1
        
        logger.info("Exported %d chats to %s", exported, output_dir)
        return exported

