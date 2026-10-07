/* ==========================================================================
   Keyword Database UI Application Logic
   Excel Upload → MySQL Data Matching → Details Display & Download
   ========================================================================== */

const CONFIG = {
    API_BASE_URL: 'http://localhost:8001',
    ENDPOINTS: {
        MATCH_EXCEL: '/api/products/match-excel',
        GET_PRODUCTS: '/api/products',
        GET_KEYWORDS: '/api/keywords',
        GET_COMPETITORS: '/api/competitors/products'
    }
};

const state = {
    selectedFile: null,
    matchedData: null,
    loadedProducts: [],
    filteredProducts: [],
    currentPage: 1,
    currentLimit: 100,
    currentSkip: 0,
    totalProductsCount: 0,
    currentModalAsin: null,
    currentModalTab: 'keywords',
    recentDownloads: []
};

function initApp() {
    initFileUploadHandlers();
    loadRecentDownloads();
    navigateToMarketplace('home');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

/* ==========================================================================
   1. EXCEL FILE UPLOAD & PICKER HANDLING
   ========================================================================== */
function initFileUploadHandlers() {
    const fileInput = document.getElementById('excelFileInput');
    const dropzone = document.getElementById('dropzone');

    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                handleFileSelect(e.target.files[0]);
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
                handleFileSelect(e.dataTransfer.files[0]);
            }
        });
    }
}

function handleFileSelect(file) {
    const validExtensions = ['.xlsx', '.xls'];
    const fileName = file.name.toLowerCase();
    const isValid = validExtensions.some(ext => fileName.endsWith(ext));

    if (!isValid) {
        showToast('Invalid file format. Please select an Excel file (.xlsx or .xls).', 'error');
        return;
    }

    state.selectedFile = file;

    // Display file metadata
    document.getElementById('fileName').innerText = file.name;
    document.getElementById('fileSize').innerText = `${(file.size / 1024).toFixed(1)} KB`;
    document.getElementById('fileDetailsPanel').classList.remove('hidden');

    // Parse product count using SheetJS in browser for instant feedback
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const firstSheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[firstSheetName];
            const jsonRows = XLSX.utils.sheet_to_json(worksheet);

            const detectedCount = jsonRows.length;
            document.getElementById('detectedProductCount').innerText = detectedCount.toLocaleString();

            // Enable start button
            const startBtn = document.getElementById('startCollectionBtn');
            if (startBtn) {
                startBtn.disabled = false;
            }
        } catch (err) {
            console.error('SheetJS parse error:', err);
            document.getElementById('detectedProductCount').innerText = '0';
        }
    };
    reader.readAsArrayBuffer(file);
}

/* ==========================================================================
   2. MATCH EXCEL WITH MYSQL & FETCH EXISTING DATA
   ========================================================================== */
async function startKeywordCollection() {
    if (!state.selectedFile) {
        showToast('Please choose an Excel file first.', 'error');
        return;
    }

    const startBtn = document.getElementById('startCollectionBtn');
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = `
            <svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
                <path d="M12 2a10 10 0 0 1 10 10"></path>
            </svg>
            Matching MySQL Database...
        `;
    }

    // Show Progress Section
    const progressSection = document.getElementById('progressCardSection');
    if (progressSection) progressSection.classList.remove('hidden');
    updateProgressBar(20, 'Uploading Excel & querying MySQL database...', 'Matching');

    const formData = new FormData();
    formData.append('file', state.selectedFile);

    try {
        updateProgressBar(50, 'Matching products, keywords, and competitor records in MySQL...', 'Matching');
        const response = await fetch(`${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.MATCH_EXCEL}`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || 'Failed to match Excel file with database');
        }

        const data = await response.json();
        state.matchedData = data;

        // Combine matched and unmatched products
        const matchedList = (data.matched_products || []).map(p => ({ ...p, matched_status: 'matched' }));
        const unmatchedList = (data.unmatched_products || []).map(p => ({
            ...p,
            matched_status: 'unmatched',
            keyword_count: 0,
            competitor_count: 0,
            keywords: [],
            competitor_products: [],
            competitor_keywords: []
        }));

        state.loadedProducts = [...matchedList, ...unmatchedList];
        state.totalProductsCount = state.loadedProducts.length;

        updateProgressBar(100, `Matched ${data.matched_count} of ${data.total_excel_products} products with MySQL database!`, 'Completed');

        // Populate Category Filter dropdown options
        populateCategoryOptions(state.loadedProducts);

        // Update Dashboard Summary Cards
        updateSummaryCards(data);

        // Unhide Dashboard Results & Download History Sections
        document.getElementById('summaryCardsSection').classList.remove('hidden');
        document.getElementById('tableCardSection').classList.remove('hidden');
        document.getElementById('downloadsCardSection').classList.remove('hidden');

        // Render Product Results Table
        filterProducts();

        showToast(`Successfully matched ${data.matched_count} products with MySQL database!`, 'success');

    } catch (err) {
        console.error('Match Excel error:', err);
        showToast(err.message || 'Error communicating with MySQL backend API.', 'error');
        updateProgressBar(0, 'Matching failed. Please verify FastAPI backend is running.', 'Failed');
    } finally {
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Re-Run Excel Match
            `;
        }
    }
}

function updateProgressBar(percentage, statusText, statusBadge) {
    const fill = document.getElementById('progressBarFill');
    if (fill) fill.style.width = `${percentage}%`;
    const pctText = document.getElementById('progressPercentageText');
    if (pctText) pctText.innerText = `${percentage}%`;
    const stText = document.getElementById('progressStatusText');
    if (stText) stText.innerText = statusText;
    const stBadge = document.getElementById('progressStatusBadge');
    if (stBadge) stBadge.innerText = statusBadge;
}

function updateSummaryCards(data) {
    const totalMatched = data.matched_count || 0;
    const totalUnmatched = data.unmatched_count || 0;
    const totalExcel = data.total_excel_products || (totalMatched + totalUnmatched);

    let totalKeywords = 0;
    let totalCompetitors = 0;

    (data.matched_products || []).forEach(p => {
        totalKeywords += (p.keywords || []).length;
        totalCompetitors += (p.competitor_products || []).length;
    });

    const avgKeywords = totalMatched > 0 ? (totalKeywords / totalMatched).toFixed(1) : '0';

    document.getElementById('cardTotalProducts').innerText = totalExcel.toLocaleString();
    document.getElementById('cardProductsWithKeywords').innerText = totalMatched.toLocaleString();
    document.getElementById('cardTotalKeywords').innerText = totalKeywords.toLocaleString();
    document.getElementById('cardProductsWithoutKeywords').innerText = totalUnmatched.toLocaleString();

    document.getElementById('cardMatchedSubtext').innerText = `${totalMatched} Matched / ${totalExcel} Excel Products`;
    document.getElementById('cardCompletionRate').innerText = `${totalExcel > 0 ? ((totalMatched / totalExcel) * 100).toFixed(0) : 0}% Database Coverage`;
    document.getElementById('cardAvgKeywords').innerText = `Avg ${avgKeywords} Keywords/Product`;
    document.getElementById('cardUnmatchedSubtext').innerText = `${totalUnmatched} Products Not in MySQL`;
}

function populateCategoryOptions(products) {
    const select = document.getElementById('categoryFilter');
    if (!select) return;

    const categories = new Set();
    products.forEach(p => {
        if (p.category) categories.add(p.category);
    });

    select.innerHTML = '<option value="all">All Categories</option>';
    Array.from(categories).sort().forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.innerText = cat;
        select.appendChild(opt);
    });
}

/* ==========================================================================
   3. TABLE FILTERING, SORTING & PAGINATION
   ========================================================================== */
function filterProducts() {
    const searchVal = document.getElementById('searchInput').value.toLowerCase().trim();
    const statusVal = document.getElementById('statusFilter').value;
    const catVal = document.getElementById('categoryFilter').value;
    const sortVal = document.getElementById('sortControl').value;

    state.filteredProducts = state.loadedProducts.filter(p => {
        const matchesSearch = !searchVal ||
            (p.asin && p.asin.toLowerCase().includes(searchVal)) ||
            (p.product_name && p.product_name.toLowerCase().includes(searchVal));

        const matchesStatus = statusVal === 'all' ||
            (statusVal === 'matched' && p.matched) ||
            (statusVal === 'unmatched' && !p.matched);

        const matchesCat = catVal === 'all' || p.category === catVal;

        return matchesSearch && matchesStatus && matchesCat;
    });

    // Apply Sorting
    if (sortVal === 'kw_desc') {
        state.filteredProducts.sort((a, b) => (b.keyword_count || 0) - (a.keyword_count || 0));
    } else if (sortVal === 'comp_desc') {
        state.filteredProducts.sort((a, b) => (b.competitor_count || 0) - (a.competitor_count || 0));
    } else if (sortVal === 'name_asc') {
        state.filteredProducts.sort((a, b) => (a.product_name || '').localeCompare(b.product_name || ''));
    } else {
        state.filteredProducts.sort((a, b) => (a.id || 0) - (b.id || 0));
    }

    state.currentSkip = 0;
    state.currentPage = 1;
    renderTable();
}

function renderTable() {
    const tbody = document.getElementById('productTableBody');
    tbody.innerHTML = '';

    const totalFiltered = state.filteredProducts.length;
    if (totalFiltered === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 40px; color: var(--text-muted);">
                    No matched products found for your current search or filter criteria.
                </td>
            </tr>
        `;
        renderPagination(0, 0);
        return;
    }

    const pageProducts = state.filteredProducts.slice(
        state.currentSkip,
        state.currentSkip + state.currentLimit
    );

    pageProducts.forEach((p, idx) => {
        const rowNum = state.currentSkip + idx + 1;
        const tr = document.createElement('tr');

        const isMatched = p.matched;
        const matchBadgeClass = isMatched ? 'badge-completed' : 'badge-failed';
        const matchLabel = isMatched ? 'Matched' : 'No Match';

        tr.innerHTML = `
            <td>${rowNum}</td>
            <td><span class="asin-code">${escapeHtml(p.asin || p.excel_asin)}</span></td>
            <td><div class="product-title-cell" title="${escapeHtml(p.product_name)}">${escapeHtml(p.product_name)}</div></td>
            <td style="text-align: center;"><span class="kw-count-pill">${p.keyword_count || 0}</span></td>
            <td style="text-align: center;"><span class="kw-count-pill" style="background: #eff6ff; color: #1d4ed8;">${p.competitor_count || 0}</span></td>
            <td><span class="badge ${matchBadgeClass}">${matchLabel}</span></td>
            <td style="text-align: center;">
                <button type="button" class="btn btn-secondary btn-sm" onclick="openKeywordsModal('${escapeHtml(p.asin || p.excel_asin)}')" ${!isMatched ? 'disabled' : ''}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                    View Details
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    const startNum = state.currentSkip + 1;
    const endNum = Math.min(state.currentSkip + state.currentLimit, totalFiltered);
    renderPagination(startNum, endNum);
}

function renderPagination(start, end) {
    const total = state.filteredProducts.length;
    const info = document.getElementById('paginationInfo');
    info.innerText = total > 0 ? `Showing ${start} to ${end} of ${total.toLocaleString()} products` : 'Showing 0 products';

    const pageButtons = document.getElementById('pageButtons');
    pageButtons.innerHTML = '';
    if (total === 0) return;

    const totalPages = Math.ceil(total / state.currentLimit);
    const currentPage = state.currentPage;

    // Prev Button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn';
    prevBtn.disabled = currentPage === 1;
    prevBtn.innerHTML = '&laquo; Prev';
    prevBtn.onclick = () => {
        if (currentPage > 1) {
            state.currentPage--;
            state.currentSkip = (state.currentPage - 1) * state.currentLimit;
            renderTable();
        }
    };
    pageButtons.appendChild(prevBtn);

    // Page Number Buttons
    for (let p = 1; p <= totalPages; p++) {
        if (p === 1 || p === totalPages || (p >= currentPage - 2 && p <= currentPage + 2)) {
            const btn = document.createElement('button');
            btn.className = `page-btn ${p === currentPage ? 'active' : ''}`;
            btn.innerText = p;
            btn.onclick = () => {
                state.currentPage = p;
                state.currentSkip = (p - 1) * state.currentLimit;
                renderTable();
            };
            pageButtons.appendChild(btn);
        }
    }

    // Next Button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.innerHTML = 'Next &raquo;';
    nextBtn.onclick = () => {
        if (currentPage < totalPages) {
            state.currentPage++;
            state.currentSkip = (state.currentPage - 1) * state.currentLimit;
            renderTable();
        }
    };
    pageButtons.appendChild(nextBtn);
}

function changePageSize(val) {
    state.currentLimit = parseInt(val, 10);
    state.currentSkip = 0;
    state.currentPage = 1;
    renderTable();
}

/* ==========================================================================
   4. DETAILS MODAL (KEYWORDS & COMPETITOR PRODUCTS TABS)
   ========================================================================== */
function openKeywordsModal(asin) {
    state.currentModalAsin = asin;
    state.currentModalTab = 'keywords';

    const product = state.loadedProducts.find(p => p.asin === asin || p.excel_asin === asin);
    if (!product) return;

    document.getElementById('modalAsinBadge').innerText = `ASIN: ${product.asin || product.excel_asin}`;
    document.getElementById('modalProductName').innerText = product.product_name;
    document.getElementById('modalCategory').innerText = product.category || 'N/A';
    document.getElementById('modalKeywordSearch').value = '';
    document.getElementById('modalCompetitorSearch').value = '';

    document.getElementById('modalKeywordCount').innerText = `${(product.keywords || []).length} Keywords`;
    document.getElementById('modalCompetitorCount').innerText = `${(product.competitor_products || []).length} Competitors`;

    switchModalTab('keywords');
    renderModalKeywords(product.keywords || []);
    renderModalCompetitors(product.competitor_products || []);

    document.getElementById('keywordsModalBackdrop').classList.remove('hidden');
}

function switchModalTab(tabName) {
    state.currentModalTab = tabName;
    const keywordsBtn = document.getElementById('tabKeywordsBtn');
    const competitorsBtn = document.getElementById('tabCompetitorsBtn');
    const keywordsContent = document.getElementById('tabKeywordsContent');
    const competitorsContent = document.getElementById('tabCompetitorsContent');

    if (tabName === 'keywords') {
        keywordsBtn.classList.add('active');
        competitorsBtn.classList.remove('active');
        keywordsContent.classList.remove('hidden');
        competitorsContent.classList.add('hidden');
    } else {
        competitorsBtn.classList.add('active');
        keywordsBtn.classList.remove('active');
        competitorsContent.classList.remove('hidden');
        keywordsContent.classList.add('hidden');
    }
}

function filterModalKeywords() {
    const query = document.getElementById('modalKeywordSearch').value.toLowerCase().trim();
    const product = state.loadedProducts.find(p => p.asin === state.currentModalAsin || p.excel_asin === state.currentModalAsin);
    if (!product) return;

    const filtered = (product.keywords || []).filter(k => k.keyword.toLowerCase().includes(query));
    renderModalKeywords(filtered);
}

function renderModalKeywords(keywordsList) {
    const tbody = document.getElementById('modalKeywordsTableBody');
    tbody.innerHTML = '';

    if (!keywordsList || keywordsList.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; padding: 24px; color: var(--text-muted);">
                    No keyword phrases recorded in MySQL for this product.
                </td>
            </tr>
        `;
        return;
    }

    keywordsList.forEach((kw, idx) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td style="font-weight: 500;">${escapeHtml(kw.keyword)}</td>
            <td><span class="badge badge-info">${escapeHtml(kw.source || 'search_suggestions')}</span></td>
            <td style="text-align: right; font-family: monospace;">${(kw.relevance_score || 0).toFixed(1)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function filterModalCompetitors() {
    const query = document.getElementById('modalCompetitorSearch').value.toLowerCase().trim();
    const product = state.loadedProducts.find(p => p.asin === state.currentModalAsin || p.excel_asin === state.currentModalAsin);
    if (!product) return;

    const filtered = (product.competitor_products || []).filter(c =>
        (c.competitor_asin && c.competitor_asin.toLowerCase().includes(query)) ||
        (c.competitor_title && c.competitor_title.toLowerCase().includes(query)) ||
        (c.keyword && c.keyword.toLowerCase().includes(query))
    );
    renderModalCompetitors(filtered);
}

function renderModalCompetitors(competitorsList) {
    const tbody = document.getElementById('modalCompetitorTableBody');
    tbody.innerHTML = '';

    if (!competitorsList || competitorsList.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" style="text-align: center; padding: 24px; color: var(--text-muted);">
                    No competitor product records found in MySQL for this product.
                </td>
            </tr>
        `;
        return;
    }

    competitorsList.forEach((c, idx) => {
        const tr = document.createElement('tr');

        // Description formatting
        const rawDesc = c.description && String(c.description).trim();
        const descHtml = rawDesc
            ? `<div style="max-height: 90px; overflow-y: auto; padding-right: 4px; font-size: 12px; line-height: 1.4; color: var(--text-main);">${escapeHtml(rawDesc)}</div>`
            : `<span style="color: var(--text-muted); font-style: italic;">Not available</span>`;

        // Bullet Points formatting
        let bpList = [];
        if (Array.isArray(c.bullet_points)) {
            bpList = c.bullet_points.filter(b => b && String(b).trim());
        } else if (typeof c.bullet_points === 'string' && c.bullet_points.trim()) {
            bpList = [c.bullet_points.trim()];
        }

        let bpHtml = '';
        if (bpList.length > 0) {
            const items = bpList.map(b => `<li style="margin-bottom: 4px;">${escapeHtml(b)}</li>`).join('');
            bpHtml = `<ul style="margin: 0; padding-left: 16px; max-height: 100px; overflow-y: auto; font-size: 12px; line-height: 1.4; color: var(--text-main);">${items}</ul>`;
        } else {
            bpHtml = `<span style="color: var(--text-muted); font-style: italic;">Not available</span>`;
        }

        tr.innerHTML = `
            <td style="text-align: center; font-weight: 600;">${c.competitor_rank || (idx + 1)}</td>
            <td><span class="asin-code">${escapeHtml(c.competitor_asin)}</span></td>
            <td>
                <div class="product-title-cell" title="${escapeHtml(c.competitor_title)}" style="max-width: 180px;">
                    <a href="${escapeHtml(c.product_url || '#')}" target="_blank" style="color: inherit; text-decoration: none;">${escapeHtml(c.competitor_title)}</a>
                </div>
            </td>
            <td>${escapeHtml(c.price || 'N/A')}</td>
            <td><span class="badge badge-success">${c.rating ? c.rating.toFixed(1) + ' ★' : 'N/A'}</span></td>
            <td>${c.review_count ? c.review_count.toLocaleString() : 'N/A'}</td>
            <td><span class="badge badge-pending">${escapeHtml(c.marketplace || 'amazon.in')}</span></td>
            <td>${descHtml}</td>
            <td>${bpHtml}</td>
        `;
        tbody.appendChild(tr);
    });
}

function toggleCompDetail(rowId) {
    const el = document.getElementById(rowId);
    if (el) {
        el.classList.toggle('hidden');
    }
}

function closeKeywordsModal() {
    document.getElementById('keywordsModalBackdrop').classList.add('hidden');
    state.currentModalAsin = null;
}

function copyModalKeywords() {
    const product = state.loadedProducts.find(p => p.asin === state.currentModalAsin || p.excel_asin === state.currentModalAsin);
    if (!product || !product.keywords || product.keywords.length === 0) {
        showToast('No keywords to copy.', 'error');
        return;
    }

    const textList = product.keywords.map(k => k.keyword).join('\n');
    navigator.clipboard.writeText(textList).then(() => {
        showToast(`${product.keywords.length} keywords copied to clipboard!`, 'success');
    }).catch(() => {
        showToast('Failed to copy to clipboard.', 'error');
    });
}

/* ==========================================================================
   5. EXCEL & CSV EXPORT GENERATION
   ========================================================================== */
function downloadResults(format) {
    if (!state.loadedProducts || state.loadedProducts.length === 0) {
        showToast('No matched product data to download.', 'error');
        return;
    }

    const matchedProducts = state.loadedProducts.filter(p => p.matched);
    if (matchedProducts.length === 0) {
        showToast('No matched products with database records to export.', 'error');
        return;
    }

    // Build Sheet 1: Matched Products Overview
    const overviewRows = state.loadedProducts.map(p => ({
        'Excel ASIN': p.excel_asin || p.asin,
        'Database ASIN': p.asin || 'N/A',
        'Product Name': p.product_name,
        'Category': p.category || '',
        'DB Match Status': p.matched ? 'MATCHED' : 'UNMATCHED',
        'Keyword Count': p.keyword_count || 0,
        'Competitor Count': p.competitor_count || 0
    }));

    // Build Sheet 2: Competitor Products & Details
    const competitorRows = [];
    matchedProducts.forEach(p => {
        (p.competitor_products || []).forEach(c => {
            const rawDesc = c.description && String(c.description).trim();
            const descText = rawDesc ? rawDesc : 'Not available';

            let bpText = 'Not available';
            if (Array.isArray(c.bullet_points)) {
                const validBullets = c.bullet_points.filter(b => b && String(b).trim());
                if (validBullets.length > 0) {
                    bpText = validBullets.join(' | ');
                }
            } else if (typeof c.bullet_points === 'string' && c.bullet_points.trim()) {
                bpText = c.bullet_points.trim();
            }

            competitorRows.push({
                'Source Product ASIN': p.asin,
                'Source Product Name': p.product_name,
                'Search Keyword': c.keyword || '',
                'Competitor Rank': c.competitor_rank || '',
                'Competitor ASIN': c.competitor_asin || '',
                'Competitor Title': c.competitor_title || '',
                'Price': c.price || 'N/A',
                'Rating': c.rating || 'N/A',
                'Review Count': c.review_count || 0,
                'Description': descText,
                'Bullet Points': bpText,
                'Customer Reviews': Array.isArray(c.reviews) && c.reviews.length > 0 ? c.reviews.join(' | ') : 'Not available',
                'Marketplace': c.marketplace || 'amazon.in',
                'Product URL': c.product_url || ''
            });
        });
    });

    // Build Sheet 3: Product Keywords
    const keywordRows = [];
    matchedProducts.forEach(p => {
        (p.keywords || []).forEach(k => {
            keywordRows.push({
                'Source Product ASIN': p.asin,
                'Source Product Name': p.product_name,
                'Keyword Phrase': k.keyword,
                'Source': k.source || 'search_suggestions',
                'Relevance Score': k.relevance_score || 0.0
            });
        });
    });

    const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const filename = `Matched_Keyword_Database_Report_${matchedProducts.length}_Products_${dateStr}.${format === 'excel' ? 'xlsx' : 'csv'}`;

    if (format === 'excel') {
        const wb = XLSX.utils.book_new();

        const wsOverview = XLSX.utils.json_to_sheet(overviewRows);
        XLSX.utils.book_append_sheet(wb, wsOverview, "Products Overview");

        if (competitorRows.length > 0) {
            const wsCompetitors = XLSX.utils.json_to_sheet(competitorRows);
            XLSX.utils.book_append_sheet(wb, wsCompetitors, "Competitor Products Data");
        }

        if (keywordRows.length > 0) {
            const wsKeywords = XLSX.utils.json_to_sheet(keywordRows);
            XLSX.utils.book_append_sheet(wb, wsKeywords, "Harvested Keywords");
        }

        XLSX.writeFile(wb, filename);
    } else {
        downloadCSVFile(competitorRows.length > 0 ? competitorRows : overviewRows, filename);
    }

    recordDownload(filename, matchedProducts.length, keywordRows.length, format, overviewRows, competitorRows, keywordRows);
    showToast(`Successfully downloaded ${filename}!`, 'success');
}

function downloadCSVFile(rows, filename) {
    if (!rows || !rows.length) return;
    const headers = Object.keys(rows[0]);
    const csvLines = [headers.join(',')];

    rows.forEach(row => {
        const values = headers.map(header => {
            const val = row[header] === null || row[header] === undefined ? '' : String(row[header]);
            return `"${val.replace(/"/g, '""')}"`;
        });
        csvLines.push(values.join(','));
    });

    const csvContent = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvLines.join('\n'));
    const link = document.createElement('a');
    link.setAttribute('href', csvContent);
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function recordDownload(filename, productCount, keywordCount, format = 'excel', overviewRows = [], competitorRows = [], keywordRows = []) {
    const formattedDate = new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
    const record = {
        fileName: filename,
        filename: filename,
        productCount: productCount,
        keywordCount: keywordCount,
        downloadedAt: formattedDate,
        timestamp: formattedDate,
        format: format,
        overviewRows: overviewRows,
        competitorRows: competitorRows,
        keywordRows: keywordRows
    };

    if (!Array.isArray(state.recentDownloads)) {
        state.recentDownloads = [];
    }

    state.recentDownloads.unshift(record);
    if (state.recentDownloads.length > 10) {
        state.recentDownloads = state.recentDownloads.slice(0, 10);
    }

    try {
        localStorage.setItem('keywordDatabaseRecentDownloads', JSON.stringify(state.recentDownloads));
    } catch (e) {
        console.error('Failed to save recent downloads to localStorage:', e);
    }

    renderRecentDownloads();
}

function downloadRecentFile(index) {
    const record = state.recentDownloads && state.recentDownloads[index];
    if (!record) {
        showToast('Download record not found.', 'error');
        return;
    }

    const filename = record.fileName || record.filename || 'download.xlsx';
    const format = record.format || (filename.endsWith('.csv') ? 'csv' : 'excel');

    if (record.overviewRows && record.overviewRows.length > 0) {
        if (format === 'excel') {
            const wb = XLSX.utils.book_new();

            const wsOverview = XLSX.utils.json_to_sheet(record.overviewRows);
            XLSX.utils.book_append_sheet(wb, wsOverview, "Products Overview");

            if (record.competitorRows && record.competitorRows.length > 0) {
                const wsCompetitors = XLSX.utils.json_to_sheet(record.competitorRows);
                XLSX.utils.book_append_sheet(wb, wsCompetitors, "Competitor Products Data");
            }

            if (record.keywordRows && record.keywordRows.length > 0) {
                const wsKeywords = XLSX.utils.json_to_sheet(record.keywordRows);
                XLSX.utils.book_append_sheet(wb, wsKeywords, "Harvested Keywords");
            }

            XLSX.writeFile(wb, filename);
        } else {
            downloadCSVFile(record.competitorRows && record.competitorRows.length > 0 ? record.competitorRows : record.overviewRows, filename);
        }
        showToast(`Successfully downloaded ${filename}!`, 'success');
        return;
    }

    if (state.loadedProducts && state.loadedProducts.length > 0) {
        downloadResults(format);
    } else {
        showToast('No matched product data available in current session. Upload an Excel file first.', 'error');
    }
}

function loadRecentDownloads() {
    let savedDownloads = [];
    try {
        const saved = localStorage.getItem('keywordDatabaseRecentDownloads') || localStorage.getItem('22yards_recent_downloads');
        if (saved) {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed)) {
                savedDownloads = parsed;
            }
        }
    } catch (e) {
        console.error('Failed to read recent downloads from localStorage:', e);
    }

    state.recentDownloads = savedDownloads;
    console.log("Recent downloads loaded:", savedDownloads);

    renderRecentDownloads();
}

function renderRecentDownloads() {
    const container = document.getElementById('downloadsList');
    const section = document.getElementById('downloadsCardSection');
    if (!container) return;

    container.innerHTML = '';
    const savedDownloads = state.recentDownloads || [];

    console.log("Recent downloads rendered:", savedDownloads.length);

    if (!savedDownloads || savedDownloads.length === 0) {
        container.innerHTML = `
            <div class="empty-downloads-state">
                No recent downloads. Click "Download Excel" or "Download CSV" to export matched data.
            </div>
        `;
        return;
    }

    if (section) {
        section.classList.remove('hidden');
    }

    savedDownloads.forEach((dl, index) => {
        const div = document.createElement('div');
        div.className = 'download-item-card';
        const fileName = dl.fileName || dl.filename || 'Exported Report';
        const productCount = dl.productCount || 0;
        const keywordCount = dl.keywordCount || 0;
        const downloadedAt = dl.downloadedAt || dl.timestamp || 'N/A';

        div.innerHTML = `
            <div class="download-file-meta">
                <div class="download-icon-box">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                </div>
                <div>
                    <h4 class="download-title">${escapeHtml(fileName)}</h4>
                    <span class="download-subtext">${productCount} Products • ${keywordCount} Keywords • Downloaded on ${escapeHtml(downloadedAt)}</span>
                </div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="downloadRecentFile(${index})">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Download Again
            </button>
        `;
        container.appendChild(div);
    });
}

function clearDownloadHistory() {
    state.recentDownloads = [];
    try {
        localStorage.removeItem('keywordDatabaseRecentDownloads');
        localStorage.removeItem('22yards_recent_downloads');
    } catch (e) {
        console.error('Failed to clear recent downloads from localStorage:', e);
    }
    renderRecentDownloads();
    showToast('Download history cleared.', 'success');
}

/* ==========================================================================
   6. UTILITY FUNCTIONS & TOASTS
   ========================================================================== */
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

/* ==========================================================================
   FLIPKART MARKETPLACE SEPARATE UI CONTROLLER
   Independent data fetching, state management, UI rendering & exports
   ========================================================================== */

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
    isBatchRunning: false
};

function navigateToMarketplace(mkt) {
    const landingSection = document.getElementById('landingSectionView');
    const amazonSection = document.getElementById('amazonSectionView');
    const flipkartSection = document.getElementById('flipkartSectionView');
    const btnHome = document.getElementById('btnNavHome');
    const btnAmazon = document.getElementById('btnNavAmazon');
    const btnFlipkart = document.getElementById('btnNavFlipkart');
    const appSubtitle = document.getElementById('appSubtitle');

    if (btnHome) btnHome.classList.remove('active');
    if (btnAmazon) btnAmazon.classList.remove('active');
    if (btnFlipkart) btnFlipkart.classList.remove('active');

    if (mkt === 'flipkart') {
        if (landingSection) landingSection.classList.add('hidden');
        if (amazonSection) amazonSection.classList.add('hidden');
        if (flipkartSection) flipkartSection.classList.remove('hidden');
        if (btnFlipkart) btnFlipkart.classList.add('active');
        if (appSubtitle) appSubtitle.innerText = 'Flipkart Autosuggest Keyword Intelligence Workspace (DB: marketlens_flipkart)';
        loadFlipkartData();
    } else if (mkt === 'amazon') {
        if (landingSection) landingSection.classList.add('hidden');
        if (flipkartSection) flipkartSection.classList.add('hidden');
        if (amazonSection) amazonSection.classList.remove('hidden');
        if (btnAmazon) btnAmazon.classList.add('active');
        if (appSubtitle) appSubtitle.innerText = 'Amazon Product Keyword Collection Workspace (DB: marketlens)';
    } else {
        // 'home' / landing page
        if (amazonSection) amazonSection.classList.add('hidden');
        if (flipkartSection) flipkartSection.classList.add('hidden');
        if (landingSection) landingSection.classList.remove('hidden');
        if (btnHome) btnHome.classList.add('active');
        if (appSubtitle) appSubtitle.innerText = 'Amazon & Flipkart Keyword Collection Platform';
        fetchFlipkartSummary();
    }
}

function switchMarketplace(mkt) {
    navigateToMarketplace(mkt);
}

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

        const landingFkProd = document.getElementById('landingFkProdCount');
        if (landingFkProd) {
            landingFkProd.innerText = (data.total_products || 0).toLocaleString();
        }

        const landingFkKw = document.getElementById('landingFkKwCount');
        if (landingFkKw) {
            landingFkKw.innerText = (data.total_keywords || 0).toLocaleString();
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
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 32px; color: var(--text-muted);">Loading Flipkart products...</td></tr>`;
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
                <td><code style="font-weight: 600; color: var(--primary);">${escapeHtml(p.asin)}</code></td>
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

async function runFlipkartBatchFromUI() {
    const sizeSelect = document.getElementById('fkBatchSizeSelect');
    const limit = sizeSelect ? parseInt(sizeSelect.value, 10) : 10;
    const btn = document.getElementById('fkRunBatchBtn');
    const progressTrack = document.getElementById('fkProgressBarTrack');
    const progressFill = document.getElementById('fkProgressBarFill');
    const progressText = document.getElementById('fkProgressStatusText');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner" style="width: 14px; height: 14px; border: 2px solid white; border-top-color: transparent; border-radius: 50%; display: inline-block; animation: spin 1s linear infinite;"></span> Processing Batch...`;
    }

    if (progressTrack) progressTrack.classList.remove('hidden');
    if (progressText) {
        progressText.classList.remove('hidden');
        progressText.innerText = `Collecting Flipkart keywords for ${limit} pending products...`;
    }
    if (progressFill) progressFill.style.width = '40%';

    try {
        const resp = await fetch(`${CONFIG.API_BASE_URL}/api/flipkart/collect-batch?limit=${limit}`, {
            method: 'POST'
        });

        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || 'Flipkart batch collection failed');
        }

        const res = await resp.json();
        if (progressFill) progressFill.style.width = '100%';
        if (progressText) {
            progressText.innerText = `Successfully processed ${res.total_products_processed} products (${res.successful_products} completed, ${res.total_keywords_collected} keywords stored).`;
        }

        showToast(`Batch Complete: ${res.successful_products} products completed, ${res.total_keywords_collected} keywords collected!`, 'success');
        await loadFlipkartData();

    } catch (err) {
        console.error('Flipkart UI batch collection error:', err);
        showToast(err.message || 'Error executing Flipkart batch collection.', 'error');
        if (progressText) progressText.innerText = 'Batch collection failed. Check server logs.';
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                Run Flipkart Collection Batch
            `;
        }
        setTimeout(() => {
            if (progressTrack) progressTrack.classList.add('hidden');
            if (progressText) progressText.classList.add('hidden');
        }, 5000);
    }
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
