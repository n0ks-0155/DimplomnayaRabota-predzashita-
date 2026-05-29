(function () {
    const form = document.querySelector('form');
    if (!form) return;

    const state = {
        activeField: null,
        lastText: '',
    };
    const aiStorageKey = 'rpd-ai-assistant-enabled';
    const disabledText = 'AI-помощник отключён. Включите его в настройках, чтобы получить точную формулировку для этого поля.';

    function isAiEnabled() {
        return localStorage.getItem(aiStorageKey) === '1';
    }

    function isFieldAvailable(field) {
        if (!field || field.disabled || field.hidden) return false;
        if (field.offsetParent === null && !field.closest('.formula-dialog')) return false;
        return true;
    }

    function getTemplateType() {
        const templateInput = form.querySelector('input[name="template"]');
        return templateInput ? templateInput.value : '';
    }

    function isProfTemplate() {
        return getTemplateType() === 'prof';
    }

    function isOpKosForm() {
        return isProfTemplate() && Boolean(document.getElementById('kos-page'));
    }

    function fieldValue(selector) {
        const field = form.querySelector(selector);
        return field ? String(field.value || '').trim() : '';
    }

    function selectedText(selector) {
        const select = form.querySelector(selector);
        if (!select || !select.options || select.selectedIndex < 0) return '';
        return select.options[select.selectedIndex].textContent.trim();
    }

    function getFieldLabel(field) {
        const explicitContext = field.closest('[data-ai-context]')?.dataset.aiContext;
        if (explicitContext) return explicitContext.trim();
        if (field.id) {
            const label = form.querySelector(`label[for="${CSS.escape(field.id)}"]`);
            if (label) return label.textContent.trim().replace(/:$/, '');
        }
        const criterionLabel = field.closest('.mdk-assessment-criterion')?.querySelector('.mdk-checkbox-label');
        if (criterionLabel) return criterionLabel.textContent.trim().replace(/\s+/g, ' ');
        const groupLabel = field.closest('.form-group, td, .control-task-row, .control-answer-row, .test-question-row, .test-answer-row')?.querySelector('label');
        if (groupLabel) return groupLabel.textContent.trim().replace(/:$/, '');
        return field.placeholder || field.name || 'Поле формы';
    }

    function getFields() {
        return [...form.elements]
            .filter((field) => field.name && !['hidden', 'button', 'submit', 'reset', 'password'].includes(field.type))
            .map((field) => ({
                name: field.name,
                label: getFieldLabel(field),
                value: String(field.value || ''),
                required: field.required,
                type: field.tagName.toLowerCase() === 'textarea' ? 'textarea' : field.type,
            }));
    }

    function collectTopics() {
        const topics = [];
        document.querySelectorAll(
            '.mdk-plan-topic, .topic-item, [name^="topic_title_"], .control-topic-input'
        ).forEach((node) => {
            if (node.matches && node.matches('input, textarea')) {
                if (node.value.trim()) topics.push({ title: node.value.trim() });
                return;
            }
            const title = node.querySelector?.('.mdk-topic-title, .mdk-plan-topic-title-input, [name^="topic_title_"], input[placeholder*="тем"]')?.value;
            const content = node.querySelector?.('.mdk-plan-content, [name^="topic_content_"]')?.value;
            if (title || content) {
                topics.push({ title: (title || content || '').trim(), content: (content || '').trim() });
            }
        });
        return topics.filter((item) => item.title || item.content).slice(0, 100);
    }

    function collectPcs() {
        const pcs = [];
        const seen = new Set();
        const selectors = [
            '.mdk-pc-select',
            '[class*="pc-select"]',
            '#results-body input[name^="result_code_"]',
            '#kos-ok-groups .kos-ok-code',
        ];

        document.querySelectorAll(selectors.join(', ')).forEach((field) => {
            const rawValue = String(field.value || '').trim();
            if (!rawValue) return;
            rawValue.split(/\r?\n/).map((item) => item.trim()).filter(Boolean).forEach((code) => {
                if (seen.has(code)) return;
                seen.add(code);
                pcs.push({
                    code,
                    description: field.options ? field.options[field.selectedIndex]?.textContent.trim() || '' : '',
                });
            });
        });
        return pcs.slice(0, 100);
    }

    function collectKosState() {
        return {
            questions: [
                ...document.querySelectorAll(
                    '#oral-questions-container input, #mdkKosQuestions textarea, [name="oral_question[]"]'
                ),
            ].map((field) => field.value.trim()).filter(Boolean),
            tests: [...document.querySelectorAll('#test-examples-container .test-example-item')].map((item) => ({
                question: item.querySelector('[name="test_question[]"]')?.value.trim() || '',
            })).filter((item) => item.question),
            tickets: [...document.querySelectorAll('#mdkKosTickets .mdk-kos-ticket')].map((ticket) => ({
                questions: [...ticket.querySelectorAll('.mdk-kos-ticket-question-text')].map((field) => field.value.trim()).filter(Boolean),
            })).filter((ticket) => ticket.questions.length),
            control_works: [...document.querySelectorAll('#control-works-container .control-work-item')].map((work) => ({
                topic: work.querySelector('.control-topic-input')?.value.trim() || '',
                tasks: [...work.querySelectorAll('.control-task-input')].map((field) => field.value.trim()).filter(Boolean),
            })).filter((work) => work.topic || work.tasks.length),
        };
    }

    function collectContext() {
        return {
            template: getTemplateType(),
            discipline_name: fieldValue('[name="discipline_name"]'),
            competency_index: fieldValue('[name="competency_index"]'),
            mdk_index: fieldValue('[name="mdk_index"]'),
            speciality: fieldValue('[name="speciality"]'),
            speciality_name: fieldValue('[name="speciality_name"]'),
            professional_module: fieldValue('[name="professional_module"]'),
            professional_module_text: selectedText('[name="professional_module"]'),
            discipline_type: fieldValue('[name="discipline_type"]'),
        };
    }

    async function requestAssistant(action, extra = {}) {
        const response = await fetch('/ai-assistant', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action,
                context: collectContext(),
                fields: getFields(),
                topics: collectTopics(),
                pcs: collectPcs(),
                kos: collectKosState(),
                ...extra,
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
            throw new Error(data.error || 'ИИ-помощник временно недоступен.');
        }
        return data;
    }

    function ensurePanel() {
        let panel = document.getElementById('ai-assistant-panel');
        if (panel) return panel;

        panel = document.createElement('aside');
        panel.id = 'ai-assistant-panel';
        panel.className = 'ai-assistant-panel';
        panel.hidden = true;
        panel.innerHTML = `
            <div class="ai-assistant-panel-head">
                <div>
                    <div class="ai-assistant-eyebrow">ИИ-помощник РПД</div>
                    <h3 id="ai-assistant-title">Помощник</h3>
                </div>
                <button type="button" class="btn-small ai-assistant-close" aria-label="Закрыть">Закрыть</button>
            </div>
            <div class="ai-assistant-content"></div>
            <div class="ai-assistant-actions"></div>
        `;
        document.body.appendChild(panel);
        panel.querySelector('.ai-assistant-close').addEventListener('click', () => {
            panel.hidden = true;
        });
        return panel;
    }

    function showPanel(title, content, actions = []) {
        const panel = ensurePanel();
        panel.hidden = false;
        panel.querySelector('#ai-assistant-title').textContent = title;
        panel.querySelector('.ai-assistant-content').innerHTML = content;
        const actionsBox = panel.querySelector('.ai-assistant-actions');
        actionsBox.innerHTML = '';
        actions.forEach((action) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = action.secondary ? 'btn btn-secondary' : 'btn';
            button.textContent = action.label;
            button.addEventListener('click', action.onClick);
            actionsBox.appendChild(button);
        });
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function setFieldValue(field, value, mode = 'replace') {
        if (!field) return;
        if (mode === 'append' && field.value.trim()) {
            field.value = `${field.value.trim()}\n${value}`;
        } else {
            field.value = value;
        }
        field.dispatchEvent(new Event('input', { bubbles: true }));
        field.dispatchEvent(new Event('change', { bubbles: true }));
        field.focus();
    }

    function buildActiveFieldContext(field) {
        const card = field.closest('.mdk-assessment-card, .mdk-result-card, .mdk-kos-card, .mdk-plan-topic, .topic-item, .control-work-item, .control-task-item, .test-example-item, .kos-ok-group, .mdk-activity, .mdk-room, .mdk-source-group');
        const context = {
            field_label: getFieldLabel(field),
            field_name: field.name || field.className || field.id || '',
            field_placeholder: field.placeholder || '',
            section_title: field.closest('.form-section')?.querySelector('h3, h4')?.textContent.trim() || '',
        };

        if (card) {
            context.card_title = card.querySelector('h4, h5, strong, .control-work-num, .control-task-num, .mdk-kos-card-header h4')?.textContent.trim() || '';
            context.nearby_values = [...card.querySelectorAll('input, textarea, select')]
                .filter((item) => item !== field)
                .slice(0, 12)
                .map((item) => ({
                    label: getFieldLabel(item),
                    value: String(item.value || '').trim(),
                }))
                .filter((item) => item.value);
        }

        return context;
    }

    function updateAiButtonsState() {
        const enabled = isAiEnabled();
        document.querySelectorAll('.ai-suggest-button').forEach((button) => {
            const field = button.previousElementSibling;
            const available = isFieldAvailable(field);
            button.hidden = !available;
            button.disabled = !enabled || !available;
            button.classList.toggle('is-disabled', !enabled);
            button.title = enabled ? 'Предложить точный текст для этого поля' : disabledText;
            button.setAttribute('aria-disabled', String(!enabled || !available));
        });

        document.querySelectorAll('#ai-check-document, #ai-generate-kos').forEach((button) => {
            button.disabled = !enabled;
            button.classList.toggle('is-disabled', !enabled);
            button.title = enabled ? '' : disabledText;
        });
    }

    async function suggestForField(field) {
        state.activeField = field;
        if (!isAiEnabled()) {
            showPanel('AI-помощник отключён', `<p>${escapeHtml(disabledText)}</p>`);
            return;
        }
        showPanel('Готовлю формулировку', '<p>Помощник анализирует поле и данные формы...</p>');
        try {
            const data = await requestAssistant('suggest_text', {
                label: getFieldLabel(field),
                placeholder: field.placeholder || '',
                current_value: field.value || '',
                active_context: buildActiveFieldContext(field),
            });
            const text = data.text || '';
            state.lastText = text;
            if (!field.value.trim()) {
                setFieldValue(field, text);
                showPanel('Текст вставлен', `<p>${escapeHtml(data.notice || 'Формулировка добавлена в поле.')}</p>`);
                return;
            }
            showPanel(
                'Предложенный текст',
                `<p>${escapeHtml(text)}</p>${data.notice ? `<small>${escapeHtml(data.notice)}</small>` : ''}`,
                [
                    { label: 'Заменить поле', onClick: () => setFieldValue(field, text) },
                    { label: 'Добавить в конец', secondary: true, onClick: () => setFieldValue(field, text, 'append') },
                ],
            );
        } catch (error) {
            showPanel('Ошибка помощника', `<p>${escapeHtml(error.message)}</p>`);
        }
    }

    function enhanceTextareas(root = document) {
        root.querySelectorAll('textarea').forEach((field) => {
            if (field.dataset.aiEnhanced || field.id === 'formula-input') return;
            if (field.closest('.ai-assistant-panel')) return;
            if (field.closest('#kos-ok-groups')) return;
            field.dataset.aiEnhanced = '1';
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn-small ai-suggest-button';
            button.textContent = 'ИИ: предложить текст';
            button.addEventListener('click', () => suggestForField(field));
            field.insertAdjacentElement('afterend', button);
        });
        updateAiButtonsState();
    }

    function runCollectors() {
        [
            'collectMdkActivities',
            'collectMdkPcResults',
            'collectMdkThematicPlan',
            'collectMdkRooms',
            'collectMdkSources',
            'collectMdkAssessments',
            'collectMdkKosResults',
            'collectMdkKosQuestions',
            'collectMdkKosTickets',
        ].forEach((name) => {
            if (typeof window[name] === 'function') {
                try { window[name](); } catch (_) {}
            }
        });
    }

    async function checkDocument() {
        if (!isAiEnabled()) {
            showPanel('AI-помощник отключён', `<p>${escapeHtml(disabledText)}</p>`);
            return;
        }
        runCollectors();
        showPanel('Проверяю заполнение', '<p>Помощник проверяет обязательные поля, темы, компетенции и КОС...</p>');
        try {
            const data = await requestAssistant('check_document');
            const issues = (data.issues || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
            const suggestions = (data.suggestions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
            showPanel(
                'Результат проверки',
                `<h4>Замечания</h4><ol>${issues}</ol><h4>Рекомендации</h4><ol>${suggestions}</ol>${data.notice ? `<small>${escapeHtml(data.notice)}</small>` : ''}`,
            );
        } catch (error) {
            showPanel('Ошибка проверки', `<p>${escapeHtml(error.message)}</p>`);
        }
    }

    function findFirstEmptyOrCreate(containerSelector, rowSelector, addButtonSelector, inputSelector) {
        const container = document.querySelector(containerSelector);
        if (!container) return null;
        let row = [...container.querySelectorAll(rowSelector)].find((item) => {
            const input = item.querySelector(inputSelector);
            return input && !input.value.trim();
        });
        if (!row) {
            document.querySelector(addButtonSelector)?.click();
            row = [...container.querySelectorAll(rowSelector)].at(-1);
        }
        return row ? row.querySelector(inputSelector) : null;
    }

    function applyGeneratedKos(data) {
        const normalized = normalizeGeneratedKosData(data);
        const questions = normalized.questions;
        const tests = normalized.test_examples;
        const tickets = normalized.tickets;
        const controlWorks = normalized.control_works;
        const results = normalized.kos_results;

        questions.forEach((question) => {
            const mdkField = findFirstEmptyOrCreate('#mdkKosQuestions', '.mdk-kos-question-row', '#addMdkKosQuestion', '.mdk-kos-question-text');
            if (mdkField) {
                setFieldValue(mdkField, question);
                return;
            }
            const opField = findFirstEmptyOrCreate('#oral-questions-container', '.oral-question-item', '#add-oral-question-btn', 'input');
            if (opField) setFieldValue(opField, question);
        });

        tests.forEach((test) => {
            const container = document.getElementById('test-examples-container');
            if (!container) return;
            let item = [...container.querySelectorAll('.test-example-item')].find((row) => !row.querySelector('[name="test_question[]"]')?.value.trim());
            if (!item) {
                if (typeof window.addTestExample === 'function') {
                    window.addTestExample();
                } else {
                    document.querySelector('[onclick="addTestExample()"]')?.click();
                }
                item = [...container.querySelectorAll('.test-example-item')].at(-1);
            }
            if (!item) return;
            setFieldValue(item.querySelector('[name="test_question[]"]'), test.question || '');
            const answers = test.answers || [];
            ['a', 'b', 'c', 'd'].forEach((letter, index) => {
                const field = item.querySelector(`[name="test_answer_${letter}[]"]`);
                if (field && answers[index]) setFieldValue(field, answers[index]);
            });
        });

        const opControlWorks = controlWorks.length
            ? controlWorks
            : (isOpKosForm() ? tickets.map((ticket, index) => ({
                topic: `Контрольная работа ${index + 1}`,
                variants: [{ tasks: (ticket.questions || []).map((question) => ({ text: question, answers: [] })) }],
            })) : []);

        applyGeneratedControlWorks(opControlWorks);

        tickets.forEach((ticket) => {
            const container = document.getElementById('mdkKosTickets');
            if (!container) return;
            let ticketNode = [...container.querySelectorAll('.mdk-kos-ticket')].find((item) => {
                return ![...item.querySelectorAll('.mdk-kos-ticket-question-text')].some((field) => field.value.trim());
            });
            if (!ticketNode) {
                document.getElementById('addMdkKosTicket')?.click();
                ticketNode = [...container.querySelectorAll('.mdk-kos-ticket')].at(-1);
            }
            (ticket.questions || []).forEach((question) => {
                let field = [...ticketNode.querySelectorAll('.mdk-kos-ticket-question-text')].find((item) => !item.value.trim());
                if (!field) {
                    ticketNode.querySelector('.mdk-add-kos-ticket-question')?.click();
                    field = [...ticketNode.querySelectorAll('.mdk-kos-ticket-question-text')].at(-1);
                }
                if (field) setFieldValue(field, question);
            });
        });

        results.forEach((group) => {
            const card = [...document.querySelectorAll('#mdkKosResults .mdk-kos-card')].find((item) => item.dataset.code === group.code);
            if (!card) {
                applyGeneratedOpKosResult(group);
                return;
            }
            (group.items || []).forEach((item) => {
                let row = [...card.querySelectorAll('.mdk-kos-result-row')].find((node) => {
                    return !node.querySelector('.mdk-kos-result-code')?.value.trim() && !node.querySelector('.mdk-kos-result-name')?.value.trim();
                });
                if (!row) {
                    card.querySelector('.mdk-add-kos-result')?.click();
                    row = [...card.querySelectorAll('.mdk-kos-result-row')].at(-1);
                }
                if (!row) return;
                setFieldValue(row.querySelector('.mdk-kos-result-code'), item.result_code || '');
                setFieldValue(row.querySelector('.mdk-kos-result-name'), item.result_name || '');
            });
        });
    }

    function findEmptyOpKosGroup() {
        return [...document.querySelectorAll('#kos-ok-groups .kos-ok-group')].find((group) => {
            const code = group.querySelector('.kos-ok-code')?.value.trim();
            const hasItems = [...group.querySelectorAll('.kos-result-item')].some((item) => {
                return item.querySelector('.kos-res-code')?.value.trim() || item.querySelector('.kos-res-desc')?.value.trim();
            });
            return !code && !hasItems;
        });
    }

    function ensureOpKosGroup() {
        const container = document.getElementById('kos-ok-groups');
        if (!container) return null;
        let group = findEmptyOpKosGroup();
        if (!group) {
            if (typeof window.addKosOkGroup === 'function') {
                window.addKosOkGroup();
            } else {
                document.getElementById('add-kos-ok-group-btn')?.click();
            }
            group = [...container.querySelectorAll('.kos-ok-group')].at(-1);
        }
        return group || null;
    }

    function applyGeneratedOpKosResult(groupData) {
        const group = ensureOpKosGroup();
        if (!group) return;
        setFieldValue(group.querySelector('.kos-ok-code'), groupData.code || '');

        (groupData.items || []).forEach((item) => {
            let row = [...group.querySelectorAll('.kos-result-item')].find((node) => {
                return !node.querySelector('.kos-res-code')?.value.trim() && !node.querySelector('.kos-res-desc')?.value.trim();
            });
            if (!row) {
                if (typeof window.addKosResultToGroup === 'function') {
                    window.addKosResultToGroup(group);
                } else {
                    group.querySelector('.add-kos-result-to-group')?.click();
                }
                row = [...group.querySelectorAll('.kos-result-item')].at(-1);
            }
            if (!row) return;
            setFieldValue(row.querySelector('.kos-res-code'), item.result_code || item.code || item.rescode || '');
            setFieldValue(row.querySelector('.kos-res-desc'), item.result_name || item.name || item.desc || item.description || '');
        });
    }

    function findEmptyControlWork() {
        return [...document.querySelectorAll('#control-works-container .control-work-item')].find((work) => {
            return ![...work.querySelectorAll('input, textarea')].some((field) => field.value.trim());
        });
    }

    function ensureControlWork() {
        const container = document.getElementById('control-works-container');
        if (!container) return null;
        let work = findEmptyControlWork();
        if (!work) {
            if (typeof window.addControlWork === 'function') {
                window.addControlWork();
            } else {
                document.getElementById('add-control-work-btn')?.click();
            }
            work = [...container.querySelectorAll('.control-work-item')].at(-1);
        }
        return work || null;
    }

    function ensureControlVariant(work, index) {
        let variants = [...work.querySelectorAll(':scope > .control-variants-container > .control-variant-item')];
        while (variants.length <= index) {
            const addButton = work.querySelector('.control-work-header button[onclick*="addControlVariant"]');
            addButton?.click();
            variants = [...work.querySelectorAll(':scope > .control-variants-container > .control-variant-item')];
        }
        return variants[index] || null;
    }

    function ensureControlTask(variant, index) {
        let tasks = [...variant.querySelectorAll(':scope > .control-tasks-container > .control-task-item')];
        while (tasks.length <= index) {
            const addButton = variant.querySelector('.control-variant-header button[onclick*="addControlTask"]');
            addButton?.click();
            tasks = [...variant.querySelectorAll(':scope > .control-tasks-container > .control-task-item')];
        }
        return tasks[index] || null;
    }

    function applyGeneratedControlWorks(controlWorks) {
        if (!isOpKosForm() || !controlWorks.length) return;
        controlWorks.forEach((workData) => {
            const work = ensureControlWork();
            if (!work) return;
            setFieldValue(work.querySelector('.control-topic-input'), workData.topic || '');
            const variants = Array.isArray(workData.variants) && workData.variants.length ? workData.variants : [{ tasks: workData.tasks || [] }];
            variants.forEach((variantData, variantIndex) => {
                const variant = ensureControlVariant(work, variantIndex);
                if (!variant) return;
                const tasks = Array.isArray(variantData.tasks) ? variantData.tasks : [];
                tasks.forEach((taskData, taskIndex) => {
                    const task = ensureControlTask(variant, taskIndex);
                    if (!task) return;
                    const text = typeof taskData === 'string' ? taskData : (taskData.text || taskData.question || '');
                    setFieldValue(task.querySelector('.control-task-input'), text);
                    const answers = typeof taskData === 'object' && Array.isArray(taskData.answers) ? taskData.answers : [];
                    task.querySelectorAll('.control-answer-input').forEach((field, answerIndex) => {
                        const answer = answers[answerIndex];
                        if (answer) setFieldValue(field, typeof answer === 'object' ? answer.text || '' : answer);
                    });
                });
            });
        });
    }

    function normalizeGeneratedKosData(data) {
        const raw = data || {};
        return {
            questions: Array.isArray(raw.questions) ? raw.questions : [],
            test_examples: Array.isArray(raw.test_examples) ? raw.test_examples : (Array.isArray(raw.tests) ? raw.tests : []),
            tickets: Array.isArray(raw.tickets) ? raw.tickets : [],
            control_works: Array.isArray(raw.control_works) ? raw.control_works : (Array.isArray(raw.works) ? raw.works : []),
            kos_results: Array.isArray(raw.kos_results) ? raw.kos_results : (Array.isArray(raw.results) ? raw.results : []),
        };
    }

    async function generateKosByTopics() {
        if (!isAiEnabled()) {
            showPanel('AI-помощник отключён', `<p>${escapeHtml(disabledText)}</p>`);
            return;
        }
        runCollectors();
        showPanel('Генерирую КОС', '<p>Помощник готовит вопросы, тесты, билеты и результаты по темам...</p>');
        try {
            const response = await requestAssistant('generate_kos');
            const data = normalizeGeneratedKosData(response.data || response);
            const previewQuestions = (data.questions || []).slice(0, 6).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
            const previewTickets = (data.tickets || []).length;
            const previewWorks = (data.control_works || []).length;
            const tailLabel = isOpKosForm()
                ? `контрольных работ: ${previewWorks}`
                : `билетов: ${previewTickets}`;
            showPanel(
                'Черновик КОС готов',
                `<p>Подготовлено вопросов: ${(data.questions || []).length}, тестов: ${(data.test_examples || []).length}, ${tailLabel}.</p><ol>${previewQuestions}</ol>${response.notice ? `<small>${escapeHtml(response.notice)}</small>` : ''}`,
                [
                    { label: 'Вставить в форму', onClick: () => applyGeneratedKos(data) },
                    { label: 'Оставить как черновик', secondary: true, onClick: () => {} },
                ],
            );
        } catch (error) {
            showPanel('Ошибка генерации КОС', `<p>${escapeHtml(error.message)}</p>`);
        }
    }

    function addActionButtons() {
        const submit = form.querySelector('button[type="submit"]');
        if (submit && !document.getElementById('ai-check-document')) {
            const checkButton = document.createElement('button');
            checkButton.type = 'button';
            checkButton.id = 'ai-check-document';
            checkButton.className = 'btn btn-secondary ai-check-document';
            checkButton.textContent = 'ИИ: проверить заполнение';
            checkButton.addEventListener('click', checkDocument);
            submit.insertAdjacentElement('beforebegin', checkButton);
        }

        const kosTarget = document.querySelector('#kos-page .kos-hero, #mdk-kos-page .mdk-kos-hero');
        if (kosTarget && !document.getElementById('ai-generate-kos')) {
            const button = document.createElement('button');
            button.type = 'button';
            button.id = 'ai-generate-kos';
            button.className = 'btn btn-secondary ai-generate-kos';
            button.textContent = 'ИИ: сгенерировать КОС по темам';
            button.addEventListener('click', generateKosByTopics);
            kosTarget.appendChild(button);
        }
    }

    window.addEventListener('ai-assistant-setting-changed', updateAiButtonsState);
    document.addEventListener('change', (event) => {
        if (event.target.matches('.mdk-assessment-criterion input[type="checkbox"]')) {
            setTimeout(() => {
                enhanceTextareas(event.target.closest('.mdk-assessment-card') || document);
                updateAiButtonsState();
            }, 0);
        }
    });

    enhanceTextareas();
    addActionButtons();
    updateAiButtonsState();

    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType !== Node.ELEMENT_NODE) return;
                enhanceTextareas(node);
            });
        });
        addActionButtons();
        updateAiButtonsState();
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
