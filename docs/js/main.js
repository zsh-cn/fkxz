(function() {
    'use strict';

    var REPO = 'zsh-cn/fkxz';
    var ASSETS = ['cli.exe', 'main.exe', 'file_splitter.exe', 'file_downloader.exe'];
    var CACHE_KEY = 'fkxz_release_cache';
    var CACHE_TTL = 3600000;

    window.Fkxz = {
        REPO: REPO,
        ASSETS: ASSETS,

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
                    var assets = (data.assets || []).map(function(a) {
                        return { name: a.name, browser_download_url: a.browser_download_url };
                    });

                    var cacheData = { ts: Date.now(), version: version, assets: assets };
                    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cacheData));
                    callback(null, cacheData);
                })
                .catch(function(err) {
                    callback(err);
                });
        },

        getAssetUrl: function(assets, name) {
            for (var i = 0; i < assets.length; i++) {
                if (assets[i].name === name) return assets[i].browser_download_url;
            }
            return null;
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

        updateDownloadLinks: function(assets) {
            var btns = document.querySelectorAll('.download-btn[data-asset]');
            btns.forEach(function(btn) {
                var name = btn.getAttribute('data-asset');
                var url = Fkxz.getAssetUrl(assets, name);
                if (url) {
                    btn.href = url;
                } else {
                    btn.href = 'https://github.com/' + REPO + '/releases/latest';
                }
            });
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