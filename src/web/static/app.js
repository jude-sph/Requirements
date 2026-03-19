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

// Run
async function startRun() {
    const body = {
        dig_ids: document.getElementById('dig-ids').value,
        max_depth: parseInt(document.getElementById('depth').value),
        max_breadth: parseInt(document.getElementById('breadth').value),
        skip_vv: !document.getElementById('vv').checked,
        skip_judge: !document.getElementById('judge').checked,
    };
    try {
        const res = await fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json();
            showError(err.detail || 'Failed to start');
            return;
        }
        const data = await res.json();
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
        dig_ids: document.getElementById('dig-ids').value,
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
        showToast('Est: ' + data.digs + ' DIGs \u00d7 ' + data.max_calls_per_dig + ' calls = ' + data.max_total_calls + ' max API calls');
    } catch (e) {
        showError('Estimate failed');
    }
}

// Results
async function loadResults() {
    try {
        const res = await fetch('/results');
        const data = await res.json();
        renderResults(data.results);
    } catch (e) {
        console.error('Failed to load results', e);
    }
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

    addField('Technical Requirement', node.technical_requirement);
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

// Export
function downloadXlsx() {
    window.location.href = '/export';
}

// Settings
async function openSettings() {
    document.getElementById('settings-modal').style.display = '';
    try {
        var res = await fetch('/settings');
        var data = await res.json();
        var select = document.getElementById('settings-model');
        select.textContent = '';
        data.models.forEach(function(m) {
            var opt = document.createElement('option');
            opt.value = m.id;
            opt.setAttribute('data-provider', m.provider);
            opt.textContent = m.name + ' (' + m.cost_per_dig + ')';
            if (m.id === data.model) opt.selected = true;
            select.appendChild(opt);
        });
        document.getElementById('anthropic-key-status').textContent = data.has_anthropic_key ? 'Key is set' : 'Not set';
        document.getElementById('openrouter-key-status').textContent = data.has_openrouter_key ? 'Key is set' : 'Not set';
    } catch (e) {
        showError('Failed to load settings');
    }
}

function closeSettings() {
    document.getElementById('settings-modal').style.display = 'none';
}

async function saveSettings() {
    var select = document.getElementById('settings-model');
    var option = select.options[select.selectedIndex];
    var body = {
        model: select.value,
        provider: option.getAttribute('data-provider'),
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
        document.getElementById('model-name').textContent = data.model;
        closeSettings();
        showToast('Settings saved');
    } catch (e) {
        showError('Failed to save settings');
    }
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

// Load results on page load
loadResults();
