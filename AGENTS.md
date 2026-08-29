# AGENTS

Guía para agentes de IA que trabajan en este proyecto.

## Convenciones

- Sigue las convenciones del repositorio (TypeScript estricto, sin `any`).
- Mantén las funciones pequeñas y con responsabilidad única.
- No añadas dependencias innecesarias.
- Documenta únicamente cuando aporte valor.

## Estructura

- Lógica de negocio en servicios.
- Comandos o entrypoints como capa fina.
- Errores tipados con clases específicas del proyecto.
- Tests junto al código que validan.

## Validación

Antes de cerrar un cambio ejecuta los scripts de `package.json` y los tests disponibles.
