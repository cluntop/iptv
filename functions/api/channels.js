export async function onRequest(context) {
    const { request } = context;
    
    const channels = {
        total: 0,
        categories: {
            cctv: 0,
            satellite: 0,
            local: 0,
            other: 0
        },
        last_update: new Date().toISOString(),
        sources: []
    };
    
    const response = new Response(JSON.stringify(channels, null, 2), {
        headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'public, max-age=300',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': '*'
        }
    });
    
    return response;
}

export async function onRequestOptions() {
    return new Response(null, {
        headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Max-Age': '86400'
        }
    });
}
