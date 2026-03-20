// State
let currentJobId = null;
let eventSource = null;

// Upload handling
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        handleUpload(fileInput);
    }
});

async function handleUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        if (!res.ok) {
            const err = await res.json();
            showError(err.detail || 'Upload failed');
            return;
        }
        const data = await res.json();
        document.getElementById('upload-text').textContent = '\u{1F4C4} ' + file.name + ' loaded \u2014 ' + data.dig_count + ' DIGs';
        showToast('Loaded ' + data.dig_count + ' DIGs');
    } catch (e) {
        showError('Upload failed: ' + e.message);
    }
}

// DIG picker
var allDigs = [];
var selectedDigs = [];

async function loadDigs() {
    try {
        var res = await fetch('/digs');
        var data = await res.json();
        allDigs = data.digs;
    } catch (e) {
        // silently ignore
    }
}

function showDigDropdown() {
    filterDigDropdown();
    document.getElementById('dig-dropdown').style.display = '';
}

function hideDigDropdown() {
    setTimeout(function() {
        document.getElementById('dig-dropdown').style.display = 'none';
    }, 200);
}

function filterDigDropdown() {
    var query = document.getElementById('dig-ids').value.toLowerCase().trim();
    var dropdown = document.getElementById('dig-dropdown');
    dropdown.textContent = '';

    var filtered = allDigs.filter(function(d) {
        return d.id.indexOf(query) !== -1 || d.text.toLowerCase().indexOf(query) !== -1;
    });

    if (filtered.length === 0) {
        dropdown.appendChild(el('div', { className: 'dig-dropdown-empty', textContent: query ? 'No matching DIGs' : 'No DIGs loaded' }));
        return;
    }

    filtered.slice(0, 50).forEach(function(d) {
        var isSelected = selectedDigs.indexOf(d.id) !== -1;
        var item = el('div', { className: 'dig-dropdown-item' + (isSelected ? ' selected' : '') });
        item.appendChild(el('span', { className: 'dig-dropdown-id', textContent: d.id }));
        item.appendChild(el('span', { className: 'dig-dropdown-text', textContent: d.text }));
        item.addEventListener('click', function() {
            if (!isSelected) {
                selectedDigs.push(d.id);
                renderDigTags();
                filterDigDropdown();
            }
        });
        dropdown.appendChild(item);
    });

    if (filtered.length > 50) {
        dropdown.appendChild(el('div', { className: 'dig-dropdown-empty', textContent: '...and ' + (filtered.length - 50) + ' more. Type to filter.' }));
    }
}

function renderDigTags() {
    var container = document.getElementById('dig-tags');
    container.textContent = '';
    selectedDigs.forEach(function(id) {
        var tag = el('span', { className: 'dig-tag' }, [id]);
        var x = el('span', { className: 'dig-tag-x', textContent: '\u00d7' });
        x.addEventListener('click', function() {
            selectedDigs = selectedDigs.filter(function(d) { return d !== id; });
            renderDigTags();
            filterDigDropdown();
        });
        tag.appendChild(x);
        container.appendChild(tag);
    });
    // Update hidden input value
    document.getElementById('dig-ids').value = '';
}

function getSelectedDigIds() {
    // If tags are selected, use those. Otherwise use text input.
    if (selectedDigs.length > 0) {
        return selectedDigs.join(',');
    }
    return document.getElementById('dig-ids').value;
}

// Close dropdown on outside click
document.addEventListener('click', function(e) {
    var wrap = document.querySelector('.dig-picker-wrap');
    if (wrap && !wrap.contains(e.target)) {
        document.getElementById('dig-dropdown').style.display = 'none';
    }
});

// Run — with cost confirmation
var pendingRunBody = null;

async function startRun() {
    var body = {
        dig_ids: getSelectedDigIds(),
        max_depth: parseInt(document.getElementById('depth').value),
        max_breadth: parseInt(document.getElementById('breadth').value),
        skip_vv: !document.getElementById('vv').checked,
        skip_judge: !document.getElementById('judge').checked,
    };

    // Get cost estimate first
    try {
        var estRes = await fetch('/dry-run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        var est = await estRes.json();
        pendingRunBody = body;
        var modalBody = document.getElementById('cost-modal-body');
        modalBody.textContent = '';
        modalBody.appendChild(el('p', { style: 'color:#ccc; font-size:13px; margin-bottom:8px;' }, [
            est.digs + ' DIG(s) \u00d7 ' + est.max_calls_per_dig + ' max API calls each'
        ]));
        modalBody.appendChild(el('p', { style: 'color:#fff; font-size:15px; font-weight:500;' }, [
            'Up to ' + est.max_total_calls + ' API calls'
        ]));
        if (est.est_cost_usd > 0) {
            modalBody.appendChild(el('p', { style: 'color:#7c7cff; font-size:18px; font-weight:600; margin-top:8px;' }, [
                'Est. worst case: ~$' + est.est_cost_usd.toFixed(2)
            ]));
            modalBody.appendChild(el('p', { style: 'color:#666; font-size:11px; margin-top:2px;' }, [
                'Using ' + est.model + ' \u2014 based on average token usage'
            ]));
        }
        modalBody.appendChild(el('p', { style: 'color:#888; font-size:11px; margin-top:8px;' }, [
            'This is a rough estimate, not a guaranteed cap. Actual cost depends on response lengths, tree fan-out, and early termination. Typically 30-60% of the estimate.'
        ]));
        document.getElementById('cost-modal').style.display = '';
    } catch (e) {
        // If estimate fails, just run directly
        pendingRunBody = body;
        confirmRun();
    }
}

async function confirmRun() {
    document.getElementById('cost-modal').style.display = 'none';
    if (!pendingRunBody) return;
    var body = pendingRunBody;
    pendingRunBody = null;
    try {
        var res = await fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            var err = await res.json();
            showError(err.detail || 'Failed to start');
            return;
        }
        var data = await res.json();
        currentJobId = data.job_id;
        showProgress();
        connectSSE(data.job_id);
    } catch (e) {
        showError('Failed to start: ' + e.message);
    }
}

// SSE
function connectSSE(jobId) {
    if (eventSource) eventSource.close();
    eventSource = new EventSource('/stream/' + jobId);
    eventSource.onmessage = (e) => {
        const event = JSON.parse(e.data);
        handleEvent(event);
    };
    eventSource.onerror = () => {
        eventSource.close();
        eventSource = null;
    };
}

function handleEvent(event) {
    const label = document.getElementById('progress-label');
    const detail = document.getElementById('progress-detail');
    const cost = document.getElementById('progress-cost');
    const bar = document.getElementById('progress-bar');

    switch (event.type) {
        case 'started':
            label.textContent = 'Processing ' + event.total_digs + ' DIG(s)...';
            break;
        case 'dig_started':
            label.textContent = 'DIG ' + event.dig_id + ' [' + event.index + '/' + event.total + ']';
            detail.textContent = event.dig_text;
            bar.style.width = ((event.index - 1) / event.total * 100) + '%';
            break;
        case 'phase':
            detail.textContent = event.phase + ': ' + event.detail;
            break;
        case 'cost':
            cost.textContent = '$' + event.total_cost.toFixed(4);
            break;
        case 'dig_complete':
            detail.textContent = 'DIG ' + event.dig_id + ': ' + event.nodes + ' nodes, ' + event.levels + ' levels';
            break;
        case 'complete':
            label.textContent = 'Complete \u2014 ' + event.total_digs + ' DIGs, ' + event.total_nodes + ' requirements';
            cost.textContent = '$' + event.total_cost.toFixed(4);
            bar.style.width = '100%';
            detail.textContent = '';
            if (eventSource) { eventSource.close(); eventSource = null; }
            setTimeout(function() {
                hideProgress();
                loadResults();
                showToast('Done! ' + event.total_nodes + ' requirements generated ($' + event.total_cost.toFixed(4) + ')');
            }, 1500);
            break;
        case 'error':
            var msg = event.dig_id ? 'DIG ' + event.dig_id + ': ' + event.message : event.message;
            showError(msg);
            detail.textContent = 'Error: ' + msg;
            break;
        case 'cancelled':
            label.textContent = 'Cancelled';
            if (eventSource) { eventSource.close(); eventSource = null; }
            setTimeout(hideProgress, 1000);
            break;
    }
}

function showProgress() {
    document.getElementById('progress-section').style.display = '';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-cost').textContent = '';
    document.getElementById('progress-detail').textContent = '';
}

function hideProgress() {
    document.getElementById('progress-section').style.display = 'none';
}

async function cancelJob() {
    if (!currentJobId) return;
    await fetch('/cancel/' + currentJobId, { method: 'POST' });
}

// Cost estimate
async function estimateCost() {
    const body = {
        dig_ids: getSelectedDigIds(),
        max_depth: parseInt(document.getElementById('depth').value),
        max_breadth: parseInt(document.getElementById('breadth').value),
        skip_vv: !document.getElementById('vv').checked,
        skip_judge: !document.getElementById('judge').checked,
    };
    try {
        const res = await fetch('/dry-run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        var costStr = data.est_cost_usd > 0 ? ' \u2248 ~$' + data.est_cost_usd.toFixed(2) + ' worst case' : '';
        showToast('Est: ' + data.digs + ' DIGs \u00d7 ' + data.max_calls_per_dig + ' calls = ' + data.max_total_calls + ' max calls' + costStr + ' (' + data.model + ')');
    } catch (e) {
        showError('Estimate failed');
    }
}

// Results
var allResults = [];

async function loadResults() {
    try {
        var res = await fetch('/results');
        var data = await res.json();
        allResults = data.results;
        renderResults(allResults);
    } catch (e) {
        console.error('Failed to load results', e);
    }
}

function filterResults() {
    var query = document.getElementById('search-input').value.toLowerCase().trim();
    if (!query) {
        renderResults(allResults);
        return;
    }
    var filtered = allResults.filter(function(r) {
        return r.dig_id.toLowerCase().indexOf(query) !== -1 ||
               r.dig_text.toLowerCase().indexOf(query) !== -1;
    });
    renderResults(filtered);
}

// Safe text element creator
function el(tag, attrs, children) {
    const elem = document.createElement(tag);
    if (attrs) {
        Object.keys(attrs).forEach(function(key) {
            if (key === 'textContent') elem.textContent = attrs[key];
            else if (key === 'className') elem.className = attrs[key];
            else if (key === 'onclick') elem.addEventListener('click', attrs[key]);
            else if (key.startsWith('data-')) elem.setAttribute(key, attrs[key]);
            else elem.setAttribute(key, attrs[key]);
        });
    }
    if (children) {
        children.forEach(function(child) {
            if (typeof child === 'string') elem.appendChild(document.createTextNode(child));
            else if (child) elem.appendChild(child);
        });
    }
    return elem;
}

function renderResults(results) {
    const list = document.getElementById('results-list');
    const label = document.getElementById('results-label');
    list.textContent = '';

    if (!results.length) {
        list.appendChild(el('div', { style: 'color:#555;font-size:13px;padding:10px 0;', textContent: 'No results yet. Run some DIGs to see them here.' }));
        label.textContent = 'Results';
        return;
    }
    var totalNodes = results.reduce(function(s, r) { return s + r.nodes; }, 0);
    label.textContent = 'Results \u2014 ' + results.length + ' DIGs, ' + totalNodes + ' requirements';

    results.forEach(function(r) {
        var card = el('div', { className: 'result-card', id: 'card-' + r.dig_id });

        var headerLeft = el('div', { className: 'result-card-left' }, [
            el('span', { className: 'result-dig-id', textContent: 'DIG ' + r.dig_id }),
            el('span', { className: 'result-dig-text', textContent: r.dig_text }),
        ]);
        var headerRight = el('div', { className: 'result-card-right' }, [
            el('span', { className: 'result-levels', textContent: r.levels + ' levels' }),
            el('span', { className: 'result-nodes', textContent: r.nodes + ' nodes' }),
            el('span', { className: 'result-cost', textContent: '$' + r.cost.toFixed(4) }),
            el('span', { className: 'result-arrow', id: 'arrow-' + r.dig_id, textContent: '\u25b8' }),
        ]);
        var header = el('div', { className: 'result-card-header', onclick: function() { toggleCard(r.dig_id); } }, [headerLeft, headerRight]);
        var body = el('div', { className: 'result-card-body', id: 'body-' + r.dig_id });

        card.appendChild(header);
        card.appendChild(body);
        list.appendChild(card);
    });
}

async function toggleCard(digId) {
    var body = document.getElementById('body-' + digId);
    var arrow = document.getElementById('arrow-' + digId);
    if (body.classList.contains('open')) {
        body.classList.remove('open');
        arrow.classList.remove('open');
        return;
    }
    if (!body.hasChildNodes()) {
        try {
            var res = await fetch('/results/' + digId);
            var tree = await res.json();
            body.appendChild(renderTreeNode(tree.root));
        } catch (e) {
            body.appendChild(el('div', { style: 'color:#c66;padding:8px;', textContent: 'Failed to load' }));
        }
    }
    body.classList.add('open');
    arrow.classList.add('open');
}

function renderTreeNode(node) {
    if (!node) return document.createTextNode('');
    var levelClass = 'tree-level tree-level-' + Math.min(node.level, 4);
    var reqText = node.technical_requirement || '(empty)';
    if (reqText.length > 100) reqText = reqText.slice(0, 100) + '...';
    var nodeId = 'node-' + node.level + '-' + Math.random().toString(36).slice(2, 8);

    var container = el('div', { className: 'tree-node' });

    // Header row
    var header = el('div', { className: 'tree-node-header', onclick: function() { toggleNodeDetail(nodeId); } }, [
        el('span', { className: levelClass, textContent: 'L' + node.level }),
        el('span', { className: 'tree-req', textContent: reqText }),
    ]);
    container.appendChild(header);

    // Detail panel
    var detail = el('div', { className: 'node-detail', id: nodeId, style: 'display:none' });
    var dl = document.createElement('dl');

    function addField(label, value) {
        if (!value) return;
        dl.appendChild(el('dt', { textContent: label }));
        dl.appendChild(el('dd', { textContent: value }));
    }

    // Technical requirement with copy button
    if (node.technical_requirement) {
        dl.appendChild(el('dt', { textContent: 'Technical Requirement' }));
        var reqRow = el('dd', { style: 'display:flex; align-items:start; gap:4px;' }, [
            el('span', { textContent: node.technical_requirement, style: 'flex:1;' }),
            makeCopyBtn(node.technical_requirement),
        ]);
        dl.appendChild(reqRow);
    }
    addField('Rationale', node.rationale);
    addField('Allocation', (node.allocation || '-') + ' \u2014 ' + (node.chapter_code || '-'));
    addField('System Hierarchy', node.system_hierarchy_id);
    addField('Acceptance Criteria', node.acceptance_criteria);
    if (node.verification_method && node.verification_method.length) {
        addField('Verification', node.verification_method.join(', ') + ' @ ' + (node.verification_event || []).join(', '));
    }
    addField('Confidence Notes', node.confidence_notes);

    detail.appendChild(dl);
    container.appendChild(detail);

    // Children
    if (node.children && node.children.length) {
        var childrenDiv = el('div', { className: 'tree-children' });
        node.children.forEach(function(child) {
            childrenDiv.appendChild(renderTreeNode(child));
        });
        container.appendChild(childrenDiv);
    }

    return container;
}

function toggleNodeDetail(nodeId) {
    var elem = document.getElementById(nodeId);
    elem.style.display = elem.style.display === 'none' ? 'block' : 'none';
}

// Copy to clipboard
function makeCopyBtn(text) {
    var btn = el('button', { className: 'btn-copy', textContent: 'Copy' });
    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        navigator.clipboard.writeText(text).then(function() {
            btn.textContent = 'Copied';
            btn.classList.add('copied');
            setTimeout(function() {
                btn.textContent = 'Copy';
                btn.classList.remove('copied');
            }, 2000);
        });
    });
    return btn;
}

// Export
function downloadXlsx() {
    window.location.href = '/export';
}

// Settings
var settingsModels = [];
var selectedModelId = null;

async function openSettings() {
    document.getElementById('settings-modal').style.display = '';
    try {
        var res = await fetch('/settings');
        var data = await res.json();
        settingsModels = data.models;
        selectedModelId = data.model;
        renderModelCards(data.models, data.model);
        document.getElementById('anthropic-key-status').textContent = data.has_anthropic_key ? 'Key is set' : 'Not set';
        document.getElementById('openrouter-key-status').textContent = data.has_openrouter_key ? 'Key is set' : 'Not set';
    } catch (e) {
        showError('Failed to load settings');
    }
}

function renderModelCards(models, currentModel) {
    var container = document.getElementById('model-cards');
    container.textContent = '';
    models.forEach(function(m) {
        var qualityClass = 'quality-' + (m.quality || 'good').replace(' ', '-');
        var card = el('div', {
            className: 'model-card' + (m.id === currentModel ? ' selected' : ''),
            'data-model-id': m.id,
        });
        card.addEventListener('click', function() { selectModel(m.id); });

        var qualityBadge = el('span', { className: 'model-card-quality ' + qualityClass, textContent: m.quality || 'good' });
        var name = el('span', { className: 'model-card-name', textContent: m.name });
        var cost = el('span', { className: 'model-card-cost', textContent: m.cost_per_dig });
        var info = el('span', { className: 'model-card-info', textContent: '\u24d8' });
        info.addEventListener('click', function(e) {
            e.stopPropagation();
            showModelInfo(m);
        });

        card.appendChild(qualityBadge);
        card.appendChild(name);
        card.appendChild(cost);
        card.appendChild(info);
        container.appendChild(card);
    });
}

function selectModel(modelId) {
    selectedModelId = modelId;
    var cards = document.querySelectorAll('.model-card');
    cards.forEach(function(card) {
        if (card.getAttribute('data-model-id') === modelId) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });
    // Hide info panel when selecting
    document.getElementById('model-info-panel').style.display = 'none';
}

function showModelInfo(model) {
    var panel = document.getElementById('model-info-panel');
    panel.textContent = '';
    panel.style.display = '';

    panel.appendChild(el('div', { className: 'info-desc', textContent: model.description || '' }));

    var row = el('div', { className: 'info-row' });

    if (model.pros && model.pros.length) {
        var prosDiv = el('div', { className: 'info-pros' });
        prosDiv.appendChild(el('h5', { textContent: 'Pros' }));
        var prosList = document.createElement('ul');
        model.pros.forEach(function(p) { prosList.appendChild(el('li', { textContent: p })); });
        prosDiv.appendChild(prosList);
        row.appendChild(prosDiv);
    }
    if (model.cons && model.cons.length) {
        var consDiv = el('div', { className: 'info-cons' });
        consDiv.appendChild(el('h5', { textContent: 'Cons' }));
        var consList = document.createElement('ul');
        model.cons.forEach(function(c) { consList.appendChild(el('li', { textContent: c })); });
        consDiv.appendChild(consList);
        row.appendChild(consDiv);
    }
    panel.appendChild(row);

    var details = el('div', { style: 'margin-top: 8px; color: #666; font-size: 11px;' }, [
        'Provider: ' + model.provider + ' | Pricing: ' + model.price + ' | Speed: ' + (model.speed || 'medium'),
    ]);
    panel.appendChild(details);
}

function closeSettings() {
    document.getElementById('settings-modal').style.display = 'none';
    document.getElementById('model-info-panel').style.display = 'none';
}

async function saveSettings() {
    var model = settingsModels.find(function(m) { return m.id === selectedModelId; });
    if (!model) { showError('No model selected'); return; }
    var body = {
        model: model.id,
        provider: model.provider,
        anthropic_key: document.getElementById('settings-anthropic-key').value,
        openrouter_key: document.getElementById('settings-openrouter-key').value,
    };
    try {
        var res = await fetch('/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        var data = await res.json();
        document.getElementById('model-name').textContent = model.name;
        closeSettings();
        showToast('Model set to ' + model.name);
    } catch (e) {
        showError('Failed to save settings');
    }
}

// Restart notice (persistent, can't be dismissed)
function showRestartNotice() {
    // Replace update banner with restart notice
    var banner = document.getElementById('update-banner');
    banner.style.display = '';
    banner.style.background = '#2a2a15';
    banner.style.borderColor = '#5a5a20';
    var bannerText = document.getElementById('update-banner-text');
    bannerText.textContent = '';
    bannerText.style.color = '#ffcc00';

    bannerText.appendChild(el('strong', { textContent: 'Update installed. ' }));
    bannerText.appendChild(document.createTextNode('Please restart the server to apply changes. '));
    bannerText.appendChild(el('span', { style: 'color: #aaa;', textContent: 'Stop the server (Ctrl+C) and run: reqdecomp --web' }));

    // Remove the dismiss button and update button
    var dismissBtn = banner.querySelector('.btn-dismiss');
    if (dismissBtn) dismissBtn.style.display = 'none';
    var updateBtn = banner.querySelector('.btn-update-banner');
    if (updateBtn) updateBtn.style.display = 'none';
}

// Utilities
function showError(msg) {
    var banner = document.getElementById('error-banner');
    document.getElementById('error-text').textContent = msg;
    banner.style.display = '';
    setTimeout(function() { banner.style.display = 'none'; }, 10000);
}

function showToast(msg) {
    var toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.style.display = '';
    setTimeout(function() { toast.style.display = 'none'; }, 4000);
}

// Software updates
async function checkForUpdates() {
    var btn = document.getElementById('update-btn');
    var status = document.getElementById('update-status');
    btn.textContent = 'Checking...';
    btn.disabled = true;
    try {
        var res = await fetch('/check-updates');
        var data = await res.json();
        if (data.error) {
            status.textContent = data.error;
            status.style.color = '#c88';
            btn.textContent = 'Check for Updates';
            btn.disabled = false;
            btn.onclick = checkForUpdates;
        } else if (data.available) {
            status.textContent = data.behind + ' update(s) available';
            status.style.color = '#7c7cff';
            btn.textContent = 'Install Update';
            btn.disabled = false;
            btn.onclick = installUpdate;
        } else {
            status.textContent = 'Up to date';
            status.style.color = '#5a5';
            btn.textContent = 'Check for Updates';
            btn.disabled = false;
            btn.onclick = checkForUpdates;
        }
    } catch (e) {
        status.textContent = 'Could not check for updates';
        status.style.color = '#c66';
        btn.textContent = 'Check for Updates';
        btn.disabled = false;
    }
}

async function installUpdate() {
    var btn = document.getElementById('update-btn');
    var status = document.getElementById('update-status');
    btn.textContent = 'Updating...';
    btn.disabled = true;
    try {
        var res = await fetch('/update', { method: 'POST' });
        var data = await res.json();
        if (data.status === 'ok' && data.updated) {
            status.textContent = '';
            btn.textContent = 'Updated';
            showRestartNotice();
        } else if (data.status === 'ok') {
            status.textContent = data.message;
            status.style.color = '#5a5';
            btn.textContent = 'Check for Updates';
            btn.disabled = false;
            btn.onclick = checkForUpdates;
        } else {
            status.textContent = data.message;
            status.style.color = '#c66';
            btn.textContent = 'Check for Updates';
            btn.disabled = false;
            btn.onclick = checkForUpdates;
        }
    } catch (e) {
        status.textContent = 'Update failed';
        status.style.color = '#c66';
        btn.textContent = 'Check for Updates';
        btn.disabled = false;
        btn.onclick = checkForUpdates;
    }
}

// Check for updates on page load (non-blocking)
async function checkUpdatesQuietly() {
    try {
        var res = await fetch('/check-updates');
        var data = await res.json();
        if (data.available) {
            var banner = document.getElementById('update-banner');
            document.getElementById('update-banner-text').textContent =
                data.behind + ' update(s) available \u2014 new features and fixes ready to install';
            banner.style.display = '';
            // Also mark settings button
            var settingsBtn = document.querySelector('.header-right .btn-icon');
            settingsBtn.textContent = '\u2699 Settings \u2022';
            settingsBtn.style.color = '#7c7cff';
        }
    } catch (e) {
        // Silently ignore
    }
}

async function installUpdateFromBanner() {
    var banner = document.getElementById('update-banner');
    document.getElementById('update-banner-text').textContent = 'Updating...';
    try {
        var res = await fetch('/update', { method: 'POST' });
        var data = await res.json();
        if (data.status === 'ok' && data.updated) {
            document.getElementById('update-banner').style.display = 'none';
            showRestartNotice();
        } else if (data.status === 'ok') {
            banner.style.display = 'none';
            showToast(data.message);
        } else {
            document.getElementById('update-banner-text').textContent = 'Update failed: ' + data.message;
        }
    } catch (e) {
        document.getElementById('update-banner-text').textContent = 'Update failed';
    }
}

// Load on page start
loadResults();
loadDigs();
checkUpdatesQuietly();
