export function initializeBudget() {
const canvas = document.getElementById("budgetChart");
if (!canvas || !window.Chart) return;

const dailyData = JSON.parse(canvas.dataset.budget);
const chartLabels = JSON.parse(canvas.dataset.labels);
const labels = dailyData.map(d => d.day);
const cashInData = dailyData.map(d => d.cash_in || 0);
const cashOutData = dailyData.map(d => d.cash_out || 0);
const cashBalanceData = dailyData.map(d => d.cash_balance || 0);
const proposalsData = dailyData.map(d => d.proposals || 0);
const approvedData = dailyData.map(d => d.approved || 0);
const unapprovedData = proposalsData.map((total, i) => {
    const approvedAmount = Math.abs(approvedData[i] || 0);
    return -Math.max(0, total - approvedAmount);
});
const pendingData = dailyData.map(d => d.pending || 0);
const committedData = cashBalanceData.map((b, i) => b - pendingData[i]);

const ctx = canvas.getContext('2d');
const budgetChart = new window.Chart(ctx, {
    type: 'line',
    data: {
        labels: labels,
        datasets: [
            {
                label: chartLabels['Budget Balance'],
                data: cashBalanceData,
                borderColor: '#ffffff',
                backgroundColor: '#ffffff22',
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointBorderColor: '#ffffff',
                pointBackgroundColor: '#ffffff',
                stack: 'line_budget_balance'
            },
            {
                label: chartLabels['Pending Budget'],
                data: committedData,
                borderColor: '#d49aff',
                backgroundColor: '#d49aff22',
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                stack: 'line_committed'
            },
            {
                type: 'bar',
                label: chartLabels['Budget In'],
                data: cashInData,
                borderColor: '#ffffff',
                backgroundColor: '#ffffff44',
                borderWidth: 1,
                order: 1
            },
            {
                type: 'bar',
                label: chartLabels['Budget Out'],
                data: cashOutData,
                borderColor: '#b5b5b5',
                backgroundColor: '#b5b5b544',
                borderWidth: 1,
                order: 1
            },
            {
                type: 'bar',
                label: chartLabels['Proposals (Being Voted)'],
                data: unapprovedData,
                borderColor: '#87cefa',
                backgroundColor: '#87cefa88',
                borderWidth: 1,
                order: 0,
                stack: 'proposal_being_voted'
            },
            {
                type: 'bar',
                label: chartLabels['Proposals (Approved)'],
                data: approvedData,
                borderColor: '#d49aff',
                backgroundColor: '#d49aff88',
                borderWidth: 1,
                order: 0,
                stack: 'proposal_approved'
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                // Labelled checkboxes own visibility; avoid a second independent control.
                display: false,
                labels: { color: '#aaa' }
            }
        },
        scales: {
            x: {
                stacked: true,
                ticks: { color: '#b5b5b5' },
                grid: { color: '#0f3460' }
            },
            y: {
                stacked: true,
                ticks: { 
                    color: '#b5b5b5',
                    callback: function(value) { return '€' + Number(value).toLocaleString(); }
                },
                grid: { color: '#0f3460' }
            }
        }
    }
});

const chartRangeButtons = Array.from(document.querySelectorAll('.chart-range-btn'));
function applyChartRange(days) {
    let startIndex = 0;
    if (days !== 'all' && dailyData.length) {
        const latest = new Date(`${dailyData[dailyData.length - 1].day}T00:00:00`);
        const cutoff = new Date(latest);
        cutoff.setDate(cutoff.getDate() - Number(days) + 1);
        startIndex = dailyData.findIndex(d => new Date(`${d.day}T00:00:00`) >= cutoff);
        if (startIndex < 0) startIndex = dailyData.length;
    }
    budgetChart.data.labels = labels.slice(startIndex);
    [cashBalanceData, committedData, cashInData, cashOutData, unapprovedData, approvedData]
        .forEach((values, index) => { budgetChart.data.datasets[index].data = values.slice(startIndex); });
    budgetChart.update();
    document.querySelectorAll('[data-budget-day]').forEach(row => { row.hidden = startIndex > 0 && row.dataset.budgetDay < dailyData[startIndex]?.day; });
    chartRangeButtons.forEach(button => { const selected = button.dataset.days === String(days); button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected)); });
}
chartRangeButtons.forEach(button => button.addEventListener('click', () => applyChartRange(button.dataset.days)));
applyChartRange('90');

const controls = [...document.querySelectorAll('[data-budget-series]')];
function syncSeries() {
    controls.forEach(control => budgetChart.setDatasetVisibility(Number(control.dataset.budgetSeries), control.checked));
    budgetChart.update();
}
controls.forEach(control => control.addEventListener('change', syncSeries));
for (const preset of document.querySelectorAll('[data-chart-preset]')) {
    preset.addEventListener('click', () => {
        const indexes = preset.dataset.chartPreset.split(',').map(Number);
        controls.forEach(control => { control.checked = indexes.includes(Number(control.dataset.budgetSeries)); });
        syncSeries();
    });
}
syncSeries();


(() => {
    const rows = Array.from(document.querySelectorAll('.calendar-row'));
    const buttons = Array.from(document.querySelectorAll('#calendarLegendFilters .calendar-legend-btn'));
    const activeFilters = new Set(['proposal', 'approved', 'budget_in', 'budget_out']);

    function syncButtons() {
        buttons.forEach(btn => {
            const key = btn.dataset.filter;
            if (key === 'all') {
                btn.classList.toggle('active', activeFilters.size === 4); btn.setAttribute('aria-pressed', String(activeFilters.size === 4));
            } else {
                btn.classList.toggle('active', activeFilters.has(key)); btn.setAttribute('aria-pressed', String(activeFilters.has(key)));
            }
        });
    }

    function applyFilter() {
        rows.forEach(row => {
            const category = row.dataset.category;
            row.style.display = activeFilters.has(category) ? '' : 'none';
        });
    }

    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            const filter = btn.dataset.filter;
            if (filter === 'all') {
                activeFilters.clear();
                ['proposal', 'approved', 'budget_in', 'budget_out'].forEach(f => activeFilters.add(f));
            } else {
                if (activeFilters.has(filter)) {
                    activeFilters.delete(filter);
                } else {
                    activeFilters.add(filter);
                }

                if (activeFilters.size === 0) {
                    ['proposal', 'approved', 'budget_in', 'budget_out'].forEach(f => activeFilters.add(f));
                }
            }

            syncButtons();
            applyFilter();
        });
    });

    syncButtons();
    applyFilter();
})();

}
