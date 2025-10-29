// static/scripts.js (FINAL VERSION - WITH SERVE BY COLUMN)

document.addEventListener('DOMContentLoaded', () => {

    const socket = io();
    let currentUserId = sessionStorage.getItem('smartQueueUserId');
    const views = document.querySelectorAll('.view-card');
    const navLinks = document.querySelectorAll('.nav-link');
    const joinForm = document.getElementById('join-form');
    const adminLoginForm = document.getElementById('admin-login-form');
    const userStatusDisplay = document.getElementById('user-status-display');
    const userJoinFormContainer = document.getElementById('user-join-form-container');

    const switchView = (viewId) => {
        views.forEach(view => view.classList.remove('active'));
        const activeView = document.getElementById(viewId);
        if (activeView) activeView.classList.add('active');
        navLinks.forEach(link => link.classList.toggle('active', link.dataset.view === viewId));
    };

    navLinks.forEach(link => link.addEventListener('click', (e) => {
        e.preventDefault();
        switchView(e.target.dataset.view);
    }));

    document.getElementById('show-user-view-btn').addEventListener('click', () => switchView('user-view'));
    document.getElementById('show-admin-login-btn').addEventListener('click', () => switchView('admin-login-view'));
    document.getElementById('leave-queue-btn').addEventListener('click', () => {
        sessionStorage.removeItem('smartQueueUserId');
        window.location.reload();
    });
    document.getElementById('add-another-user-btn').addEventListener('click', () => {
        userStatusDisplay.style.display = 'none';
        joinForm.reset();
        userJoinFormContainer.style.display = 'block';
        document.getElementById('user-id').focus();
    });

    joinForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const userIdInput = document.getElementById('user-id').value.trim();
        const userEmailInput = document.getElementById('gmail').value.trim();
        if (userIdInput && userEmailInput) {
            currentUserId = userIdInput; 
            sessionStorage.setItem('smartQueueUserId', currentUserId);
            socket.emit('join_queue', { user_id: userIdInput, email: userEmailInput });
        }
    });

    adminLoginForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const adminId = document.getElementById('admin-id').value;
        const password = document.getElementById('admin-password').value;
        socket.emit('admin_login', { user_id: adminId, password: password });
    });

    document.getElementById('next-user-btn').addEventListener('click', () => socket.emit('next_user'));
    document.getElementById('clear-queue-btn').addEventListener('click', () => {
        if (confirm('Are you sure you want to clear the entire queue?')) {
            socket.emit('clear_queue');
        }
    });

    socket.on('connect', () => {
        console.log('Connected to SmartQueue server!');
        socket.emit('get_queue');
    });

    socket.on('position_updated', (data) => {
        if (data.user_id === currentUserId) {
            userJoinFormContainer.style.display = 'none';
            userStatusDisplay.style.display = 'block';
            switchView('user-view'); 
            document.getElementById('position-value').textContent = data.position;
            document.getElementById('people-ahead-value').textContent = data.position > 0 ? data.position - 1 : 0;
            document.getElementById('wait-time-value').textContent = data.estimated_wait;
        }
    });

    socket.on('queue_data', (data) => {
        updateAdminView(data.queue);
    });
    
    socket.on('now_serving', (data) => {
        const nowServingText = data.user_id ? `${data.user_id}` : 'None';
        document.getElementById('now-serving-banner').textContent = nowServingText;
        document.getElementById('serving-now-value').textContent = nowServingText.split(' ')[0].replace('#','');
    });

    socket.on('login_success', () => switchView('admin-view'));
    socket.on('login_failed', () => alert('Admin login failed. Please check your credentials.'));

    // --- UI UPDATE FUNCTION (UPDATED) ---
    const updateAdminView = (queue) => {
        const tableBody = document.getElementById('queue-table-body');
        const emptyMsg = document.getElementById('empty-queue-message');
        
        tableBody.innerHTML = ''; 
        
        if (!queue || queue.length === 0) {
            emptyMsg.style.display = 'block';
        } else {
            emptyMsg.style.display = 'none';
            queue.forEach((user, index) => {
                const row = document.createElement('tr');
                
                const joinTime = user.join_time 
                    ? new Date(user.join_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) 
                    : 'N/A';
                
                const waitTime = user.wait_time !== undefined ? user.wait_time : '--';
                // THIS IS THE NEW DATA
                const serveBy = user.serve_by || '--'; 

                // THE CHANGE IS HERE
                row.innerHTML = `
                    <td>${index + 1}</td>
                    <td>${user.user_name || user.user_id}</td>
                    <td>${user.email}</td>
                    <td>${joinTime}</td>
                    <td>${waitTime}</td> 
                    <td>${serveBy}</td>
                    <td><span class="status-badge status-waiting">Waiting</span></td>
                `;
                tableBody.appendChild(row);
            });
        }
    };
    
    switchView('home-view');
});