// Lógica de la página "Conectar" (generar APK). En archivo externo para que el editor lo
// analice como JavaScript real: así reconoce los globals del DOM (FormData, fetch, Event, URL…).
// Los dos valores que dependen de PHP llegan por window.ACCES_CONFIG (ver conectar.php).
const BACKEND_BASE_URL = window.ACCES_CONFIG.backendBaseUrl;
const OWNER_TOKEN = window.ACCES_CONFIG.ownerToken;

const form = document.getElementById('build-form');
const iconInput = document.getElementById('icon');
const fileDrop = document.getElementById('file-drop');
const filePreview = document.getElementById('file-preview');
const filePreviewImg = document.getElementById('file-preview-img');
const filePreviewName = document.getElementById('file-preview-name');
const submitBtn = document.getElementById('submit-btn');
const statusBox = document.getElementById('status');
const statusDot = document.getElementById('status-dot');
const statusLabel = document.getElementById('status-label');
const statusDetail = document.getElementById('status-detail');

function showIconPreview() {
    const file = iconInput.files[0];
    if (!file) { filePreview.style.display = 'none'; return; }
    filePreviewImg.src = URL.createObjectURL(file);
    filePreviewName.textContent = file.name;
    filePreview.style.display = 'flex';
}
iconInput.addEventListener('change', showIconPreview);

['dragover', 'dragenter'].forEach((evt) =>
    fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.add('dragover'); })
);
['dragleave', 'drop'].forEach((evt) =>
    fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.remove('dragover'); })
);
fileDrop.addEventListener('drop', (e) => {
    if (e.dataTransfer.files[0]) {
        iconInput.files = e.dataTransfer.files;
        showIconPreview();
    }
});

function setStatus(label, detail, kind) {
    statusBox.classList.add('visible');
    statusLabel.textContent = label;
    statusDetail.textContent = detail || '';
    statusDot.className = 'dot' + (kind ? ' ' + kind : '');
}

async function pollJob(jobId) {
    const res = await fetch(`${BACKEND_BASE_URL}/api/apps/${jobId}`, {
        headers: { Authorization: `Bearer ${OWNER_TOKEN}` },
    });
    const data = await res.json();

    if (data.status === 'done') {
        setStatus('Listo', '', 'done');
        const link = document.createElement('a');
        link.href = `${BACKEND_BASE_URL}${data.downloadUrl}`;
        link.className = 'download-link';
        link.textContent = 'Descargar APK';
        statusDetail.appendChild(document.createElement('br'));
        statusDetail.appendChild(link);
        submitBtn.disabled = false;
        return;
    }
    if (data.status === 'failed') {
        setStatus('Falló la compilación', data.error || '', 'failed');
        submitBtn.disabled = false;
        return;
    }
    setStatus('Compilando…', 'Esto puede tardar unos minutos.');
    setTimeout(() => pollJob(jobId), 3000);
}

let isSubmitting = false;
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Evitar múltiples envíos
    if (isSubmitting) return;

    isSubmitting = true;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Procesando...';
    setStatus('Encolando…', '');

    const formData = new FormData();
    formData.append('appName', document.getElementById('appName').value);
    formData.append('icon', iconInput.files[0]);
    const url = document.getElementById('contentUrl').value;
    if (url) formData.append('contentUrl', url);

    try {
        const res = await fetch(`${BACKEND_BASE_URL}/api/apps`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${OWNER_TOKEN}` },
            body: formData,
        });
        const data = await res.json();
        if (!res.ok) {
            // DIAGNÓSTICO TEMPORAL: mostrar el detalle real si el servidor lo mandó (ver server.js).
            const detail = data.debug ? ` [${data.debug.code || ''} ${data.debug.message || ''}]` : '';
            setStatus('Error', (data.error || 'No se pudo encolar el build') + detail, 'failed');
            console.error('[conectar] /api/apps error:', data);
            isSubmitting = false;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Generar APK';
            return;
        }
        pollJob(data.jobId);
    } catch (err) {
        setStatus('Error de red', err.message, 'failed');
        isSubmitting = false;
        submitBtn.disabled = false;
        submitBtn.textContent = 'Generar APK';
    }
});
