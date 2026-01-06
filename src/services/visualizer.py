"""
Visualization service for cursor activity and cost data.

Generates charts and graphs for analyzing usage patterns and costs.
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure
import pandas as pd

from src.core.db import ChatDatabase

logger = logging.getLogger(__name__)


class ActivityVisualizer:
    """
    Service for creating visualizations of cursor activity and costs.
    """
    
    def __init__(self, db: ChatDatabase, output_dir: str = "."):
        """
        Initialize visualizer.
        
        Parameters
        ----
        db : ChatDatabase
            Database instance
        output_dir : str
            Directory to save visualization files
        """
        self.db = db
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def create_cost_over_time_chart(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = "day"
    ) -> str:
        """
        Create a chart showing cost over time.
        
        Parameters
        ----
        start_date : str, optional
            Start date (ISO format)
        end_date : str, optional
            End date (ISO format)
        group_by : str
            Grouping: "day", "week", or "month"
            
        Returns
        ----
        str
            Path to saved chart file
        """
        cursor = self.db.conn.cursor()
        
        conditions = []
        params = []
        
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # Query cost data grouped by time period
        if group_by == "day":
            date_format = "%Y-%m-%d"
            group_sql = "DATE(timestamp)"
        elif group_by == "week":
            date_format = "%Y-W%V"
            group_sql = "strftime('%Y-W%W', timestamp)"
        elif group_by == "month":
            date_format = "%Y-%m"
            group_sql = "strftime('%Y-%m', timestamp)"
        else:
            date_format = "%Y-%m-%d"
            group_sql = "DATE(timestamp)"
        
        cursor.execute(f"""
            SELECT {group_sql} as period, COALESCE(SUM(cost), 0) as total_cost
            FROM cursor_activity
            {where_clause}
            GROUP BY period
            ORDER BY period ASC
        """, params)
        
        data = cursor.fetchall()
        if not data:
            logger.warning("No activity data found for the specified period")
            return None
        
        periods = [row[0] for row in data]
        costs = [row[1] or 0.0 for row in data]
        
        # Create chart
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(periods, costs, marker='o', linewidth=2, markersize=6)
        ax.fill_between(periods, costs, alpha=0.3)
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Cost (USD)', fontsize=12)
        ax.set_title('Cost Over Time', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha='right')
        
        # Format y-axis as currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))
        
        plt.tight_layout()
        
        # Save chart
        filename = f"cost_over_time_{group_by}.png"
        filepath = self.output_dir / filename
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        logger.info("Saved cost over time chart to %s", filepath)
        return str(filepath)
    
    def create_cost_by_model_chart(self) -> str:
        """
        Create a chart showing cost breakdown by model.
        
        Returns
        ----
        str
            Path to saved chart file
        """
        cursor = self.db.conn.cursor()
        
        cursor.execute("""
            SELECT model, COALESCE(SUM(cost), 0) as total_cost, COUNT(*) as count
            FROM cursor_activity
            WHERE model IS NOT NULL AND cost IS NOT NULL
            GROUP BY model
            ORDER BY total_cost DESC
        """)
        
        data = cursor.fetchall()
        if not data:
            logger.warning("No model cost data found")
            return None
        
        models = [row[0] for row in data]
        costs = [row[1] or 0.0 for row in data]
        counts = [row[2] for row in data]
        
        # Create chart
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Cost pie chart
        colors = plt.cm.Set3(range(len(models)))
        ax1.pie(costs, labels=models, autopct='%1.1f%%', startangle=90, colors=colors)
        ax1.set_title('Cost by Model', fontsize=14, fontweight='bold')
        
        # Usage count bar chart
        ax2.bar(models, counts, color=colors)
        ax2.set_xlabel('Model', fontsize=12)
        ax2.set_ylabel('Usage Count', fontsize=12)
        ax2.set_title('Usage Count by Model', fontsize=14, fontweight='bold')
        ax2.tick_params(axis='x', rotation=45, ha='right')
        ax2.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        # Save chart
        filename = "cost_by_model.png"
        filepath = self.output_dir / filename
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        logger.info("Saved cost by model chart to %s", filepath)
        return str(filepath)
    
    def create_activity_timeline_chart(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> str:
        """
        Create a timeline chart showing activity over time.
        
        Parameters
        ----
        start_date : str, optional
            Start date (ISO format)
        end_date : str, optional
            End date (ISO format)
            
        Returns
        ----
        str
            Path to saved chart file
        """
        cursor = self.db.conn.cursor()
        
        conditions = []
        params = []
        
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        cursor.execute(f"""
            SELECT DATE(timestamp) as date, activity_type, COUNT(*) as count
            FROM cursor_activity
            {where_clause}
            GROUP BY date, activity_type
            ORDER BY date ASC, activity_type ASC
        """, params)
        
        data = cursor.fetchall()
        if not data:
            logger.warning("No activity data found for the specified period")
            return None
        
        # Organize data by activity type
        activity_types = set(row[1] for row in data)
        dates = sorted(set(row[0] for row in data))
        
        activity_data = {atype: [] for atype in activity_types}
        for date, atype, count in data:
            activity_data[atype].append((date, count))
        
        # Create chart
        fig, ax = plt.subplots(figsize=(14, 6))
        
        for atype in activity_types:
            dates_atype = [d for d, _ in activity_data[atype]]
            counts_atype = [c for _, c in activity_data[atype]]
            
            # Fill in missing dates with 0
            full_counts = []
            for date in dates:
                if date in dates_atype:
                    idx = dates_atype.index(date)
                    full_counts.append(counts_atype[idx])
                else:
                    full_counts.append(0)
            
            ax.plot(dates, full_counts, marker='o', label=atype, linewidth=2)
        
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Activity Count', fontsize=12)
        ax.set_title('Activity Timeline', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Save chart
        filename = "activity_timeline.png"
        filepath = self.output_dir / filename
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        logger.info("Saved activity timeline chart to %s", filepath)
        return str(filepath)
    
    def create_chat_cost_distribution_chart(self) -> str:
        """
        Create a chart showing the distribution of chat costs.
        
        Returns
        ----
        str
            Path to saved chart file
        """
        cursor = self.db.conn.cursor()
        
        cursor.execute("""
            SELECT estimated_cost
            FROM chats
            WHERE estimated_cost IS NOT NULL AND estimated_cost > 0
            ORDER BY estimated_cost ASC
        """)
        
        costs = [row[0] for row in cursor.fetchall()]
        if not costs:
            logger.warning("No chat cost data found")
            return None
        
        # Create chart
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Histogram
        ax1.hist(costs, bins=30, edgecolor='black', alpha=0.7)
        ax1.set_xlabel('Cost per Chat (USD)', fontsize=12)
        ax1.set_ylabel('Frequency', fontsize=12)
        ax1.set_title('Chat Cost Distribution', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='y')
        ax1.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.4f}'))
        
        # Box plot
        ax2.boxplot(costs, vert=True)
        ax2.set_ylabel('Cost per Chat (USD)', fontsize=12)
        ax2.set_title('Chat Cost Box Plot', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.4f}'))
        
        plt.tight_layout()
        
        # Save chart
        filename = "chat_cost_distribution.png"
        filepath = self.output_dir / filename
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        logger.info("Saved chat cost distribution chart to %s", filepath)
        return str(filepath)
    
    def create_summary_dashboard(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> str:
        """
        Create a comprehensive dashboard with multiple charts.
        
        Parameters
        ----
        start_date : str, optional
            Start date (ISO format)
        end_date : str, optional
            End date (ISO format)
            
        Returns
        ----
        str
            Path to saved dashboard file
        """
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)
        
        # Get summary data
        summary = self.db.get_activity_summary(start_date, end_date)
        
        # 1. Cost over time (top left)
        ax1 = fig.add_subplot(gs[0, 0])
        cursor = self.db.conn.cursor()
        conditions = []
        params = []
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        cursor.execute(f"""
            SELECT DATE(timestamp) as date, COALESCE(SUM(cost), 0) as total_cost
            FROM cursor_activity
            {where_clause}
            GROUP BY date
            ORDER BY date ASC
        """, params)
        
        cost_data = cursor.fetchall()
        if cost_data:
            dates = [row[0] for row in cost_data]
            costs = [row[1] or 0.0 for row in cost_data]
            ax1.plot(dates, costs, marker='o', linewidth=2)
            ax1.fill_between(dates, costs, alpha=0.3)
        ax1.set_title('Cost Over Time', fontweight='bold')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Cost (USD)')
        ax1.grid(True, alpha=0.3)
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))
        
        # 2. Cost by model (top right)
        ax2 = fig.add_subplot(gs[0, 1])
        cursor.execute(f"""
            SELECT model, COALESCE(SUM(cost), 0) as total_cost
            FROM cursor_activity
            {where_clause} AND model IS NOT NULL
            GROUP BY model
            ORDER BY total_cost DESC
            LIMIT 10
        """, params)
        
        model_data = cursor.fetchall()
        if model_data:
            models = [row[0] for row in model_data]
            costs = [row[1] or 0.0 for row in model_data]
            ax2.barh(models, costs)
        ax2.set_title('Top 10 Models by Cost', fontweight='bold')
        ax2.set_xlabel('Total Cost (USD)')
        ax2.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))
        ax2.grid(True, alpha=0.3, axis='x')
        
        # 3. Activity by type (bottom left)
        ax3 = fig.add_subplot(gs[1, 0])
        activity_by_type = summary.get("activity_by_type", {})
        if activity_by_type:
            types = list(activity_by_type.keys())
            counts = list(activity_by_type.values())
            ax3.bar(types, counts)
        ax3.set_title('Activity by Type', fontweight='bold')
        ax3.set_xlabel('Activity Type')
        ax3.set_ylabel('Count')
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
        ax3.grid(True, alpha=0.3, axis='y')
        
        # 4. Summary stats (bottom right)
        ax4 = fig.add_subplot(gs[1, 1])
        ax4.axis('off')
        stats_text = f"""
        Summary Statistics
        
        Total Cost: ${summary.get('total_cost', 0):.2f}
        Total Tokens: {summary.get('total_tokens', 0):,}
        Input Tokens: {summary.get('total_input_tokens', 0):,}
        Output Tokens: {summary.get('total_output_tokens', 0):,}
        
        Top Models:
        """
        for model, data in list(summary.get('cost_by_model', {}).items())[:5]:
            stats_text += f"\n  {model}: ${data['cost']:.2f} ({data['count']} uses)"
        
        ax4.text(0.1, 0.5, stats_text, fontsize=11, verticalalignment='center',
                family='monospace', transform=ax4.transAxes)
        
        # 5. Chat cost distribution (bottom span)
        ax5 = fig.add_subplot(gs[2, :])
        cursor.execute("""
            SELECT estimated_cost
            FROM chats
            WHERE estimated_cost IS NOT NULL AND estimated_cost > 0
        """)
        
        chat_costs = [row[0] for row in cursor.fetchall()]
        if chat_costs:
            ax5.hist(chat_costs, bins=30, edgecolor='black', alpha=0.7)
        ax5.set_title('Chat Cost Distribution', fontweight='bold')
        ax5.set_xlabel('Cost per Chat (USD)')
        ax5.set_ylabel('Frequency')
        ax5.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.4f}'))
        ax5.grid(True, alpha=0.3, axis='y')
        
        # Save dashboard
        filename = "activity_dashboard.png"
        filepath = self.output_dir / filename
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        logger.info("Saved activity dashboard to %s", filepath)
        return str(filepath)
