/* Todo Sobre Todo — Definiciones de nodos y componentes UI del grafo.
   Sin estado de red ni de layout: solo React.createElement.
   Sin imports de API ni de layout helpers.
*/

import React from 'react';
import { Handle, Position } from '@xyflow/react';

export const STAGE_INFO = {
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

export const FIXED_NODE_DEFS = [
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

export const DEFAULT_EDGES = [
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

export function PromptNode(props) {
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

    return React.createElement('div', { className: cls },
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
    );
}

export const NODE_TYPES = { prompt: PromptNode };

export function Legend() {
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

export function Toolbar(props) {
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

export function NodeEditor(props) {
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
