(function () {
    const endpoint = '/study-plan-hours';

    function setStatus(form, message, kind = '') {
        const status = form.querySelector('.study-plan-status');
        if (!status) return;
        status.textContent = message || '';
        status.classList.toggle('is-ok', kind === 'ok');
        status.classList.toggle('is-error', kind === 'error');
    }

    function formatValue(value) {
        if (value === null || value === undefined) return '';
        return String(value);
    }

    function setField(id, value, notify = true) {
        const field = document.getElementById(id);
        if (!field || value === null || value === undefined || value === '') return;
        field.value = formatValue(value);
        if (notify) {
            field.dispatchEvent(new Event('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    async function loadHours(form, index) {
        const cleanIndex = (index || '').trim();
        if (!cleanIndex) {
            setStatus(form, 'Выберите индекс, чтобы подтянуть часы из учебного плана.');
            return null;
        }

        const payload = new FormData();
        payload.append('index', cleanIndex);

        setStatus(form, `Ищу часы для ${cleanIndex}...`);
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                body: payload,
                credentials: 'same-origin',
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.error || 'Не удалось прочитать учебный план.');
            }
            setStatus(form, `Часы для ${cleanIndex} подтянуты из ${data.source}.`, 'ok');
            return data.item || null;
        } catch (error) {
            setStatus(form, error.message, 'error');
            return null;
        }
    }

    function setupProfForm(form) {
        const indexSelect = document.getElementById('competency_index');
        if (!indexSelect) return;

        async function update() {
            const item = await loadHours(form, indexSelect.value);
            if (!item) return;
            setField('hours_lecture', item.lecture || 0);
            setField('hours_practice', item.practice || 0);
            setField('hours_self', item.self || 0);
            setField('hours_exam', item.attestation || 0);
            if (typeof window.calculateTotal === 'function') {
                window.calculateTotal();
            }
        }

        indexSelect.addEventListener('change', update);
    }

    function setupMdkForm(form) {
        const indexSelect = document.getElementById('mdk_index');
        if (!indexSelect) return;

        async function update() {
            const item = await loadHours(form, indexSelect.value);
            if (!item) return;
            setField('mdk_workload_classes_hours', item.classes || item.total || 0);
            setField('mdk_workload_self_hours', item.self || 0);
            setField('mdk_workload_consultations_hours', item.consultations || 0);
            setField('mdk_workload_attestation_hours', item.attestation || 0);
            if (typeof window.updateWorkloadTotals === 'function') {
                window.updateWorkloadTotals();
            }
        }

        indexSelect.addEventListener('change', update);
    }

    function practicePlanIndex() {
        const kind = (document.getElementById('practice_kind')?.value || '').toLowerCase();
        const moduleIndex = (document.getElementById('professional_module_index')?.value || '').trim().toUpperCase();
        if (!moduleIndex) return '';
        if (/^(УП|ПП|ПДП)\./i.test(moduleIndex)) {
            return moduleIndex;
        }
        const match = moduleIndex.match(/(\d{2})/);
        if (!match) return moduleIndex;
        const prefix = kind.includes('производ') ? 'ПП' : 'УП';
        return `${prefix}.${match[1]}.01`;
    }

    function setupPracticeForm(form) {
        const moduleIndex = document.getElementById('professional_module_index');
        const practiceKind = document.getElementById('practice_kind');
        if (!moduleIndex || !practiceKind) return;

        async function update() {
            const index = practicePlanIndex();
            const item = await loadHours(form, index);
            if (!item) return;
            setField('practice_semester', item.semester);
            setField('practice_hours', item.total);
            setField('practice_weeks', item.weeks);
        }

        moduleIndex.addEventListener('change', update);
        moduleIndex.addEventListener('blur', update);
        practiceKind.addEventListener('change', update);
    }

    document.addEventListener('DOMContentLoaded', () => {
        const profForm = document.getElementById('mainForm');
        const mdkForm = document.getElementById('mdkForm');
        const practiceForm = document.getElementById('pracForm');
        if (profForm) setupProfForm(profForm);
        if (mdkForm) setupMdkForm(mdkForm);
        if (practiceForm) setupPracticeForm(practiceForm);
    });
})();
