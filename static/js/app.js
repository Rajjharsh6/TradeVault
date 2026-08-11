// =========================================================
// TradeVault - app.js
// =========================================================

document.addEventListener("DOMContentLoaded", function () {
    // Top bar date
    var dateEl = document.getElementById("topbarDate");
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString(undefined, {
            weekday: "short", year: "numeric", month: "short", day: "numeric"
        });
    }

    // Sidebar toggle (mobile)
    var toggleBtn = document.getElementById("sidebarToggle");
    var sidebar = document.getElementById("sidebar");
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
    }
});

// =========================================================
// Chart.js color palette / defaults
// =========================================================

var CHART_COLORS = {
    blue: "#4f7cff",
    green: "#22c55e",
    red: "#ef4444",
    amber: "#f5a623",
    grid: "rgba(255,255,255,0.06)",
    text: "#8b92a5"
};

function baseChartOptions(extra) {
    var options = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { labels: { color: CHART_COLORS.text, boxWidth: 12, font: { size: 11 } } }
        },
        scales: {
            x: {
                ticks: { color: CHART_COLORS.text, font: { size: 10 } },
                grid: { color: CHART_COLORS.grid }
            },
            y: {
                ticks: { color: CHART_COLORS.text, font: { size: 10 } },
                grid: { color: CHART_COLORS.grid }
            }
        }
    };
    return Object.assign(options, extra || {});
}

function barColors(values) {
    return values.map(function (v) { return v >= 0 ? CHART_COLORS.green : CHART_COLORS.red; });
}

// =========================================================
// Dashboard charts
// =========================================================

window.TradeVaultCharts = {
    renderDashboardCharts: function (data) {
        var equityCtx = document.getElementById("equityCurveChart");
        if (equityCtx) {
            new Chart(equityCtx, {
                type: "line",
                data: {
                    labels: data.equityLabels,
                    datasets: [{
                        label: "Equity",
                        data: data.equityValues,
                        borderColor: CHART_COLORS.blue,
                        backgroundColor: "rgba(79,124,255,0.12)",
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    }]
                },
                options: baseChartOptions({ plugins: { legend: { display: false } } })
            });
        }

        var pnlDayCtx = document.getElementById("pnlByDayChart");
        if (pnlDayCtx) {
            new Chart(pnlDayCtx, {
                type: "bar",
                data: {
                    labels: data.pnlByDayLabels,
                    datasets: [{ label: "P&L", data: data.pnlByDayValues, backgroundColor: barColors(data.pnlByDayValues) }]
                },
                options: baseChartOptions({ plugins: { legend: { display: false } } })
            });
        }

        var winLossCtx = document.getElementById("winLossChart");
        if (winLossCtx) {
            new Chart(winLossCtx, {
                type: "doughnut",
                data: {
                    labels: data.winLossLabels,
                    datasets: [{
                        data: data.winLossValues,
                        backgroundColor: [CHART_COLORS.green, CHART_COLORS.red, CHART_COLORS.amber]
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: CHART_COLORS.text } } } }
            });
        }
    },

    renderAnalyticsCharts: function (data) {
        var charts = [
            { id: "equityCurveChart", type: "line", labels: data.equityLabels, values: data.equityValues, color: CHART_COLORS.blue, fill: true },
            { id: "dailyPnlChart", type: "bar", labels: data.dailyLabels, values: data.dailyValues, colored: true },
            { id: "weeklyPnlChart", type: "bar", labels: data.weeklyLabels, values: data.weeklyValues, colored: true },
            { id: "monthlyPnlChart", type: "bar", labels: data.monthlyLabels, values: data.monthlyValues, colored: true },
            { id: "pnlBySymbolChart", type: "bar", labels: data.symbolLabels, values: data.symbolValues, colored: true },
            { id: "pnlByStrategyChart", type: "bar", labels: data.strategyLabels, values: data.strategyValues, colored: true },
            { id: "pnlBySessionChart", type: "bar", labels: data.sessionLabels, values: data.sessionValues, colored: true }
        ];

        charts.forEach(function (c) {
            var ctx = document.getElementById(c.id);
            if (!ctx) return;
            new Chart(ctx, {
                type: c.type,
                data: {
                    labels: c.labels,
                    datasets: [{
                        label: "P&L",
                        data: c.values,
                        borderColor: c.color || CHART_COLORS.blue,
                        backgroundColor: c.colored ? barColors(c.values) : "rgba(79,124,255,0.12)",
                        fill: !!c.fill,
                        tension: 0.3,
                        pointRadius: c.type === "line" ? 0 : undefined
                    }]
                },
                options: baseChartOptions({ plugins: { legend: { display: false } } })
            });
        });

        var winLossCtx = document.getElementById("winLossChart");
        if (winLossCtx) {
            new Chart(winLossCtx, {
                type: "doughnut",
                data: {
                    labels: data.winLossLabels,
                    datasets: [{
                        data: data.winLossValues,
                        backgroundColor: [CHART_COLORS.green, CHART_COLORS.red, CHART_COLORS.amber]
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: CHART_COLORS.text } } } }
            });
        }
    }
};

// =========================================================
// Calendar
// =========================================================

window.TradeVaultCalendar = {
    data: {},
    currentDate: new Date(),

    init: function (calendarData) {
        this.data = calendarData || {};
        this.render();

        var prevBtn = document.getElementById("calPrevMonth");
        var nextBtn = document.getElementById("calNextMonth");
        var self = this;
        if (prevBtn) prevBtn.addEventListener("click", function () {
            self.currentDate.setMonth(self.currentDate.getMonth() - 1);
            self.render();
        });
        if (nextBtn) nextBtn.addEventListener("click", function () {
            self.currentDate.setMonth(self.currentDate.getMonth() + 1);
            self.render();
        });
    },

    render: function () {
        var grid = document.getElementById("calendarGrid");
        var label = document.getElementById("calMonthLabel");
        if (!grid) return;

        var year = this.currentDate.getFullYear();
        var month = this.currentDate.getMonth();
        label.textContent = this.currentDate.toLocaleDateString(undefined, { month: "long", year: "numeric" });

        grid.innerHTML = "";

        var weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        weekdays.forEach(function (wd) {
            var el = document.createElement("div");
            el.className = "cal-weekday-label";
            el.textContent = wd;
            grid.appendChild(el);
        });

        var firstDay = new Date(year, month, 1).getDay();
        var daysInMonth = new Date(year, month + 1, 0).getDate();

        for (var i = 0; i < firstDay; i++) {
            var empty = document.createElement("div");
            empty.className = "cal-day empty";
            grid.appendChild(empty);
        }

        var self = this;
        for (var d = 1; d <= daysInMonth; d++) {
            var dateStr = year + "-" + String(month + 1).padStart(2, "0") + "-" + String(d).padStart(2, "0");
            var dayData = this.data[dateStr];

            var cell = document.createElement("div");
            cell.className = "cal-day";

            var numEl = document.createElement("div");
            numEl.className = "cal-day-num";
            numEl.textContent = d;
            cell.appendChild(numEl);

            if (dayData) {
                cell.classList.add("has-trades", dayData.pnl >= 0 ? "positive" : "negative");
                var pnlEl = document.createElement("div");
                pnlEl.className = "cal-day-pnl " + (dayData.pnl >= 0 ? "pnl-positive" : "pnl-negative");
                pnlEl.textContent = dayData.pnl;
                cell.appendChild(pnlEl);

                var countEl = document.createElement("div");
                countEl.className = "cal-day-count";
                countEl.textContent = dayData.count + " trade(s)";
                cell.appendChild(countEl);

                cell.addEventListener("click", function (dateKey, dd) {
                    return function () { self.showDay(dateKey, dd); };
                }(dateStr, dayData));
            }

            grid.appendChild(cell);
        }
    },

    showDay: function (dateStr, dayData) {
        var panel = document.getElementById("calendarDayPanel");
        var title = document.getElementById("calendarDayTitle");
        var tbody = document.getElementById("calendarDayTrades");
        if (!panel || !tbody) return;

        panel.style.display = "block";
        title.textContent = "Trades on " + dateStr;
        tbody.innerHTML = "";

        dayData.trades.forEach(function (t) {
            var row = document.createElement("tr");
            row.innerHTML =
                "<td class='mono'>" + (t.symbol || "") + "</td>" +
                "<td><span class='badge badge-" + (t.direction === "Long" ? "long" : "short") + "'>" + (t.direction || "") + "</span></td>" +
                "<td class='mono'>" + (t.entry_price != null ? t.entry_price : "-") + "</td>" +
                "<td class='mono'>" + (t.exit_price != null ? t.exit_price : "-") + "</td>" +
                "<td class='mono " + ((t.profit_loss || 0) >= 0 ? "pnl-positive" : "pnl-negative") + "'>" + (t.profit_loss != null ? t.profit_loss : "-") + "</td>" +
                "<td><span class='badge badge-" + ((t.result || "").toLowerCase()) + "'>" + (t.result || "") + "</span></td>";
            tbody.appendChild(row);
        });

        panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
};
