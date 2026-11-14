self.addEventListener('install', (event) => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // 警告：别动这个判断顺序！通用 OPTIONS 分支一旦排到 /fkxz 前面，Edge 下载前探测会收到空 204，浏览器直接不创建下载任务（2026-11 踩过坑）。
    // /fkxz 是下载入口：任何方法（含 OPTIONS 探测）都必须生成带 Content-Disposition 的下载响应，
    // 否则浏览器不会创建下载任务。此判断必须放在通用 OPTIONS 分支之前。
    if (url.pathname.endsWith('/fkxz')) {
        const fkxUrl = url.searchParams.get('fkx');
        const resumeParam = url.searchParams.get('resume');
        const resumeOffset = resumeParam ? parseInt(resumeParam, 10) || 0 : 0;
        if (fkxUrl) {
            event.respondWith(
                streamDownload(fkxUrl, event.request, resumeOffset).catch(e => {
                    console.error('下载失败:', e);
                    return new Response('下载失败: ' + e.message, {
                        status: 500,
                        headers: { 'Access-Control-Allow-Origin': '*' }
                    });
                })
            );
        } else {
            event.respondWith(
                new Response('缺少 fkx 参数', {
                    status: 400,
                    headers: { 'Access-Control-Allow-Origin': '*' }
                })
            );
        }
    } else if (event.request.method === 'OPTIONS') {
        event.respondWith(new Response(null, {
            status: 204,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Range'
            }
        }));
    }
});

async function streamDownload(fkxUrl, request, resumeOffset) {
    try {
        const fkxRes = await fetch(fkxUrl);
        if (!fkxRes.ok) throw new Error('无法获取文件信息: HTTP ' + fkxRes.status);
        const fkxText = await fkxRes.text();
        const info = parseFkx(fkxText);
        if (!info.filename || !info.chunks?.length) throw new Error('文件信息格式不正确');

        const baseUrl = getBaseUrl(fkxUrl);
        const totalSize = info.chunks.reduce((s, c) => s + c.size, 0);
        const sanitizedName = String(info.filename)
            .replace(/[\r\n\t]/g, '')
            .replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g, '_')
            .replace(/^\.+/, '')
            .trim() || 'download';
        const asciiName = sanitizedName.replace(/[^\x20-\x7e]/g, '_').replace(/["\\;]/g, '_');

        const etag = 'W/"' + fnv1a(fkxText) + '"';

        let rangeStart = resumeOffset || 0;
        let rangeEnd = totalSize - 1;
        const rangeHeader = request.headers.get('Range');
        const ifRange = (request.headers.get('If-Range') || '').trim();
        let parsedRange = resolveRange(rangeHeader, totalSize);

        if (parsedRange !== null && ifRange && ifRange !== etag) {
            parsedRange = null;
            resumeOffset = 0;
        }

        if (parsedRange === 'unsatisfiable') {
            return new Response('请求的字节范围无效', {
                status: 416,
                headers: {
                    'Content-Range': `bytes */${totalSize}`,
                    'Accept-Ranges': 'bytes',
                    'Access-Control-Allow-Origin': '*'
                }
            });
        }

        if (parsedRange) {
            rangeStart = parsedRange.start;
            rangeEnd = parsedRange.end;
        }
        const finalIsRange = parsedRange !== null;
        if (rangeStart < 0 || (totalSize > 0 && rangeStart >= totalSize)) {
            return new Response('请求的字节范围无效', {
                status: 416,
                headers: {
                    'Content-Range': `bytes */${totalSize}`,
                    'Accept-Ranges': 'bytes',
                    'Access-Control-Allow-Origin': '*'
                }
            });
        }
        const rangeLength = Math.max(0, rangeEnd - rangeStart + 1);

        let startChunkIdx = 0, startOffset = rangeStart;
        let cumulativeSize = 0;
        for (let i = 0; i < info.chunks.length; i++) {
            if (cumulativeSize + info.chunks[i].size > rangeStart) {
                startChunkIdx = i;
                startOffset = rangeStart - cumulativeSize;
                break;
            }
            cumulativeSize += info.chunks[i].size;
        }

        const chunkStarts = [];
        for (let i = 0, acc = 0; i < info.chunks.length; i++) {
            chunkStarts.push(acc);
            acc += info.chunks[i].size;
        }
        const inRange = (idx) => idx < info.chunks.length && chunkStarts[idx] <= rangeEnd;

        const ACTIVE = 3;
        const PREFETCH_AHEAD = 1;
        const MAX_BUFFER = 4 * 1024 * 1024;
        const chunkUrl = (idx) => baseUrl + info.chunks[idx].filename;

        const createChunkReader = (idx, reqHeaders, pending, ctrl) => {
            const src = {
                idx, queue: [], buffered: 0, done: false, error: null,
                waiter: null, resume: null, cancelled: false,
                ctrl: ctrl || new AbortController()
            };

            const notify = () => {
                if (src.waiter && (src.queue.length || src.done || src.error)) {
                    const w = src.waiter;
                    src.waiter = null;
                    w.resolve();
                }
            };

            const take = () => {
                const data = src.queue.shift();
                src.buffered -= data.length;
                if (src.resume && src.buffered < MAX_BUFFER) {
                    const r = src.resume;
                    src.resume = null;
                    r();
                }
                return { done: false, value: data };
            };

            const next = () => {
                if (src.queue.length) return Promise.resolve(take());
                if (src.error) return Promise.reject(src.error);
                if (src.done) return Promise.resolve({ done: true });
                return new Promise((resolve) => { src.waiter = { resolve }; }).then(() => {
                    if (src.queue.length) return take();
                    if (src.error) throw src.error;
                    return { done: true };
                });
            };

            const cancel = () => {
                src.cancelled = true;
                try { src.ctrl.abort(); } catch (e) { }
                if (src.resume) { const r = src.resume; src.resume = null; r(); }
                if (src.waiter) { const w = src.waiter; src.waiter = null; w.resolve(); }
            };

            let emitted = 0;

            const readBody = async (res) => {
                if (!res.ok) throw new Error('无法下载分片: ' + info.chunks[idx].filename);
                let skip = (idx === startChunkIdx && startOffset > 0 && res.status !== 206) ? startOffset : 0;
                const reader = res.body.getReader();
                while (!src.cancelled) {
                    if (src.buffered >= MAX_BUFFER) {
                        await new Promise((r) => { src.resume = r; });
                        continue;
                    }
                    const { done, value } = await reader.read();
                    if (done) break;
                    let data = value;
                    if (skip > 0) {
                        if (data.length <= skip) { skip -= data.length; continue; }
                        data = data.subarray(skip);
                        skip = 0;
                    }
                    src.queue.push(data);
                    src.buffered += data.length;
                    emitted += data.length;
                    notify();
                }
            };

            (async () => {
                try {
                    let usedPrefetch = false;
                    let res = null;
                    if (pending) {
                        try { res = await pending; } catch (e) { res = null; }
                        usedPrefetch = !!res;
                    }
                    if (!res) {
                        res = await fetch(chunkUrl(idx), { headers: reqHeaders, signal: src.ctrl.signal });
                    }

                    try {
                        await readBody(res);
                    } catch (e) {
                        if (!usedPrefetch || emitted > 0 || src.cancelled) throw e;
                        const fresh = await fetch(chunkUrl(idx), { headers: reqHeaders, signal: src.ctrl.signal });
                        await readBody(fresh);
                    }

                    if (!src.cancelled) { src.done = true; notify(); }
                } catch (e) {
                    if (!src.cancelled) { src.error = e; notify(); }
                }
            })();

            return { next, cancel };
        };

        const active = new Map();
        const prefetched = new Map();
        let aborted = false;

        const PREFETCH_TTL = 30 * 1000;

        const prefetchChunk = (idx) => {
            if (aborted || !inRange(idx)) return;
            if (active.has(idx) || prefetched.has(idx)) return;
            const ctrl = new AbortController();
            const pending = fetch(chunkUrl(idx), { signal: ctrl.signal }).catch(() => null);
            prefetched.set(idx, { pending, ctrl, createdAt: Date.now() });
        };

        const ensure = (idx, reqHeaders) => {
            if (aborted || !inRange(idx) || active.has(idx)) return;
            const pf = prefetched.get(idx);
            if (pf && Date.now() - pf.createdAt <= PREFETCH_TTL) {
                prefetched.delete(idx);
                active.set(idx, createChunkReader(idx, reqHeaders, pf.pending, pf.ctrl));
            } else {
                if (pf) {
                    prefetched.delete(idx);
                    try { pf.ctrl.abort(); } catch (e) { }
                }
                active.set(idx, createChunkReader(idx, reqHeaders, null, null));
            }
        };

        const closeAll = () => {
            aborted = true;
            for (const src of active.values()) src.cancel();
            active.clear();
            for (const pf of prefetched.values()) pf.ctrl.abort();
            prefetched.clear();
        };

        const stream = new ReadableStream({
            async start(controller) {
                let rangeSent = 0;
                try {
                    for (let i = startChunkIdx; i < info.chunks.length && rangeSent < rangeLength; i++) {
                        if (aborted) return;
                        const firstHeaders = (i === startChunkIdx && startOffset > 0)
                            ? { Range: 'bytes=' + startOffset + '-' }
                            : undefined;
                        ensure(i, firstHeaders);
                        for (let k = 1; k < ACTIVE; k++) ensure(i + k);
                        for (let k = ACTIVE; k < ACTIVE + PREFETCH_AHEAD; k++) prefetchChunk(i + k);

                        const src = active.get(i);
                        while (true) {
                            const { done, value } = await src.next();
                            if (done || aborted) break;

                            let data = value;
                            if (rangeSent + data.length > rangeLength) {
                                data = data.subarray(0, rangeLength - rangeSent);
                            }
                            if (data.length > 0) {
                                controller.enqueue(data);
                                rangeSent += data.length;
                            }
                            if (rangeSent >= rangeLength) break;
                        }

                        active.delete(i);
                        src.cancel();
                    }
                    if (aborted) return;
                    closeAll();
                    controller.close();
                } catch (e) {
                    if (aborted) return;
                    closeAll();
                    controller.error(e);
                }
            },
            cancel() {
                closeAll();
            }
        });

        const headers = {
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': `attachment; filename="${asciiName}"; filename*=UTF-8''${encodeURIComponent(sanitizedName)}`,
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length, Content-Range, Accept-Ranges, ETag',
            'Accept-Ranges': 'bytes',
            'ETag': etag
        };

        if (finalIsRange || resumeOffset > 0) {
            headers['Content-Range'] = `bytes ${rangeStart}-${rangeEnd}/${totalSize}`;
            headers['Content-Length'] = String(rangeLength);
            return new Response(stream, { status: 206, headers });
        }

        headers['Content-Length'] = String(totalSize);
        return new Response(stream, { headers });
    } catch (e) {
        console.error('下载失败:', e);
        return new Response('下载失败: ' + e.message, {
            status: 500,
            headers: { 'Access-Control-Allow-Origin': '*' }
        });
    }
}

function parseFkx(content) {
    const info = { chunks: [] };
    for (const line of content.trim().split('\n')) {
        const eqIdx = line.indexOf('=');
        if (eqIdx < 0) continue;
        const key = line.substring(0, eqIdx), value = line.substring(eqIdx + 1);
        if (key.startsWith('chunk_')) {
            const parts = value.split(',');
            if (parts.length >= 2) info.chunks.push({
                filename: parts[0].trim().replace(/^.*[\\/]/, ''),
                size: parseInt(parts[1].trim()) || 0
            });
        } else {
            info[key] = value.trim();
        }
    }
    return info;
}

function getBaseUrl(url) {
    const parsed = new URL(url);
    const pathParts = parsed.pathname.split('/');
    pathParts.pop();
    return parsed.origin + pathParts.join('/') + '/';
}

function fnv1a(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
        h ^= str.charCodeAt(i);
        h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(16).padStart(8, '0');
}

function resolveRange(rangeHeader, totalSize) {
    if (!rangeHeader) return null;
    const m = /^bytes\s*=\s*(.+)$/i.exec(String(rangeHeader).trim());
    if (!m) return null;
    const spec = m[1].split(',')[0].trim();
    const r = /^(\d*)-(\d*)$/.exec(spec);
    if (!r) return null;
    const startStr = r[1];
    const endStr = r[2];
    if (startStr === '' && endStr === '') return null;

    if (startStr === '') {
        const n = parseInt(endStr, 10);
        if (!n) return 'unsatisfiable';
        return { start: Math.max(0, totalSize - n), end: totalSize - 1 };
    }

    const start = parseInt(startStr, 10);
    let end = endStr === '' ? totalSize - 1 : parseInt(endStr, 10);
    if (!Number.isFinite(start) || start >= totalSize) return 'unsatisfiable';
    if (!Number.isFinite(end)) end = totalSize - 1;
    if (end >= totalSize) end = totalSize - 1;
    if (end < start) return 'unsatisfiable';
    return { start, end };
}
