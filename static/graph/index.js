/* Todo Sobre Todo — Entry point del editor de grafo y del runner.
   Carga via importmap (esm.sh). Sin build step. Sin dependencias NPM.
   Importa los modulos del directorio graph/ y monta la app.
*/

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
    ReactFlow,
    ReactFlowProvider,
    Background,
    Controls,
    MiniMap,
    Panel,
    useNodesState,
    useEdgesState,
    addEdge,
    useReactFlow,
} from '@xyflow/react';

import { FIXED_NODE_DEFS, DEFAULT_EDGES, STAGE_INFO, NODE_TYPES, Legend, Toolbar, NodeEditor } from './nodes.js';
import { postJSON, saveNodeStub, deleteNodeStub, saveLayoutStub, executeNodeStub } from './api.js';
import { buildInitialNodes, buildInitialEdges } from './layout.js';

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
            } catch (e) { /* RF puede no estar listo todavia */ }
        }, 60);
        return function () { clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /* Propagar seleccion al aside */
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
        if (!window.confirm('¿Eliminar el nodo «' + id + '»? Las conexiones que apuntan o salen de el tambien desapareceran.')) {
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

    /* Auto-save layout (debounce 600ms) — solo editor */
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
        if (!window.confirm('¿Ejecutar los ' + nodes.length + ' nodos en cadena? Esta accion no se puede deshacer.')) return;
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

function mount() {
    var data = window.__GRAPH_DATA__ || { mode: 'editor', nodes: [], edges: [] };
    var rootEl = document.getElementById('graph-root');
    if (!rootEl) return;

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
