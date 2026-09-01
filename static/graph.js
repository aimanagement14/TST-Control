/* Todo Sobre Todo — Editor de grafo y runner.
   Carga via importmap (esm.sh). Sin build step. Sin dependencias NPM.

   Editor (mode=editor) y runner (mode=runner) sobre el mismo motor,
   diferenciados por los endpoints y por el affordance de cada toolbar.
*/

import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
    ReactFlow,
    ReactFlowProvider,
    Background,
    Controls,
    MiniMap,
    Panel,
    Handle,
    Position,
    useNodesState,
    useEdgesState,
    addEdge,
    useReactFlow,
} from '@xyflow/react';

/* -------------------------------------------------------------------------- */
/* Mapa de etapas: cada nodo fijo tiene número y categoría para la cromática. */
/* -------------------------------------------------------------------------- */

const STAGE_INFO = {
    research:         { num: '01', category: 'research' },
    concept:          { num: '02', category: 'concept'  },
    script_long:      { num: '03', category: 'script'   },
    script_short:     { num: '04', category: 'script'   },
    scenes:           { num: '05', category: 'post'     },
    metadata_youtube: { num: '06', category: 'meta'     },
    metadata_shorts:  { num: '07', category: 'meta'     },
    thumbnail_long:   { num: '08', category: 'thumb'    },
    thumbnail_short:  { num: '09', category: 'thumb'    },
};

const FIXED_NODE_DEFS = [
    { key: 'research',         label: 'Investigación',    x: 0,    y: 0   },
    { key: 'concept',          label: 'Concepto',         x: 320,  y: 0   },
    { key: 'script_long',      label: 'Guion 5 min',      x: 640,  y: 0   },
    { key: 'script_short',     label: 'Guion 1 min',      x: 640,  y: 200 },
    { key: 'scenes',           label: 'Escenas',          x: 960,  y: 100 },
    { key: 'metadata_youtube', label: 'Metadata YouTube', x: 1280, y: 0   },
    { key: 'metadata_shorts',  label: 'Metadata Shorts',  x: 1280, y: 200 },
    { key: 'thumbnail_long',   label: 'Miniatura 16:9',   x: 1600, y: 0   },
    { key: 'thumbnail_short',  label: 'Miniatura 9:16',   x: 1600, y: 200 },
];

const DEFAULT_EDGES = [
    { id: 'e1', source: 'research',         target: 'concept' },
    { id: 'e2', source: 'concept',          target: 'script_long' },
    { id: 'e3', source: 'concept',          target: 'script_short' },
    { id: 'e4', source: 'script_long',      target: 'scenes' },
    { id: 'e5', source: 'script_short',     target: 'scenes' },
    { id: 'e6', source: 'script_long',      target: 'metadata_youtube' },
    { id: 'e7', source: 'script_short',     target: 'metadata_shorts' },
    { id: 'e8', source: 'script_long',      target: 'thumbnail_long' },
    { id: 'e9', source: 'script_short',     target: 'thumbnail_short' },
];

/* -------------------------------------------------------------------------- */
/* Backend client                                                            */
/* -------------------------------------------------------------------------- */

async function postJSON(url, payload) {
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

/* -------------------------------------------------------------------------- */
/* Stubs (fallback si no hay URLs — sólo desarrollo local sin backend)        */
/* -------------------------------------------------------------------------- */

function mockDelay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

async function saveNodeStub(_profileId, node) {
    await mockDelay(180);
    return { ok: true, nodeId: node.id };
}
async function deleteNodeStub(_profileId, nodeId) {
    await mockDelay(180);
    return { ok: true, nodeId: nodeId };
}
async function saveLayoutStub(_profileId, payload) {
    await mockDelay(160);
    return { ok: true, payload: payload };
}
async function executeNodeStub(_projectId, nodeKey) {
    await new Promise(function (r) { setTimeout(r, 1500); });
    return {
        ok: true,
        nodeKey: nodeKey,
        output: '[MOCK] Ejecución simulada de ' + nodeKey + '.\nSin backend conectado todavía.',
    };
}

/* -------------------------------------------------------------------------- */
/* Custom node (fotograma)                                                   */
/* -------------------------------------------------------------------------- */

function PromptNode(props) {
    var data = props.data || {};
    var status = data.status || 'idle';
    var cls = 'react-flow__node-prompt' +
              (data.isFixed ? ' is-fixed' : ' is-custom') +
              (status === 'running' ? ' is-running' : '') +
              (status === 'ok'      ? ' is-ok'      : '') +
              (status === 'error'   ? ' is-error'   : '');

    var preview = (data.sysPrompt || '').slice(0, 140);
    var stageInfo = STAGE_INFO[data.key] || null;
    var stageNum = data.stageNum || (stageInfo && stageInfo.num) || '·';
    var statusLabel = status === 'idle' ? 'EN ESPERA'
                    : status === 'running' ? 'EN MARCHA'
                    : status === 'ok'      ? 'OK'
                    : status === 'error'   ? 'ERROR'
                    : status;

    return (
        React.createElement('div', { className: cls },
            React.createElement(Handle, {
                type: 'target',
                position: Position.Top,
                style: { background: 'var(--slate-3)' },
            }),
            React.createElement('div', { className: 'node-strip' },
                React.createElement('span', { className: 'stage' },
                    React.createElement('span', { className: 'perf', 'aria-hidden': 'true' }),
                    React.createElement('span', { className: 'stage-num' }, stageNum)
                ),
                React.createElement('span', {
                    className: 'status-dot',
                    title: statusLabel,
                    'aria-label': statusLabel,
                })
            ),
            React.createElement('div', { className: 'node-body' },
                React.createElement('div', { className: 'node-title' },
                    data.label || data.key || props.id
                ),
                React.createElement('div', { className: 'node-key' }, data.key || props.id),
                preview
                    ? React.createElement('p', { className: 'preview' },
                        preview + ((data.sysPrompt || '').length > 140 ? '…' : ''))
                    : null
            ),
            !data.isFixed && data.onDelete
                ? React.createElement('div', { className: 'node-actions' },
                    React.createElement('button', {
                        className: 'btn btn-danger btn-sm node-delete',
                        onClick: function (e) { e.stopPropagation(); data.onDelete(props.id); },
                    }, 'Eliminar'))
                : null,
            React.createElement(Handle, {
                type: 'source',
                position: Position.Bottom,
                style: { background: 'var(--slate-3)' },
            })
        )
    );
}

const NODE_TYPES = { prompt: PromptNode };

/* -------------------------------------------------------------------------- */
/* Leyenda (Panel inferior)                                                  */
/* -------------------------------------------------------------------------- */

function Legend(props) {
    var items = [
        { cls: '',             label: 'En espera' },
        { cls: 'is-running',  label: 'En marcha' },
        { cls: 'is-ok',       label: 'OK' },
        { cls: 'is-error',    label: 'Error' },
        { cls: 'is-custom',   label: 'Auxiliar' },
    ];
    return React.createElement('div', { className: 'graph-legend', role: 'note' },
        items.map(function (it) {
            return React.createElement('span', { key: it.cls || 'idle', className: 'legend-item' },
                React.createElement('span', { className: 'swatch ' + it.cls }),
                it.label
            );
        })
    );
}

/* -------------------------------------------------------------------------- */
/* Toolbar (Panel superior)                                                  */
/* -------------------------------------------------------------------------- */

function Toolbar(props) {
    var mode = props.mode;
    var busy = props.busy || false;
    var onAdd = props.onAdd;
    var onFit = props.onFit;
    var onResetLayout = props.onResetLayout;
    var onRunAll = props.onRunAll;
    var nodeCount = props.nodeCount || 0;
    var fixedCount = props.fixedCount || 0;

    return React.createElement('div', { className: 'graph-toolbar' },
        React.createElement('span', {
            className: 'btn btn-ghost btn-sm',
            style: { cursor: 'default', color: 'var(--paper-3)' },
            title: 'Nodos totales',
        },
            React.createElement('span', { className: 'btn-label' }, 'Nodos '),
            React.createElement('strong', { style: { color: 'var(--paper)' } }, nodeCount),
            React.createElement('span', { style: { color: 'var(--paper-3)', margin: '0 .25rem' } }, '/'),
            React.createElement('span', { style: { color: 'var(--amber)' } }, fixedCount)
        ),
        React.createElement('span', { className: 'sep' }),
        React.createElement('button', {
            className: 'btn btn-ghost btn-sm',
            onClick: onAdd,
        }, React.createElement('span', { className: 'btn-label' }, '+ '), 'Añadir nodo'),
        React.createElement('button', {
            className: 'btn btn-ghost btn-sm',
            onClick: onFit,
        }, React.createElement('span', { className: 'btn-label' }, '· '), 'Auto-fit'),
        mode === 'editor'
            ? React.createElement('button', {
                className: 'btn btn-ghost btn-sm',
                onClick: onResetLayout,
            }, React.createElement('span', { className: 'btn-label' }, '↺ '), 'Reset layout')
            : null,
        mode === 'runner'
            ? React.createElement(React.Fragment, null,
                React.createElement('span', { className: 'sep' }),
                React.createElement('button', {
                    className: 'btn btn-primary btn-sm',
                    disabled: busy,
                    onClick: onRunAll,
                }, busy ? 'Ejecutando…' : 'Ejecutar todo')
              )
            : null
    );
}

/* -------------------------------------------------------------------------- */
/* Aside / editor lateral                                                    */
/* -------------------------------------------------------------------------- */

function NodeEditor(props) {
    var node = props.node;
    var onChange = props.onChange;
    var onSave = props.onSave;
    var onExecute = props.onExecute;
    var onClose = props.onClose;
    var mode = props.mode;
    var busy = props.busy || false;
    var lastSaved = props.lastSaved || null;

    if (!node) {
        return React.createElement('div', { className: 'graph-aside-empty' },
            React.createElement('span', { className: 'icon', 'aria-hidden': 'true' }, '◌'),
            React.createElement('p', null,
                'Selecciona un nodo del grafo para editar sus prompts o ver su salida.'
            )
        );
    }

    var data = node.data || {};
    var stageInfo = STAGE_INFO[data.key] || null;
    var stageNum = data.stageNum || (stageInfo && stageInfo.num) || '·';
    var status = data.status || 'idle';
    var statusLabel = status === 'running' ? 'En marcha'
                    : status === 'ok'      ? 'OK'
                    : status === 'error'   ? 'Error'
                    : 'En espera';

    return React.createElement('div', { className: 'graph-aside-card' },
        React.createElement('div', { className: 'graph-aside-head' },
            React.createElement('div', null,
                React.createElement('p', { className: 'stage-num' },
                    React.createElement('span', { style: { color: 'var(--paper-3)' } }, 'ETAPA '),
                    stageNum
                ),
                React.createElement('h3', null, data.label || node.id),
                React.createElement('p', { className: 'node-key' },
                    React.createElement('span', {
                        className: 'chip ' + (
                            status === 'running' ? 'chip-next' :
                            status === 'ok'      ? 'chip-done' :
                            status === 'error'   ? 'chip-alert' : ''
                        ),
                        style: { marginRight: '6px' }
                    }, statusLabel),
                    data.isFixed ? 'Nodo fijo del pipeline' : 'Nodo auxiliar'
                )
            ),
            React.createElement('button', {
                className: 'btn btn-ghost btn-sm',
                onClick: onClose,
                'aria-label': 'Cerrar panel',
            }, 'Cerrar')
        ),

        React.createElement('label', { className: 'field' },
            React.createElement('span', { className: 'label' },
                'Instrucciones del sistema',
                React.createElement('span', {
                    style: {
                        color: 'var(--paper-3)',
                        fontFamily: 'var(--font-body)',
                        textTransform: 'none',
                        letterSpacing: 0,
                        marginLeft: '.4rem',
                        fontSize: '.72rem',
                    }
                }, '— SYS prompt')
            ),
            React.createElement('textarea', {
                rows: 6,
                value: data.sysPrompt || '',
                onChange: function (e) { onChange('sysPrompt', e.target.value); },
            })
        ),

        React.createElement('label', { className: 'field' },
            React.createElement('span', { className: 'label' },
                'Petición al modelo',
                React.createElement('span', {
                    style: {
                        color: 'var(--paper-3)',
                        fontFamily: 'var(--font-body)',
                        textTransform: 'none',
                        letterSpacing: 0,
                        marginLeft: '.4rem',
                        fontSize: '.72rem',
                    }
                }, '— USER prompt')
            ),
            React.createElement('textarea', {
                rows: 9,
                value: data.userPrompt || '',
                onChange: function (e) { onChange('userPrompt', e.target.value); },
            })
        ),

        mode === 'runner' && (data.output || status === 'running')
            ? React.createElement('div', { className: 'run-output', style: { marginTop: 0 } },
                React.createElement('div', { className: 'panel-head' },
                    React.createElement('h4', { className: 'title-plain' }, 'Última salida')
                ),
                React.createElement('pre', { className: 'run-output-pre' },
                    status === 'running' ? 'Ejecutando…' : (data.output || '')
                )
              )
            : null,

        React.createElement('div', { className: 'graph-aside-foot' },
            mode === 'editor'
                ? React.createElement('button', {
                    className: 'btn btn-primary',
                    disabled: busy,
                    onClick: onSave,
                }, busy ? 'Guardando…' : 'Guardar cambios')
                : null,
            mode === 'runner'
                ? React.createElement('button', {
                    className: 'btn btn-primary',
                    disabled: busy,
                    onClick: onExecute,
                }, busy ? 'Ejecutando…' : 'Ejecutar este nodo')
                : null,
            React.createElement('span', {
                style: {
                    marginLeft: 'auto',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '.7rem',
                    color: 'var(--paper-3)',
                    alignSelf: 'center',
                }
            },
                lastSaved
                    ? 'Guardado ' + new Date(lastSaved).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    : 'Sin cambios pendientes'
            )
        )
    );
}

/* -------------------------------------------------------------------------- */
/* Layout helpers                                                            */
/* -------------------------------------------------------------------------- */

function buildInitialNodes(graphData, handlers) {
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

function buildInitialEdges(graphData) {
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

/* -------------------------------------------------------------------------- */
/* App principal                                                             */
/* -------------------------------------------------------------------------- */

function GraphApp(props) {
    var graphData = props.graphData;
    var mode = graphData.mode || 'editor';
    var profileId = graphData.profileId;
    var projectId = graphData.projectId;
    var urls = {
        saveUrl:    graphData.saveUrl    || (graphData.urls && graphData.urls.saveUrl),
        deleteUrl:  graphData.deleteUrl  || (graphData.urls && graphData.urls.deleteUrl),
        layoutUrl:  graphData.layoutUrl  || (graphData.urls && graphData.urls.layoutUrl),
        executeUrl: graphData.executeUrl || (graphData.urls && graphData.urls.executeUrl),
        resetUrl:   graphData.resetUrl   || (graphData.urls && graphData.urls.resetUrl),
    };
    var onSelect = props.onSelect;

    var saveNodeFn = urls.saveUrl ? function (id, node) {
        return postJSON(urls.saveUrl, {
            node_key: node.data.key,
            label: node.data.label,
            sys_prompt: node.data.sysPrompt,
            user_prompt: node.data.userPrompt,
            inputs_json: JSON.stringify(node.data.inputs || []),
            position_x: node.position.x,
            position_y: node.position.y,
            is_fixed: node.data.isFixed !== false,
        });
    } : saveNodeStub;
    var deleteNodeFn = urls.deleteUrl ? function (id) {
        return postJSON(urls.deleteUrl, { node_key: id });
    } : deleteNodeStub;
    var saveLayoutFn = urls.layoutUrl ? function (payload) {
        return postJSON(urls.layoutUrl, payload);
    } : saveLayoutStub;
    var executeFn = urls.executeUrl ? function (nodeKey) {
        return postJSON(urls.executeUrl, { node_key: nodeKey });
    } : executeNodeStub;

    var nodesInit = useMemo(function () {
        return buildInitialNodes(graphData, { onDelete: null });
    }, [graphData]);

    var edgesInit = useMemo(function () {
        return buildInitialEdges(graphData);
    }, [graphData]);

    var _nodesState = useNodesState(nodesInit);
    var nodes = _nodesState[0];
    var setNodes = _nodesState[1];
    var onNodesChange = _nodesState[2];
    var _edgesState = useEdgesState(edgesInit);
    var edges = _edgesState[0];
    var setEdges = _edgesState[1];
    var onEdgesChange = _edgesState[2];

    var reactFlow = useReactFlow();
    var layoutTimerRef = useRef(null);
    var busyRef = useRef(false);
    var lastSavedRef = useRef({});

    var fixedCount = useMemo(function () {
        return nodes.filter(function (n) { return n.data && n.data.isFixed; }).length;
    }, [nodes]);

    var selectedNode = useMemo(function () {
        var arr = (nodes || []).filter(function (n) { return n.selected; });
        return arr.length ? arr[0] : null;
    }, [nodes]);

    /* Inyecta onDelete en cada nodo tras el primer render */
    useEffect(function () {
        setNodes(function (curr) {
            return curr.map(function (n) {
                if (n.data && n.data.onDelete) return n;
                return Object.assign({}, n, {
                    data: Object.assign({}, n.data, {
                        onDelete: function (id) { handleDelete(id); },
                    }),
                });
            });
        });
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /* fitView robusto al primer render */
    useEffect(function () {
        var t = setTimeout(function () {
            try {
                reactFlow.fitView({ padding: 0.18, includeHiddenNodes: false, duration: 350 });
            } catch (e) { /* RF puede no estar listo todavía */ }
        }, 60);
        return function () { clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /* Propagar selección al aside */
    useEffect(function () {
        if (typeof onSelect === 'function') {
            onSelect(selectedNode ? selectedNode.id : null);
        }
    }, [selectedNode, onSelect]);

    var updateNodeData = useCallback(function (id, patch) {
        setNodes(function (curr) {
            return curr.map(function (n) {
                if (n.id !== id) return n;
                return Object.assign({}, n, {
                    data: Object.assign({}, n.data, patch),
                });
            });
        });
    }, [setNodes]);

    var handleDelete = useCallback(function (id) {
        var target = nodes.find(function (n) { return n.id === id; });
        if (target && target.data && target.data.isFixed) return;
        if (!window.confirm('¿Eliminar el nodo «' + id + '»? Las conexiones que apuntan o salen de él también desaparecerán.')) {
            return;
        }
        setNodes(function (curr) { return curr.filter(function (n) { return n.id !== id; }); });
        setEdges(function (curr) {
            return curr.filter(function (e) { return e.source !== id && e.target !== id; });
        });
        if (mode === 'editor') {
            deleteNodeFn(id).catch(function () { /* ignore */ });
        }
    }, [nodes, setNodes, setEdges, mode, deleteNodeFn]);

    var handleConnect = useCallback(function (params) {
        setEdges(function (eds) {
            var newEdge = Object.assign({}, params, {
                animated: mode === 'runner',
                className: mode === 'runner' ? 'is-running' : '',
            });
            return addEdge(newEdge, eds);
        });
    }, [setEdges, mode]);

    /* Auto-save layout (debounce 600ms) — sólo editor */
    var persistLayout = useCallback(function () {
        if (mode !== 'editor') return;
        if (layoutTimerRef.current) clearTimeout(layoutTimerRef.current);
        layoutTimerRef.current = setTimeout(function () {
            var payload = {
                nodes: nodes.map(function (n) {
                    return {
                        id: n.id,
                        position: { x: n.position.x, y: n.position.y },
                        type: n.type,
                    };
                }),
            };
            saveLayoutFn(payload).catch(function () { /* ignore */ });
        }, 600);
    }, [nodes, mode, saveLayoutFn]);

    useEffect(function () {
        persistLayout();
    }, [nodes, persistLayout]);

    var handleSaveSelected = useCallback(function () {
        if (!selectedNode) return;
        busyRef.current = true;
        saveNodeFn(selectedNode.id, selectedNode)
            .then(function () {
                lastSavedRef.current[selectedNode.id] = Date.now();
            })
            .catch(function (err) {
                window.alert('Error guardando nodo: ' + (err && err.message ? err.message : err));
            })
            .then(function () {
                busyRef.current = false;
            });
    }, [selectedNode, saveNodeFn]);

    var handleExecuteSelected = useCallback(function () {
        if (!selectedNode || !projectId) return;
        var id = selectedNode.id;
        var key = (selectedNode.data && selectedNode.data.key) || id;
        updateNodeData(id, { status: 'running', output: '' });
        executeFn(key).then(function (res) {
            var output = (res && (res.output || res.data && res.data.output)) || '';
            updateNodeData(id, { status: res && res.ok ? 'ok' : 'error', output: output });
        }).catch(function (err) {
            updateNodeData(id, { status: 'error', output: 'Error: ' + (err && err.message ? err.message : err) });
        });
    }, [selectedNode, projectId, updateNodeData, executeFn]);

    var handleAddNode = useCallback(function () {
        var i = (nodes.filter(function (n) { return /^custom_/.test(n.id); }).length) + 1;
        var id = 'custom_' + i;
        var last = nodes[nodes.length - 1];
        var pos = last
            ? { x: last.position.x + 240, y: last.position.y }
            : { x: 0, y: 260 };
        var newNode = {
            id: id,
            type: 'prompt',
            position: pos,
            data: {
                key: id,
                label: 'Nodo ' + i,
                stageNum: '·',
                sysPrompt: '',
                userPrompt: '',
                isFixed: false,
                status: 'idle',
                output: '',
                onDelete: function (nid) { handleDelete(nid); },
            },
        };
        setNodes(function (curr) { return curr.concat([newNode]); });
    }, [nodes, setNodes, handleDelete]);

    var handleFit = useCallback(function () {
        try { reactFlow.fitView({ padding: 0.18, duration: 350 }); } catch (e) {}
    }, [reactFlow]);

    var handleResetLayout = useCallback(function () {
        if (!window.confirm('¿Restablecer las posiciones por defecto de los 9 nodos fijos?')) return;
        setNodes(function (curr) {
            return curr.map(function (n) {
                var def = FIXED_NODE_DEFS.find(function (d) { return d.key === n.data.key; });
                if (!def) return n;
                return Object.assign({}, n, { position: { x: def.x, y: def.y } });
            });
        });
        setTimeout(function () { handleFit(); }, 60);
    }, [setNodes, handleFit]);

    var handleRunAll = useCallback(function () {
        if (!projectId) return;
        if (!window.confirm('¿Ejecutar los ' + nodes.length + ' nodos en cadena? Esta acción no se puede deshacer.')) return;
        busyRef.current = true;
        var queue = nodes.slice();
        function step() {
            var n = queue.shift();
            if (!n) { busyRef.current = false; return; }
            var key = (n.data && n.data.key) || n.id;
            updateNodeData(n.id, { status: 'running', output: '' });
            executeFn(key).then(function (res) {
                var output = (res && (res.output || res.data && res.data.output)) || '';
                updateNodeData(n.id, { status: res && res.ok ? 'ok' : 'error', output: output });
                setTimeout(step, 250);
            }).catch(function (err) {
                updateNodeData(n.id, { status: 'error', output: 'Error: ' + (err && err.message ? err.message : err) });
                setTimeout(step, 250);
            });
        }
        step();
    }, [nodes, projectId, updateNodeData, executeFn]);

    return React.createElement(ReactFlow,
        {
            nodes: nodes,
            edges: edges,
            onNodesChange: onNodesChange,
            onEdgesChange: onEdgesChange,
            onConnect: handleConnect,
            nodeTypes: NODE_TYPES,
            fitView: true,
            fitViewOptions: { padding: 0.18 },
            minZoom: 0.3,
            maxZoom: 1.6,
            proOptions: { hideAttribution: true },
            defaultEdgeOptions: { type: 'smoothstep' },
        },
        React.createElement(Background, { gap: 28, size: 1, color: 'rgba(165,177,194,0.10)' }),
        React.createElement(Controls, { position: 'bottom-right', showInteractive: false }),
        React.createElement(MiniMap, {
            pannable: true,
            zoomable: true,
            maskColor: 'rgba(10, 13, 19, 0.78)',
            nodeColor: function (n) {
                if (n.data && n.data.isFixed) return '#58B7E8';
                return '#F0A83C';
            },
            nodeStrokeColor: '#232D3D',
            style: { width: 160, height: 96 },
        }),
        React.createElement(Panel, { position: 'top-right' },
            React.createElement(Toolbar, {
                mode: mode,
                busy: false,
                onAdd: handleAddNode,
                onFit: handleFit,
                onResetLayout: handleResetLayout,
                onRunAll: handleRunAll,
                nodeCount: nodes.length,
                fixedCount: fixedCount,
            })
        ),
        React.createElement(Panel, { position: 'bottom-left' },
            React.createElement(Legend, null)
        )
    );
}

/* -------------------------------------------------------------------------- */
/* Mount                                                                     */
/* -------------------------------------------------------------------------- */

function mount() {
    var data = window.__GRAPH_DATA__ || { mode: 'editor', nodes: [], edges: [] };
    var rootEl = document.getElementById('graph-root');
    if (!rootEl) return;

    /* Si no hay datos, genera los 9 nodos por defecto en cliente. */
    if (!Array.isArray(data.nodes) || data.nodes.length === 0) {
        data.nodes = FIXED_NODE_DEFS.map(function (def) {
            var info = STAGE_INFO[def.key];
            return {
                id: def.key,
                key: def.key,
                label: def.label,
                stageNum: info ? info.num : '·',
                sysPrompt: '',
                userPrompt: '',
                position: { x: def.x, y: def.y },
                isFixed: true,
                inputs: [],
            };
        });
    }
    if (!Array.isArray(data.edges) || data.edges.length === 0) {
        data.edges = DEFAULT_EDGES.slice();
    }

    var mode = data.mode || 'editor';
    var asideEl = document.getElementById('graph-aside');
    var urls = {
        saveUrl:    data.saveUrl    || null,
        deleteUrl:  data.deleteUrl  || null,
        layoutUrl:  data.layoutUrl  || null,
        executeUrl: data.executeUrl || null,
        resetUrl:   data.resetUrl   || null,
    };
    data.urls = urls;

    var mainRoot = createRoot(rootEl);
    mainRoot.render(
        React.createElement(ReactFlowProvider, null,
            React.createElement(GraphAppWrap, { graphData: data, asideEl: asideEl })
        )
    );
}

/* El wrapper fuera de GraphApp garantiza que useReactFlow tenga provider. */
function GraphAppWrap(props) {
    var asideEl = props.asideEl;
    var graphData = props.graphData;
    var mode = graphData.mode || 'editor';
    var urls = graphData.urls || {};
    var _selected = useState(null);
    var selectedId = _selected[0];
    var setSelectedId = _selected[1];

    var _busy = useState(false);
    var busy = _busy[0];
    var setBusy = _busy[1];

    var _lastSaved = useState(null);
    var lastSavedTick = _lastSaved[0];
    var setLastSavedTick = _lastSaved[1];

    var dataRef = useRef(graphData);
    dataRef.current = graphData;

    function getNodeById(id) {
        return dataRef.current.nodes.find(function (n) { return (n.id || n.key) === id; });
    }

    var handleSelect = useCallback(function (id) {
        setSelectedId(id);
    }, []);

    /* Render del aside */
    useEffect(function () {
        if (!asideEl) return;
        var asideRoot = createRoot(asideEl);
        var node = selectedId ? getNodeById(selectedId) : null;
        var nodeObj = node ? {
            id: node.id || node.key,
            data: Object.assign({}, node, {
                onDelete: function () {},
            }),
        } : null;

        asideRoot.render(
            React.createElement(NodeEditor, {
                node: nodeObj,
                mode: mode,
                busy: busy,
                lastSaved: lastSavedTick,
                onChange: function (field, value) {
                    if (!node) return;
                    node[field] = value;
                },
                onSave: function () {
                    if (mode !== 'editor' || !node || !urls.saveUrl) return;
                    setBusy(true);
                    postJSON(urls.saveUrl, {
                        node_key: node.key,
                        label: node.label,
                        sys_prompt: node.sysPrompt || '',
                        user_prompt: node.userPrompt || '',
                        inputs_json: JSON.stringify(node.inputs || []),
                        position_x: node.position ? node.position.x : 0,
                        position_y: node.position ? node.position.y : 0,
                        is_fixed: !!node.isFixed,
                    }).then(function () {
                        setLastSavedTick(Date.now());
                    }).catch(function (err) {
                        window.alert('Error guardando nodo: ' + (err && err.message ? err.message : err));
                    }).then(function () {
                        setBusy(false);
                    });
                },
                onExecute: function () {
                    if (mode !== 'runner' || !node || !graphData.projectId || !urls.executeUrl) return;
                    setBusy(true);
                    postJSON(urls.executeUrl, { node_key: node.key || node.id })
                        .then(function (res) {
                            node.output = (res && res.output) || '';
                            setLastSavedTick(Date.now());
                        })
                        .catch(function (err) {
                            window.alert('Error ejecutando nodo: ' + (err && err.message ? err.message : err));
                        })
                        .then(function () {
                            setBusy(false);
                        });
                },
                onClose: function () { setSelectedId(null); },
            })
        );
    }, [selectedId, mode, busy, lastSavedTick, urls, graphData.projectId, asideEl]);

    return React.createElement(GraphApp, { graphData: graphData, onSelect: handleSelect });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
} else {
    mount();
}
