// static/scripts.js — SmartQueue Enhanced UI v2

document.addEventListener('DOMContentLoaded', () => {

    const socket = io();
    let currentUserId = sessionStorage.getItem('smartQueueUserId');
    let queueIsPaused = false;

    const views = document.querySelectorAll('.view-card');
    const navLinks = document.querySelectorAll('.nav-link');

    const joinForm = document.getElementById('join-form');
    const adminLoginForm = document.getElementById('admin-login-form');
    const userStatusDisplay = document.getElementById('user-status-display');
    const userJoinFormContainer = document.getElementById('user-join-form-container');
    const pauseBtn = document.getElementById('pause-queue-btn');

    // ── Toast System ───────────────────────────────────────────────
    function showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
        toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // ── View Switcher ──────────────────────────────────────────────
    const switchView = (viewId) => {
        views.forEach(v => v.classList.remove('active'));
        const target = document.getElementById(viewId);
        if (target) {
            target.classList.add('active');
            const shell = document.querySelector('.app-shell');
            if (shell) shell.scrollTop = 0;
        }
        navLinks.forEach(l => l.classList.toggle('active', l.dataset.view === viewId));
    };

    navLinks.forEach(link =>
        link.addEventListener('click', e => {
            e.preventDefault();
            switchView(e.currentTarget.dataset.view);
        })
    );

    document.getElementById('show-user-view-btn').addEventListener('click', () => switchView('user-view'));
    document.getElementById('show-admin-login-btn').addEventListener('click', () => switchView('admin-login-view'));

    document.getElementById('leave-queue-btn').addEventListener('click', () => {
        if (currentUserId) {
            socket.emit('leave_queue', { user_id: currentUserId });
        }
        sessionStorage.removeItem('smartQueueUserId');
        window.location.reload();
    });

    document.getElementById('add-another-user-btn').addEventListener('click', () => {
        userStatusDisplay.style.display = 'none';
        userJoinFormContainer.style.display = 'block';
        joinForm.reset();
        document.getElementById('user-id').focus();
    });

    // ── Join Queue (HTTP / Vercel Fix) ─────────────────────────────
    joinForm.addEventListener('submit', async e => {
        e.preventDefault();
        if (queueIsPaused) {
            showToast('Queue is currently paused. Please wait.', 'warning');
            return;
        }
        const userId = document.getElementById('user-id').value.trim();
        const email = document.getElementById('gmail').value.trim();
        const priority = document.querySelector('input[name="priority"]:checked')?.value || 'normal';

        if (userId && email) {
            try {
                const res = await fetch('/api/join', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: userId, email, priority })
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    currentUserId = userId;
                    sessionStorage.setItem('smartQueueUserId', currentUserId);

                    // Manually trigger the "joined" state view update
                    userJoinFormContainer.style.display = 'none';
                    userStatusDisplay.style.display = 'flex';
                    switchView('user-view');
                    document.getElementById('position-value').textContent = data.position;
                    // ... other UI updates happen via polling/socket ...
                    showToast(`You joined at position #${data.position}. Est. wait: ${data.estimated_wait} min`, 'success');

                    // Force a poll immediately
                    pollData();
                } else {
                    showToast(data.error || 'Could not join queue.', 'error');
                }
            } catch (err) {
                showToast('Network error joining queue.', 'error');
                console.error(err);
            }
        }
    });

    // ── Admin Login (HTTP / Vercel Fix) ────────────────────────────
    adminLoginForm.addEventListener('submit', async e => {
        e.preventDefault();
        const uid = document.getElementById('admin-id').value;
        const pwd = document.getElementById('admin-password').value;

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: uid, password: pwd })
            });
            const data = await res.json();

            if (res.ok && data.success) {
                showToast('Admin login successful!', 'success');
                switchView('admin-view');
            } else {
                showToast('Admin login failed. Check your credentials.', 'error');
            }
        } catch (err) {
            showToast('Login network error.', 'error');
        }
    });

    // ── Polling Fallback (for Vercel) ──────────────────────────────
    // Vercel websockets disconnect often. Polling ensures data stays fresh.
    async function pollData() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                // Update specific socket-like handlers
                if (data.queue) updateAdminView(data.queue);
                if (data.stats) socket.listeners('stats_update').forEach(fn => fn(data.stats)); // Mock event trigger? No, just manual update

                // Manual UI Update reusing socket logic parts
                const stats = data.stats;
                if (stats) {
                    const fmtWait = (v) => (v != null && v > 0) ? v : '--';
                    document.getElementById('stat-queue-len').textContent = stats.queue_length;
                    document.getElementById('stat-avg-wait').textContent = fmtWait(stats.avg_wait_minutes);
                    // ... (rest of stats update logic) ...
                    queueIsPaused = data.paused;
                    updatePauseUI(data.paused);
                }

                // Update my position
                if (currentUserId && data.queue) {
                    const me = data.queue.find(u => u.user_id === currentUserId || u.user_name === currentUserId);
                    if (me) {
                        const myPos = data.queue.indexOf(me) + 1;
                        document.getElementById('position-value').textContent = myPos;
                        document.getElementById('people-ahead-value').textContent = myPos > 0 ? myPos - 1 : 0;
                        document.getElementById('wait-time-value').textContent = me.wait_time;
                    } else if (sessionStorage.getItem('smartQueueUserId')) {
                        // User was in session but not in queue anymore (served or removed)
                        // Optional: Handle this case
                    }
                }
            }
        } catch (e) { console.error("Polling error", e); }
    }

    // Poll every 5 seconds
    setInterval(pollData, 5000);

    // ── Admin Controls ─────────────────────────────────────────────
    document.getElementById('next-user-btn').addEventListener('click', () => socket.emit('next_user'));

    pauseBtn.addEventListener('click', () => {
        if (queueIsPaused) {
            socket.emit('resume_queue');
        } else {
            socket.emit('pause_queue');
        }
    });

    document.getElementById('clear-queue-btn').addEventListener('click', () => {
        if (confirm('Are you sure you want to clear the entire queue?')) {
            socket.emit('clear_queue');
        }
    });

    // ── Socket Events ──────────────────────────────────────────────
    socket.on('connect', () => {
        console.log('✅ Connected to SmartQueue server!');
        socket.emit('get_queue');
    });

    socket.on('position_updated', data => {
        if (data.user_id === currentUserId) {
            userJoinFormContainer.style.display = 'none';
            userStatusDisplay.style.display = 'flex';
            switchView('user-view');

            document.getElementById('position-value').textContent = data.position;
            document.getElementById('people-ahead-value').textContent = data.position > 0 ? data.position - 1 : 0;
            document.getElementById('wait-time-value').textContent = data.estimated_wait;

            const priorityLabels = { normal: '🟢 Normal', senior: '🟡 Senior', emergency: '🔴 Emergency' };
            const pDisplay = document.getElementById('priority-display-value');
            if (pDisplay) pDisplay.textContent = priorityLabels[data.priority] || 'Normal';

            showToast(`You joined at position #${data.position}. Est. wait: ${data.estimated_wait} min`, 'success');
        }
    });

    socket.on('join_rejected', data => {
        showToast(data.reason || 'Could not join queue.', 'error');
        sessionStorage.removeItem('smartQueueUserId');
    });

    socket.on('left_queue', data => {
        showToast(`${data.user_id} has left the queue.`, 'info');
    });

    socket.on('queue_data', data => {
        updateAdminView(data.queue);
        // Update current user's position from live queue data
        if (currentUserId && data.queue) {
            const me = data.queue.find(u => u.user_id === currentUserId || u.user_name === currentUserId);
            if (me) {
                const myPos = data.queue.indexOf(me) + 1;
                document.getElementById('position-value').textContent = myPos;
                document.getElementById('people-ahead-value').textContent = myPos > 0 ? myPos - 1 : 0;
                document.getElementById('wait-time-value').textContent = me.wait_time;
            }
        }
    });

    socket.on('now_serving', data => {
        const text = data.user_id ? `${data.user_id}` : 'None';
        const banner = document.getElementById('now-serving-banner');
        const inline = document.getElementById('serving-now-value');
        if (banner) banner.textContent = text;
        if (inline) inline.textContent = text.split(' ')[0].replace('#', '');
    });

    socket.on('you_are_next', data => {
        if (data.user_id === currentUserId) {
            const banner = document.getElementById('youre-next-banner');
            if (banner) banner.style.display = 'block';
            showToast("🎯 You're next! Head to the counter.", 'success', 8000);
        }
    });

    socket.on('stats_update', data => {
        // Helper: only show positive numbers, otherwise '--'
        const fmtWait = (v) => (v != null && v > 0) ? v : '--';

        // Header pill
        const qLen = document.getElementById('stat-queue-len');
        const avg = document.getElementById('stat-avg-wait');
        if (qLen) qLen.textContent = data.queue_length;
        if (avg) avg.textContent = fmtWait(data.avg_wait_minutes);

        // Hero stats
        const heroQ = document.getElementById('hero-queue-len');
        const heroS = document.getElementById('hero-served');
        const heroA = document.getElementById('hero-avg-wait');
        if (heroQ) heroQ.textContent = data.queue_length;
        if (heroS) heroS.textContent = data.served_today;
        if (heroA) heroA.textContent = fmtWait(data.avg_wait_minutes);

        // Admin stat cards
        const aQ = document.getElementById('admin-stat-queue');
        const aS = document.getElementById('admin-stat-served');
        const aA = document.getElementById('admin-stat-avg');
        if (aQ) aQ.textContent = data.queue_length;
        if (aS) aS.textContent = data.served_today;
        if (aA) aA.textContent = fmtWait(data.avg_wait_minutes);

        // Pause state
        queueIsPaused = data.paused;
        updatePauseUI(data.paused);
    });

    socket.on('queue_paused', () => {
        queueIsPaused = true;
        updatePauseUI(true);
        showToast('Queue has been paused.', 'warning');
    });

    socket.on('queue_resumed', () => {
        queueIsPaused = false;
        updatePauseUI(false);
        showToast('Queue has been resumed.', 'success');
    });

    socket.on('login_success', () => {
        showToast('Admin login successful!', 'success');
        switchView('admin-view');
    });
    socket.on('login_failed', () => showToast('Admin login failed. Check your credentials.', 'error'));

    // ── Pause UI Helper ────────────────────────────────────────────
    function updatePauseUI(paused) {
        const pausedBanner = document.getElementById('paused-banner');
        const statusIcon = document.getElementById('queue-status-icon');
        const statusText = document.getElementById('queue-status-text');

        if (pausedBanner) pausedBanner.style.display = paused ? 'block' : 'none';

        if (pauseBtn) {
            if (paused) {
                pauseBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> Resume Queue`;
                pauseBtn.classList.add('is-paused');
            } else {
                pauseBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Pause Queue`;
                pauseBtn.classList.remove('is-paused');
            }
        }

        if (statusIcon) statusIcon.textContent = paused ? '⏸️' : '▶️';
        if (statusText) statusText.textContent = paused ? 'Paused' : 'Active';
    }

    // ── Admin Table Renderer ───────────────────────────────────────
    const priorityLabels = {
        normal: '🟢 Normal',
        senior: '🟡 Senior',
        emergency: '🔴 Emergency'
    };

    const updateAdminView = (queue) => {
        const tableBody = document.getElementById('queue-table-body');
        const emptyMsg = document.getElementById('empty-queue-message');
        if (!tableBody) return;

        tableBody.innerHTML = '';

        if (!queue || queue.length === 0) {
            emptyMsg.style.display = 'block';
            return;
        }
        emptyMsg.style.display = 'none';

        queue.forEach((user, index) => {
            const row = document.createElement('tr');
            const joinTime = user.join_time
                ? new Date(user.join_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
                : 'N/A';
            const priority = user.priority || 'normal';
            row.innerHTML = `
                <td>${index + 1}</td>
                <td>${user.user_name || user.user_id}</td>
                <td><span class="priority-badge ${priority}">${priorityLabels[priority] || priority}</span></td>
                <td>${user.email || '--'}</td>
                <td>${joinTime}</td>
                <td>${user.wait_time ?? '--'}</td>
                <td>${user.serve_by || '--'}</td>
                <td><span class="status-badge status-waiting">Waiting</span></td>
            `;
            tableBody.appendChild(row);
        });
    };

    // ── Initial View ───────────────────────────────────────────────
    switchView('home-view');
});