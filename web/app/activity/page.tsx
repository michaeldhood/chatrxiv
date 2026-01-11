"use client";

import { useState, useEffect } from 'react';
import { fetchActivitySummary, fetchDailyActivity, type ActivitySummary, type DailyActivityAggregate } from '@/lib/api';

export default function ActivityPage() {
  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  const [dailyData, setDailyData] = useState<DailyActivityAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');

  const loadData = async () => {
    setLoading(true);
    try {
      const [summaryData, dailyData] = await Promise.all([
        fetchActivitySummary(startDate || undefined, endDate || undefined),
        fetchDailyActivity(startDate || undefined, endDate || undefined),
      ]);
      setSummary(summaryData);
      setDailyData(dailyData);
    } catch (error) {
      console.error('Failed to load activity data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [startDate, endDate]);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('en-US').format(value);
  };

  if (loading) {
    return (
      <div className="bg-card border border-border rounded-xl p-6">
        <p className="text-muted-foreground">Loading activity data...</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="bg-card border border-border rounded-xl p-6">
        <p className="text-muted-foreground">No activity data available. Load your CSV export first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Date Filters */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xl font-semibold mb-4">Date Range</h2>
        <div className="flex gap-4">
          <div>
            <label htmlFor="start-date" className="block text-sm font-medium mb-1">Start Date</label>
            <input
              id="start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-2 bg-background border border-border rounded-md text-foreground"
            />
          </div>
          <div>
            <label htmlFor="end-date" className="block text-sm font-medium mb-1">End Date</label>
            <input
              id="end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-2 bg-background border border-border rounded-md text-foreground"
            />
          </div>
          {(startDate || endDate) && (
            <div className="flex items-end">
              <button
                onClick={() => {
                  setStartDate('');
                  setEndDate('');
                }}
                className="px-4 py-2 bg-muted hover:bg-muted/80 rounded-md text-sm"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Summary Stats */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xl font-semibold mb-4">Summary Statistics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-sm text-muted-foreground">Total Cost</div>
            <div className="text-2xl font-bold text-primary">{formatCurrency(summary.total_cost)}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Total Tokens</div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_tokens)}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Input Tokens</div>
            <div className="text-lg">{formatNumber(summary.total_input_tokens_with_cache + summary.total_input_tokens_no_cache)}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Output Tokens</div>
            <div className="text-lg">{formatNumber(summary.total_output_tokens)}</div>
          </div>
        </div>
      </div>

      {/* Cost by Model */}
      {Object.keys(summary.cost_by_model).length > 0 && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-xl font-semibold mb-4">Cost by Model</h2>
          <div className="space-y-2">
            {Object.entries(summary.cost_by_model)
              .sort(([, a], [, b]) => b.cost - a.cost)
              .map(([model, data]) => (
                <div key={model} className="flex items-center justify-between p-3 bg-muted/50 rounded-md">
                  <div>
                    <div className="font-medium">{model}</div>
                    <div className="text-sm text-muted-foreground">{data.count} uses</div>
                  </div>
                  <div className="text-lg font-semibold text-primary">{formatCurrency(data.cost)}</div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Activity by Kind */}
      {Object.keys(summary.activity_by_kind).length > 0 && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-xl font-semibold mb-4">Activity by Kind</h2>
          <div className="space-y-2">
            {Object.entries(summary.activity_by_kind)
              .sort(([, a], [, b]) => b - a)
              .map(([kind, count]) => (
                <div key={kind} className="flex items-center justify-between p-3 bg-muted/50 rounded-md">
                  <div className="font-medium">{kind}</div>
                  <div className="text-lg font-semibold">{formatNumber(count)}</div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Daily Activity Table */}
      {dailyData.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-xl font-semibold mb-4">Daily Activity</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-2">Date</th>
                  <th className="text-right p-2">Cost</th>
                  <th className="text-right p-2">Activities</th>
                  <th className="text-right p-2">Input Tokens</th>
                  <th className="text-right p-2">Output Tokens</th>
                  <th className="text-right p-2">Total Tokens</th>
                </tr>
              </thead>
              <tbody>
                {dailyData.map((day, index) => (
                  <tr key={`${day.date}-${index}`} className="border-b border-border/50 hover:bg-muted/30">
                    <td className="p-2">{day.date}</td>
                    <td className="text-right p-2 font-medium text-primary">{formatCurrency(day.total_cost)}</td>
                    <td className="text-right p-2">{formatNumber(day.activity_count)}</td>
                    <td className="text-right p-2 text-muted-foreground">
                      {formatNumber(day.input_tokens_with_cache + day.input_tokens_no_cache)}
                    </td>
                    <td className="text-right p-2 text-muted-foreground">{formatNumber(day.output_tokens)}</td>
                    <td className="text-right p-2 font-medium">{formatNumber(day.total_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
