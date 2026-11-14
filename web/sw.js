self.addEventListener('install', (event) => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

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
        // 其他路径的 CORS 预检；204 属于 null body status，不能带 body
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

        let rangeStart = resumeOffset || 0;
        let rangeEnd = totalSize - 1;
        const rangeHeader = request.headers.get('Range');
        const isRangeRequest = !!rangeHeader;
        if (rangeHeader) {
            const match = rangeHeader.match(/bytes=(\d+)-(\d*)/);
            if (match && match[1] !== undefined) {
                rangeStart = parseInt(match[1], 10) || 0;
                if (match[2] !== '' && match[2] !== undefined) {
                    rangeEnd = parseInt(match[2], 10) || totalSize - 1;
                }
                if (rangeEnd >= totalSize) rangeEnd = totalSize - 1;
            }
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

        const PREFETCH_AHEAD = 1;
        const prefetched = new Map();
        const chunkUrl = (idx) => baseUrl + info.chunks[idx].filename;

        // 每个预取请求独立的 controller：被取走并正在读取的分片不再被 abort，
        // 只取消那些还没用上的预取，避免下载被取消时把正在传输的流一起打断。
        const prefetch = (idx) => {
            if (idx >= info.chunks.length || prefetched.has(idx)) return;
            const ctrl = new AbortController();
            const pending = fetch(chunkUrl(idx), { signal: ctrl.signal }).catch(() => null);
            prefetched.set(idx, { pending, ctrl });
        };

        const takeChunk = async (idx, headers) => {
            const entry = prefetched.get(idx);
            if (entry) {
                prefetched.delete(idx);
                const buffered = await entry.pending;
                if (buffered && buffered.ok) return buffered;
            }
            return fetch(chunkUrl(idx), { headers });
        };

        const stream = new ReadableStream({
            async start(controller) {
                let rangeSent = 0;
                for (let i = startChunkIdx; i < info.chunks.length && rangeSent < rangeLength; i++) {
                    try {
                        const chunkHeaders = {};
                        if (i === startChunkIdx && startOffset > 0) {
                            chunkHeaders['Range'] = 'bytes=' + startOffset + '-';
                        }
                        if (rangeSent + info.chunks[i].size < rangeLength) {
                            for (let k = 1; k <= PREFETCH_AHEAD; k++) prefetch(i + k);
                        }
                        const chunkRes = await takeChunk(i, chunkHeaders);
                        if (!chunkRes.ok) {
                            throw new Error('无法下载分片: ' + info.chunks[i].filename);
                        }
                        const reader = chunkRes.body.getReader();
                        let skipBytes = 0;
                        if (i === startChunkIdx && startOffset > 0 && chunkRes.status !== 206) {
                            skipBytes = startOffset;
                        }
                        let chunkOffset = 0;
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;

                            if (skipBytes && chunkOffset + value.length <= skipBytes) {
                                chunkOffset += value.length;
                                continue;
                            }

                            let data = value;
                            if (skipBytes && chunkOffset < skipBytes) {
                                data = value.subarray(skipBytes - chunkOffset);
                            }
                            chunkOffset += value.length;

                            if (rangeSent + data.length > rangeLength) {
                                data = data.subarray(0, rangeLength - rangeSent);
                            }

                            if (data.length > 0) {
                                controller.enqueue(data);
                                rangeSent += data.length;
                            }

                            if (rangeSent >= rangeLength) break;
                        }
                    } catch (e) {
                        controller.error(e);
                        return;
                    }
                }
                for (const entry of prefetched.values()) entry.ctrl.abort();
                prefetched.clear();
                controller.close();
            },
            cancel() {
                for (const entry of prefetched.values()) entry.ctrl.abort();
                prefetched.clear();
            }
        });

        const headers = {
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': `attachment; filename="${asciiName}"; filename*=UTF-8''${encodeURIComponent(sanitizedName)}`,
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length, Content-Range, Accept-Ranges',
            'Accept-Ranges': 'bytes'
        };

        if (isRangeRequest || resumeOffset > 0) {
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
