# Nubbix Support AI

Asistente de soporte con IA para clasificar consultas y preparar respuestas y acciones sugeridas para un equipo de atención al cliente.

**En desarrollo.** El repositorio contiene la definición de arquitectura inicial. La aplicación todavía no está disponible para ejecutar.

## Objetivo

Ayudar a un agente de soporte a responder consultas de facturación, problemas técnicos, gestión de cuentas y otros asuntos. Cada propuesta seguirá un contrato JSON estable y pasará por controles de entrada y salida antes de presentarse para revisión humana.

## Funcionalidades previstas

- **CLI y API:** acceso al mismo flujo de clasificación y generación.
- **Dos proveedores:** integración independiente con OpenAI y Google.
- **Laboratorio local:** pruebas de tickets y comparación de versiones de prompts.
- **Trazabilidad:** timeline e inspector de solicitudes, respuestas, reintentos, consumo y latencia.
- **Prompts versionados:** instrucciones, contexto y ejemplos en YAML, con changelog.
- **Evaluaciones:** métricas de clasificación, revisión de respuestas y casos adversariales con controles benignos.

## Arquitectura

La propuesta utiliza Python, FastAPI, Pydantic y los SDK oficiales de ambos proveedores. El laboratorio se servirá desde la misma aplicación con HTML, CSS y JavaScript, sin una compilación frontend independiente.

La [documentación de arquitectura](docs/architecture.md) describe el flujo, las responsabilidades de cada módulo y las decisiones de diseño.

## Datos y alcance

Nubbix es un SaaS ficticio utilizado como escenario de soporte. El manual y los casos serán sintéticos. Las acciones se sugieren para una persona: el asistente no ejecutará reintegros ni modificará cuentas.

Los resultados de calidad y costo se publicarán cuando existan evaluaciones reales. Las credenciales y el historial de ejecuciones permanecerán fuera del repositorio.
