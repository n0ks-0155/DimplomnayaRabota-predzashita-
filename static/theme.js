(function () {
    const root = document.documentElement;
    const storageKey = 'kos-theme';
    const aiStorageKey = 'rpd-ai-assistant-enabled';
    const accessibilityStorageKey = 'rpd-vision-accessibility-enabled';
    const moonSvg = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M21 12.79A9 9 0 1 1 11.21 3c.36 0 .52.45.24.67A7 7 0 1 0 20.33 12c.22-.28.67-.12.67.24Z"/></svg>';
    const sunSvg = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4.75a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0V5.5a.75.75 0 0 1 .75-.75Zm0 12.25a.75.75 0 0 1 .75.75v1.5a.75.75 0 1 1-1.5 0v-1.5A.75.75 0 0 1 12 17Zm7.25-5.75a.75.75 0 0 1 0 1.5h-1.5a.75.75 0 0 1 0-1.5h1.5Zm-12.5 0a.75.75 0 0 1 0 1.5h-1.5a.75.75 0 1 1 0-1.5h1.5Zm9.08-4.33a.75.75 0 0 1 1.06 1.06l-1.06 1.06a.75.75 0 0 1-1.06-1.06l1.06-1.06Zm-7.66 7.66a.75.75 0 0 1 1.06 1.06l-1.06 1.06a.75.75 0 1 1-1.06-1.06l1.06-1.06Zm8.72 2.12a.75.75 0 0 1 0 1.06.75.75 0 0 1-1.06 0l-1.06-1.06a.75.75 0 0 1 1.06-1.06l1.06 1.06Zm-7.66-7.66a.75.75 0 0 1 0 1.06.75.75 0 0 1-1.06 0L7.11 8.04a.75.75 0 1 1 1.06-1.06l1.06 1.06ZM12 8.25A3.75 3.75 0 1 1 8.25 12 3.75 3.75 0 0 1 12 8.25Z"/></svg>';
    const gearSvg = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M19.43 12.98c.04-.32.07-.65.07-.98s-.02-.66-.07-.98l2.02-1.57a.5.5 0 0 0 .12-.64l-1.91-3.3a.5.5 0 0 0-.6-.22l-2.38.96a7.1 7.1 0 0 0-1.7-.98l-.36-2.53A.5.5 0 0 0 14.13 2h-3.82a.5.5 0 0 0-.5.42l-.36 2.53c-.61.24-1.18.56-1.7.98l-2.38-.96a.5.5 0 0 0-.6.22l-1.91 3.3a.5.5 0 0 0 .12.64L5 11.02a7.7 7.7 0 0 0 0 1.96l-2.02 1.57a.5.5 0 0 0-.12.64l1.91 3.3a.5.5 0 0 0 .6.22l2.38-.96c.52.41 1.09.74 1.7.98l.36 2.53a.5.5 0 0 0 .5.42h3.82a.5.5 0 0 0 .5-.42l.36-2.53c.61-.24 1.18-.56 1.7-.98l2.38.96a.5.5 0 0 0 .6-.22l1.91-3.3a.5.5 0 0 0-.12-.64l-2.02-1.57ZM12.22 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7Z"/></svg>';
    const glassesSvg = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7.5 10.25c-2.2 0-4 1.8-4 4s1.8 4 4 4a4 4 0 0 0 3.92-3.24h1.16a4 4 0 1 0 .13-1.5h-1.42a4 4 0 0 0-3.79-3.26Zm0 1.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5Zm9 0a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM5.1 7.43a.75.75 0 0 1 .97-.43l3.08 1.18a.75.75 0 1 1-.54 1.4L5.53 8.4a.75.75 0 0 1-.43-.97Zm12.83-.43a.75.75 0 1 1 .54 1.4l-3.08 1.18a.75.75 0 0 1-.54-1.4l3.08-1.18Z"/></svg>';

    function applyTheme(theme) {
        root.setAttribute('data-theme', theme);
        localStorage.setItem(storageKey, theme);
    }

    function applyAccessibility(enabled) {
        if (enabled) {
            root.setAttribute('data-accessibility', 'vision');
        } else {
            root.removeAttribute('data-accessibility');
        }
        localStorage.setItem(accessibilityStorageKey, enabled ? '1' : '0');
    }

    function preferredTheme() {
        const saved = localStorage.getItem(storageKey);
        if (saved === 'dark' || saved === 'light') return saved;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function mountToggle() {
        if (document.querySelector('.theme-toggle')) return;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'theme-toggle';
        btn.setAttribute('aria-live', 'polite');

        function syncState() {
            const isDark = root.getAttribute('data-theme') === 'dark';
            const label = isDark ? 'Включить светлую тему' : 'Включить тёмную тему';
            btn.setAttribute('aria-label', label);
            btn.setAttribute('title', label);
            btn.setAttribute('aria-pressed', String(isDark));
            btn.innerHTML = isDark ? sunSvg : moonSvg;
        }

        btn.addEventListener('click', function () {
            const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            syncState();
        });

        syncState();
        document.body.appendChild(btn);
    }

    function hasFormPage() {
        return Boolean(document.querySelector('form'));
    }

    function mountVisionMode() {
        if (document.querySelector('.vision-toggle')) return;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'theme-toggle vision-toggle';
        btn.innerHTML = glassesSvg;
        btn.setAttribute('aria-label', 'Открыть режим для слабовидящих');
        btn.setAttribute('title', 'Режим для слабовидящих');
        btn.setAttribute('aria-expanded', 'false');

        const panel = document.createElement('div');
        panel.className = 'vision-popover';
        panel.hidden = true;
        panel.innerHTML = `
            <div class="vision-title">Режим для слабовидящих</div>
            <label class="vision-row" for="vision-accessibility-enabled">
                <span>
                    <strong>Адаптировать интерфейс</strong>
                    <small>Крупнее текст, выше контраст, заметнее границы и фокус.</small>
                </span>
                <input type="checkbox" id="vision-accessibility-enabled" class="apple-switch-input">
                <span class="apple-switch" aria-hidden="true"></span>
            </label>
        `;

        const checkbox = panel.querySelector('#vision-accessibility-enabled');
        checkbox.checked = localStorage.getItem(accessibilityStorageKey) === '1';
        checkbox.addEventListener('change', () => {
            applyAccessibility(checkbox.checked);
        });

        btn.addEventListener('click', () => {
            const nextHidden = !panel.hidden ? true : false;
            panel.hidden = nextHidden;
            btn.setAttribute('aria-expanded', String(!nextHidden));
        });

        document.addEventListener('click', (event) => {
            if (panel.hidden || panel.contains(event.target) || btn.contains(event.target)) return;
            panel.hidden = true;
            btn.setAttribute('aria-expanded', 'false');
        });

        document.body.appendChild(btn);
        document.body.appendChild(panel);
    }

    function mountSettings() {
        if (!hasFormPage() || document.querySelector('.settings-toggle')) return;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'theme-toggle settings-toggle';
        btn.innerHTML = gearSvg;
        btn.setAttribute('aria-label', 'Открыть настройки');
        btn.setAttribute('title', 'Настройки');
        btn.setAttribute('aria-expanded', 'false');

        const panel = document.createElement('div');
        panel.className = 'settings-popover';
        panel.hidden = true;
        panel.innerHTML = `
            <div class="settings-title">Настройки</div>
            <label class="settings-row" for="ai-assistant-enabled">
                <span>
                    <strong>Включение AI-помощника <span class="settings-beta">(БЕТА)</span></strong>
                    <small>Ответы, выдаваемые AI, могут быть неточными.</small>
                </span>
                <input type="checkbox" id="ai-assistant-enabled" class="apple-switch-input">
                <span class="apple-switch" aria-hidden="true"></span>
            </label>
        `;

        const checkbox = panel.querySelector('#ai-assistant-enabled');
        checkbox.checked = localStorage.getItem(aiStorageKey) === '1';
        checkbox.addEventListener('change', () => {
            localStorage.setItem(aiStorageKey, checkbox.checked ? '1' : '0');
            window.dispatchEvent(new CustomEvent('ai-assistant-setting-changed', {
                detail: { enabled: checkbox.checked }
            }));
        });

        btn.addEventListener('click', () => {
            const nextHidden = !panel.hidden ? true : false;
            panel.hidden = nextHidden;
            btn.setAttribute('aria-expanded', String(!nextHidden));
        });

        document.addEventListener('click', (event) => {
            if (panel.hidden || panel.contains(event.target) || btn.contains(event.target)) return;
            panel.hidden = true;
            btn.setAttribute('aria-expanded', 'false');
        });

        document.body.appendChild(btn);
        document.body.appendChild(panel);
    }

    applyTheme(preferredTheme());
    applyAccessibility(localStorage.getItem(accessibilityStorageKey) === '1');
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            mountToggle();
            mountVisionMode();
            mountSettings();
        });
    } else {
        mountToggle();
        mountVisionMode();
        mountSettings();
    }
})();
