/* Todo Sobre Todo — Editor de grafo y runner.
   Carga via importmap (esm.sh). Sin build step. Sin dependencias NPM.

   Este modulo expone tanto el editor (modo "editor") como el runner
   (modo "runner") en funcion de window.__GRAPH_DATA__.mode. Los endpoints
   de backend estan stubbed; el otro agente los implementara en paralelo.
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
} from '@xyflow/react';

/* -------------------------------------------------------------------------- */
/* Constantes: 9 nodos fijos del pipeline                                     */
/* -------------------------------------------------------------------------- */

const FIXED_NODE_DEFS = [
    { key: 'research',         label: 'Investigación',    x: 0,    y: 0   },
    { key: 'concept',          label: 'Concepto',         x: 280,  y: 0   },
    { key: 'script_long',      label: 'Guion 5 min',      x: 560,  y: 0   },
    { key: 'script_short',     label: 'Guion 1 min',      x: 560,  y: 180 },
    { key: 'scenes',           label: 'Escenas',          x: 840,  y: 90  },
    { key: 'metadata_youtube', label: 'Metadata YouTube', x: 1120, y: 0   },
    { key: 'metadata_shorts',  label: 'Metadata Shorts',  x: 1120, y: 180 },
    { key: 'thumbnail_long',   label: 'Miniatura 5 min',  x: 1400, y: 0   },
    { key: 'thumbnail_short',  label: 'Miniatura 1 min',  x: 1400, y: 180 },
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
/* Endpoints mock                                                             */
/* -------------------------------------------------------------------------- */

function mockDelay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

// TODO: integrate with backend routes — currently stub returns OK.
async function saveNode(profileId, node) {
    await mockDelay(200);
    return { ok: true, nodeId: node.id };
}

// TODO: integrate with backend routes — currently stub returns OK.
async function deleteNode(profileId, nodeId) {
    await mockDelay(200);
    return { ok: true, nodeId: nodeId };
}

// TODO: integrate with backend routes — currently stub returns OK.
async function saveLayout(profileId, payload) {
    await mockDelay(200);
    return { ok: true, payload: payload };
}

// TODO: integrate with backend routes — currently stub returns OK.
async function executeNode(projectId, nodeKey) {
    await new Promise(function (r) { setTimeout(r, 1500); });
    return {
        ok: true,
        nodeKey: nodeKey,
        output: '[MOCK OUTPUT] Ejecución simulada del nodo ' + nodeKey + '...\n' +
                'Sin backend conectado todavía. Esta interfaz se implementará ' +
                'vía /projects/' + projectId + '/run/execute.',
    };
}

/* -------------------------------------------------------------------------- */
/* Custom node                                                                */
/* -------------------------------------------------------------------------- */

function PromptNode(props) {
    var data = props.data || {};
    var status = data.status || 'idle';
    var cls = 'react-flow__node-prompt' +
              (status === 'running' ? ' is-running' : '') +
              (status === 'ok'      ? ' is-ok'      : '') +
              (status === 'error'   ? ' is-error'   : '');

    var preview = (data.sysPrompt || '').slice(0, 90);

    return (
        React.createElement('div', { className: cls },
            React.createElement(Handle, {
                type: 'target',
                position: Position.Top,
                style: { background: 'var(--paper-3)' },
            }),
            React.createElement('div', { className: 'node-title' },
                React.createElement('span', { className: 'status-dot' }),
                React.createElement('strong', null, data.label || data.key || props.id)
            ),
            preview ? React.createElement('div', { className: 'preview' }, preview + (data.sysPrompt && data.sysPrompt.length > 90 ? '…' : '')) : null,
            !data.isFixed && data.onDelete
                ? React.createElement('button', {
                    className: 'btn btn-danger btn-sm node-delete',
                    onClick: function (e) { e.stopPropagation(); data.onDelete(props.id); },
                }, 'Eliminar')
                : null,
            React.createElement(Handle, {
                type: 'source',
                position: Position.Bottom,
                style: { background: 'var(--paper-3)' },
            })
        )
    );
}

const NODE_TYPES = { prompt: PromptNode };

/* -------------------------------------------------------------------------- */
/* Side panel: editor del nodo seleccionado                                   */
/* -------------------------------------------------------------------------- */

function NodeEditor(props) {
    var node = props.node;
    var onChange = props.onChange;
    var onSave = props.onSave;
    var onExecute = props.onExecute;
    var onClose = props.onClose;
    var mode = props.mode;
    var busy = props.busy;

    if (!node) {
        return (
            React.createElement('div', { className: 'panel graph-aside-panel' },
                React.createElement('div', { className: 'panel-head' },
                    React.createElement('h3', null, 'Sin selección')
                ),
                React.createElement('p', { className: 'hint' },
                    'Selecciona un nodo del grafo para editar su prompt. ' +
                    'Los nueve nodos fijos cubren el pipeline completo.'
                )
            )
        );
    }

    var data = node.data || {};

    return (
        React.createElement('div', { className: 'panel graph-aside-panel' },
            React.createElement('div', { className: 'panel-head' },
                React.createElement('div', null,
                    React.createElement('p', { className: 'eyebrow' }, data.key || node.id),
                    React.createElement('h3', null, data.label || node.id)
                ),
                React.createElement('button', {
                    className: 'btn btn-ghost btn-sm',
                    onClick: onClose,
                }, 'Cerrar')
            ),
            data.isFixed
                ? React.createElement('p', { className: 'chip chip-done', style: { alignSelf: 'flex-start' } }, 'Nodo fijo del pipeline')
                : React.createElement('p', { className: 'chip', style: { alignSelf: 'flex-start' } }, 'Nodo auxiliar'),
            React.createElement('label', { className: 'field' },
                React.createElement('span', { className: 'label' }, 'Instrucciones del sistema (sysPrompt)'),
                React.createElement('textarea', {
                    rows: 5,
                    value: data.sysPrompt || '',
                    onChange: function (e) { onChange('sysPrompt', e.target.value); },
                })
            ),
            React.createElement('label', { className: 'field' },
                React.createElement('span', { className: 'label' }, 'Petición (userPrompt)'),
                React.createElement('textarea', {
                    rows: 8,
                    value: data.userPrompt || '',
                    onChange: function (e) { onChange('userPrompt', e.target.value); },
                })
            ),
            React.createElement('div', { className: 'actions' },
                React.createElement('button', {
                    className: 'btn btn-primary',
                    disabled: busy,
                    onClick: onSave,
                }, busy ? 'Guardando…' : 'Guardar'),
                mode === 'runner'
                    ? React.createElement('button', {
                        className: 'btn btn-ghost',
                        disabled: busy,
                        onClick: onExecute,
                    }, busy ? 'Ejecutando…' : 'Ejecutar')
                    : null
            ),
            data.status && data.status !== 'idle'
                ? React.createElement('p', { className: 'hint mt-2' }, 'Estado: ', React.createElement('b', null, data.status))
                : null
        )
    );
}

/* -------------------------------------------------------------------------- */
/* Layout grid                                                                */
/* -------------------------------------------------------------------------- */

function buildInitialNodes(graphData, handlers) {
    if (Array.isArray(graphData.nodes) && graphData.nodes.length > 0) {
        return graphData.nodes.map(function (n) {
            return {
                id: n.id || n.key,
                type: 'prompt',
                position: n.position || { x: 0, y: 0 },
                data: {
                    key: n.key,
                    label: n.label || n.key,
                    sysPrompt: n.sysPrompt || '',
                    userPrompt: n.userPrompt || '',
                    isFixed: !!n.isFixed,
                    status: n.status || 'idle',
                    output: n.output || '',
                    onDelete: handlers.onDelete,
                },
            };
        });
    }
    // Fallback: 9 nodos fijos por defecto
    return FIXED_NODE_DEFS.map(function (def) {
        return {
            id: def.key,
            type: 'prompt',
            position: { x: def.x, y: def.y },
            data: {
                key: def.key,
                label: def.label,
                sysPrompt: '',
                userPrompt: '',
                isFixed: true,
                status: 'idle',
                output: '',
                onDelete: handlers.onDelete,
            },
        };
    });
}

function buildInitialEdges(graphData) {
    if (Array.isArray(graphData.edges) && graphData.edges.length > 0) {
        return graphData.edges.map(function (e) {
            return {
                id: e.id,
                source: e.source,
                target: e.target,
                animated: !!e.animated,
            };
        });
    }
    return DEFAULT_EDGES.map(function (e) {
        return { id: e.id, source: e.source, target: e.target };
    });
}

/* -------------------------------------------------------------------------- */
/* App principal                                                              */
/* -------------------------------------------------------------------------- */

function GraphApp(props) {
    var graphData = props.graphData;
    var mode = graphData.mode || 'editor';
    var profileId = graphData.profileId;
    var projectId = graphData.projectId;

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

    var selectedNode = useMemo(function () {
        var arr = (nodes || []).filter(function (n) { return n.selected; });
        return arr.length ? arr[0] : null;
    }, [nodes]);

    var busyRef = useRef(false);
    var layoutTimerRef = useRef(null);

    /* Inyecta el onDelete en cada nodo tras el primer render */
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
        if (!window.confirm('¿Eliminar el nodo «' + id + '»? Las conexiones que apuntan o salen de él también desaparecerán.')) {
            return;
        }
        setNodes(function (curr) { return curr.filter(function (n) { return n.id !== id; }); });
        setEdges(function (curr) {
            return curr.filter(function (e) { return e.source !== id && e.target !== id; });
        });
        if (mode === 'editor' && profileId) {
            // TODO: integrate with backend routes — currently stub returns OK.
            deleteNode(profileId, id).catch(function () { /* ignore */ });
        }
    }, [setNodes, setEdges, mode, profileId]);

    var handleConnect = useCallback(function (params) {
        setEdges(function (eds) {
            return addEdge(Object.assign({}, params, { animated: mode === 'runner' }), eds);
        });
    }, [setEdges, mode]);

    /* Auto-save layout (debounce 600ms) */
    var persistLayout = useCallback(function () {
        if (mode !== 'editor' || !profileId) return;
        if (layoutTimerRef.current) clearTimeout(layoutTimerRef.current);
        layoutTimerRef.current = setTimeout(function () {
            var payload = {
                nodes: nodes.map(function (n) {
                    return { id: n.id, position: n.position, type: n.type };
                }),
                edges: edges,
            };
            // TODO: integrate with backend routes — currently stub returns OK.
            saveLayout(profileId, payload).catch(function () { /* ignore */ });
        }, 600);
    }, [nodes, edges, mode, profileId]);

    useEffect(function () {
        persistLayout();
    }, [nodes, edges, persistLayout]);

    var handleSaveSelected = useCallback(function () {
        if (!selectedNode || !profileId) return;
        busyRef.current = true;
        saveNode(profileId, {
            id: selectedNode.id,
            data: selectedNode.data,
        }).finally(function () {
            busyRef.current = false;
        });
    }, [selectedNode, profileId]);

    var handleExecuteSelected = useCallback(function () {
        if (!selectedNode || !projectId) return;
        var id = selectedNode.id;
        var key = (selectedNode.data && selectedNode.data.key) || id;
        updateNodeData(id, { status: 'running', output: '' });
        executeNode(projectId, key).then(function (res) {
            updateNodeData(id, { status: 'ok', output: res.output });
            renderRunOutput(key, res.output);
        }).catch(function () {
            updateNodeData(id, { status: 'error', output: 'Error de ejecución mock.' });
        });
    }, [selectedNode, projectId, updateNodeData]);

    var handleAddNode = useCallback(function () {
        var i = (nodes.filter(function (n) { return /^custom_/.test(n.id); }).length) + 1;
        var id = 'custom_' + i;
        var last = nodes[nodes.length - 1];
        var pos = last
            ? { x: last.position.x + 240, y: last.position.y }
            : { x: 0, y: 240 };
        var newNode = {
            id: id,
            type: 'prompt',
            position: pos,
            data: {
                key: id,
                label: 'Nodo ' + i,
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

    var handleSidebarChange = useCallback(function (field, value) {
        if (!selectedNode) return;
        updateNodeData(selectedNode.id, (function () { var p = {}; p[field] = value; return p; })());
    }, [selectedNode, updateNodeData]);

    var handleCloseAside = useCallback(function () {
        setNodes(function (curr) {
            return curr.map(function (n) { return Object.assign({}, n, { selected: false }); });
        });
    }, [setNodes]);

    var onSelectionChange = useCallback(function (sel) {
        // Noop: selectedNode se recalcula por la prop selected de cada nodo.
        return sel;
    }, []);

    return (
        React.createElement(ReactFlow,
            {
                nodes: nodes,
                edges: edges,
                onNodesChange: onNodesChange,
                onEdgesChange: onEdgesChange,
                onConnect: handleConnect,
                onSelectionChange: onSelectionChange,
                nodeTypes: NODE_TYPES,
                fitView: true,
                minZoom: 0.3,
                maxZoom: 1.5,
                proOptions: { hideAttribution: true },
            },
            React.createElement(Background, { gap: 24, size: 1, color: 'rgba(165,177,194,0.08)' }),
            React.createElement(Controls, null),
            React.createElement(MiniMap, {
                pannable: true,
                zoomable: true,
                maskColor: 'rgba(10,13,19,0.7)',
                nodeColor: '#4FBF87',
            }),
            React.createElement(Panel, { position: 'top-right' },
                React.createElement('div', { className: 'actions' },
                    React.createElement('button', {
                        className: 'btn btn-ghost btn-sm',
                        onClick: handleAddNode,
                    }, '+ Añadir nodo'),
                    mode === 'runner' && projectId
                        ? React.createElement('button', {
                            className: 'btn btn-primary btn-sm',
                            onClick: function () {
                                nodes.forEach(function (n) {
                                    updateNodeData(n.id, { status: 'running', output: '' });
                                    var key = (n.data && n.data.key) || n.id;
                                    executeNode(projectId, key).then(function (res) {
                                        updateNodeData(n.id, { status: 'ok', output: res.output });
                                    }).catch(function () {
                                        updateNodeData(n.id, { status: 'error', output: 'Error mock.' });
                                    });
                                });
                            },
                        }, 'Ejecutar todo')
                        : null
                )
            )
        )
    );
}

/* -------------------------------------------------------------------------- */
/* Output panel (solo runner)                                                 */
/* -------------------------------------------------------------------------- */

function renderRunOutput(key, output) {
    var panel = document.getElementById('run-output');
    if (!panel) return;
    panel.innerHTML = '';
    var head = document.createElement('div');
    head.className = 'panel-head';
    var h = document.createElement('h3');
    h.textContent = 'Salida del nodo: ' + key;
    head.appendChild(h);
    panel.appendChild(head);
    var pre = document.createElement('pre');
    pre.className = 'run-output-pre';
    pre.textContent = output;
    panel.appendChild(pre);
}

/* -------------------------------------------------------------------------- */
/* Mount                                                                      */
/* -------------------------------------------------------------------------- */

function mount() {
    var data = window.__GRAPH_DATA__ || { mode: 'editor', nodes: [], edges: [] };
    var rootEl = document.getElementById('graph-root');
    var asideEl = document.getElementById('graph-aside');
    if (!rootEl) return;

    /* Si no hay datos, genera los 9 nodos por defecto en cliente. */
    if (!Array.isArray(data.nodes) || data.nodes.length === 0) {
        data.nodes = FIXED_NODE_DEFS.map(function (def) {
            return {
                id: def.key,
                key: def.key,
                label: def.label,
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

    var root = createRoot(rootEl);
    root.render(
        React.createElement(ReactFlowProvider, null,
            React.createElement(GraphApp, { graphData: data })
        )
    );

    /* Render del aside en su propio root */
    if (asideEl) {
        var selectedId = null;
        function AsideRoot() {
            var _u = useState(selectedId);
            var current = _u[0];
            var setCurrent = _u[1];

            useEffect(function () {
                function handler(e) {
                    var d = e && e.detail;
                    if (!d) return;
                    selectedId = d.id;
                    setCurrent(d.id);
                }
                window.addEventListener('graph:select', handler);
                return function () { window.removeEventListener('graph:select', handler); };
            }, []);

            var node = current
                ? { id: current, data: data.nodes.find(function (n) { return n.id === current; }) || { key: current, label: current } }
                : null;

            return React.createElement(NodeEditor,
                {
                    node: node,
                    onChange: function (field, value) {
                        if (!node) return;
                        var n = data.nodes.find(function (x) { return x.id === current; });
                        if (n) n[field] = value;
                        if (mode === 'editor' && profileId) {
                            // TODO: integrate with backend routes — currently stub returns OK.
                            saveNode(profileId, n).catch(function () {});
                        }
                    },
                    onSave: function () {
                        if (mode !== 'editor' || !profileId || !current) return;
                        var n = data.nodes.find(function (x) { return x.id === current; });
                        if (!n) return;
                        // TODO: integrate with backend routes — currently stub returns OK.
                        saveNode(profileId, n).catch(function () {});
                    },
                    onExecute: function () {
                        if (mode !== 'runner' || !projectId || !current) return;
                        var n = data.nodes.find(function (x) { return x.id === current; });
                        var key = (n && n.key) || current;
                        if (n) n.status = 'running';
                        executeNode(projectId, key).then(function (res) {
                            if (n) { n.status = 'ok'; n.output = res.output; }
                            renderRunOutput(key, res.output);
                            setCurrent(current); // force re-render
                        });
                    },
                    onClose: function () { selectedId = null; setCurrent(null); },
                    mode: data.mode || 'editor',
                    busy: false,
                }
            );
        }
        var mode = data.mode || 'editor';
        var profileId = data.profileId;
        var projectId = data.projectId;

        var asideRoot = createRoot(asideEl);
        asideRoot.render(React.createElement(AsideRoot));

        /* Listeners: cuando ReactFlow cambia la selección, propagamos al aside */
        setTimeout(function () {
            var rfEl = rootEl.querySelector('.react-flow');
            if (rfEl) {
                rfEl.addEventListener('click', function (e) {
                    var nodeEl = e.target.closest('.react-flow__node');
                    if (!nodeEl) return;
                    var id = nodeEl.getAttribute('data-id');
                    if (id) {
                        window.dispatchEvent(new CustomEvent('graph:select', { detail: { id: id } }));
                    }
                });
            }
        }, 100);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
} else {
    mount();
}
