// ============================================================
// PROFESSIONAL DATA CENTER DASHBOARD CLIENT
// HTML/CSS/JavaScript frontend for the Python + SQL Server backend
// ============================================================

class DashboardClient {
    constructor() {
        this.apiBase = '/api';
        this.updateInterval = 1000;
        this.eventsInterval = 5000;
        this.analyticsInterval = 10000;
        this.chartPointLimit = 60;
        this.reportGenerating = false;
        this.pollingPaused = false;
        this.state = {
            tags: {},
            events: [],
            analytics: null,
            serverCount: 4,
            currentView: 'overview',
            charts: {},
            databaseConnected: false,
            lastUpdate: null,
            lastHistoryLoad: {}
        };
        this.timers = [];
        this.init();
    }

    // ============================================================
    // INITIALIZATION
    // ============================================================

    async init() {
        this.setupEventListeners();

        const savedTheme = localStorage.getItem('theme') || 'dark';
        this.updateThemeToggle(savedTheme);
        this.showView('overview');
        this.updateCustomDateVisibility();

        await Promise.allSettled([
            this.loadState(),
            this.loadEvents(),
            this.loadAnalytics(false)
        ]);

        this.timers.push(setInterval(() => {
            if (!this.pollingPaused) this.loadState();
        }, this.updateInterval));

        this.timers.push(setInterval(() => {
            if (!this.pollingPaused) this.loadEvents();
        }, this.eventsInterval));

        this.timers.push(setInterval(() => {
            if (!this.pollingPaused) this.loadAnalytics(false);
        }, this.analyticsInterval));
    }

    // ============================================================
    // API HELPERS
    // ============================================================

    async fetchJson(url, options = {}) {
        const response = await fetch(url, {
            cache: 'no-store',
            ...options
        });

        let data = null;
        try {
            data = await response.json();
        } catch (error) {
            data = { error: `Invalid server response (${response.status})` };
        }

        if (!response.ok) {
            const message = data?.message || data?.error || `Request failed (${response.status})`;
            const requestError = new Error(message);
            requestError.status = response.status;
            requestError.data = data;
            throw requestError;
        }
        return data;
    }

    async loadState() {
        try {
            const data = await this.fetchJson(`${this.apiBase}/state`);
            this.state.tags = data.tags || {};
            this.state.databaseConnected = Boolean(data.database_connected);
            this.state.lastUpdate = data.last_update || data.timestamp || null;
            this.renderAll();
            this.updateConnectionStatus(this.state.databaseConnected, data.database_error);
            this.updateTimestamp(this.state.lastUpdate);
        } catch (error) {
            console.error('Error loading state:', error);
            this.updateConnectionStatus(false, error.message);
        }
    }

    async loadEvents() {
        try {
            const data = await this.fetchJson(`${this.apiBase}/events?limit=50`);
            this.state.events = Array.isArray(data) ? data : [];
            this.renderEvents();
            if (this.state.currentView === 'alarms') this.renderAlarmSummary();
            if (this.state.currentView.startsWith('server')) {
                const server = Number(this.state.currentView.replace('server', ''));
                this.renderServerAlarms(server);
            }
        } catch (error) {
            console.error('Error loading events:', error);
        }
    }

    async loadAnalytics(showNotification = false) {
        try {
            const data = await this.fetchJson(`${this.apiBase}/analytics`);
            this.state.analytics = data;
            this.renderAnalytics();
            this.updateAIBadge();
            if (showNotification) {
                this.showToast('AI analysis regenerated from the latest SQL values', 'success');
            }
        } catch (error) {
            console.error('Error loading analytics:', error);
            if (showNotification) this.showToast(error.message, 'error');
        }
    }

    async refreshData() {
        try {
            const data = await this.fetchJson(`${this.apiBase}/refresh`);
            await Promise.allSettled([this.loadState(), this.loadEvents(), this.loadAnalytics(false)]);
            const time = data.last_update ? new Date(data.last_update).toLocaleTimeString() : 'now';
            this.showToast(`Data refreshed from SQL Server at ${time}`, 'success');
        } catch (error) {
            console.error('Error refreshing data:', error);
            this.showToast(`Refresh failed: ${error.message}`, 'error');
        }
    }

    async loadHistory(server, force = false) {
        const now = Date.now();
        const lastLoad = this.state.lastHistoryLoad[server] || 0;
        if (!force && now - lastLoad < 10000) return null;

        try {
            const history = await this.fetchJson(`${this.apiBase}/history?server=${server}&limit=120`);
            this.state.lastHistoryLoad[server] = now;
            return Array.isArray(history) ? history : [];
        } catch (error) {
            console.error(`Error loading Server ${server} history:`, error);
            return [];
        }
    }

    // ============================================================
    // PRESERVED CONTROL BUTTONS
    // ============================================================

    async invokeReadOnlyControl(action, server) {
        try {
            await this.fetchJson(`${this.apiBase}/${action}?server=${server}`);
        } catch (error) {
            const message = error.data?.message || error.message;
            this.showToast(message, 'warning');
        }
    }

    toggleServer(server) {
        return this.invokeReadOnlyControl('toggle', server);
    }

    stressServer(server) {
        return this.invokeReadOnlyControl('stress', server);
    }

    resetServer(server) {
        return this.invokeReadOnlyControl('reset', server);
    }

    toggleSimulation() {
        this.pollingPaused = !this.pollingPaused;
        this.updateSimulationButton(!this.pollingPaused);

        if (this.pollingPaused) {
            this.showToast('Live dashboard polling paused. SQL and AVEVA continue running.', 'info');
        } else {
            this.showToast('Live dashboard polling resumed', 'success');
            this.refreshData();
        }
    }

    // ============================================================
    // NAVIGATION
    // ============================================================

    showView(view) {
        document.querySelectorAll('.view-section').forEach(section => section.classList.remove('active'));
        const target = document.getElementById(`view-${view}`);
        if (!target) return;
        target.classList.add('active');

        document.querySelectorAll('.sidebar-nav li[data-view]').forEach(item => {
            item.classList.toggle('active', item.dataset.view === view);
        });

        this.state.currentView = view;

        const titles = {
            overview: ['Data Center Overview', 'Real-Time Server Monitoring & Performance Analytics'],
            server1: ['Server 1 - Detailed Monitoring', 'Live SQL metrics, history and alarms'],
            server2: ['Server 2 - Detailed Monitoring', 'Live SQL metrics, history and alarms'],
            server3: ['Server 3 - Detailed Monitoring', 'Live SQL metrics, history and alarms'],
            server4: ['Server 4 - Detailed Monitoring', 'Live SQL metrics, history and alarms'],
            analytics: ['AI Analytics', 'Explainable AIOps recommendations based on live KPIs and documented challenges'],
            summary: ['Summary Dashboard', 'Aggregated metrics across all four servers'],
            reports: ['Professional Reports', 'Filtered PDF and CSV reporting with Schneider Electric and AVEVA branding'],
            alarms: ['Alarm Summary', 'Active and historical alarm events from SQL Server']
        };

        const [title, subtitle] = titles[view] || ['Data Center', 'Monitoring'];
        document.getElementById('pageTitle').textContent = title;
        document.getElementById('pageSubtitle').textContent = subtitle;

        if (view.startsWith('server')) {
            const server = Number(view.replace('server', ''));
            this.renderServerDetail(server, true);
        } else if (view === 'summary') {
            this.renderSummaryDashboard();
        } else if (view === 'alarms') {
            this.renderAlarmSummary();
        } else if (view === 'analytics') {
            this.renderAnalytics();
            this.loadAnalytics(false);
        } else if (view === 'reports') {
            this.updateCustomDateVisibility();
            document.getElementById('reportPreviewDate').textContent = new Date().toLocaleString();
        }

        document.getElementById('sidebar')?.classList.remove('mobile-open');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    openReports() {
        this.showView('reports');
        this.showToast('Select report filters, preview, then export PDF or CSV', 'info');
    }

    // ============================================================
    // CORE RENDERING
    // ============================================================

    renderAll() {
        this.renderSummary();
        this.renderPerformance();
        this.renderHealthStatus();
        this.renderServers();
        this.updateSidebarBadges();
        this.updateAlarmBadge();

        if (this.state.currentView.startsWith('server')) {
            const server = Number(this.state.currentView.replace('server', ''));
            const container = document.getElementById(`view-server${server}`);
            if (!container?.dataset.liveInitialized) {
                this.renderServerDetail(server, false);
            } else {
                this.updateServerDetail(server);
                this.appendLiveChartPoint(server);
            }
        }
        if (this.state.currentView === 'summary') this.renderSummaryDashboard();
        if (this.state.currentView === 'alarms') this.renderAlarmSummary();
    }

    renderSummary() {
        const tags = this.state.tags;
        const serversUp = this.number(tags.DC_Servers_Up);
        const avgCPU = this.number(tags.DC_Avg_CPU);
        const avgRAM = tags.DC_Avg_RAM !== undefined ? this.number(tags.DC_Avg_RAM) : this.getAverage('RAM_Percent');
        const maxTemp = this.number(tags.DC_Max_Temp);
        const totalNetwork = this.number(tags.DC_Total_Network);

        this.setText('serversUp', serversUp.toFixed(0));
        this.setHtml('totalCPU', `${avgCPU.toFixed(1)} <span class="unit">%</span>`);
        this.setHtml('totalRAM', `${avgRAM.toFixed(1)} <span class="unit">%</span>`);
        this.setHtml('avgTemp', `${maxTemp.toFixed(1)} <span class="unit">Â°C</span>`);
        this.setHtml('totalNetwork', `${totalNetwork.toFixed(1)} <span class="unit">Mbps</span>`);
        this.setText('alarmCount', String(this.countAlarms()));
    }

    renderPerformance() {
        const avgCPU = this.getAverage('CPU_Percent');
        const avgRAM = this.getAverage('RAM_Percent');
        const avgDisk = this.getAverage('Disk_Percent');
        const avgNetwork = this.getAverage('Network_Mbps');
        const networkPercent = Math.min(100, (avgNetwork / 300) * 100);

        this.setText('perfCPU', `${avgCPU.toFixed(1)}%`);
        this.setWidth('perfCPUbar', avgCPU);
        this.setText('perfRAM', `${avgRAM.toFixed(1)}%`);
        this.setWidth('perfRAMbar', avgRAM);
        this.setText('perfDISK', `${avgDisk.toFixed(1)}%`);
        this.setWidth('perfDISKbar', avgDisk);
        this.setText('perfNET', `${networkPercent.toFixed(1)}%`);
        this.setWidth('perfNETbar', networkPercent);
    }

    renderHealthStatus() {
        const tags = this.state.tags;
        const cpuValues = this.metricValues('CPU_Percent');
        const ramValues = this.metricValues('RAM_Percent');
        const diskValues = this.metricValues('Disk_Percent');

        const cpuMax = cpuValues.length ? Math.max(...cpuValues) : 0;
        const ramMax = ramValues.length ? Math.max(...ramValues) : 0;
        const diskMax = diskValues.length ? Math.max(...diskValues) : 0;

        this.applyHealthStatus('healthCPU', cpuMax, 75, 90, 'CPU');
        this.applyHealthStatus('healthRAM', ramMax, 80, 90, 'Memory');
        this.applyHealthStatus('healthDISK', diskMax, 80, 90, 'Disk');

        for (let server = 1; server <= 4; server += 1) {
            if (!this.bool(tags[`Server${server}_Status`])) {
                const cpuElement = document.getElementById('healthCPU');
                if (cpuElement) {
                    cpuElement.textContent = `Critical - Server ${server} Offline`;
                    cpuElement.className = 'status red';
                }
                break;
            }
        }
    }

    applyHealthStatus(elementId, value, warning, critical, label) {
        const element = document.getElementById(elementId);
        if (!element) return;
        if (value >= critical) {
            element.textContent = `Critical - ${label} threshold exceeded`;
            element.className = 'status red';
        } else if (value >= warning) {
            element.textContent = `Warning - ${label} headroom reduced`;
            element.className = 'status orange';
        } else {
            element.textContent = 'Normal';
            element.className = 'status green';
        }
    }

    renderServers() {
        const grid = document.getElementById('serversGrid');
        if (!grid) return;
        grid.innerHTML = '';
        for (let server = 1; server <= 4; server += 1) {
            grid.appendChild(this.createServerCard(server));
        }
    }

    createServerCard(server) {
        const tags = this.state.tags;
        const online = this.bool(tags[`Server${server}_Status`]);
        const cpu = this.number(tags[`Server${server}_CPU_Percent`]);
        const ram = this.number(tags[`Server${server}_RAM_Percent`]);
        const disk = this.number(tags[`Server${server}_Disk_Percent`]);
        const temperature = this.number(tags[`Server${server}_Temp_C`]);
        const network = this.number(tags[`Server${server}_Network_Mbps`]);
        const latency = this.number(tags[`Server${server}_Latency_ms`]);
        const health = this.getServerAnalytics(server)?.health_score;

        const cpuAlarm = this.bool(tags[`Server${server}_CPU_Alarm`]);
        const tempAlarm = this.bool(tags[`Server${server}_Temp_Alarm`]);
        const downAlarm = this.bool(tags[`Server${server}_Down_Alarm`]);

        const card = document.createElement('div');
        card.className = `server-card ${online ? '' : 'offline'}`;
        card.innerHTML = `
            <div class="server-header">
                <div class="name">
                    <span class="status-indicator ${online ? 'online' : 'offline'}"></span>
                    Server ${server}
                </div>
                <span class="status-badge ${online ? 'online' : 'offline'}">${online ? 'â— UP' : 'â— DOWN'}</span>
            </div>
            <div class="server-metrics">
                ${this.metricTile('CPU', cpu, '%', this.getValueClass(cpu, 75, 90))}
                ${this.metricTile('RAM', ram, '%', this.getValueClass(ram, 80, 90))}
                ${this.metricTile('Disk', disk, '%', this.getValueClass(disk, 80, 90))}
                ${this.metricTile('Temp', temperature, 'Â°C', this.getValueClass(temperature, 60, 75))}
                ${this.metricTile('Network', network, 'Mbps', 'normal')}
                ${this.metricTile('Latency', latency, 'ms', this.getValueClass(latency, 30, 50))}
                ${this.metricTile('Health', health ?? this.calculateClientHealth(server), '/100', this.getHealthClass(health ?? this.calculateClientHealth(server)))}
                ${this.metricTile('Data Source', 0, '', 'normal', 'SQL Live')}
            </div>
            <div class="server-alarms">
                <span class="alarm-badge ${cpuAlarm ? 'active' : 'inactive'}">${cpuAlarm ? 'âš ' : 'âœ“'} CPU HIGH</span>
                <span class="alarm-badge ${tempAlarm ? 'active' : 'inactive'}">${tempAlarm ? 'âš ' : 'âœ“'} TEMP HIGH</span>
                <span class="alarm-badge ${downAlarm ? 'active' : 'inactive'}">${downAlarm ? 'âš ' : 'âœ“'} DOWN</span>
            </div>
            <div class="server-controls">
                <button class="btn ${online ? 'btn-danger' : 'btn-success'}" onclick="client.toggleServer(${server})" disabled title="Read-only live SQL mode; use AVEVA controls">${online ? 'ðŸ”Œ Off' : 'ðŸ”‹ On'}</button>
                <button class="btn btn-warning" onclick="client.stressServer(${server})" disabled title="Read-only live SQL mode; use AVEVA controls">âš¡ Stress</button>
                <button class="btn btn-primary" onclick="client.resetServer(${server})" disabled title="Read-only live SQL mode; use AVEVA controls">â†º Reset</button>
                <button class="btn btn-outline" onclick="client.showView('server${server}')">ðŸ“Š Details</button>
            </div>
        `;
        return card;
    }

    metricTile(label, value, unit, cssClass, overrideText = null) {
        const display = overrideText ?? `${this.number(value).toFixed(1)}<span class="unit">${unit}</span>`;
        return `
            <div class="metric">
                <div class="metric-label">${label}</div>
                <div class="metric-value ${cssClass}">${display}</div>
            </div>
        `;
    }

    // ============================================================
    // EVENTS AND ALARMS
    // ============================================================

    renderEvents() {
        const tbody = document.getElementById('eventsBody');
        if (!tbody) return;
        const events = this.state.events || [];
        this.setText('eventCount', String(events.length));

        if (!events.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);">No alarm events recorded</td></tr>';
            return;
        }

        tbody.innerHTML = events.slice(0, 25).map(event => {
            const time = event.timestamp ? new Date(event.timestamp).toLocaleString() : '-';
            const status = this.escapeHtml(event.status || event.severity || 'INFO');
            const statusClass = this.eventClass(status);
            return `
                <tr>
                    <td>${time}</td>
                    <td>${event.server ? `SERVER ${this.escapeHtml(event.server)}` : 'N/A'}</td>
                    <td>${this.escapeHtml(event.event || 'System event')}</td>
                    <td><span class="status-badge ${statusClass}">${status}</span></td>
                </tr>
            `;
        }).join('');
    }

    renderAlarmSummary() {
        const grid = document.getElementById('alarmSummaryGrid');
        if (!grid) return;
        const events = this.state.events || [];
        const active = events.filter(event => String(event.status).toUpperCase() === 'ACTIVE');
        const cleared = events.filter(event => String(event.status).toUpperCase() === 'CLEARED');

        let html = `
            <div style="background:var(--bg-secondary);padding:20px;border-radius:12px;border:1px solid var(--border-color);grid-column:1/-1;">
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;text-align:center;">
                    <div><div style="color:var(--text-muted);font-size:12px;">Recent Events</div><div style="font-size:30px;font-weight:800;">${events.length}</div></div>
                    <div><div style="color:var(--text-muted);font-size:12px;">Active</div><div style="font-size:30px;font-weight:800;color:#d32f2f;">${active.length}</div></div>
                    <div><div style="color:var(--text-muted);font-size:12px;">Cleared</div><div style="font-size:30px;font-weight:800;color:#00c853;">${cleared.length}</div></div>
                </div>
            </div>
        `;

        if (!events.length) {
            html += '<div class="empty-state" style="grid-column:1/-1;"><div style="font-size:48px;">âœ…</div><h3>No alarms recorded</h3><p>Current SQL query returned no alarm events.</p></div>';
        } else {
            html += `
                <div style="background:var(--bg-secondary);padding:18px;border-radius:12px;border:1px solid var(--border-color);grid-column:1/-1;">
                    <div class="events-table-wrap">
                        <table class="events-table">
                            <thead><tr><th>Date/Time</th><th>Server</th><th>Event</th><th>Severity</th><th>State</th></tr></thead>
                            <tbody>
                                ${events.map(event => `
                                    <tr>
                                        <td>${event.timestamp ? new Date(event.timestamp).toLocaleString() : '-'}</td>
                                        <td>${event.server ? `SERVER ${this.escapeHtml(event.server)}` : 'N/A'}</td>
                                        <td>${this.escapeHtml(event.event || 'System event')}</td>
                                        <td>${this.escapeHtml(event.severity || 'INFO')}</td>
                                        <td><span class="status-badge ${this.eventClass(event.status)}">${this.escapeHtml(event.status || 'INFO')}</span></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }
        grid.innerHTML = html;
    }

    renderServerAlarms(server) {
        const tbody = document.getElementById(`serverAlarmBody${server}`);
        if (!tbody) return;
        const events = (this.state.events || []).filter(event => Number(event.server) === server);
        if (!events.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">No SQL alarm events for this server</td></tr>';
            return;
        }

        tbody.innerHTML = events.slice(0, 25).map(event => {
            const date = event.timestamp ? new Date(event.timestamp) : null;
            const state = String(event.status || 'INFO').toUpperCase();
            return `
                <tr>
                    <td>${date ? date.toLocaleTimeString() : '-'}</td>
                    <td>${date ? date.toLocaleDateString() : '-'}</td>
                    <td>Server${server}</td>
                    <td>${this.escapeHtml(event.event || 'System event')}</td>
                    <td><span class="status-badge ${this.eventClass(state)}">${this.escapeHtml(state)}</span></td>
                    <td>${state === 'ACTIVE' ? '1' : '0'}</td>
                    <td>${this.escapeHtml(event.severity || 'INFO')}</td>
                </tr>
            `;
        }).join('');
    }

    // ============================================================
    // SERVER DETAIL AND REAL SQL HISTORY CHARTS
    // ============================================================

    renderServerDetail(server, forceHistory = false) {
        const container = document.getElementById(`view-server${server}`);
        if (!container) return;

        const tags = this.state.tags;
        const online = this.bool(tags[`Server${server}_Status`]);
        const cpu = this.number(tags[`Server${server}_CPU_Percent`]);
        const ram = this.number(tags[`Server${server}_RAM_Percent`]);
        const disk = this.number(tags[`Server${server}_Disk_Percent`]);
        const temperature = this.number(tags[`Server${server}_Temp_C`]);
        const network = this.number(tags[`Server${server}_Network_Mbps`]);
        const latency = this.number(tags[`Server${server}_Latency_ms`]);
        const ai = this.getServerAnalytics(server);
        const health = ai?.health_score ?? this.calculateClientHealth(server);
        const capacity = ai?.capacity_headroom ?? Math.max(0, 100 - Math.max(cpu, ram, disk));

        const cpuAlarm = this.bool(tags[`Server${server}_CPU_Alarm`]);
        const tempAlarm = this.bool(tags[`Server${server}_Temp_Alarm`]);
        const downAlarm = this.bool(tags[`Server${server}_Down_Alarm`]);

        container.innerHTML = `
            <div class="performance-section">
                <div class="section-title">ðŸ–¥ï¸ Server ${server} - Detailed Monitoring</div>
                <div id="serverDetailBadges${server}" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
                    <span id="serverDetailStatus${server}" class="status-badge ${online ? 'online' : 'offline'}" style="font-size:14px;padding:6px 20px;">${online ? 'â— UP - SQL Live' : 'â— DOWN - SQL Live'}</span>
                    ${cpuAlarm ? '<span class="status-badge active" style="font-size:14px;padding:6px 20px;">âš  CPU ALARM</span>' : ''}
                    ${tempAlarm ? '<span class="status-badge active" style="font-size:14px;padding:6px 20px;">âš  TEMP ALARM</span>' : ''}
                    ${downAlarm ? '<span class="status-badge active" style="font-size:14px;padding:6px 20px;">âš  SERVER DOWN</span>' : ''}
                </div>

                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="card-title">ðŸ“Š SQL KPI Values</div>
                        <div class="detail-metrics">
                            ${this.detailMetric('CPU Usage', cpu, '%', this.getValueClass(cpu, 75, 90), `detailCpu${server}`)}
                            ${this.detailMetric('RAM Usage', ram, '%', this.getValueClass(ram, 80, 90), `detailRam${server}`)}
                            ${this.detailMetric('Disk Usage', disk, '%', this.getValueClass(disk, 80, 90), `detailDisk${server}`)}
                            ${this.detailMetric('Temperature', temperature, 'Â°C', this.getValueClass(temperature, 60, 75), `detailTemp${server}`)}
                            ${this.detailMetric('Network Throughput', network, 'Mbps', 'normal', `detailNetwork${server}`)}
                            ${this.detailMetric('Latency', latency, 'ms', this.getValueClass(latency, 30, 50), `detailLatency${server}`)}
                            ${this.detailMetric('Health Score', health, '/100', this.getHealthClass(health), `detailHealth${server}`)}
                            ${this.detailMetric('Capacity Headroom', capacity, '%', this.getValueClass(100 - capacity, 75, 90), `detailCapacity${server}`)}
                        </div>
                        <div class="read-only-note">No random or simulated values are displayed here. Every raw KPI comes from SQL Server; health and headroom are labeled calculated KPIs.</div>
                    </div>

                    <div class="detail-card">
                        <div class="card-title">ðŸ“ˆ Live SQL Signal Charts</div>
                        <div class="chart-container"><canvas id="chartCPU${server}"></canvas></div>
                        <div class="chart-container"><canvas id="chartRAM${server}"></canvas></div>
                        <div class="chart-container"><canvas id="chartTemp${server}"></canvas></div>
                        <div id="historyMessage${server}" class="section-note">Loading SQL history, then continuing as a live one-second scrolling signal...</div>
                    </div>
                </div>

                <div class="detail-card" style="margin-top:20px;">
                    <div class="card-title">ðŸ”” Alarm Status (Server ${server})</div>
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;">
                        ${this.alarmTile('CPU HIGH ALARM', `CPU â‰¥ 90%`, cpuAlarm, `detailCpuAlarm${server}`)}
                        ${this.alarmTile('TEMPERATURE HIGH ALARM', `Temperature â‰¥ 75Â°C`, tempAlarm, `detailTempAlarm${server}`)}
                        ${this.alarmTile('SERVER DOWN ALARM', 'Status = DOWN', downAlarm, `detailDownAlarm${server}`)}
                    </div>
                </div>

                <div class="detail-card" style="margin-top:20px;">
                    <div class="card-title">ðŸŽ® Existing Server Controls</div>
                    <div style="display:flex;gap:12px;flex-wrap:wrap;">
                        <button id="detailToggleButton${server}" class="btn ${online ? 'btn-danger' : 'btn-success'}" onclick="client.toggleServer(${server})" disabled title="Read-only live SQL mode">${online ? 'ðŸ”Œ Toggle OFF' : 'ðŸ”‹ Toggle ON'}</button>
                        <button class="btn btn-warning" onclick="client.stressServer(${server})" disabled title="Read-only live SQL mode">âš¡ CPU Stress Test</button>
                        <button class="btn btn-primary" onclick="client.resetServer(${server})" disabled title="Read-only live SQL mode">â†º Reset Server</button>
                        <button class="btn btn-outline" onclick="client.refreshData()">âŸ³ Refresh Data</button>
                        <button class="btn btn-outline" onclick="client.showView('overview')">â† Back to Overview</button>
                    </div>
                    <div class="read-only-note">The operational control buttons are preserved, but disabled because AVEVA is the source of truth. This prevents the web dashboard from changing industrial data accidentally.</div>
                </div>

                <div class="detail-card" style="margin-top:20px;">
                    <div class="card-title">ðŸ“‹ Server ${server} Alarm Viewer</div>
                    <div class="events-table-wrap">
                        <table class="events-table">
                            <thead><tr><th>Time</th><th>Date</th><th>Alarm Tag</th><th>Alarm Comment</th><th>Status</th><th>Value</th><th>Priority</th></tr></thead>
                            <tbody id="serverAlarmBody${server}"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        container.dataset.liveInitialized = 'true';
        this.renderServerAlarms(server);
        this.loadHistory(server, forceHistory).then(history => {
            if (history === null) return;
            if (this.state.currentView !== `server${server}`) return;
            const message = document.getElementById(`historyMessage${server}`);
            if (!history.length) {
                if (message) message.textContent = 'No historical rows were returned. The chart is now building from live SQL samples every second.';
                this.createCharts(server, []);
                return;
            }
            if (message) message.textContent = `${history.length} SQL samples loaded. New values now enter from the right every second, like a monitoring heartbeat.`;
            this.createCharts(server, history);
        });
    }

    detailMetric(label, value, unit, cssClass, valueId = '') {
        const idAttribute = valueId ? ` id="${valueId}"` : '';
        return `
            <div class="detail-metric">
                <div class="label">${label}</div>
                <div${idAttribute} class="value ${cssClass}">${this.number(value).toFixed(1)}<span class="unit">${unit}</span></div>
            </div>
        `;
    }

    alarmTile(title, condition, active, statusId = '') {
        const idAttribute = statusId ? ` id="${statusId}"` : '';
        return `
            <div style="padding:16px;background:var(--bg-input);border-radius:8px;border:1px solid var(--border-color);">
                <div style="font-size:13px;color:var(--text-muted);font-weight:600;">${title}</div>
                <div style="font-size:14px;margin-top:4px;">${condition}</div>
                <div${idAttribute} style="font-size:16px;font-weight:700;margin-top:6px;color:${active ? '#d32f2f' : '#00c853'};">${active ? 'âš  ACTIVE' : 'âœ“ NORMAL'}</div>
            </div>
        `;
    }

    updateServerDetail(server) {
        const tags = this.state.tags;
        const online = this.bool(tags[`Server${server}_Status`]);
        const cpu = this.number(tags[`Server${server}_CPU_Percent`]);
        const ram = this.number(tags[`Server${server}_RAM_Percent`]);
        const disk = this.number(tags[`Server${server}_Disk_Percent`]);
        const temperature = this.number(tags[`Server${server}_Temp_C`]);
        const network = this.number(tags[`Server${server}_Network_Mbps`]);
        const latency = this.number(tags[`Server${server}_Latency_ms`]);
        const ai = this.getServerAnalytics(server);
        const health = ai?.health_score ?? this.calculateClientHealth(server);
        const capacity = ai?.capacity_headroom ?? Math.max(0, 100 - Math.max(cpu, ram, disk));

        this.updateDetailValue(`detailCpu${server}`, cpu, '%', this.getValueClass(cpu, 75, 90));
        this.updateDetailValue(`detailRam${server}`, ram, '%', this.getValueClass(ram, 80, 90));
        this.updateDetailValue(`detailDisk${server}`, disk, '%', this.getValueClass(disk, 80, 90));
        this.updateDetailValue(`detailTemp${server}`, temperature, 'Â°C', this.getValueClass(temperature, 60, 75));
        this.updateDetailValue(`detailNetwork${server}`, network, 'Mbps', 'normal');
        this.updateDetailValue(`detailLatency${server}`, latency, 'ms', this.getValueClass(latency, 30, 50));
        this.updateDetailValue(`detailHealth${server}`, health, '/100', this.getHealthClass(health));
        this.updateDetailValue(`detailCapacity${server}`, capacity, '%', this.getValueClass(100 - capacity, 75, 90));

        const cpuAlarm = this.bool(tags[`Server${server}_CPU_Alarm`]);
        const tempAlarm = this.bool(tags[`Server${server}_Temp_Alarm`]);
        const downAlarm = this.bool(tags[`Server${server}_Down_Alarm`]);

        const badgeWrap = document.getElementById(`serverDetailBadges${server}`);
        if (badgeWrap) {
            badgeWrap.innerHTML = `
                <span id="serverDetailStatus${server}" class="status-badge ${online ? 'online' : 'offline'}" style="font-size:14px;padding:6px 20px;">${online ? 'â— UP - SQL Live' : 'â— DOWN - SQL Live'}</span>
                ${cpuAlarm ? '<span class="status-badge active" style="font-size:14px;padding:6px 20px;">âš  CPU ALARM</span>' : ''}
                ${tempAlarm ? '<span class="status-badge active" style="font-size:14px;padding:6px 20px;">âš  TEMP ALARM</span>' : ''}
                ${downAlarm ? '<span class="status-badge active" style="font-size:14px;padding:6px 20px;">âš  SERVER DOWN</span>' : ''}
            `;
        }

        this.updateAlarmStatus(`detailCpuAlarm${server}`, cpuAlarm);
        this.updateAlarmStatus(`detailTempAlarm${server}`, tempAlarm);
        this.updateAlarmStatus(`detailDownAlarm${server}`, downAlarm);

        const toggleButton = document.getElementById(`detailToggleButton${server}`);
        if (toggleButton) {
            toggleButton.className = `btn ${online ? 'btn-danger' : 'btn-success'}`;
            toggleButton.textContent = online ? 'ðŸ”Œ Toggle OFF' : 'ðŸ”‹ Toggle ON';
        }
    }

    updateDetailValue(elementId, value, unit, cssClass) {
        const element = document.getElementById(elementId);
        if (!element) return;
        element.className = `value ${cssClass}`;
        element.innerHTML = `${this.number(value).toFixed(1)}<span class="unit">${unit}</span>`;
    }

    updateAlarmStatus(elementId, active) {
        const element = document.getElementById(elementId);
        if (!element) return;
        element.style.color = active ? '#d32f2f' : '#00c853';
        element.textContent = active ? 'âš  ACTIVE' : 'âœ“ NORMAL';
    }

    createCharts(server, history) {
        ['cpu', 'ram', 'temp'].forEach(metric => {
            const chart = this.state.charts[`${metric}${server}`];
            if (chart) {
                chart.destroy();
                delete this.state.charts[`${metric}${server}`];
            }
        });

        if (typeof Chart === 'undefined') return;

        const trimmedHistory = Array.isArray(history) ? history.slice(-this.chartPointLimit) : [];
        const fallbackTimestamp = this.state.lastUpdate || new Date().toISOString();
        const source = trimmedHistory.length ? trimmedHistory : [{
            timestamp: fallbackTimestamp,
            cpu: this.number(this.state.tags[`Server${server}_CPU_Percent`]),
            ram: this.number(this.state.tags[`Server${server}_RAM_Percent`]),
            temperature: this.number(this.state.tags[`Server${server}_Temp_C`])
        }];

        const labels = source.map(item => item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : '-');
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const textColor = isDark ? '#c9e9f4' : '#17324d';
        const gridColor = isDark ? 'rgba(42, 164, 205, 0.22)' : 'rgba(11, 79, 108, 0.16)';

        const baseOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 220, easing: 'linear' },
            interaction: { mode: 'index', intersect: false },
            normalized: true,
            plugins: {
                legend: { labels: { color: textColor, font: { size: 11, weight: '600' }, usePointStyle: true } },
                tooltip: { enabled: true }
            },
            scales: {
                x: {
                    grid: { color: gridColor, lineWidth: 1 },
                    ticks: { display: false },
                    border: { display: false }
                },
                y: {
                    grid: { color: gridColor, lineWidth: 1 },
                    ticks: { color: textColor, font: { size: 9 }, maxTicksLimit: 6 },
                    border: { display: false }
                }
            }
        };

        this.createLineChart(`chartCPU${server}`, `cpu${server}`, labels, source.map(item => item.cpu), 'CPU Usage %', '#5ee8ff', 'rgba(94, 232, 255, 0.07)', baseOptions, 0, 100);
        this.createLineChart(`chartRAM${server}`, `ram${server}`, labels, source.map(item => item.ram), 'RAM Usage %', '#71f1c5', 'rgba(113, 241, 197, 0.06)', baseOptions, 0, 100);
        this.createLineChart(`chartTemp${server}`, `temp${server}`, labels, source.map(item => item.temperature), 'Temperature Â°C', '#ffb45e', 'rgba(255, 180, 94, 0.06)', baseOptions, 20, 100);
    }

    createLineChart(canvasId, stateKey, labels, values, label, borderColor, backgroundColor, baseOptions, suggestedMin, suggestedMax) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const options = JSON.parse(JSON.stringify(baseOptions));
        options.scales.y.min = suggestedMin;
        options.scales.y.max = suggestedMax;

        const neonGlow = {
            id: `neonGlow-${stateKey}`,
            beforeDatasetDraw(chart) {
                const ctx = chart.ctx;
                ctx.save();
                ctx.shadowColor = borderColor;
                ctx.shadowBlur = 12;
                ctx.shadowOffsetX = 0;
                ctx.shadowOffsetY = 0;
            },
            afterDatasetDraw(chart) {
                chart.ctx.restore();
            }
        };

        this.state.charts[stateKey] = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label,
                    data: values,
                    borderColor,
                    backgroundColor,
                    fill: true,
                    tension: 0.28,
                    cubicInterpolationMode: 'monotone',
                    pointRadius: context => context.dataIndex === context.dataset.data.length - 1 ? 3 : 0,
                    pointHoverRadius: 5,
                    pointBackgroundColor: borderColor,
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 1,
                    borderWidth: 3
                }]
            },
            options,
            plugins: [neonGlow]
        });
    }

    appendLiveChartPoint(server) {
        const timestamp = this.state.lastUpdate ? new Date(this.state.lastUpdate) : new Date();
        const label = Number.isNaN(timestamp.getTime()) ? new Date().toLocaleTimeString() : timestamp.toLocaleTimeString();
        const values = {
            cpu: this.number(this.state.tags[`Server${server}_CPU_Percent`]),
            ram: this.number(this.state.tags[`Server${server}_RAM_Percent`]),
            temp: this.number(this.state.tags[`Server${server}_Temp_C`])
        };

        Object.entries(values).forEach(([metric, value]) => {
            const chart = this.state.charts[`${metric}${server}`];
            if (!chart) return;
            chart.data.labels.push(label);
            chart.data.datasets[0].data.push(value);
            while (chart.data.labels.length > this.chartPointLimit) chart.data.labels.shift();
            while (chart.data.datasets[0].data.length > this.chartPointLimit) chart.data.datasets[0].data.shift();
            chart.update();
        });

        const message = document.getElementById(`historyMessage${server}`);
        if (message) message.textContent = `Live one-second signal Â· newest SQL sample ${label} Â· rolling ${this.chartPointLimit}-point window`;
    }

    // ============================================================
    // SUMMARY DASHBOARD
    // ============================================================

    renderSummaryDashboard() {
        const grid = document.getElementById('summaryGrid');
        if (!grid) return;
        const tags = this.state.tags;
        let html = '';

        for (let server = 1; server <= 4; server += 1) {
            const online = this.bool(tags[`Server${server}_Status`]);
            const cpu = this.number(tags[`Server${server}_CPU_Percent`]);
            const ram = this.number(tags[`Server${server}_RAM_Percent`]);
            const disk = this.number(tags[`Server${server}_Disk_Percent`]);
            const temperature = this.number(tags[`Server${server}_Temp_C`]);
            const network = this.number(tags[`Server${server}_Network_Mbps`]);
            const latency = this.number(tags[`Server${server}_Latency_ms`]);
            const health = this.getServerAnalytics(server)?.health_score ?? this.calculateClientHealth(server);

            html += `
                <div style="background:var(--bg-secondary);padding:20px;border-radius:12px;border:1px solid var(--border-color);text-align:left;">
                    <h4 style="font-size:18px;font-weight:700;margin-bottom:12px;color:${online ? '#00c853' : '#d32f2f'};">${online ? 'ðŸŸ¢' : 'ðŸ”´'} Server ${server}</h4>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:14px;">
                        <div><span style="color:var(--text-muted);">CPU:</span> <strong>${cpu.toFixed(1)}%</strong></div>
                        <div><span style="color:var(--text-muted);">RAM:</span> <strong>${ram.toFixed(1)}%</strong></div>
                        <div><span style="color:var(--text-muted);">Disk:</span> <strong>${disk.toFixed(1)}%</strong></div>
                        <div><span style="color:var(--text-muted);">Temp:</span> <strong>${temperature.toFixed(1)}Â°C</strong></div>
                        <div><span style="color:var(--text-muted);">Network:</span> <strong>${network.toFixed(1)} Mbps</strong></div>
                        <div><span style="color:var(--text-muted);">Latency:</span> <strong>${latency.toFixed(1)} ms</strong></div>
                        <div><span style="color:var(--text-muted);">Health:</span> <strong>${health}/100</strong></div>
                        <div><span style="color:var(--text-muted);">Status:</span> <strong>${online ? 'Online' : 'Offline'}</strong></div>
                    </div>
                    <button class="btn btn-outline btn-sm" style="margin-top:12px;width:100%;" onclick="client.showView('server${server}')">View Details â†’</button>
                </div>
            `;
        }
        grid.innerHTML = html;
    }

    // ============================================================
    // AI ANALYTICS
    // ============================================================

    renderAnalytics() {
        const analytics = this.state.analytics;
        if (!analytics) return;

        const hero = document.getElementById('analyticsHero');
        const serverGrid = document.getElementById('aiServerKpis');
        const challengeList = document.getElementById('challengeList');
        const recommendationList = document.getElementById('recommendationList');
        const sourceList = document.getElementById('sourceList');
        if (!hero || !serverGrid || !challengeList || !recommendationList || !sourceList) return;

        const system = analytics.system;
        hero.innerHTML = `
            <div class="ai-hero-card">
                <div class="ai-engine-name">${this.escapeHtml(analytics.engine.name)}</div>
                <p class="section-note">${this.escapeHtml(analytics.engine.type)}. ${this.escapeHtml(analytics.engine.note)}</p>
                <div class="recommendation-meta" style="margin-top:10px;">
                    <span class="pill">Source: SQL Live</span>
                    <span class="pill">Generated ${new Date(analytics.generated_at).toLocaleTimeString()}</span>
                </div>
            </div>
            ${this.aiStatCard('System Health', `${this.number(system.health_score).toFixed(1)}/100`, this.getHealthColor(system.health_score))}
            ${this.aiStatCard('Risk Level', system.risk_label, this.getRiskColor(system.risk_label))}
            ${this.aiStatCard('Critical Actions', system.critical_recommendations, system.critical_recommendations ? '#d32f2f' : '#00c853')}
            ${this.aiStatCard('High Priority', system.high_recommendations, system.high_recommendations ? '#ff6f00' : '#00c853')}
        `;

        serverGrid.innerHTML = analytics.server_kpis.map(item => {
            const ringClass = item.health_label.toLowerCase();
            return `
                <div class="server-ai-card">
                    <div class="server-ai-header">
                        <div>
                            <div style="font-size:17px;font-weight:800;">Server ${item.server}</div>
                            <div class="section-note">${item.status ? 'Online' : 'Offline'} Â· Risk ${item.risk_score}/100</div>
                        </div>
                        <div class="health-score-ring ${ringClass}">${item.health_score}</div>
                    </div>
                    <div class="mini-kpi-grid">
                        ${this.miniKpi('CPU', `${item.cpu.toFixed(1)}%`, item.cpu_state)}
                        ${this.miniKpi('RAM', `${item.ram.toFixed(1)}%`, item.ram_state)}
                        ${this.miniKpi('Disk', `${item.disk.toFixed(1)}%`, item.disk_state)}
                        ${this.miniKpi('Temp', `${item.temperature.toFixed(1)}Â°C`, item.thermal_state)}
                        ${this.miniKpi('Latency', `${item.latency.toFixed(1)} ms`, item.latency_state)}
                        ${this.miniKpi('Headroom', `${item.capacity_headroom.toFixed(1)}%`, item.capacity_headroom < 10 ? 'critical' : item.capacity_headroom < 25 ? 'warning' : 'healthy')}
                    </div>
                    <button class="btn btn-outline btn-sm" style="margin-top:12px;width:100%;" onclick="client.showView('server${item.server}')">Open Server Details</button>
                </div>
            `;
        }).join('');

        challengeList.innerHTML = analytics.challenges.map(challenge => `
            <div class="challenge-card ${challenge.active ? 'active' : 'inactive'}">
                <div class="challenge-title">${challenge.active ? 'âš ' : 'âœ“'} ${this.escapeHtml(challenge.name)}</div>
                <p>${this.escapeHtml(challenge.description)}</p>
                <div class="recommendation-meta" style="margin-top:8px;">
                    <span class="pill ${challenge.active ? 'medium' : 'low'}">${challenge.active ? 'Detected/Relevant' : 'Currently Controlled'}</span>
                    ${challenge.source_ids.map(id => `<span class="pill">${this.escapeHtml(id)}</span>`).join('')}
                </div>
            </div>
        `).join('');

        recommendationList.innerHTML = analytics.recommendations.map(item => `
            <div class="recommendation-card ${item.priority}">
                <div class="recommendation-meta">
                    <span class="pill ${item.priority}">${this.escapeHtml(item.priority)}</span>
                    <span class="pill">${item.server ? `Server ${item.server}` : 'Data Center'}</span>
                    <span class="pill">Confidence ${item.confidence}%</span>
                </div>
                <div class="recommendation-title">${this.escapeHtml(item.problem)}</div>
                <p><strong>Evidence:</strong> ${this.escapeHtml(item.evidence)}</p>
                <p><strong>Business/technical impact:</strong> ${this.escapeHtml(item.impact)}</p>
                <p><strong>Recommended solution:</strong> ${this.escapeHtml(item.recommended_action)}</p>
                <ol>${item.how_to_overcome.map(step => `<li>${this.escapeHtml(step)}</li>`).join('')}</ol>
                <div class="recommendation-meta" style="margin-top:8px;">${item.source_ids.map(id => `<span class="pill">${this.escapeHtml(id)}</span>`).join('')}</div>
            </div>
        `).join('');

        sourceList.innerHTML = analytics.sources.map(source => `
            <div class="source-card">
                <div class="source-title">${this.escapeHtml(source.organization)} - ${this.escapeHtml(source.title)}</div>
                <p>${this.escapeHtml(source.supports)}</p>
                <div class="recommendation-meta" style="margin-top:8px;">
                    <span class="pill">${this.escapeHtml(source.id)}</span>
                    <span class="pill">${this.escapeHtml(source.year)}</span>
                    <a class="btn btn-outline btn-sm" href="${this.escapeAttribute(source.url)}" target="_blank" rel="noopener noreferrer">Open Source</a>
                </div>
            </div>
        `).join('');
    }

    aiStatCard(label, value, color) {
        return `<div class="ai-stat-card"><div class="ai-stat-label">${label}</div><div class="ai-stat-value" style="color:${color};">${this.escapeHtml(value)}</div></div>`;
    }

    miniKpi(label, value, status) {
        const color = status === 'critical' ? '#d32f2f' : status === 'warning' ? '#ff9100' : '#00c853';
        return `<div class="mini-kpi"><div class="label">${label}</div><div class="value" style="color:${color};">${value}</div></div>`;
    }

    updateAIBadge() {
        const badge = document.getElementById('aiBadge');
        if (!badge || !this.state.analytics) return;
        const count = this.state.analytics.system.critical_recommendations + this.state.analytics.system.high_recommendations;
        badge.textContent = count > 0 ? String(count) : 'OK';
        badge.className = `badge ${count > 0 ? '' : 'offline'}`;
    }

    // ============================================================
    // REPORT BUILDER
    // ============================================================

    updateCustomDateVisibility() {
        const range = document.getElementById('reportRange')?.value || 'current';
        const show = range === 'custom';
        const fromGroup = document.getElementById('dateFromGroup');
        const toGroup = document.getElementById('dateToGroup');
        if (fromGroup) fromGroup.style.display = show ? 'flex' : 'none';
        if (toGroup) toGroup.style.display = show ? 'flex' : 'none';
    }

    collectReportOptions() {
        const metrics = Array.from(document.querySelectorAll('.metric-check input:checked')).map(input => input.value);
        return {
            report_type: document.getElementById('reportType')?.value || 'executive',
            scope: document.getElementById('reportScope')?.value || 'all',
            range: document.getElementById('reportRange')?.value || 'current',
            format: document.getElementById('reportFormat')?.value || 'pdf',
            date_from: document.getElementById('reportDateFrom')?.value || '',
            date_to: document.getElementById('reportDateTo')?.value || '',
            metrics
        };
    }

    validateReportOptions(options) {
        if (!options.metrics.length) {
            this.showToast('Select at least one report item', 'warning');
            return false;
        }
        if (options.range === 'custom' && (!options.date_from || !options.date_to)) {
            this.showToast('Select both From and To dates for a custom report', 'warning');
            return false;
        }
        if (options.range === 'custom' && options.date_from > options.date_to) {
            this.showToast('The From date must be earlier than the To date', 'warning');
            return false;
        }
        return true;
    }

    buildReportQuery(options, includeFormat = false) {
        const params = new URLSearchParams({
            report_type: options.report_type,
            scope: options.scope,
            range: options.range,
            metrics: options.metrics.join(',')
        });
        if (options.date_from) params.set('date_from', options.date_from);
        if (options.date_to) params.set('date_to', options.date_to);
        if (includeFormat) params.set('format', options.format);
        return params.toString();
    }

    async previewReport() {
        const options = this.collectReportOptions();
        if (!this.validateReportOptions(options)) return;
        const preview = document.getElementById('reportPreview');
        if (!preview) return;

        preview.innerHTML = '<div class="empty-state" style="color:#64748b;"><div style="font-size:42px;">â³</div><h3>Building preview from SQL data...</h3></div>';
        try {
            const data = await this.fetchJson(`${this.apiBase}/report/preview?${this.buildReportQuery(options)}`);
            this.renderReportPreview(data);
            this.showToast(`Preview generated from ${data.row_count} matching SQL row(s)`, 'success');
        } catch (error) {
            preview.innerHTML = `<div class="empty-state" style="color:#b91c1c;"><h3>Preview failed</h3><p>${this.escapeHtml(error.message)}</p></div>`;
            this.showToast(error.message, 'error');
        }
    }

    renderReportPreview(data) {
        const preview = document.getElementById('reportPreview');
        if (!preview) return;
        const aggregates = data.aggregates || [];
        const recommendations = data.recommendations || [];
        const system = data.system || {};

        preview.innerHTML = `
            <div class="report-preview-header">
                <div>
                    <img class="report-preview-logo" src="/assets/schneider-aveva-logo.png" alt="Schneider Electric and AVEVA" onerror="this.style.display='none';this.nextElementSibling.style.display='block';" />
                    <div style="display:none;font-weight:800;"><span style="color:#087a4b;">Schneider Electric</span><span style="color:#64748b;"> | AVEVA</span></div>
                </div>
                <div style="text-align:right;font-size:11px;color:#64748b;">${new Date(data.generated_at).toLocaleString()}<br/>${this.escapeHtml(data.options.report_type)} Â· ${this.escapeHtml(data.options.scope)} Â· ${this.escapeHtml(data.options.range)}</div>
            </div>
            <h2 style="font-size:20px;color:#0b4f6c;margin-bottom:6px;">Data Center Monitoring Report Preview</h2>
            <p style="font-size:12px;color:#64748b;">${data.row_count} matching SQL row(s). System health ${this.number(system.health_score).toFixed(1)}/100; risk ${this.escapeHtml(system.risk_label || '-')}.</p>
            <table>
                <thead><tr><th>Server</th><th>Samples</th><th>CPU Avg/Max</th><th>RAM Avg</th><th>Disk Avg/Max</th><th>Temp Avg/Max</th><th>Latency Avg/Max</th><th>Availability</th></tr></thead>
                <tbody>
                    ${aggregates.length ? aggregates.map(item => `
                        <tr>
                            <td>Server ${item.server}</td>
                            <td>${item.samples}</td>
                            <td>${item.cpu_avg.toFixed(1)}% / ${item.cpu_max.toFixed(1)}%</td>
                            <td>${item.ram_avg.toFixed(1)}%</td>
                            <td>${item.disk_avg.toFixed(1)}% / ${item.disk_max.toFixed(1)}%</td>
                            <td>${item.temp_avg.toFixed(1)}Â°C / ${item.temp_max.toFixed(1)}Â°C</td>
                            <td>${item.latency_avg.toFixed(1)} / ${item.latency_max.toFixed(1)} ms</td>
                            <td>${item.availability_percent.toFixed(2)}%</td>
                        </tr>
                    `).join('') : '<tr><td colspan="8">No SQL rows matched the selected filters.</td></tr>'}
                </tbody>
            </table>
            <h3 style="font-size:15px;color:#17324d;margin:18px 0 8px;">AI Recommendations</h3>
            ${recommendations.length ? recommendations.slice(0, 6).map(item => `
                <div style="border-left:4px solid ${item.priority === 'critical' ? '#d32f2f' : item.priority === 'high' ? '#ff6f00' : '#00c853'};padding:8px 10px;margin-bottom:8px;background:#f8fafc;">
                    <strong>[${this.escapeHtml(item.priority.toUpperCase())}] ${item.server ? `Server ${item.server}` : 'Data Center'} - ${this.escapeHtml(item.problem)}</strong>
                    <div style="font-size:11px;color:#475569;margin-top:3px;">${this.escapeHtml(item.recommended_action)}</div>
                </div>
            `).join('') : '<p style="font-size:12px;color:#64748b;">No recommendations returned.</p>'}
            <p style="font-size:10px;color:#64748b;margin-top:16px;">Logo file detected by backend: ${data.logo_available ? 'Yes' : 'No - text fallback will be used in PDF'}. PDF output includes a research basis and a data-source note.</p>
        `;
    }

    async exportSelectedReport() {
        const options = this.collectReportOptions();
        if (!this.validateReportOptions(options) || this.reportGenerating) return;

        const button = document.getElementById('reportExportButton');
        const status = document.getElementById('reportExportStatus');
        const originalText = button?.innerHTML || 'â¬‡ Export';
        this.reportGenerating = true;
        if (button) {
            button.disabled = true;
            button.innerHTML = 'â³ Generating...';
        }
        if (status) status.textContent = `Preparing ${options.format.toUpperCase()} report...`;

        try {
            const url = `${this.apiBase}/report?${this.buildReportQuery(options, true)}`;
            const response = await fetch(url, { cache: 'no-store' });
            if (!response.ok) {
                let message = `Report generation failed (${response.status})`;
                const responseText = await response.text();
                if (responseText) {
                    try {
                        const data = JSON.parse(responseText);
                        message = data.error || data.message || message;
                    } catch (error) {
                        message = responseText;
                    }
                }
                throw new Error(message);
            }

            const blob = await response.blob();
            if (!blob.size) throw new Error('The server returned an empty report file.');

            const disposition = response.headers.get('Content-Disposition') || '';
            const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
            const defaultName = `DataCenter_Report_${new Date().toISOString().replace(/[:.]/g, '-')}.${options.format}`;
            const filename = filenameMatch?.[1] || defaultName;
            const objectUrl = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = objectUrl;
            link.download = filename;
            link.rel = 'noopener';
            link.style.display = 'none';
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.setTimeout(() => URL.revokeObjectURL(objectUrl), 5000);

            if (status) status.textContent = `${filename} generated successfully.`;
            this.showToast(`${options.format.toUpperCase()} report downloaded successfully`, 'success');
        } catch (error) {
            console.error('Report export failed:', error);
            if (status) status.textContent = `Generation failed: ${error.message}`;
            this.showToast(`Report generation failed: ${error.message}`, 'error');
        } finally {
            this.reportGenerating = false;
            if (button) {
                button.disabled = false;
                button.innerHTML = originalText;
            }
        }
    }

    // Backward-compatible name used by the original Quick Action.
    exportReport() {
        this.openReports();
    }

    // ============================================================
    // QUICK ACTIONS
    // ============================================================

    healthCheck() {
        const alarms = this.countAlarms();
        const offline = 4 - this.metricValues('Status', false).length;
        if (!this.state.databaseConnected) {
            this.showToast('Health check unavailable: SQL Server is disconnected', 'error');
        } else if (alarms === 0 && offline === 0) {
            this.showToast('Health check: all monitored servers are within alarm limits', 'success');
        } else {
            this.showToast(`Health check: ${alarms} active alarm condition(s) detected`, 'warning');
        }
    }

    viewAlarms() {
        this.showView('alarms');
        this.showToast('Viewing SQL alarm summary', 'info');
    }

    // ============================================================
    // UTILITIES
    // ============================================================

    number(value, fallback = 0) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    bool(value) {
        if (typeof value === 'boolean') return value;
        if (typeof value === 'number') return value !== 0;
        return ['true', '1', 'yes', 'up', 'online'].includes(String(value || '').toLowerCase());
    }

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    escapeAttribute(value) {
        return this.escapeHtml(value).replaceAll('`', '&#096;');
    }

    setText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    }

    setHtml(id, value) {
        const element = document.getElementById(id);
        if (element) element.innerHTML = value;
    }

    setWidth(id, value) {
        const element = document.getElementById(id);
        if (element) element.style.width = `${Math.max(0, Math.min(100, this.number(value)))}%`;
    }

    metricValues(metric, onlineOnly = true) {
        const values = [];
        for (let server = 1; server <= 4; server += 1) {
            const online = this.bool(this.state.tags[`Server${server}_Status`]);
            if (metric === 'Status') {
                if (online) values.push(1);
                continue;
            }
            if (!onlineOnly || online) values.push(this.number(this.state.tags[`Server${server}_${metric}`]));
        }
        return values;
    }

    getAverage(metric) {
        const values = this.metricValues(metric);
        return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
    }

    countAlarms() {
        let count = 0;
        for (let server = 1; server <= 4; server += 1) {
            if (this.bool(this.state.tags[`Server${server}_CPU_Alarm`])) count += 1;
            if (this.bool(this.state.tags[`Server${server}_Temp_Alarm`])) count += 1;
            if (this.bool(this.state.tags[`Server${server}_Down_Alarm`])) count += 1;
        }
        return count;
    }

    getValueClass(value, warning, critical) {
        if (value >= critical) return 'critical';
        if (value >= warning) return 'warning';
        return 'normal';
    }

    getHealthClass(score) {
        if (score < 40) return 'critical';
        if (score < 65) return 'critical';
        if (score < 85) return 'warning';
        return 'normal';
    }

    calculateClientHealth(server) {
        if (!this.bool(this.state.tags[`Server${server}_Status`])) return 0;
        const cpu = this.number(this.state.tags[`Server${server}_CPU_Percent`]);
        const ram = this.number(this.state.tags[`Server${server}_RAM_Percent`]);
        const disk = this.number(this.state.tags[`Server${server}_Disk_Percent`]);
        const temperature = this.number(this.state.tags[`Server${server}_Temp_C`]);
        const latency = this.number(this.state.tags[`Server${server}_Latency_ms`]);
        let score = 100;
        score -= Math.max(0, cpu - 65) * 0.60;
        score -= Math.max(0, ram - 70) * 0.45;
        score -= Math.max(0, disk - 75) * 0.35;
        score -= Math.max(0, temperature - 55) * 0.80;
        score -= Math.max(0, latency - 20) * 0.40;
        return Math.max(0, Math.min(100, Math.round(score)));
    }

    getServerAnalytics(server) {
        return this.state.analytics?.server_kpis?.find(item => Number(item.server) === Number(server)) || null;
    }

    getHealthColor(score) {
        if (score >= 85) return '#00c853';
        if (score >= 65) return '#ff9100';
        return '#d32f2f';
    }

    getRiskColor(label) {
        const normalized = String(label || '').toLowerCase();
        if (normalized === 'critical') return '#d32f2f';
        if (normalized === 'high') return '#ff6f00';
        if (normalized === 'moderate') return '#ff9100';
        return '#00c853';
    }

    eventClass(status) {
        const normalized = String(status || '').toLowerCase();
        if (['active', 'critical', 'high', 'alarm'].includes(normalized)) return 'active';
        if (['cleared', 'recovery', 'resolved', 'normal'].includes(normalized)) return 'cleared';
        return 'warning';
    }

    updateSidebarBadges() {
        for (let server = 1; server <= 4; server += 1) {
            const badge = document.getElementById(`s${server}badge`);
            if (!badge) continue;
            const online = this.bool(this.state.tags[`Server${server}_Status`]);
            badge.textContent = online ? 'â—' : 'â—‹';
            badge.className = `badge ${online ? '' : 'offline'}`;
        }
    }

    updateAlarmBadge() {
        const badge = document.getElementById('alarmBadge');
        if (!badge) return;
        const count = this.countAlarms();
        badge.textContent = String(count);
        badge.className = `badge ${count > 0 ? '' : 'offline'}`;
    }

    updateConnectionStatus(connected, errorMessage = null) {
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        if (!dot || !text) return;
        dot.className = `dot ${connected ? 'online' : 'offline'}`;
        text.textContent = connected ? 'SQL Connected' : 'SQL Disconnected';
        text.title = errorMessage || '';
    }

    updateSimulationButton(isRunning) {
        const button = document.getElementById('simToggle');
        if (!button) return;
        if (isRunning) {
            button.textContent = 'â¸ Pause Live';
            button.className = 'btn btn-warning btn-sm';
        } else {
            button.textContent = 'â–¶ Resume Live';
            button.className = 'btn btn-success btn-sm';
        }
    }

    updateTimestamp(timestamp = null) {
        const element = document.getElementById('lastUpdate');
        if (!element) return;
        if (this.pollingPaused) {
            element.textContent = 'â¸ Display paused';
            return;
        }
        const date = timestamp ? new Date(timestamp) : new Date();
        element.textContent = Number.isNaN(date.getTime()) ? 'ðŸ”„ Updating...' : `ðŸ”„ ${date.toLocaleTimeString()}`;
    }

    updateThemeToggle(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        const slider = document.querySelector('.theme-switch .slider');
        if (slider) slider.style.transform = theme === 'light' ? 'translateX(24px)' : 'translateX(0)';
        this.updateChartColors();
    }

    updateChartColors() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const textColor = isDark ? '#e8edf5' : '#1a1a2e';
        const gridColor = isDark ? '#1e2a38' : '#dee2e6';
        Object.values(this.state.charts).forEach(chart => {
            if (!chart?.options?.scales) return;
            if (chart.options.plugins?.legend?.labels) chart.options.plugins.legend.labels.color = textColor;
            ['x', 'y'].forEach(axis => {
                if (chart.options.scales[axis]?.grid) chart.options.scales[axis].grid.color = gridColor;
                if (chart.options.scales[axis]?.ticks) chart.options.scales[axis].ticks.color = textColor;
            });
            chart.update('none');
        });
    }

    // ============================================================
    // TOASTS AND EVENT LISTENERS
    // ============================================================

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    setupEventListeners() {
        document.querySelectorAll('.sidebar-nav li[data-view]').forEach(item => {
            item.addEventListener('click', () => this.showView(item.dataset.view));
        });

        document.getElementById('menuToggle')?.addEventListener('click', event => {
            event.stopPropagation();
            document.getElementById('sidebar')?.classList.toggle('mobile-open');
        });

        document.addEventListener('click', event => {
            if (window.innerWidth > 992) return;
            const sidebar = document.getElementById('sidebar');
            const menuToggle = document.getElementById('menuToggle');
            if (sidebar && menuToggle && !sidebar.contains(event.target) && !menuToggle.contains(event.target)) {
                sidebar.classList.remove('mobile-open');
            }
        });

        document.addEventListener('keydown', event => {
            const target = event.target;
            const typing = target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement;
            if (typing) return;
            if ((event.key === 'r' || event.key === 'R') && !event.ctrlKey && !event.metaKey) this.refreshData();
            if (event.key === 'Escape') this.showView('overview');
            if (event.key >= '1' && event.key <= '4' && !event.ctrlKey && !event.metaKey) this.showView(`server${event.key}`);
        });
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', next);
    if (window.client) window.client.updateThemeToggle(next);
    else document.documentElement.setAttribute('data-theme', next);
}

function startDashboard() {
    if (window.client) return;
    window.client = new DashboardClient();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startDashboard, { once: true });
} else {
    startDashboard();
}