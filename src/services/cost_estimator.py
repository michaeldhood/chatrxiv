"""
Cost estimation service for AI model usage.

Provides pricing information and cost calculation for various AI models.
"""
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (input/output) as of 2024-2025
# Prices are in USD
MODEL_PRICING = {
    # Claude models (Anthropic)
    "claude-4.5-opus-high-thinking": {"input": 15.0, "output": 75.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20240620": {"input": 3.0, "output": 15.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-2.1": {"input": 8.0, "output": 24.0},
    "claude-2.0": {"input": 8.0, "output": 24.0},
    "claude-instant-1.2": {"input": 0.8, "output": 2.4},
    # GPT models (OpenAI)
    "gpt-4-turbo-preview": {"input": 10.0, "output": 30.0},
    "gpt-4-0125-preview": {"input": 10.0, "output": 30.0},
    "gpt-4-1106-preview": {"input": 10.0, "output": 30.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    # Cursor-specific models
    "agent_review": {"input": 3.0, "output": 15.0},  # Approximate as Claude Sonnet
    # Default fallback pricing (Claude Sonnet pricing)
    "default": {"input": 3.0, "output": 15.0},
}


class CostEstimator:
    """
    Service for estimating costs of AI model usage.

    Provides methods to calculate costs based on token counts and model type.
    """

    def __init__(self, custom_pricing: Optional[Dict[str, Dict[str, float]]] = None):
        """
        Initialize cost estimator.

        Parameters
        ----
        custom_pricing : Dict[str, Dict[str, float]], optional
            Custom pricing overrides. Format: {model_name: {"input": price, "output": price}}
        """
        self.pricing = MODEL_PRICING.copy()
        if custom_pricing:
            self.pricing.update(custom_pricing)

    def get_model_pricing(self, model: Optional[str]) -> Tuple[float, float]:
        """
        Get pricing for a specific model.

        Parameters
        ----
        model : str, optional
            Model name/identifier

        Returns
        ----
        Tuple[float, float]
            (input_price_per_1M_tokens, output_price_per_1M_tokens)
        """
        if not model:
            model = "default"

        # Try exact match first
        if model in self.pricing:
            prices = self.pricing[model]
            return prices["input"], prices["output"]

        # Try partial matches (e.g., "claude-3-5-sonnet" matches "claude-3-5-sonnet-20241022")
        for model_key, prices in self.pricing.items():
            if model_key != "default" and model_key.startswith(model):
                return prices["input"], prices["output"]

        # Try reverse match (model starts with key)
        for model_key, prices in self.pricing.items():
            if model_key != "default" and model.startswith(model_key):
                return prices["input"], prices["output"]

        # Fallback to default
        default_prices = self.pricing["default"]
        logger.warning("Unknown model '%s', using default pricing", model)
        return default_prices["input"], default_prices["output"]

    def estimate_cost(
        self,
        model: Optional[str],
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> float:
        """
        Estimate cost for token usage.

        Parameters
        ----
        model : str, optional
            Model name/identifier
        tokens_input : int
            Number of input tokens
        tokens_output : int
            Number of output tokens

        Returns
        ----
        float
            Estimated cost in USD
        """
        input_price, output_price = self.get_model_pricing(model)

        # Calculate cost: (tokens / 1M) * price_per_1M
        input_cost = (tokens_input / 1_000_000) * input_price
        output_cost = (tokens_output / 1_000_000) * output_price

        total_cost = input_cost + output_cost
        return round(total_cost, 6)  # Round to 6 decimal places

    def estimate_chat_cost(
        self,
        model: Optional[str],
        message_count: int,
        avg_input_tokens_per_message: Optional[int] = None,
        avg_output_tokens_per_message: Optional[int] = None,
    ) -> float:
        """
        Estimate cost for a chat conversation.

        Uses heuristics if token counts are not available.

        Parameters
        ----
        model : str, optional
            Model name/identifier
        message_count : int
            Total number of messages in the chat
        avg_input_tokens_per_message : int, optional
            Average input tokens per message. If None, uses heuristic.
        avg_output_tokens_per_message : int, optional
            Average output tokens per message. If None, uses heuristic.

        Returns
        ----
        float
            Estimated cost in USD
        """
        # Heuristics: assume roughly half messages are user, half are assistant
        user_messages = message_count // 2
        assistant_messages = message_count - user_messages

        # Default token estimates (conservative)
        if avg_input_tokens_per_message is None:
            avg_input_tokens_per_message = 500  # Average user message
        if avg_output_tokens_per_message is None:
            avg_output_tokens_per_message = 1000  # Average assistant response

        total_input_tokens = user_messages * avg_input_tokens_per_message
        total_output_tokens = assistant_messages * avg_output_tokens_per_message

        return self.estimate_cost(model, total_input_tokens, total_output_tokens)

    def update_chat_costs(self, db, update_existing: bool = False) -> int:
        """
        Update estimated costs for all chats in the database.

        Parameters
        ----
        db : ChatDatabase
            Database instance
        update_existing : bool
            If True, update costs even if already calculated

        Returns
        ----
        int
            Number of chats updated
        """
        cursor = db.conn.cursor()

        if update_existing:
            # Update all chats
            cursor.execute("""
                SELECT id, model, messages_count, estimated_cost
                FROM chats
                WHERE messages_count > 0
            """)
        else:
            # Only update chats without cost estimates
            cursor.execute("""
                SELECT id, model, messages_count, estimated_cost
                FROM chats
                WHERE messages_count > 0 AND estimated_cost IS NULL
            """)

        updated_count = 0
        for row in cursor.fetchall():
            chat_id, model, messages_count, existing_cost = row

            # Skip if cost already calculated and not updating existing
            if not update_existing and existing_cost is not None:
                continue

            # Estimate cost based on message count
            estimated_cost = self.estimate_chat_cost(model, messages_count)

            # Update database
            cursor.execute("""
                UPDATE chats SET estimated_cost = ? WHERE id = ?
            """, (estimated_cost, chat_id))

            updated_count += 1

        db.conn.commit()
        logger.info("Updated estimated costs for %d chats", updated_count)
        return updated_count
