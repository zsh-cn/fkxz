(function() {
    'use strict';

    var REPO = 'zsh-cn/fkxz';
    var CACHE_KEY = 'fkxz_release_cache';
    var CACHE_TTL = 3600000;

    window.Fkxz = {
        REPO: REPO,

        getRelease: function(callback) {
            var cached = sessionStorage.getItem(CACHE_KEY);
            if (cached) {
                try {
                    var data = JSON.parse(cached);
                    if (Date.now() - data.ts < CACHE_TTL) {
                        callback(null, data);
                        return;
                    }
                } catch(e) {}
            }

            fetch('https://api.github.com/repos/' + REPO + '/releases/latest')
                .then(function(res) {
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    return res.json();
                })
                .then(function(data) {
                    var version = data.tag_name || data.name || 'Unknown';

                    var cacheData = { ts: Date.now(), version: version };
                    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cacheData));
                    callback(null, cacheData);
                })
                .catch(function(err) {
                    callback(err);
                });
        },

        updateVersionBadge: function(el, version) {
            if (!el) return;
            var textEl = el.querySelector('.version-text');
            el.classList.remove('loading', 'error');
            el.classList.add('loaded');
            if (textEl) textEl.textContent = version;
            el.href = 'https://github.com/' + REPO + '/releases/tag/' + version;
        },

        showVersionError: function(el) {
            if (!el) return;
            var textEl = el.querySelector('.version-text');
            el.classList.remove('loading');
            el.classList.add('error');
            if (textEl) textEl.textContent = '无法获取版本信息';
        },

        initTabs: function() {
            document.querySelectorAll('.tabs').forEach(function(tabGroup) {
                tabGroup.addEventListener('click', function(e) {
                    var btn = e.target.closest('.tab-btn');
                    if (!btn) return;

                    var tabs = tabGroup.querySelectorAll('.tab-btn');
                    var tabName = btn.getAttribute('data-tab');
                    var container = tabGroup.closest('.tab-container');
                    if (!container) {
                        container = tabGroup.parentElement;
                    }

                    tabs.forEach(function(t) { t.classList.remove('active'); });
                    btn.classList.add('active');

                    var panels = container.querySelectorAll(':scope > .tab-panel, .tab-panel');
                    panels.forEach(function(p) {
                        if (p.getAttribute('data-tab') === tabName) {
                            p.classList.add('active');
                        } else {
                            p.classList.remove('active');
                        }
                    });
                });
            });
        }
    };
})();