/* Todo Sobre Todo — Backend client del editor de grafo.
   postJSON() hace POST JSON contra los endpoints del backend.
   Los stubs son el fallback cuando los URLs no estan en graphData
   (modo dev sin backend conectado).
*/

export async function postJSON(url, payload) {
    var res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload || {}),
    });
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
        var msg = (data && (data.error || data.message)) || ('HTTP ' + res.status);
        throw new Error(msg);
    }
    return data || {};
}

function mockDelay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

export async function saveNodeStub(_profileId, node) {
    await mockDelay(180);
    return { ok: true, nodeId: node.id };
}

export async function deleteNodeStub(_profileId, nodeId) {
    await mockDelay(180);
    return { ok: true, nodeId: nodeId };
}

export async function saveLayoutStub(_profileId, payload) {
    await mockDelay(160);
    return { ok: true, payload: payload };
}

export async function executeNodeStub(_projectId, nodeKey) {
    await new Promise(function (r) { setTimeout(r, 1500); });
    return {
        ok: true,
        nodeKey: nodeKey,
        output: '[MOCK] Ejecución simulada de ' + nodeKey + '.\nSin backend conectado todavía.',
    };
}
