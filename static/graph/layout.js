/* Todo Sobre Todo — Helpers de layout para inicializar nodos y edges.
   Sin React, sin fetch: solo mapeos de graphData a nodos/edges de
   React Flow.
*/

import { STAGE_INFO, FIXED_NODE_DEFS, DEFAULT_EDGES } from './nodes.js';

export function buildInitialNodes(graphData, handlers) {
    var source = (Array.isArray(graphData.nodes) && graphData.nodes.length > 0)
        ? graphData.nodes
        : FIXED_NODE_DEFS.map(function (d) {
            return { id: d.key, key: d.key, label: d.label, position: { x: d.x, y: d.y }, isFixed: true };
        });
    return source.map(function (n) {
        var info = STAGE_INFO[n.key] || null;
        return {
            id: n.id || n.key,
            type: 'prompt',
            position: n.position || { x: 0, y: 0 },
            data: {
                key: n.key,
                label: n.label || n.key,
                stageNum: info ? info.num : '·',
                sysPrompt: n.sysPrompt || '',
                userPrompt: n.userPrompt || '',
                isFixed: n.isFixed !== false && !/^custom_/.test(n.id || n.key || ''),
                status: n.status || 'idle',
                output: n.output || n.lastOutput || '',
                durationMs: n.durationMs || null,
                lastRunAt: n.lastRunAt || null,
                onDelete: handlers.onDelete,
            },
        };
    });
}

export function buildInitialEdges(graphData) {
    var source = (Array.isArray(graphData.edges) && graphData.edges.length > 0)
        ? graphData.edges
        : DEFAULT_EDGES;
    return source.map(function (e) {
        return {
            id: e.id,
            source: e.source,
            target: e.target,
            animated: !!e.animated,
            className: e.animated ? 'is-running' : '',
        };
    });
}
