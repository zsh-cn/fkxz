(function() {
    'use strict';

    var REPO = 'zsh-cn/fkxz';
    var CACHE_KEY = 'fkxz_release_cache';
    var CACHE_TTL = 3600000;
    var THEME_KEY = 'fkxz-theme';

    var prefersReducedMotion = function() {
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    };

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
                } catch (e) {}
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

        initTheme: function() {
            var btn = document.querySelector('.theme-toggle');
            if (!btn) return;

            var root = document.documentElement;
            var sync = function() {
                var dark = root.classList.contains('dark');
                btn.setAttribute('aria-label', dark ? '切换到浅色模式' : '切换到深色模式');
                btn.setAttribute('title', dark ? '切换到浅色模式' : '切换到深色模式');
                btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
            };

            sync();

            btn.addEventListener('click', function() {
                var dark = root.classList.toggle('dark');
                try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (e) {}
                sync();
            });
        },

        initTabs: function() {
            document.querySelectorAll('.tabs').forEach(function(tabGroup) {
                var buttons = Array.prototype.slice.call(tabGroup.querySelectorAll('.tab-btn'));

                buttons.forEach(function(btn) {
                    btn.setAttribute('role', 'tab');
                    btn.setAttribute('aria-selected', btn.classList.contains('active') ? 'true' : 'false');
                });
                tabGroup.setAttribute('role', 'tablist');

                tabGroup.addEventListener('click', function(e) {
                    var btn = e.target.closest('.tab-btn');
                    if (!btn) return;

                    var container = tabGroup.closest('.tab-container') || tabGroup.parentElement;
                    var tabName = btn.getAttribute('data-tab');
                    if (!tabName) return;

                    buttons.forEach(function(t) {
                        var on = t === btn;
                        t.classList.toggle('active', on);
                        t.setAttribute('aria-selected', on ? 'true' : 'false');
                    });

                    container.querySelectorAll('.tab-panel').forEach(function(p) {
                        p.classList.toggle('active', p.getAttribute('data-tab') === tabName);
                    });
                });
            });
        },

        initCopy: function() {
            var ICON_COPY = '<svg class="icon-copy" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M6.5 15H5.5A1.5 1.5 0 014 13.5v-8A1.5 1.5 0 015.5 4h8A1.5 1.5 0 0115 5.5v1"/></svg>';
            var ICON_CHECK = '<svg class="icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>';

            document.querySelectorAll('.code-block').forEach(function(block) {
                var pre = block.querySelector('pre');
                if (!pre || !navigator.clipboard) return;

                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'copy-btn';
                btn.setAttribute('aria-label', '复制代码');
                btn.setAttribute('title', '复制代码');
                btn.innerHTML = ICON_COPY + ICON_CHECK;

                btn.addEventListener('click', function() {
                    navigator.clipboard.writeText(pre.innerText).then(function() {
                        btn.classList.add('copied');
                        btn.setAttribute('title', '已复制');
                        setTimeout(function() {
                            btn.classList.remove('copied');
                            btn.setAttribute('title', '复制代码');
                        }, 1600);
                    }).catch(function() {});
                });

                block.appendChild(btn);
            });
        },

        initReveal: function() {
            if (!('IntersectionObserver' in window) || prefersReducedMotion()) return;

            var selector = '.feature-card, .platform-card, .download-card, .web-exp-card, .step, ' +
                           '.req-card, .usage-detail, .mode-card, .table-wrap';
            var items = document.querySelectorAll(selector);
            if (!items.length) return;

            var observer = new IntersectionObserver(function(entries) {
                entries.forEach(function(entry) {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add('is-visible');
                    observer.unobserve(entry.target);
                });
            }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });

            items.forEach(function(el, i) {
                var rect = el.getBoundingClientRect();
                if (rect.top < window.innerHeight * 0.9) return;
                el.classList.add('reveal-init');
                el.style.transitionDelay = (Math.min(i, 5) * 40) + 'ms';
                observer.observe(el);
            });
        },

        initHeader: function() {
            var header = document.querySelector('header');
            if (!header) return;

            var onScroll = function() {
                header.classList.toggle('is-scrolled', window.scrollY > 4);
            };

            onScroll();
            window.addEventListener('scroll', onScroll, { passive: true });
        }
    };

    document.addEventListener('DOMContentLoaded', function() {
        window.Fkxz.initTheme();
        window.Fkxz.initHeader();
        window.Fkxz.initCopy();
        window.Fkxz.initReveal();
    });
})();
