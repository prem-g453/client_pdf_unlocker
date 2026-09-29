// Client PDF Unlocker Front-End Application Logic

const state = {
    currentUser: null,
    excelFile: null,
    excelValidation: null,
    pdfFiles: [],
    currentJobId: null,
    jobStatus: null,
    sseEventSource: null,
    activeTab: 'unlocker', // 'unlocker' or 'admin'
    adminAuditPage: 1,
    tableFilter: 'all' // 'all', 'unlocked', 'already_unlocked', 'no_match', 'error'
};

// --- DOM Elements & Helpers ---
const $ = (id) => document.getElementById(id);

function showToast(message, type = 'info') {
    const container = $('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    const bgColors = {
        success: 'bg-emerald-600/90 border-emerald-500 text-white',
        error: 'bg-rose-600/90 border-rose-500 text-white',
        warning: 'bg-amber-600/90 border-amber-500 text-white',
        info: 'bg-slate-800/90 border-slate-700 text-slate-100'
    };
    
    toast.className = `flex items-center gap-3 px-4 py-3 rounded-xl border backdrop-blur-md shadow-xl transition-all duration-300 transform translate-y-2 opacity-0 ${bgColors[type] || bgColors.info}`;
    toast.innerHTML = `
        <span class="text-sm font-medium">${message}</span>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.remove('translate-y-2', 'opacity-0');
    }, 10);
    
    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// --- Auth Handling ---
async function checkAuth() {
    try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
            state.currentUser = await res.json();
            renderAuthUI();
        } else {
            state.currentUser = null;
            renderAuthUI();
        }
    } catch (err) {
        state.currentUser = null;
        renderAuthUI();
    }
}

function renderAuthUI() {
    const authOverlay = $('auth-modal');
    const userBar = $('user-bar');
    const adminNavBtn = $('nav-admin-btn');
    
    if (state.currentUser) {
        if (authOverlay) authOverlay.classList.add('hidden');
        if (userBar) {
            userBar.classList.remove('hidden');
            $('current-username').textContent = state.currentUser.username;
            $('current-role-badge').textContent = state.currentUser.role.toUpperCase();
            
            if (state.currentUser.role === 'admin') {
                $('current-role-badge').className = 'px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-400 border border-indigo-500/30';
                if (adminNavBtn) adminNavBtn.classList.remove('hidden');
            } else {
                $('current-role-badge').className = 'px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
                if (adminNavBtn) adminNavBtn.classList.add('hidden');
            }
        }
    } else {
        if (authOverlay) authOverlay.classList.remove('hidden');
        if (userBar) userBar.classList.add('hidden');
    }
}

async function handleLogin(e) {
    if (e) e.preventDefault();
    const username = $('login-username').value.trim();
    const password = $('login-password').value;
    const errorEl = $('login-error');
    errorEl.classList.add('hidden');

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await res.json();
        if (!res.ok) {
            errorEl.textContent = data.detail || 'Login failed.';
            errorEl.classList.remove('hidden');
            return;
        }

        state.currentUser = data.user;
        renderAuthUI();
        showToast(`Welcome back, ${state.currentUser.username}!`, 'success');
    } catch (err) {
        errorEl.textContent = 'Server connection error. Please try again.';
        errorEl.classList.remove('hidden');
    }
}

function quickFillLogin(role) {
    if (role === 'admin') {
        $('login-username').value = 'admin';
        $('login-password').value = 'Admin@12345';
    } else {
        $('login-username').value = 'staff';
        $('login-password').value = 'Staff@12345';
    }
    handleLogin();
}

async function handleLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    state.currentUser = null;
    renderAuthUI();
    showToast('Logged out safely.', 'info');
}

// --- Navigation Tabs ---
function switchTab(tab) {
    state.activeTab = tab;
    if (tab === 'unlocker') {
        $('unlocker-view').classList.remove('hidden');
        $('admin-view').classList.add('hidden');
        $('nav-unlocker-btn').classList.add('text-indigo-400', 'border-b-2', 'border-indigo-500');
        $('nav-unlocker-btn').classList.remove('text-slate-400');
        $('nav-admin-btn').classList.remove('text-indigo-400', 'border-b-2', 'border-indigo-500');
        $('nav-admin-btn').classList.add('text-slate-400');
    } else {
        $('unlocker-view').classList.add('hidden');
        $('admin-view').classList.remove('hidden');
        $('nav-admin-btn').classList.add('text-indigo-400', 'border-b-2', 'border-indigo-500');
        $('nav-admin-btn').classList.remove('text-slate-400');
        $('nav-unlocker-btn').classList.remove('text-indigo-400', 'border-b-2', 'border-indigo-500');
        $('nav-unlocker-btn').classList.add('text-slate-400');
        loadAdminData();
    }
}

// --- Step 1: Excel Upload & Validation ---
function initExcelDropzone() {
    const dropzone = $('excel-dropzone');
    const input = $('excel-file-input');

    dropzone.addEventListener('click', () => input.click());
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleExcelFileSelected(e.dataTransfer.files[0]);
        }
    });

    input.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleExcelFileSelected(e.target.files[0]);
        }
    });

    $('allow-non-pan').addEventListener('change', () => {
        if (state.excelFile) {
            validateExcel(state.excelFile);
        }
    });
}

async function handleExcelFileSelected(file) {
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
        showToast('Please upload an Excel spreadsheet (.xlsx or .xls)', 'error');
        return;
    }
    state.excelFile = file;
    await validateExcel(file);
}

async function validateExcel(file) {
    const formData = new FormData();
    formData.append('excel_file', file);
    formData.append('allow_non_pan', $('allow-non-pan').checked);

    $('excel-loading').classList.remove('hidden');
    $('excel-preview-box').classList.add('hidden');
    $('excel-error-box').classList.add('hidden');

    try {
        const res = await fetch('/api/unlock/validate-excel', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        $('excel-loading').classList.add('hidden');

        if (!res.ok) {
            $('excel-error-msg').textContent = data.detail || 'Could not validate Excel file.';
            $('excel-error-box').classList.remove('hidden');
            state.excelValidation = null;
            updateUnlockButtonState();
            return;
        }

        state.excelValidation = data;
        renderExcelPreview(file, data);
        updateUnlockButtonState();
    } catch (err) {
        $('excel-loading').classList.add('hidden');
        $('excel-error-msg').textContent = 'Error connecting to validation service.';
        $('excel-error-box').classList.remove('hidden');
        updateUnlockButtonState();
    }
}

function renderExcelPreview(file, data) {
    $('excel-filename-display').textContent = file.name;
    $('excel-filesize-display').textContent = formatBytes(file.size);
    $('excel-valid-count').textContent = `${data.valid_count} valid clients`;
    
    // Warnings count
    const warnBadge = $('excel-warn-badge');
    if (data.warning_count > 0) {
        warnBadge.textContent = `${data.warning_count} warnings / duplicates`;
        warnBadge.className = 'px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30';
        warnBadge.classList.remove('hidden');
        renderExcelWarnings(data.warnings);
        $('excel-warnings-drawer').classList.remove('hidden');
    } else {
        warnBadge.classList.add('hidden');
        $('excel-warnings-drawer').classList.add('hidden');
    }

    $('excel-preview-box').classList.remove('hidden');
    $('step-1-card').classList.add('completed');
    $('step-1-card').classList.remove('active');
    $('step-2-card').classList.add('active');
}

function renderExcelWarnings(warnings) {
    const list = $('excel-warnings-list');
    list.innerHTML = '';
    warnings.forEach(w => {
        const item = document.createElement('div');
        item.className = 'flex items-center justify-between text-xs py-1.5 px-2 bg-slate-900/60 rounded border border-white/5';
        item.innerHTML = `
            <div class="flex items-center gap-2">
                <span class="text-slate-400 font-mono">Row ${w.row_number}:</span>
                <span class="font-medium text-slate-200">${w.client_name || '(Blank Name)'}</span>
                <span class="text-amber-400/80">(${w.reason})</span>
            </div>
            <span class="px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold ${w.action === 'Skipped' ? 'bg-rose-500/20 text-rose-300' : 'bg-indigo-500/20 text-indigo-300'}">${w.action}</span>
        `;
        list.appendChild(item);
    });
}

function removeExcelFile() {
    state.excelFile = null;
    state.excelValidation = null;
    $('excel-file-input').value = '';
    $('excel-preview-box').classList.add('hidden');
    $('excel-error-box').classList.add('hidden');
    $('step-1-card').classList.remove('completed');
    $('step-1-card').classList.add('active');
    updateUnlockButtonState();
}

// --- Step 2: Multi-PDF Upload ---
function initPdfDropzone() {
    const dropzone = $('pdf-dropzone');
    const input = $('pdf-file-input');

    dropzone.addEventListener('click', () => input.click());
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handlePdfFilesSelected(Array.from(e.dataTransfer.files));
        }
    });

    input.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handlePdfFilesSelected(Array.from(e.target.files));
        }
    });
}

function handlePdfFilesSelected(newFiles) {
    const validPdfs = newFiles.filter(f => f.name.match(/\.pdf$/i));
    if (validPdfs.length < newFiles.length) {
        showToast('Non-PDF files were ignored.', 'warning');
    }

    if (state.pdfFiles.length + validPdfs.length > 500) {
        showToast('Maximum 500 PDFs allowed per batch.', 'error');
        return;
    }

    // Check 50MB limit per file
    const oversized = validPdfs.filter(f => f.size > 50 * 1024 * 1024);
    if (oversized.length > 0) {
        showToast(`${oversized.length} file(s) exceed 50 MB limit and were skipped.`, 'error');
    }

    const eligible = validPdfs.filter(f => f.size <= 50 * 1024 * 1024);
    state.pdfFiles = [...state.pdfFiles, ...eligible];

    renderPdfList();
    updateUnlockButtonState();
}

function renderPdfList() {
    const container = $('pdf-list-container');
    const badge = $('pdf-count-badge');
    const totalSizeEl = $('pdf-total-size');

    if (state.pdfFiles.length === 0) {
        container.classList.add('hidden');
        badge.classList.add('hidden');
        $('step-2-card').classList.remove('completed');
        return;
    }

    badge.textContent = `${state.pdfFiles.length} file(s)`;
    badge.classList.remove('hidden');

    const totalSize = state.pdfFiles.reduce((acc, f) => acc + f.size, 0);
    totalSizeEl.textContent = `Total size: ${formatBytes(totalSize)}`;

    const list = $('pdf-files-items');
    list.innerHTML = '';

    state.pdfFiles.forEach((file, idx) => {
        const item = document.createElement('div');
        item.className = 'flex items-center justify-between p-2 rounded-lg bg-slate-900/50 border border-white/5 text-xs hover:border-white/10 transition-colors';
        item.innerHTML = `
            <div class="flex items-center gap-2 truncate pr-2">
                <svg class="w-4 h-4 text-rose-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
                </svg>
                <span class="text-slate-200 truncate font-medium">${file.name}</span>
                <span class="text-slate-500 flex-shrink-0">${formatBytes(file.size)}</span>
            </div>
            <button type="button" onclick="removePdfFile(${idx})" class="p-1 text-slate-500 hover:text-rose-400 transition-colors">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        `;
        list.appendChild(item);
    });

    container.classList.remove('hidden');
    $('step-2-card').classList.add('completed');
}

function removePdfFile(idx) {
    state.pdfFiles.splice(idx, 1);
    renderPdfList();
    updateUnlockButtonState();
}

function clearAllPdfs() {
    state.pdfFiles = [];
    $('pdf-file-input').value = '';
    renderPdfList();
    updateUnlockButtonState();
}

// --- Step 3: Job Submission & Unlock Execution ---
function updateUnlockButtonState() {
    const btn = $('btn-start-unlock');
    const isValid = state.excelValidation && state.excelValidation.valid_count > 0 && state.pdfFiles.length > 0;
    btn.disabled = !isValid;
    if (isValid) {
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
        btn.classList.add('hover:shadow-indigo-500/25', 'hover:scale-[1.01]');
        $('step-3-card').classList.add('active');
    } else {
        btn.classList.add('opacity-50', 'cursor-not-allowed');
        btn.classList.remove('hover:shadow-indigo-500/25', 'hover:scale-[1.01]');
        $('step-3-card').classList.remove('active');
    }
}

async function startUnlockJob() {
    if (!state.excelFile || state.pdfFiles.length === 0) return;

    const btn = $('btn-start-unlock');
    btn.disabled = true;
    $('btn-unlock-spinner').classList.remove('hidden');
    $('btn-unlock-text').textContent = 'Uploading & Initializing...';

    const formData = new FormData();
    formData.append('excel_file', state.excelFile);
    formData.append('allow_non_pan', $('allow-non-pan').checked);
    state.pdfFiles.forEach(file => {
        formData.append('pdf_files', file);
    });

    try {
        const res = await fetch('/api/unlock/start', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Could not start unlock job.', 'error');
            resetUnlockBtn();
            return;
        }

        state.currentJobId = data.job_id;
        showToast('Job started! Processing PDFs in parallel...', 'info');
        
        // Hide upload steps, show live progress view
        $('workflow-section').classList.add('hidden');
        $('progress-section').classList.remove('hidden');
        
        // Connect to SSE stream
        connectJobSSE(data.job_id);

    } catch (err) {
        showToast('Network error while starting job.', 'error');
        resetUnlockBtn();
    }
}

function resetUnlockBtn() {
    const btn = $('btn-start-unlock');
    btn.disabled = false;
    $('btn-unlock-spinner').classList.add('hidden');
    $('btn-unlock-text').textContent = 'Start Decryption Process';
}

// --- SSE Real-time Streaming ---
function connectJobSSE(jobId) {
    if (state.sseEventSource) {
        state.sseEventSource.close();
    }

    const eventSource = new EventSource(`/api/unlock/jobs/${jobId}/progress`);
    state.sseEventSource = eventSource;

    eventSource.addEventListener('status', (e) => {
        const data = JSON.parse(e.data);
        updateProgressDisplay(data);
    });

    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        handleSingleFileProgress(data);
    });

    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        handleJobCompleted(data);
        eventSource.close();
    });

    eventSource.onerror = () => {
        // Fallback to polling if SSE disconnected
        eventSource.close();
        pollJobStatus(jobId);
    };
}

async function pollJobStatus(jobId) {
    try {
        const res = await fetch(`/api/unlock/jobs/${jobId}/status`);
        if (res.ok) {
            const data = await res.json();
            updateProgressDisplay(data);
            if (!data.is_completed) {
                setTimeout(() => pollJobStatus(jobId), 1000);
            } else {
                handleJobCompleted(data);
            }
        }
    } catch (e) {}
}

function updateProgressDisplay(jobData) {
    state.jobStatus = jobData;
    
    // Update progress bar
    const percent = Math.min(100, Math.max(0, jobData.percent_complete || 0));
    $('progress-bar-fill').style.width = `${percent}%`;
    $('progress-percent-label').textContent = `${Math.round(percent)}%`;
    $('progress-counts-label').textContent = `${jobData.processed_files} / ${jobData.total_files} files processed`;

    // Counter cards
    $('count-unlocked').textContent = jobData.unlocked_count;
    $('count-already').textContent = jobData.already_unlocked_count;
    $('count-no-match').textContent = jobData.no_match_count;
    $('count-errors').textContent = jobData.error_count;

    renderResultsTable(jobData.results);
}

function handleSingleFileProgress(fileData) {
    // Update live counters
    $('count-unlocked').textContent = fileData.unlocked_count;
    $('count-already').textContent = fileData.already_unlocked_count;
    $('count-no-match').textContent = fileData.no_match_count;
    $('count-errors').textContent = fileData.error_count;

    const percent = Math.min(100, Math.max(0, fileData.percent_complete || 0));
    $('progress-bar-fill').style.width = `${percent}%`;
    $('progress-percent-label').textContent = `${Math.round(percent)}%`;
    $('progress-counts-label').textContent = `${fileData.processed_files} / ${fileData.total_files} files processed`;

    // Append / update row in table
    addOrUpdateTableRow(fileData);
}

function handleJobCompleted(jobData) {
    state.jobStatus = jobData;
    updateProgressDisplay(jobData);

    $('progress-spinner-icon').classList.add('hidden');
    $('progress-complete-icon').classList.remove('hidden');
    $('progress-status-heading').textContent = 'Processing Completed';

    // Summary banner
    const summaryCard = $('summary-banner');
    const summaryText = $('summary-text');
    const successCount = jobData.unlocked_count + jobData.already_unlocked_count;
    const failedCount = jobData.no_match_count + jobData.error_count;

    if (failedCount === 0) {
        summaryCard.className = 'p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 mb-6 flex items-center justify-between';
        summaryText.innerHTML = `<span class="font-bold text-emerald-400">Success!</span> All ${jobData.total_files} file(s) unlocked and decrypted.`;
    } else {
        summaryCard.className = 'p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 mb-6 flex items-center justify-between';
        summaryText.innerHTML = `
            <div>
                <span class="font-bold text-amber-400">${successCount} unlocked, ${failedCount} failed</span>
                <p class="text-xs text-slate-400 mt-0.5">Hint: For failed files, check if the client name is spelled differently or missing from the Excel sheet.</p>
            </div>
        `;
    }
    summaryCard.classList.remove('hidden');

    // Enable download action buttons
    $('actions-bar').classList.remove('hidden');
    $('btn-download-zip').onclick = () => downloadZip();
    $('btn-download-csv').onclick = () => downloadCsv();
}

// --- Results Table Rendering ---
function renderResultsTable(results) {
    const tbody = $('results-tbody');
    tbody.innerHTML = '';
    
    if (!results || results.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-slate-500">Processing files...</td></tr>`;
        return;
    }

    const filtered = filterResults(results);
    filtered.forEach(r => {
        tbody.appendChild(createTableRowElement(r));
    });
}

function filterResults(results) {
    if (state.tableFilter === 'all') return results;
    if (state.tableFilter === 'unlocked') return results.filter(r => r.status === 'Unlocked');
    if (state.tableFilter === 'already_unlocked') return results.filter(r => r.status === 'Already unlocked');
    if (state.tableFilter === 'no_match') return results.filter(r => r.status === 'No matching password');
    if (state.tableFilter === 'error') return results.filter(r => r.status === 'Error');
    return results;
}

function setTableFilter(filter) {
    state.tableFilter = filter;
    
    // Update button styling
    ['all', 'unlocked', 'already_unlocked', 'no_match', 'error'].forEach(f => {
        const btn = $(`filter-${f}`);
        if (btn) {
            if (f === filter) {
                btn.className = 'px-3 py-1 text-xs font-semibold rounded-lg bg-indigo-600 text-white shadow-sm';
            } else {
                btn.className = 'px-3 py-1 text-xs font-semibold rounded-lg bg-slate-800/80 text-slate-400 hover:text-slate-200 border border-white/5';
            }
        }
    });

    if (state.jobStatus) {
        renderResultsTable(state.jobStatus.results);
    }
}

function addOrUpdateTableRow(r) {
    const tbody = $('results-tbody');
    // Check if placeholder row exists
    if (tbody.children.length === 1 && tbody.children[0].innerText.includes('Processing files')) {
        tbody.innerHTML = '';
    }

    let existingRow = document.getElementById(`row-${r.file_id}`);
    if (existingRow) {
        existingRow.replaceWith(createTableRowElement(r));
    } else {
        tbody.appendChild(createTableRowElement(r));
    }
}

function createTableRowElement(r) {
    const tr = document.createElement('tr');
    tr.id = `row-${r.file_id}`;
    tr.className = 'border-b border-white/5 hover:bg-slate-800/30 transition-colors';

    let statusBadge = '';
    if (r.status === 'Unlocked') {
        statusBadge = '<span class="badge-unlocked px-2.5 py-1 rounded-full text-xs font-semibold">Unlocked</span>';
    } else if (r.status === 'Already unlocked') {
        statusBadge = '<span class="badge-already px-2.5 py-1 rounded-full text-xs font-semibold">Already Unlocked</span>';
    } else if (r.status === 'No matching password') {
        statusBadge = '<span class="badge-no-match px-2.5 py-1 rounded-full text-xs font-semibold">No Matching Password</span>';
    } else {
        statusBadge = '<span class="badge-error px-2.5 py-1 rounded-full text-xs font-semibold">Error</span>';
    }

    let actionBtn = '';
    if (r.download_url) {
        actionBtn = `
            <a href="${r.download_url}" target="_blank" download class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                Download
            </a>
        `;
    } else {
        actionBtn = `<span class="text-xs text-slate-600">—</span>`;
    }

    tr.innerHTML = `
        <td class="py-3 px-4 font-mono text-xs text-slate-300">${r.original_filename}</td>
        <td class="py-3 px-4 font-mono text-xs text-indigo-300">${r.output_filename || '<span class="text-slate-600">—</span>'}</td>
        <td class="py-3 px-4">${statusBadge}</td>
        <td class="py-3 px-4 text-xs font-medium text-slate-300">
            ${r.matched_client ? `<span class="text-emerald-300">${r.matched_client}</span>` : (r.error_message ? `<span class="text-rose-400/90">${r.error_message}</span>` : '<span class="text-slate-600">N/A</span>')}
        </td>
        <td class="py-3 px-4 text-right">${actionBtn}</td>
    `;
    return tr;
}

// --- Downloads & Reset ---
function downloadZip() {
    if (!state.currentJobId) return;
    window.location.href = `/api/unlock/jobs/${state.currentJobId}/download-all`;
    showToast('Preparing ZIP download. Files will be cleaned up.', 'info');
}

function downloadCsv() {
    if (!state.currentJobId) return;
    window.location.href = `/api/unlock/jobs/${state.currentJobId}/report.csv`;
}

function startNewJob() {
    if (state.sseEventSource) {
        state.sseEventSource.close();
    }
    state.excelFile = null;
    state.excelValidation = null;
    state.pdfFiles = [];
    state.currentJobId = null;
    state.jobStatus = null;

    $('excel-file-input').value = '';
    $('pdf-file-input').value = '';
    
    $('excel-preview-box').classList.add('hidden');
    $('excel-warnings-drawer').classList.add('hidden');
    $('pdf-list-container').classList.add('hidden');
    $('summary-banner').classList.add('hidden');
    $('actions-bar').classList.add('hidden');
    $('results-tbody').innerHTML = '';

    $('step-1-card').className = 'step-card glass-panel rounded-2xl p-6 relative active';
    $('step-2-card').className = 'step-card glass-panel rounded-2xl p-6 relative';
    $('step-3-card').className = 'step-card glass-panel rounded-2xl p-6 relative';

    $('progress-section').classList.add('hidden');
    $('workflow-section').classList.remove('hidden');

    resetUnlockBtn();
    updateUnlockButtonState();
}

// --- Admin Panel Operations ---
async function loadAdminData() {
    await Promise.all([loadAdminUsers(), loadAuditLogs(1)]);
}

async function loadAdminUsers() {
    const list = $('admin-users-list');
    list.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-slate-500">Loading users...</td></tr>';

    try {
        const res = await fetch('/api/admin/users');
        if (!res.ok) throw new Error();
        const users = await res.json();
        
        list.innerHTML = '';
        users.forEach(u => {
            const tr = document.createElement('tr');
            tr.className = 'border-b border-white/5 hover:bg-slate-800/30';
            const isSelf = state.currentUser && state.currentUser.id === u.id;
            
            tr.innerHTML = `
                <td class="py-3 px-4 text-xs font-mono text-slate-400">#${u.id}</td>
                <td class="py-3 px-4 text-sm font-semibold text-slate-200">${u.username}</td>
                <td class="py-3 px-4">
                    <span class="px-2 py-0.5 rounded text-xs font-semibold ${u.role === 'admin' ? 'bg-indigo-500/20 text-indigo-400' : 'bg-emerald-500/20 text-emerald-400'}">${u.role.toUpperCase()}</span>
                </td>
                <td class="py-3 px-4">
                    <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium ${u.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}">
                        <span class="w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
                        ${u.is_active ? 'Active' : 'Disabled'}
                    </span>
                </td>
                <td class="py-3 px-4 text-right">
                    ${!isSelf ? `
                        <button onclick="toggleUserStatus(${u.id}, ${!u.is_active})" class="text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors">
                            ${u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                    ` : '<span class="text-xs text-slate-500">(Current)</span>'}
                </td>
            `;
            list.appendChild(tr);
        });
    } catch (e) {
        list.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-rose-400">Failed to load users.</td></tr>';
    }
}

async function handleCreateUser(e) {
    e.preventDefault();
    const username = $('new-user-name').value.trim();
    const password = $('new-user-pass').value;
    const role = $('new-user-role').value;

    try {
        const res = await fetch('/api/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role })
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Could not create user.', 'error');
            return;
        }

        showToast(`User ${username} created successfully!`, 'success');
        $('new-user-form').reset();
        loadAdminUsers();
    } catch (e) {
        showToast('Error creating user.', 'error');
    }
}

async function toggleUserStatus(userId, newStatus) {
    try {
        const res = await fetch(`/api/admin/users/${userId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: newStatus })
        });
        if (res.ok) {
            showToast('User status updated.', 'success');
            loadAdminUsers();
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to update user status.', 'error');
        }
    } catch (e) {
        showToast('Network error.', 'error');
    }
}

async function loadAuditLogs(page = 1) {
    state.adminAuditPage = page;
    const list = $('admin-audit-list');
    list.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-slate-500">Loading audit log...</td></tr>';
    
    const searchUser = $('audit-search-user').value.trim();
    const url = `/api/admin/audit-logs?page=${page}&page_size=10${searchUser ? `&username=${encodeURIComponent(searchUser)}` : ''}`;

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error();
        const data = await res.json();
        
        list.innerHTML = '';
        if (data.items.length === 0) {
            list.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-slate-500">No audit records found.</td></tr>';
            $('audit-page-indicator').textContent = 'Page 1 of 1';
            return;
        }

        data.items.forEach(log => {
            const tr = document.createElement('tr');
            tr.className = 'border-b border-white/5 hover:bg-slate-800/30 text-xs';
            const dt = new Date(log.timestamp).toLocaleString();
            
            tr.innerHTML = `
                <td class="py-3 px-4 font-mono text-slate-400">${dt}</td>
                <td class="py-3 px-4 font-medium text-slate-200">${log.username}</td>
                <td class="py-3 px-4 font-mono text-indigo-300">${log.job_id.substring(0, 8)}</td>
                <td class="py-3 px-4 font-semibold text-slate-300">${log.total_files}</td>
                <td class="py-3 px-4">
                    <span class="text-emerald-400 font-semibold">${log.unlocked_count + log.already_unlocked_count}</span>
                    <span class="text-slate-600">/</span>
                    <span class="text-rose-400 font-semibold">${log.no_match_count + log.error_count}</span>
                </td>
                <td class="py-3 px-4 font-mono text-slate-400">${log.duration_seconds}s</td>
            `;
            list.appendChild(tr);
        });

        const totalPages = Math.ceil(data.total / 10) || 1;
        $('audit-page-indicator').textContent = `Page ${page} of ${totalPages} (${data.total} total)`;
        $('audit-prev-btn').disabled = page <= 1;
        $('audit-next-btn').disabled = page >= totalPages;

    } catch (e) {
        list.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-rose-400">Failed to load audit logs.</td></tr>';
    }
}

function exportAuditCsv() {
    window.location.href = '/api/admin/audit-logs/export';
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    initExcelDropzone();
    initPdfDropzone();

    $('login-form').addEventListener('submit', handleLogin);
    $('new-user-form').addEventListener('submit', handleCreateUser);
    $('btn-start-unlock').addEventListener('click', startUnlockJob);
    $('audit-search-user').addEventListener('input', () => loadAuditLogs(1));
});
