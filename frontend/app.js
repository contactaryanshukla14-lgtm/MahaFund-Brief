/* ═══════════════════════════════════════════════════════════════════════
   MahaFund Brief — Frontend Application Logic
   Handles form submission, tab switching, progress simulation,
   and communication with the FastAPI backend.
   ═══════════════════════════════════════════════════════════════════════ */

// Update this URL once your AWS App Runner service is deployed
const AWS_API_URL = 'https://3s74p2ixni.ap-south-1.awsapprunner.com';

const isProduction = window.location.hostname === 'mahafundbrief.arisetoascend.com' || window.location.hostname.includes('vercel.app');
const API_BASE = isProduction ? AWS_API_URL : window.location.origin;

// ── Tab Switching ──────────────────────────────────────────────────────
function switchTab(tab) {
    const reraTab = document.getElementById('tab-rera');
    const manualTab = document.getElementById('tab-manual');
    const reraForm = document.getElementById('form-rera');
    const manualForm = document.getElementById('form-manual');

    if (tab === 'rera') {
        reraTab.classList.add('active');
        manualTab.classList.remove('active');
        reraForm.classList.remove('hidden');
        manualForm.classList.add('hidden');
    } else {
        manualTab.classList.add('active');
        reraTab.classList.remove('active');
        manualForm.classList.remove('hidden');
        reraForm.classList.add('hidden');
    }

    // Reset any visible progress/errors
    document.getElementById('progress-area').classList.add('hidden');
    document.getElementById('error-area').classList.add('hidden');
}

// ── Form Submissions ───────────────────────────────────────────────────
function submitRera(event) {
    event.preventDefault();
    const rera = document.getElementById('rera-input').value.trim();
    if (!rera) return;
    startGeneration({ rera_number: rera });
}

function submitManual(event) {
    event.preventDefault();
    const project = document.getElementById('project-input').value.trim();
    const developer = document.getElementById('developer-input').value.trim();
    const location = document.getElementById('location-input').value.trim();
    if (!project) return;
    startGeneration({ project, developer, location });
}

// ── Generation Pipeline ────────────────────────────────────────────────
async function startGeneration(payload) {
    // Hide forms, show progress
    document.getElementById('form-rera').classList.add('hidden');
    document.getElementById('form-manual').classList.add('hidden');
    document.getElementById('error-area').classList.add('hidden');
    document.getElementById('progress-area').classList.remove('hidden');

    // Disable tab switching during generation
    document.getElementById('tab-rera').disabled = true;
    document.getElementById('tab-manual').disabled = true;

    // Start progress simulation
    const progressSim = simulateProgress();

    try {
        const response = await fetch(`${API_BASE}/generate-brief`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            progressSim.complete();
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || `Server error: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let done = false;

        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunkStr = decoder.decode(value, { stream: true });
                const lines = chunkStr.split('\n');
                
                for (let line of lines) {
                    line = line.trim();
                    if (!line) continue;
                    
                    try {
                        const data = JSON.parse(line);
                        
                        if (data.status === 'error') {
                            throw new Error(data.detail || 'Pipeline error');
                        }
                        
                        if (data.status === 'complete') {
                            progressSim.complete();
                            
                            // Convert Base64 back to Blob
                            const byteCharacters = atob(data.file_base64);
                            const byteNumbers = new Array(byteCharacters.length);
                            for (let i = 0; i < byteCharacters.length; i++) {
                                byteNumbers[i] = byteCharacters.charCodeAt(i);
                            }
                            const byteArray = new Uint8Array(byteNumbers);
                            const blob = new Blob([byteArray], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
                            
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = data.filename || 'MahaFund_Brief.docx';
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            URL.revokeObjectURL(url);

                            updateProgress(100, 'Brief downloaded successfully!', 4);
                            setTimeout(resetForm, 3000);
                        }
                        // If status === 'processing', we just do nothing and let the simulation run
                    } catch (e) {
                        if (e.message !== 'Unexpected end of JSON input') {
                            throw e;
                        }
                    }
                }
            }
        }

    } catch (error) {
        progressSim.complete();
        showError(error.message);
        setTimeout(resetForm, 5000);
    }
}

// ── Progress Simulation ────────────────────────────────────────────────
function simulateProgress() {
    let progress = 0;
    let step = 0;
    let cancelled = false;

    const stages = [
        { target: 25, duration: 20000, label: 'Extracting MahaRERA data...', step: 1 },
        { target: 50, duration: 30000, label: 'Gathering market intelligence...', step: 2 },
        { target: 75, duration: 15000, label: 'Running AI eligibility analysis...', step: 3 },
        { target: 90, duration: 10000, label: 'Generating report document...', step: 4 },
    ];

    function runStage(idx) {
        if (cancelled || idx >= stages.length) return;
        const stage = stages[idx];
        updateProgress(progress, stage.label, stage.step);

        const interval = setInterval(() => {
            if (cancelled) { clearInterval(interval); return; }
            progress += (stage.target - progress) * 0.03;
            if (progress >= stage.target - 1) {
                progress = stage.target;
                clearInterval(interval);
                runStage(idx + 1);
            }
            updateProgress(Math.round(progress), stage.label, stage.step);
        }, stage.duration / 30);
    }

    runStage(0);

    return {
        complete: () => {
            cancelled = true;
        }
    };
}

function updateProgress(percent, statusText, activeStep) {
    document.getElementById('progress-fill').style.width = percent + '%';
    document.getElementById('progress-status').textContent = statusText;

    const steps = ['step-rera-progress', 'step-agents-progress', 'step-analysis-progress', 'step-report-progress'];
    steps.forEach((id, i) => {
        const el = document.getElementById(id);
        el.classList.remove('active', 'done');
        if (i + 1 < activeStep) el.classList.add('done');
        else if (i + 1 === activeStep) el.classList.add('active');
    });
}

// ── Error Display ──────────────────────────────────────────────────────
function showError(message) {
    document.getElementById('progress-area').classList.add('hidden');
    const errorArea = document.getElementById('error-area');
    document.getElementById('error-message').textContent = message;
    errorArea.classList.remove('hidden');
}

// ── Reset Form ─────────────────────────────────────────────────────────
function resetForm() {
    document.getElementById('progress-area').classList.add('hidden');
    document.getElementById('error-area').classList.add('hidden');
    document.getElementById('tab-rera').disabled = false;
    document.getElementById('tab-manual').disabled = false;

    // Show whichever tab is currently active
    if (document.getElementById('tab-rera').classList.contains('active')) {
        document.getElementById('form-rera').classList.remove('hidden');
    } else {
        document.getElementById('form-manual').classList.remove('hidden');
    }

    // Reset progress bar
    document.getElementById('progress-fill').style.width = '0%';
}
