/* ==========================================================================
   Flipkart Keyword Intelligence Workspace Application Controller
   Connects ONLY to Flipkart MySQL Database ('marketlens_flipkart')
   ========================================================================== */

const CONFIG = {
    API_BASE_URL: 'http://localhost:8001'
};

const flipkartState = {
    summary: null,
    products: [],
    categories: [],
    currentPage: 1,
    pageSize: 100,
    totalCount: 0,
    searchQuery: '',
    statusFilter: 'all',
    categoryFilter: 'all',
    sortOrder: 'id_asc',
    modalProduct: null,
    modalKeywords: [],
    selectedFile: null,
    detectedCount: 0,
    sessionProducts: [],
    sessionCurrentPage: 1,
    sessionPageSize: 100,
    isBatchRunning: false
};

function initFlipkartApp() {
    initFlipkartFileUploadHandlers();
    loadFlipkartData();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFlipkartApp);
} else {
    initFlipkartApp();
}

/* ==========================================================================
   1. EXCEL FILE UPLOAD & DROPZONE HANDLING FOR NEW COLLECTION
   ========================================================================== */
function initFlipkartFileUploadHandlers() {
    const fileInput = document.getElementById('fkExcelFileInput');
    const dropzone = document.getElementById('fkDropzone');

    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                handleFlipkartFileSelect(e.target.files[0]);
            }
        });
    }

    if (dropzone) {
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                handleFlipkartFileSelect(e.dataTransfer.files[0]);
            }
        });
    }
}

function handleFlipkartFileSelect(file) {
    const validExtensions = ['.xlsx', '.xls'];
    const fileName = file.name.toLowerCase();
    const isValid = validExtensions.some(ext => fileName.endsWith(ext));

    if (!isValid) {
        showToast('Invalid file format. Please select an Excel file (.xlsx or .xls).', 'error');
        return;
    }

    flipkartState.selectedFile = file;

    // Display file metadata
    document.getElementById('fkFileName').innerText = file.name;
    document.getElementById('fkFileSize').innerText = `${(file.size / 1024).toFixed(1)} KB`;
    document.getElementById('fkFileDetailsPanel').classList.remove('hidden');

    // Parse product count using SheetJS in browser for instant feedback
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const firstSheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[firstSheetName];
            const jsonRows = XLSX.utils.sheet_to_json(worksheet);

            flipkartState.detectedCount = jsonRows.length;
            document.getElementById('fkDetectedProductCount').innerText = flipkartState.detectedCount.toLocaleString();

            const startBtn = document.getElementById('fkStartCollectionBtn');
            if (startBtn) {
                startBtn.disabled = false;
            }

            const subtext = document.getElementById('fkSessionSubtext');
            if (subtext) {
                subtext.innerText = `Excel file "${file.name}" loaded (${flipkartState.detectedCount} products). Click "Start Flipkart Keyword Collection" to run collection for these products.`;
            }

            showToast(`Excel file loaded with ${flipkartState.detectedCount} products. Click "Start Flipkart Keyword Collection" to run collection.`, 'info');
        } catch (err) {
            console.error('SheetJS parse error:', err);
            document.getElementById('fkDetectedProductCount').innerText = '0';
        }
    };
    reader.readAsArrayBuffer(file);
}

/* ==========================================================================
   2. READ-ONLY INITIALIZATION FOR STORED DATABASE RECORDS
   ========================================================================== */
async function loadFlipkartData() {
    await fetchFlipkartSummary();
    await fetchFlipkartCategories();
    await fetchFlipkartProducts();
}

async function fetchFlipkartSummary() {
    try {
        const resp = await fetch(`${CONFIG.API_BASE_URL}/api/flipkart/summary`);
        if (!resp.ok) return;
        const data = await resp.json();
        flipkartState.summary = data;

        const fkTotal = document.getElementById('fkTotalProductsCount');
        if (fkTotal) fkTotal.innerText = (data.total_products || 0).toLocaleString();
        const fkComp = document.getElementById('fkCompletedProductsCount');
        if (fkComp) fkComp.innerText = (data.completed_products || 0).toLocaleString();
        const fkPend = document.getElementById('fkPendingProductsCount');
        if (fkPend) fkPend.innerText = (data.pending_products || 0).toLocaleString();
        const fkFail = document.getElementById('fkFailedProductsCount');
        if (fkFail) fkFail.innerText = (data.failed_products || 0).toLocaleString();
        const fkKw = document.getElementById('fkTotalKeywordsCount');
        if (fkKw) fkKw.innerText = (data.total_keywords || 0).toLocaleString();

        const countBadge = document.getElementById('fkHeaderCountBadge');
        if (countBadge) {
            countBadge.innerText = `${(data.completed_products || 0).toLocaleString()} Done`;
        }
    } catch (err) {
        console.error('Error fetching Flipkart summary:', err);
    }
}

async function fetchFlipkartCategories() {
    try {
        const resp = await fetch(`${CONFIG.API_BASE_URL}/api/flipkart/categories`);
        if (!resp.ok) return;
        const categories = await resp.json();
        flipkartState.categories = categories || [];

        const select = document.getElementById('fkCategoryFilter');
        if (select) {
            let html = '<option value="all">All Categories</option>';
            categories.forEach(cat => {
                html += `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`;
            });
            select.innerHTML = html;
        }
    } catch (err) {
        console.error('Error fetching Flipkart categories:', err);
    }
}

async function fetchFlipkartProducts() {
    const tableBody = document.getElementById('fkProductTableBody');
    if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 32px; color: var(--text-muted);">Loading Flipkart database records...</td></tr>`;
    }

    const skip = (flipkartState.currentPage - 1) * flipkartState.pageSize;
    const limit = flipkartState.pageSize;

    let url = `${CONFIG.API_BASE_URL}/api/flipkart/products?skip=${skip}&limit=${limit}`;
    if (flipkartState.statusFilter && flipkartState.statusFilter !== 'all') {
        url += `&status=${encodeURIComponent(flipkartState.statusFilter)}`;
    }
    if (flipkartState.categoryFilter && flipkartState.categoryFilter !== 'all') {
        url += `&category=${encodeURIComponent(flipkartState.categoryFilter)}`;
    }
    if (flipkartState.searchQuery) {
        url += `&search=${encodeURIComponent(flipkartState.searchQuery)}`;
    }
    if (flipkartState.sortOrder) {
        url += `&sort=${encodeURIComponent(flipkartState.sortOrder)}`;
    }

    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error('Failed to fetch Flipkart products');

        const totalHeader = resp.headers.get('X-Total-Count');
        if (totalHeader) {
            flipkartState.totalCount = parseInt(totalHeader, 10);
        }

        const data = await resp.json();
        flipkartState.products = data || [];

        renderFlipkartProductTable();
        renderFlipkartPagination();

    } catch (err) {
        console.error('Error loading Flipkart products:', err);
        if (tableBody) {
            tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 32px; color: #dc2626;">Failed to load Flipkart products from server.</td></tr>`;
        }
    }
}

function renderFlipkartProductTable() {
    const tableBody = document.getElementById('fkProductTableBody');
    if (!tableBody) return;

    if (!flipkartState.products || flipkartState.products.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 32px; color: var(--text-muted);">No Flipkart products found matching criteria.</td></tr>`;
        return;
    }

    let html = '';
    flipkartState.products.forEach((p, idx) => {
        const rowNum = (flipkartState.currentPage - 1) * flipkartState.pageSize + idx + 1;

        let statusBadge = '';
        const st = (p.flipkart_status || 'pending').toLowerCase();
        if (st === 'completed') {
            statusBadge = `<span class="badge badge-success">Completed</span>`;
        } else if (st === 'failed') {
            statusBadge = `<span class="badge badge-danger">Failed</span>`;
        } else if (st === 'in_progress') {
            statusBadge = `<span class="badge badge-processing">In Progress</span>`;
        } else {
            statusBadge = `<span class="badge badge-pending">Pending</span>`;
        }

        html += `
            <tr>
                <td>${rowNum}</td>
                <td><code style="font-weight: 600; color: #1d4ed8;">${escapeHtml(p.asin)}</code></td>
                <td style="font-weight: 500;">${escapeHtml(p.product_name)}</td>
                <td><span class="badge" style="background: var(--bg-secondary); color: var(--text-muted);">${escapeHtml(p.category || 'General')}</span></td>
                <td>${statusBadge}</td>
                <td style="text-align: center;">
                    <span class="badge ${p.keyword_count > 0 ? 'badge-info' : 'badge-warning'}">${p.keyword_count} Keywords</span>
                </td>
                <td style="text-align: center;">
                    <button type="button" class="btn btn-sm btn-outline" onclick="openFlipkartModal(${p.id})">
                        View Keywords
                    </button>
                </td>
            </tr>
        `;
    });

    tableBody.innerHTML = html;
}

function renderFlipkartPagination() {
    const info = document.getElementById('fkPaginationInfo');
    const buttons = document.getElementById('fkPageButtons');

    const total = flipkartState.totalCount;
    const start = total === 0 ? 0 : (flipkartState.currentPage - 1) * flipkartState.pageSize + 1;
    const end = Math.min(flipkartState.currentPage * flipkartState.pageSize, total);

    if (info) {
        info.innerText = `Showing ${start} - ${end} of ${total.toLocaleString()} Flipkart products`;
    }

    if (!buttons) return;
    const totalPages = Math.ceil(total / flipkartState.pageSize) || 1;

    let btnHtml = `
        <button type="button" class="page-btn" ${flipkartState.currentPage === 1 ? 'disabled' : ''} onclick="changeFlipkartPage(${flipkartState.currentPage - 1})">&laquo; Prev</button>
    `;

    for (let p = 1; p <= totalPages; p++) {
        if (p === 1 || p === totalPages || (p >= flipkartState.currentPage - 2 && p <= flipkartState.currentPage + 2)) {
            btnHtml += `<button type="button" class="page-btn ${p === flipkartState.currentPage ? 'active' : ''}" onclick="changeFlipkartPage(${p})">${p}</button>`;
        } else if (p === flipkartState.currentPage - 3 || p === flipkartState.currentPage + 3) {
            btnHtml += `<span style="padding: 0 4px; color: var(--text-muted);">...</span>`;
        }
    }

    btnHtml += `
        <button type="button" class="page-btn" ${flipkartState.currentPage === totalPages ? 'disabled' : ''} onclick="changeFlipkartPage(${flipkartState.currentPage + 1})">Next &raquo;</button>
    `;

    buttons.innerHTML = btnHtml;
}

function changeFlipkartPage(newPage) {
    flipkartState.currentPage = newPage;
    fetchFlipkartProducts();
}

function changeFlipkartPageSize(newSize) {
    flipkartState.pageSize = parseInt(newSize, 10);
    flipkartState.currentPage = 1;
    fetchFlipkartProducts();
}

function filterFlipkartProducts() {
    const searchInput = document.getElementById('fkSearchInput');
    const statusFilter = document.getElementById('fkStatusFilter');
    const categoryFilter = document.getElementById('fkCategoryFilter');
    const sortControl = document.getElementById('fkSortControl');

    flipkartState.searchQuery = searchInput ? searchInput.value.trim() : '';
    flipkartState.statusFilter = statusFilter ? statusFilter.value : 'all';
    flipkartState.categoryFilter = categoryFilter ? categoryFilter.value : 'all';
    flipkartState.sortOrder = sortControl ? sortControl.value : 'id_asc';

    flipkartState.currentPage = 1;
    fetchFlipkartProducts();
}

/* ==========================================================================
   3. EXPLICIT FLIPKART KEYWORD COLLECTION TRIGGER & SESSION RESULTS RENDER
   ========================================================================== */
async function startFlipkartUploadCollection() {
    if (!flipkartState.selectedFile) {
        showToast('Please select an Excel file first.', 'error');
        return;
    }

    const startBtn = document.getElementById('fkStartCollectionBtn');
    const progressSection = document.getElementById('fkProgressCardSection');
    const emptyState = document.getElementById('fkSessionEmptyState');
    const sessionTableContainer = document.getElementById('fkSessionTableContainer');
    const subtext = document.getElementById('fkSessionSubtext');

    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = `
            <svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
                <path d="M12 2a10 10 0 0 1 10 10"></path>
            </svg>
            Collecting Flipkart Keywords...
        `;
    }

    if (progressSection) progressSection.classList.remove('hidden');
    updateFlipkartProgress(25, 'Uploading Excel file and matching session products in MySQL...', 'Processing');

    const formData = new FormData();
    formData.append('file', flipkartState.selectedFile);

    try {
        updateFlipkartProgress(60, 'Processing Flipkart keywords for uploaded products...', 'Processing');
        const resp = await fetch(`${CONFIG.API_BASE_URL}/api/flipkart/match-excel`, {
            method: 'POST',
            body: formData
        });

        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || 'Flipkart session collection failed');
        }

        const res = await resp.json();
        flipkartState.sessionProducts = res.products || [];
        flipkartState.sessionCurrentPage = 1;

        updateFlipkartProgress(100, `Completed session collection of ${res.total_excel_products} uploaded products (${res.successful_products} completed, ${res.total_keywords_collected} keywords collected).`, 'Completed');

        // Update Session Results UI
        if (emptyState) emptyState.classList.add('hidden');
        if (sessionTableContainer) sessionTableContainer.classList.remove('hidden');
        if (subtext) {
            subtext.innerText = `Current Session Complete: ${res.successful_products} products completed, ${res.no_keywords_count || 0} with Keywords Not Available (${res.total_keywords_collected || 0} total keywords collected across ${res.total_excel_products} uploaded products).`;
        }

        renderFlipkartSessionTable();

        showToast(`Collection Complete: ${res.successful_products} completed, ${res.no_keywords_count || 0} Keywords Not Available across ${res.total_excel_products} uploaded products!`, 'success');
        await loadFlipkartData();

    } catch (err) {
        console.error('Flipkart UI session collection error:', err);
        showToast(err.message || 'Error executing Flipkart collection for uploaded file.', 'error');
        updateFlipkartProgress(0, 'Collection failed. Please check server logs.', 'Failed');
    } finally {
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Re-Run Flipkart Keyword Collection
            `;
        }
    }
}

function renderFlipkartSessionTable() {
    const tbody = document.getElementById('fkSessionTableBody');
    if (!tbody) return;

    if (!flipkartState.sessionProducts || flipkartState.sessionProducts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-muted);">No items in current collection session. Upload an Excel spreadsheet to begin.</td></tr>`;
        renderFlipkartSessionPagination();
        return;
    }

    const startIdx = (flipkartState.sessionCurrentPage - 1) * flipkartState.sessionPageSize;
    const endIdx = Math.min(startIdx + flipkartState.sessionPageSize, flipkartState.sessionProducts.length);
    const pageProducts = flipkartState.sessionProducts.slice(startIdx, endIdx);

    let html = '';
    pageProducts.forEach((p, idx) => {
        const rowNum = startIdx + idx + 1;
        const isNoKeywords = p.keywords_status === 'no_keywords' || p.keyword_count === 0;

        let statusBadge = '';
        let kwBadge = '';
        let actionBtn = '';

        if (isNoKeywords) {
            statusBadge = `<span class="badge badge-warning" style="background: #fef3c7; color: #92400e; border: 1px solid #fde68a;">Keywords Not Available</span>`;
            kwBadge = `<span class="badge badge-warning" style="background: #fff7ed; color: #c2410c; border: 1px solid #ffedd5;">Keywords Not Available</span>`;
            actionBtn = `<button type="button" class="btn btn-sm btn-outline" disabled style="opacity: 0.5; cursor: not-allowed;">Keywords Not Available</button>`;
        } else {
            statusBadge = `<span class="badge badge-success">Completed</span>`;
            kwBadge = `<span class="badge badge-info">${p.keyword_count} Keywords</span>`;
            actionBtn = `<button type="button" class="btn btn-sm btn-outline" onclick="openFlipkartModal(${p.id})">View Keywords</button>`;
        }

        html += `
            <tr>
                <td>${rowNum}</td>
                <td><code style="font-weight: 600; color: #1d4ed8;">${escapeHtml(p.asin || '')}</code></td>
                <td style="font-weight: 500;">${escapeHtml(p.product_name || '')}</td>
                <td><span class="badge" style="background: var(--bg-secondary); color: var(--text-muted);">${escapeHtml(p.category || 'General')}</span></td>
                <td>${statusBadge}</td>
                <td style="text-align: center;">${kwBadge}</td>
                <td style="text-align: center;">${actionBtn}</td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
    renderFlipkartSessionPagination();
}

function renderFlipkartSessionPagination() {
    const info = document.getElementById('fkSessionPaginationInfo');
    const buttons = document.getElementById('fkSessionPageButtons');

    const total = flipkartState.sessionProducts ? flipkartState.sessionProducts.length : 0;
    const start = total === 0 ? 0 : (flipkartState.sessionCurrentPage - 1) * flipkartState.sessionPageSize + 1;
    const end = Math.min(flipkartState.sessionCurrentPage * flipkartState.sessionPageSize, total);

    if (info) {
        info.innerText = `Showing ${start} - ${end} of ${total.toLocaleString()} current session products`;
    }

    if (!buttons) return;
    const totalPages = Math.ceil(total / flipkartState.sessionPageSize) || 1;

    let btnHtml = `
        <button type="button" class="page-btn" ${flipkartState.sessionCurrentPage === 1 ? 'disabled' : ''} onclick="changeFlipkartSessionPage(${flipkartState.sessionCurrentPage - 1})">&laquo; Prev</button>
    `;

    for (let p = 1; p <= totalPages; p++) {
        if (p === 1 || p === totalPages || (p >= flipkartState.sessionCurrentPage - 2 && p <= flipkartState.sessionCurrentPage + 2)) {
            btnHtml += `<button type="button" class="page-btn ${p === flipkartState.sessionCurrentPage ? 'active' : ''}" onclick="changeFlipkartSessionPage(${p})">${p}</button>`;
        } else if (p === flipkartState.sessionCurrentPage - 3 || p === flipkartState.sessionCurrentPage + 3) {
            btnHtml += `<span style="padding: 0 4px; color: var(--text-muted);">...</span>`;
        }
    }

    btnHtml += `
        <button type="button" class="page-btn" ${flipkartState.sessionCurrentPage === totalPages ? 'disabled' : ''} onclick="changeFlipkartSessionPage(${flipkartState.sessionCurrentPage + 1})">Next &raquo;</button>
    `;

    buttons.innerHTML = btnHtml;
}

function changeFlipkartSessionPage(newPage) {
    if (newPage < 1) return;
    const totalPages = Math.ceil((flipkartState.sessionProducts || []).length / flipkartState.sessionPageSize) || 1;
    if (newPage > totalPages) return;
    flipkartState.sessionCurrentPage = newPage;
    renderFlipkartSessionTable();
}

function changeFlipkartSessionPageSize(newSize) {
    flipkartState.sessionPageSize = parseInt(newSize, 10);
    flipkartState.sessionCurrentPage = 1;
    renderFlipkartSessionTable();
}

function updateFlipkartProgress(percentage, statusText, statusBadge) {
    const fill = document.getElementById('fkProgressBarFill');
    if (fill) fill.style.width = `${percentage}%`;
    const pctText = document.getElementById('fkProgressPercentageText');
    if (pctText) pctText.innerText = `${percentage}%`;
    const stText = document.getElementById('fkProgressStatusText');
    if (stText) stText.innerText = statusText;
    const stBadge = document.getElementById('fkProgressStatusBadge');
    if (stBadge) stBadge.innerText = statusBadge;
}

/* ==========================================================================
   4. MODAL & EXPORT CONTROLLERS
   ========================================================================== */
async function openFlipkartModal(productId) {
    try {
        const resp = await fetch(`${CONFIG.API_BASE_URL}/api/flipkart/products/${productId}`);
        if (!resp.ok) throw new Error('Failed to load product keyword details');

        const data = await resp.json();
        flipkartState.modalProduct = data;
        flipkartState.modalKeywords = data.keywords || [];

        document.getElementById('fkModalAsinBadge').innerText = `FSN / ASIN: ${data.asin}`;
        document.getElementById('fkModalProductName').innerText = data.product_name;
        document.getElementById('fkModalCategory').innerText = data.category || 'General';

        const statusBadge = document.getElementById('fkModalStatusBadge');
        if (statusBadge) {
            statusBadge.innerText = data.flipkart_status;
            statusBadge.className = `meta-value badge ${data.flipkart_status === 'completed' ? 'badge-success' : (data.flipkart_status === 'failed' ? 'badge-danger' : 'badge-pending')}`;
        }

        document.getElementById('fkModalKeywordCount').innerText = `${data.keyword_count} Keywords`;

        renderFlipkartModalKeywords(flipkartState.modalKeywords, data.flipkart_status);
        document.getElementById('flipkartModalBackdrop').classList.remove('hidden');

    } catch (err) {
        console.error('Error opening Flipkart modal:', err);
        showToast('Error loading Flipkart keywords for this product', 'error');
    }
}

function renderFlipkartModalKeywords(keywords, flipkartStatus) {
    const tbody = document.getElementById('fkModalTableBody');
    if (!tbody) return;

    if (flipkartStatus === 'pending') {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 24px; color: #b45309; font-weight: 500;">Product is pending Flipkart keyword collection. No Flipkart keywords collected yet.</td></tr>`;
        return;
    }

    if (!keywords || keywords.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 24px; color: var(--text-muted);">No Flipkart search suggestion keywords stored for this product.</td></tr>`;
        return;
    }

    let html = '';
    keywords.forEach((k, idx) => {
        html += `
            <tr>
                <td>${idx + 1}</td>
                <td style="font-weight: 600; color: var(--text-main);">${escapeHtml(k.keyword)}</td>
                <td><span class="badge badge-info" style="font-size: 11px;">${escapeHtml(k.source)}</span></td>
                <td style="text-align: right; color: var(--text-muted);">${(k.relevance_score || 0).toFixed(1)}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function filterFlipkartModalKeywords() {
    const q = (document.getElementById('fkModalSearchInput')?.value || '').toLowerCase().trim();
    if (!flipkartState.modalKeywords) return;

    if (!q) {
        renderFlipkartModalKeywords(flipkartState.modalKeywords);
        return;
    }

    const filtered = flipkartState.modalKeywords.filter(k => (k.keyword || '').toLowerCase().includes(q));
    renderFlipkartModalKeywords(filtered);
}

function closeFlipkartModal() {
    const modal = document.getElementById('flipkartModalBackdrop');
    if (modal) modal.classList.add('hidden');
}

function copyFlipkartModalKeywords() {
    if (!flipkartState.modalKeywords || flipkartState.modalKeywords.length === 0) {
        showToast('No Flipkart keywords to copy.', 'error');
        return;
    }

    const textList = flipkartState.modalKeywords.map(k => k.keyword).join('\n');
    navigator.clipboard.writeText(textList).then(() => {
        showToast(`Copied ${flipkartState.modalKeywords.length} Flipkart keywords to clipboard!`, 'success');
    }).catch(err => {
        console.error('Clipboard copy error:', err);
        showToast('Failed to copy to clipboard.', 'error');
    });
}

function downloadFlipkartExport(format) {
    if (!flipkartState.products || flipkartState.products.length === 0) {
        showToast('No Flipkart products to export.', 'error');
        return;
    }

    const exportRows = flipkartState.products.map(p => ({
        'Product ID': p.id,
        'FSN / ASIN': p.asin,
        'Product Name': p.product_name,
        'Category': p.category || 'General',
        'Flipkart Status': p.flipkart_status,
        'Keywords Count': p.keyword_count,
        'Marketplace': 'flipkart'
    }));

    const dateStr = new Date().toISOString().slice(0, 10);
    const filename = `flipkart_keywords_export_${dateStr}.${format === 'csv' ? 'csv' : 'xlsx'}`;

    if (format === 'csv') {
        const worksheet = XLSX.utils.json_to_sheet(exportRows);
        const csvOutput = XLSX.utils.sheet_to_csv(worksheet);
        const blob = new Blob([csvOutput], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(url);
    } else {
        const worksheet = XLSX.utils.json_to_sheet(exportRows);
        const workbook = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(workbook, worksheet, 'Flipkart Products');
        XLSX.writeFile(workbook, filename);
    }

    showToast(`Exported Flipkart dataset to ${filename}`, 'success');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(12px)';
        toast.style.transition = 'all 0.25s ease';
        setTimeout(() => toast.remove(), 250);
    }, 4000);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
