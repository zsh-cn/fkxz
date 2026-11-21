function toInt(value) {
    const text = String(value === undefined || value === null ? '' : value).trim();
    if (!/^[+-]?\d+$/.test(text)) return null;
    const number = parseInt(text, 10);
    return Number.isFinite(number) ? number : null;
}

function parseFkx(content) {
    const info = { chunks: [] };
    const indexed = new Map();
    const lines = String(content === undefined || content === null ? '' : content).split(/\r?\n/);

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].replace(/^\uFEFF/, '').trim();
        if (!line) continue;
        const eqIdx = line.indexOf('=');
        if (eqIdx < 0) continue;

        const key = line.substring(0, eqIdx).trim();
        const value = line.substring(eqIdx + 1).trim();
        if (!key) continue;

        if (key.indexOf('chunk_') === 0) {
            const index = toInt(key.substring(6));
            if (index === null) continue;
            if (index < 1) throw new Error('分片编号无效: ' + key);
            if (indexed.has(index)) throw new Error('分片编号重复: ' + key);

            const parts = value.split(',');
            if (parts.length < 2) throw new Error('分片条目格式不正确: ' + key);
            const size = toInt(parts[1]);
            if (size === null || size < 0) throw new Error('分片大小无效: ' + key);

            indexed.set(index, {
                index: index,
                filename: parts[0].trim().replace(/^.*[\\/]/, ''),
                size: size,
                sha256: parts.length >= 3 ? parts[2].trim() : ''
            });
        } else {
            info[key] = value;
        }
    }

    const indexes = Array.from(indexed.keys()).sort((a, b) => a - b);
    if (!indexes.length) throw new Error('未找到任何分片条目');
    for (let n = 0; n < indexes.length; n++) {
        if (indexes[n] !== n + 1) {
            throw new Error('分片编号不连续: 期望 ' + (n + 1) + '，实际 ' + indexes[n]);
        }
    }

    info.chunks = indexes.map((idx) => indexed.get(idx));
    return validateManifest(info);
}

function validateManifest(info) {
    const chunks = info.chunks || [];
    if (!chunks.length) throw new Error('未找到任何分片条目');
    if (!String(info.filename || '').trim()) throw new Error('缺少 filename 字段');

    const total = chunks.reduce((sum, chunk) => sum + chunk.size, 0);
    if (info.total_size !== undefined && info.total_size !== null && info.total_size !== '') {
        const declaredTotal = toInt(info.total_size);
        if (declaredTotal === null) throw new Error('total_size 不是数字');
        if (declaredTotal !== total) {
            throw new Error('清单总大小与分片之和不一致（' + declaredTotal + ' != ' + total + '）');
        }
    }
    if (info.num_chunks !== undefined && info.num_chunks !== null && info.num_chunks !== '') {
        const declaredCount = toInt(info.num_chunks);
        if (declaredCount === null) throw new Error('num_chunks 不是数字');
        if (declaredCount !== chunks.length) {
            throw new Error('清单分片数与条目数不一致（' + declaredCount + ' != ' + chunks.length + '）');
        }
    }

    info.totalSize = total;
    return info;
}

async function loadManifestInfo(fkxUrl) {
    const response = await fetch(fkxUrl);
    if (!response.ok) throw new Error('无法获取文件信息: HTTP ' + response.status);
    return parseFkx(await response.text());
}

self.addEventListener('install', (event) => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type !== 'fkx-info') return;
    const port = event.ports && event.ports[0];
    if (!port) return;
    event.waitUntil((async () => {
        try {
            const info = await loadManifestInfo(data.url);
            port.postMessage({
                ok: true,
                info: {
                    filename: info.filename,
                    totalSize: info.totalSize,
                    numChunks: info.chunks.length
                }
            });
        } catch (e) {
            port.postMessage({ ok: false, error: e.message });
        }
    })());
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    if (url.pathname.endsWith('/fkxz')) {
        const fkxUrl = url.searchParams.get('fkx');
        if (fkxUrl) {
            event.respondWith(
                streamDownload(fkxUrl, event.request).catch(e => {
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

async function streamDownload(fkxUrl, request) {
    try {
        const signal = request.signal;
        const info = await loadManifestInfo(fkxUrl);

        const baseUrl = getBaseUrl(fkxUrl);
        const totalSize = info.totalSize;
        const sanitizedName = String(info.filename)
            .replace(/[\r\n\t]/g, '')
            .replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g, '_')
            .replace(/^\.+/, '')
            .trim() || 'download';
        const asciiName = sanitizedName.replace(/[^\x20-\x7e]/g, '_').replace(/["\\;]/g, '_');

        let rangeStart = 0;
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

        if (isRangeRequest && rangeStart >= totalSize) {
            return new Response(null, {
                status: 416,
                headers: {
                    'Content-Range': `bytes */${totalSize}`,
                    'Access-Control-Allow-Origin': '*'
                }
            });
        }

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

        const chunkUrl = (idx) => baseUrl + info.chunks[idx].filename;

        const stream = new ReadableStream({
            async start(controller) {
                let rangeSent = 0;
                for (let i = startChunkIdx; i < info.chunks.length && rangeSent < rangeLength; i++) {
                    try {
                        if (signal?.aborted) throw new Error('下载已取消');
                        const chunkHeaders = {};
                        if (i === startChunkIdx && startOffset > 0) {
                            chunkHeaders['Range'] = 'bytes=' + startOffset + '-';
                        }
                        const chunkRes = await fetch(chunkUrl(i), { headers: chunkHeaders, signal });
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
                            if (signal?.aborted) throw new Error('下载已取消');
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
                controller.close();
            }
        });

        const headers = {
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': `attachment; filename="${asciiName}"; filename*=UTF-8''${encodeURIComponent(sanitizedName)}`,
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length, Content-Range, Accept-Ranges',
            'Accept-Ranges': 'bytes'
        };

        if (isRangeRequest) {
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

function getBaseUrl(url) {
    const parsed = new URL(url);
    const pathParts = parsed.pathname.split('/');
    pathParts.pop();
    return parsed.origin + pathParts.join('/') + '/';
}
