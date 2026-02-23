export async function onRequest(context) {
    const { request, env } = context;
    
    const stats = {
        channels: 0,
        sources: 0,
        last_update: new Date().toISOString(),
        version: "1.0.0"
    };
    
    try {
        const cache = await caches.open('iptv-stats');
        const cached = await cache.match(request);
        
        if (cached) {
            return cached;
        }
        
        const response = new Response(JSON.stringify(stats, null, 2), {
            headers: {
                'Content-Type': 'application/json; charset=utf-8',
                'Cache-Control': 'public, max-age=300',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS'
            }
        });
        
        await cache.put(request, response.clone());
        return response;
    } catch (error) {
        return new Response(JSON.stringify(stats), {
            headers: {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*'
            }
        });
    }
}
