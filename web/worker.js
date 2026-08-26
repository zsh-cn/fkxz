export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let fkxUrl = url.searchParams.get('fkx');
    
    if (!fkxUrl) {
      return new Response('缺少 fkx 参数', { status: 400 });
    }
    
    if (!fkxUrl.startsWith('http://') && !fkxUrl.startsWith('https://')) {
      fkxUrl = new URL(fkxUrl, request.url).href;
    }
    
    if (!fkxUrl.endsWith('.fkx')) {
      return new Response('fkx 参数必须指向 .fkx 文件', { status: 400 });
    }
    
    try {
      const fkxResponse = await fetch(fkxUrl);
      if (!fkxResponse.ok) {
        return new Response('无法获取文件信息', { status: fkxResponse.status });
      }
      
      const fkxContent = await fkxResponse.text();
      const fkxInfo = parseFkx(fkxContent);
      
      if (!fkxInfo.filename || !fkxInfo.chunks || fkxInfo.chunks.length === 0) {
        return new Response('文件信息格式不正确', { status: 400 });
      }
      
      const baseUrl = getBaseUrl(fkxUrl);
      const totalSize = fkxInfo.chunks.reduce((sum, chunk) => sum + chunk.size, 0);
      
      const headers = new Headers({
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="${fkxInfo.filename}"; filename*=UTF-8''${encodeURIComponent(fkxInfo.filename)}`,
        'Access-Control-Allow-Origin': '*',
      });
      
      return new Response(createStream(baseUrl, fkxInfo.chunks, totalSize), { headers });
    } catch (error) {
      console.error('下载合并失败:', error);
      return new Response(`下载合并失败: ${error.message}`, { status: 500 });
    }
  }
};

function parseFkx(content) {
  const info = { chunks: [] };
  const lines = content.trim().split('\n');
  
  for (const line of lines) {
    if (!line.includes('=')) continue;
    
    const [key] = line.split('=', 1);
    const value = line.substring(key.length + 1);
    
    if (key.startsWith('chunk_')) {
      const parts = value.split(',');
      if (parts.length >= 2) {
        info.chunks.push({
          filename: parts[0].trim(),
          size: parseInt(parts[1].trim(), 10) || 0,
        });
      }
    } else {
      info[key] = value.trim();
    }
  }
  
  return info;
}

function getBaseUrl(fkxUrl) {
  const parsed = new URL(fkxUrl);
  const pathParts = parsed.pathname.split('/');
  pathParts.pop();
  return `${parsed.protocol}//${parsed.host}${pathParts.join('/')}/`;
}

async function* streamChunks(baseUrl, chunks) {
  for (const chunk of chunks) {
    const chunkUrl = baseUrl + chunk.filename;
    const response = await fetch(chunkUrl);
    
    if (!response.ok) {
      throw new Error(`无法下载分片: ${chunk.filename}`);
    }
    
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield value;
    }
  }
}

function createStream(baseUrl, chunks, totalSize) {
  const { writable, readable } = new FixedLengthStream(totalSize);
  
  (async () => {
    const writer = writable.getWriter();
    try {
      for await (const chunk of streamChunks(baseUrl, chunks)) {
        await writer.write(chunk);
      }
      await writer.close();
    } catch (error) {
      writer.abort(error);
    }
  })();
  
  return readable;
}