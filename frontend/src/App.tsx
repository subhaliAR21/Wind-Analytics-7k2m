
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Clock3,
  RefreshCw,
  Search,
  Wind,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./App.css";

type Metrics = {
  MAE: number | null;
  RMSE: number | null;
  bias: number | null;
};

type Match = {
  delivery_hour: string;
  actual_generation: number;
  forecast_generation: number;
  forecast_published_at: string | null;
  decision_cutoff: string | null;
  error: number;
  absolute_error: number;
};

type Analysis = {
  period: string;
  timezone: string;
  decision_cutoff_assumption: string;
  actual_records_returned: number;
  forecast_records_returned: number;
  hourly_actual_points: number;
  eligible_hourly_forecasts: number;
  matched_hourly_intervals: number;
  unmatched_hourly_actual_points: number;
  metrics: Metrics;
  matched_intervals: Match[];
  sample_matches?: Match[];
};

type SortKey =
  | "delivery_hour"
  | "actual_generation"
  | "forecast_generation"
  | "error"
  | "absolute_error";

const formatNumber = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value)
    ? "—"
    : value.toLocaleString("en-GB", {
        maximumFractionDigits: 2,
        minimumFractionDigits: 2,
      });

const formatDate = (value: string | null | undefined) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hour12: false,
  }) + " UTC";
};

const dateInputValue = (value: string) => value.slice(0, 10);

function App() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [startDate, setStartDate] = useState("2026-01-01");
  const [endDate, setEndDate] = useState("2026-01-31");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("delivery_hour");
  const [sortAscending, setSortAscending] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 24;

  async function loadAnalysis() {
    setLoading(true);
    setErrorMessage("");

    try {
      const response = await fetch("/api/analysis");

      if (!response.ok) {
        throw new Error(`API request failed (${response.status})`);
      }

      const data: Analysis = await response.json();

      if (!Array.isArray(data.matched_intervals)) {
        throw new Error(
          "The API response does not contain matched_intervals. Check the updated backend code."
        );
      }

      setAnalysis(data);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to load analysis data."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAnalysis();
  }, []);

  const allMatches = analysis?.matched_intervals ?? [];

  const filteredMatches = useMemo(() => {
    const filtered = allMatches.filter((item) => {
      const deliveryDate = dateInputValue(item.delivery_hour);

      const matchesDate =
        (!startDate || deliveryDate >= startDate) &&
        (!endDate || deliveryDate <= endDate);

      const searchText = search.trim().toLowerCase();
      const matchesSearch =
        !searchText ||
        item.delivery_hour.toLowerCase().includes(searchText) ||
        formatDate(item.delivery_hour).toLowerCase().includes(searchText);

      return matchesDate && matchesSearch;
    });

    return filtered.sort((a, b) => {
      let comparison = 0;

      if (sortKey === "delivery_hour") {
        comparison =
          new Date(a.delivery_hour).getTime() -
          new Date(b.delivery_hour).getTime();
      } else {
        comparison = a[sortKey] - b[sortKey];
      }

      return sortAscending ? comparison : -comparison;
    });
  }, [allMatches, startDate, endDate, search, sortKey, sortAscending]);

  const chartData = useMemo(
    () =>
      filteredMatches.map((item) => ({
        time: item.delivery_hour,
        label: new Date(item.delivery_hour).toLocaleString("en-GB", {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "UTC",
          hour12: false,
        }),
        actual: item.actual_generation,
        forecast: item.forecast_generation,
      })),
    [filteredMatches]
  );

  const totalPages = Math.max(1, Math.ceil(filteredMatches.length / pageSize));
  const currentPage = Math.min(page, totalPages);

  const pageRows = filteredMatches.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  function changeSort(key: SortKey) {
    if (sortKey === key) {
      setSortAscending((previous) => !previous);
    } else {
      setSortKey(key);
      setSortAscending(key === "delivery_hour");
    }
    setPage(1);
  }

  function resetFilters() {
    setStartDate("2026-01-01");
    setEndDate("2026-01-31");
    setSearch("");
    setPage(1);
  }

  const sortIcon = (key: SortKey) => {
    if (sortKey !== key) return null;
    return sortAscending ? (
      <ArrowUp size={13} />
    ) : (
      <ArrowDown size={13} />
    );
  };

  if (loading) {
    return (
      <main className="app-shell">
        <div className="loading-state">
          <RefreshCw className="spin" size={28} />
          <h2>Loading wind intelligence</h2>
          <p>Fetching January 2026 forecast and actual generation data…</p>
        </div>
      </main>
    );
  }

  if (errorMessage || !analysis) {
    return (
      <main className="app-shell">
        <div className="error-state">
          <AlertCircle size={32} />
          <h2>Unable to load the analysis</h2>
          <p>{errorMessage || "No analysis data was returned."}</p>
          <p>
            Confirm that the Python backend is running at port 8000 and that
            the Vite development server is running.
          </p>
          <button className="primary-button" onClick={() => void loadAnalysis()}>
            <RefreshCw size={16} /> Try again
          </button>
        </div>
      </main>
    );
  }

  const metricCards = [
    {
      label: "Mean absolute error",
      short: "MAE",
      value: analysis.metrics.MAE,
      description: "Average absolute forecast error",
      icon: Activity,
    },
    {
      label: "Root mean squared error",
      short: "RMSE",
      value: analysis.metrics.RMSE,
      description: "Penalises larger forecast errors",
      icon: BarChart3,
    },
    {
      label: "Forecast bias",
      short: "BIAS",
      value: analysis.metrics.bias,
      description:
        analysis.metrics.bias != null && analysis.metrics.bias > 0
          ? "Average overforecast"
          : "Average underforecast",
      icon: Wind,
    },
  ];

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="Wind Intelligence home">
          <span className="brand-mark">
            <Wind size={23} />
          </span>
          <span>
            <strong>Wind Intelligence</strong>
            <small>Forecast performance workspace</small>
          </span>
        </a>

        <div className="topbar-right">
          <span className="live-indicator">
            <span className="status-dot" /> API connected
          </span>
          <button
            className="icon-button"
            title="Refresh analysis"
            aria-label="Refresh analysis"
            onClick={() => void loadAnalysis()}
          >
            <RefreshCw size={17} />
          </button>
        </div>
      </header>

      <section className="hero">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            UK ENERGY PROCUREMENT · ANALYTICS
          </div>
          <h1>Wind forecast intelligence</h1>
          <p className="hero-description">
            Understand forecast accuracy against actual national wind
            generation, using information available before delivery.
          </p>
          <div className="hero-meta">
            <span>
              <CalendarDays size={15} /> January 2026
            </span>
            <span>
              <Clock3 size={15} /> All timestamps in UTC
            </span>
          </div>
        </div>

        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="hero-icon">
            <Wind size={54} strokeWidth={1.2} />
          </div>
          <div className="hero-stat">
            <span>Matched hours</span>
            <strong>
              {analysis.matched_hourly_intervals.toLocaleString("en-GB")}
            </strong>
          </div>
        </div>
      </section>

      <section className="section-heading">
        <div>
          <h2>Forecast performance</h2>
          <p>Performance metrics across the complete matched dataset.</p>
        </div>
        <span className="period-pill">
          <span className="status-dot" /> {analysis.period}
        </span>
      </section>

      <section className="metric-grid">
        {metricCards.map((metric) => {
          const Icon = metric.icon;

          return (
            <article className="metric-card" key={metric.short}>
              <div className="metric-card-top">
                <span className="metric-label">{metric.label}</span>
                <span className="metric-icon">
                  <Icon size={19} />
                </span>
              </div>
              <div className="metric-value">{formatNumber(metric.value)}</div>
              <div className="metric-bottom">
                <span className="metric-code">{metric.short}</span>
                <span className="metric-description">
                  {metric.description}
                </span>
              </div>
            </article>
          );
        })}
      </section>

      <section className="section-heading chart-heading">
        <div>
          <h2>Actual vs forecast generation</h2>
          <p>
            {filteredMatches.length.toLocaleString("en-GB")} hourly intervals
            shown · Filter the period below to explore the trend.
          </p>
        </div>
        <span className="subtle-tag">Hourly comparison</span>
      </section>

      <section className="panel chart-panel">
        <div className="chart-legend">
          <span>
            <i className="legend-dot actual-dot" /> Actual generation
          </span>
          <span>
            <i className="legend-dot forecast-dot" /> Forecast generation
          </span>
        </div>

        {chartData.length > 0 ? (
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                margin={{ top: 10, right: 16, left: 4, bottom: 8 }}
              >
                <CartesianGrid
                  strokeDasharray="3 5"
                  vertical={false}
                  stroke="var(--border)"
                />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={45}
                />
                <YAxis
                  tick={{ fill: "var(--muted)", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={68}
                  tickFormatter={(value: number) =>
                    value.toLocaleString("en-GB")
                  }
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--panel)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                    color: "var(--text)",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "var(--muted)", marginBottom: 5 }}
                  formatter={(value, name) => [
                    formatNumber(Number(value)),
                    name === "actual" ? "Actual" : "Forecast",
                  ]}
                />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="actual"
                  stroke="#18a878"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="forecast"
                  stroke="#6478ef"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="empty-state">
            No matched hourly records found for these filters.
          </div>
        )}
        <div className="chart-footer">
          <span>
            <CheckCircle2 size={15} /> Actuals and forecasts matched by delivery
            hour
          </span>
          <span>UTC</span>
        </div>
      </section>

      <section className="section-heading coverage-heading">
        <div>
          <h2>Data coverage</h2>
          <p>Source data and matching completeness for the selected month.</p>
        </div>
      </section>

      <section className="coverage-grid">
        <article className="panel coverage-card">
          <div className="coverage-icon">
            <Activity size={19} />
          </div>
          <div>
            <span className="coverage-label">Hourly actual points</span>
            <strong>{analysis.hourly_actual_points.toLocaleString("en-GB")}</strong>
            <small>Aggregated from half-hour actuals</small>
          </div>
        </article>

        <article className="panel coverage-card">
          <div className="coverage-icon forecast-coverage-icon">
            <Wind size={19} />
          </div>
          <div>
            <span className="coverage-label">Eligible forecasts</span>
            <strong>
              {analysis.eligible_hourly_forecasts.toLocaleString("en-GB")}
            </strong>
            <small>Latest publication before the cutoff</small>
          </div>
        </article>

        <article className="panel coverage-card">
          <div className="coverage-icon match-coverage-icon">
            <CheckCircle2 size={19} />
          </div>
          <div>
            <span className="coverage-label">Matched intervals</span>
            <strong>
              {analysis.matched_hourly_intervals.toLocaleString("en-GB")}
            </strong>
            <small>
              {analysis.unmatched_hourly_actual_points.toLocaleString("en-GB")}{" "}
              unmatched actual hours
            </small>
          </div>
        </article>
      </section>

      <section className="panel assumption-panel">
        <div className="assumption-icon">
          <Clock3 size={19} />
        </div>
        <div>
          <h3>Decision-time assumption</h3>
          <p>{analysis.decision_cutoff_assumption}</p>
          <small>
            This assumption should be validated with the procurement team.
            Results may change if a different buying decision cutoff is used.
          </small>
        </div>
      </section>

      <section className="section-heading table-heading">
        <div>
          <h2>Hourly interval explorer</h2>
          <p>
            Search, filter, sort and inspect the full set of matched hourly
            records.
          </p>
        </div>
        <span className="subtle-tag">
          {filteredMatches.length.toLocaleString("en-GB")} records
        </span>
      </section>

      <section className="panel table-panel">
        <div className="filter-toolbar">
          <label className="filter-field">
            <span>Start date</span>
            <input
              type="date"
              value={startDate}
              max={endDate || "2026-01-31"}
              onChange={(event) => {
                setStartDate(event.target.value);
                setPage(1);
              }}
            />
          </label>

          <label className="filter-field">
            <span>End date</span>
            <input
              type="date"
              value={endDate}
              min={startDate || "2026-01-01"}
              onChange={(event) => {
                setEndDate(event.target.value);
                setPage(1);
              }}
            />
          </label>

          <label className="search-field">
            <span>Search delivery time</span>
            <span className="search-input-wrap">
              <Search size={16} />
              <input
                type="search"
                placeholder="e.g. 2026-01-15"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
              />
            </span>
          </label>

          <button className="secondary-button" onClick={resetFilters}>
            Reset filters
          </button>
        </div>

        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => changeSort("delivery_hour")}
                  >
                    Delivery hour {sortIcon("delivery_hour")}
                  </button>
                </th>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => changeSort("actual_generation")}
                  >
                    Actual {sortIcon("actual_generation")}
                  </button>
                </th>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => changeSort("forecast_generation")}
                  >
                    Forecast {sortIcon("forecast_generation")}
                  </button>
                </th>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => changeSort("error")}
                  >
                    Error {sortIcon("error")}
                  </button>
                </th>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => changeSort("absolute_error")}
                  >
                    Absolute error {sortIcon("absolute_error")}
                  </button>
                </th>
                <th>Forecast published</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((item) => (
                <tr key={item.delivery_hour}>
                  <td className="date-cell">{formatDate(item.delivery_hour)}</td>
                  <td>{formatNumber(item.actual_generation)}</td>
                  <td>{formatNumber(item.forecast_generation)}</td>
                  <td
                    className={
                      item.error > 0
                        ? "error-positive"
                        : item.error < 0
                          ? "error-negative"
                          : ""
                    }
                  >
                    {item.error > 0 ? "+" : ""}
                    {formatNumber(item.error)}
                  </td>
                  <td>{formatNumber(item.absolute_error)}</td>
                  <td className="published-cell">
                    {formatDate(item.forecast_published_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {pageRows.length === 0 && (
          <div className="empty-state">
            No records match your selected dates or search.
          </div>
        )}

        <div className="table-footer">
          <span>
            Showing{" "}
            {filteredMatches.length === 0
              ? 0
              : (currentPage - 1) * pageSize + 1}
            –
            {Math.min(currentPage * pageSize, filteredMatches.length)} of{" "}
            {filteredMatches.length.toLocaleString("en-GB")} records
          </span>

          <div className="pagination">
            <button
              className="secondary-button"
              disabled={currentPage <= 1}
              onClick={() => setPage((previous) => Math.max(1, previous - 1))}
            >
              Previous
            </button>
            <span>
              Page {currentPage} of {totalPages}
            </span>
            <button
              className="secondary-button"
              disabled={currentPage >= totalPages}
              onClick={() =>
                setPage((previous) => Math.min(totalPages, previous + 1))
              }
            >
              Next
            </button>
          </div>
        </div>
      </section>

      <footer className="app-footer">
        <div className="footer-brand">
          <Wind size={17} /> Wind Intelligence
        </div>
        <span>Data source: Elexon BMRS · FUELHH and WINDFOR</span>
        <span>January 2026 · UTC</span>
      </footer>
    </main>
  );
}

export default App;
