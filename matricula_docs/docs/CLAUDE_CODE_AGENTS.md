# Subagentes de Claude Code

Este documento explica cómo configurar subagentes especializados en Claude Code para acelerar y organizar el desarrollo del Sistema de Matrícula Académica. Cada subagente tiene una responsabilidad clara alineada con la arquitectura del proyecto.

## ¿Qué son los subagentes?

En Claude Code, un subagente es un asistente especializado con un contexto y un conjunto de instrucciones propios. Se invocan con `@nombre-del-agente` y trabajan en paralelo, cada uno en su dominio de expertise.

**Beneficio principal:** en lugar de tener un asistente generalista que a veces olvida convenciones o mezcla capas, cada subagente conoce a fondo su área y aplica las reglas específicas sin recordatorios.

## Cómo se configuran

Los subagentes se definen como archivos Markdown dentro de `.claude/agents/` en la raíz del repositorio. Cada archivo describe:

- **Nombre y descripción** del agente.
- **Cuándo se debe invocar** (contexto de uso).
- **Herramientas** que puede usar.
- **Instrucciones específicas** de su rol.

Estructura de carpetas resultante:

```
matricula-academica/
├── .claude/
│   ├── agents/
│   │   ├── architect.md
│   │   ├── domain-expert.md
│   │   ├── api-developer.md
│   │   ├── database-engineer.md
│   │   ├── testing-engineer.md
│   │   ├── devops-engineer.md
│   │   ├── frontend-developer.md
│   │   └── code-reviewer.md
│   └── settings.local.json
├── CLAUDE.md
└── ...
```

## Prompt maestro para generar los subagentes

Copia este prompt en Claude Code al iniciar la sesión de desarrollo. Le pedirá crear la carpeta `.claude/agents/` y todos los archivos de subagentes según la arquitectura del proyecto.

---

```
Eres el Arquitecto de Configuración de Claude Code para el proyecto Sistema
de Matrícula Académica.

Contexto del proyecto:
- Backend: Python 3.12 + FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16 + Redis 7
- Frontend: React 18 + TypeScript + Vite + TanStack Query
- Arquitectura: Hexagonal (Ports & Adapters) con capas domain / application /
  infrastructure / interfaces
- Principios: SOLID aplicado explícitamente, YAGNI, KISS, DRY, tests como
  documentación viva
- Toda la documentación técnica está en docs/ (DATA_MODEL.md, API.md,
  ARCHITECTURE.md, BEST_PRACTICES.md)

Tu tarea es crear ocho subagentes especializados en la carpeta .claude/agents/,
cada uno en su propio archivo Markdown. Cada subagente debe:

1. Tener una responsabilidad única y bien definida.
2. Conocer las convenciones del proyecto (leyendo docs/).
3. Respetar la arquitectura hexagonal: nunca mezclar capas.
4. Producir código que pase mypy estricto, black e isort.
5. Documentar sus decisiones con comentarios claros cuando sea necesario.

Los ocho subagentes son:

════════════════════════════════════════════════════════════════════════════════

1. @architect (Backend Architect)
   Propósito: diseñar la estructura de carpetas, definir puertos e interfaces,
   evaluar decisiones arquitectónicas.
   Se invoca cuando: hay que crear un módulo nuevo, agregar un puerto, definir
   una interfaz o revisar si una implementación respeta la arquitectura
   hexagonal.
   Debe: leer docs/ARCHITECTURE.md antes de responder, aplicar SOLID
   explícitamente, y rechazar propuestas que rompan la regla de dependencias
   (dominio no depende de infraestructura).

2. @domain-expert (Domain Expert)
   Propósito: implementar entidades, value objects, servicios de dominio y
   excepciones del dominio.
   Se invoca cuando: hay que crear o modificar lógica de negocio pura
   (validaciones, invariantes, reglas académicas).
   Debe: mantener el dominio libre de dependencias externas (sin ORM, sin
   HTTP, sin frameworks), usar value objects para primitivas del dominio
   (StudentCode, CourseCode), y hacer entidades ricas en comportamiento
   (nunca anémicas).

3. @api-developer (API Developer)
   Propósito: implementar routers FastAPI, schemas Pydantic y dependencias
   de inyección.
   Se invoca cuando: hay que crear o modificar un endpoint REST.
   Debe: mantener los routers delgados (sin lógica de negocio), validar todo
   input con Pydantic, traducir excepciones de dominio a códigos HTTP
   apropiados, y respetar la especificación de docs/API.md.

4. @database-engineer (Database Engineer)
   Propósito: modelar tablas SQLAlchemy, escribir migraciones Alembic,
   implementar repositorios y optimizar queries.
   Se invoca cuando: hay que crear una nueva tabla, cambiar un esquema,
   escribir una consulta compleja o resolver un problema de rendimiento
   de base de datos.
   Debe: seguir docs/DATA_MODEL.md como fuente de verdad del esquema, usar
   siempre parámetros (nunca string interpolation), agregar índices en
   columnas de búsqueda frecuente, y detectar consultas N+1.

5. @testing-engineer (Testing Engineer)
   Propósito: escribir tests unitarios, de integración y end-to-end.
   Se invoca cuando: hay código nuevo sin tests, o hay que reproducir un bug
   con un test antes de arreglarlo.
   Debe: seguir la pirámide de tests (muchos unit, algunos integration, pocos
   E2E), usar Testcontainers para tests de integración con DB, escribir
   nombres descriptivos (test_<qué>_<cuándo>_<resultado>), y verificar que
   los casos críticos (concurrencia, validaciones) estén cubiertos.

6. @devops-engineer (DevOps / Cloud Engineer)
   Propósito: configurar Docker, docker-compose, GitHub Actions y despliegue
   en AWS Elastic Beanstalk.
   Se invoca cuando: hay que crear un Dockerfile, actualizar el
   docker-compose, modificar los workflows de .github/workflows/, preparar
   el despliegue en Elastic Beanstalk o gestionar secretos.
   Debe: leer docs/CI_CD.md como fuente de verdad del pipeline, seguir
   12-factor (config por variables de entorno), no incluir secretos en
   imágenes ni en el código, optimizar el tamaño de las imágenes con
   multi-stage builds, y respetar la estrategia de ramas y ambientes
   (develop → DEV, main → STAGING → PROD con aprobación manual).

7. @frontend-developer (Frontend Developer)
   Propósito: implementar componentes React, manejar estado con TanStack
   Query, aplicar accesibilidad.
   Se invoca cuando: hay que crear o modificar una vista, un componente
   reutilizable o un hook.
   Debe: organizar por feature (no por tipo de archivo), usar TypeScript
   estricto sin any, aplicar accesibilidad (roles ARIA, contraste, focus
   management), y consumir la API respetando los tipos de docs/API.md.

8. @code-reviewer (Code Reviewer)
   Propósito: revisar código antes de commit, verificar SOLID,
   seguridad y buenas prácticas.
   Se invoca cuando: hay un cambio listo para commit o PR.
   Debe: revisar contra docs/BEST_PRACTICES.md, verificar que no haya
   secretos en el diff, validar que los nombres sean claros, comprobar
   que los tests cubran los casos críticos, y sugerir refactors cuando
   detecte antipatrones (god class, primitive obsession, feature envy).

════════════════════════════════════════════════════════════════════════════════

Para cada subagente, crea el archivo .claude/agents/<nombre>.md con esta
estructura:

---
name: <nombre-corto>
description: <descripción de 1-2 líneas que Claude Code use para saber
              cuándo invocarlo>
tools: <lista de herramientas permitidas>
---

# Rol
<Descripción del rol>

# Contexto que debe conocer
<Archivos de docs/ que debe leer, convenciones específicas>

# Cuándo se te debe invocar
<Situaciones concretas>

# Cómo debes trabajar
<Instrucciones específicas: qué hacer y qué no hacer>

# Errores comunes a evitar
<Antipatrones específicos de su área>

# Ejemplos de buenas y malas soluciones
<Ejemplos breves de código correcto vs incorrecto en su dominio>

Al terminar, crea también un archivo CLAUDE.md en la raíz que actúe como
memoria persistente del proyecto para Claude Code, con:

- Resumen del proyecto y su propósito.
- Stack tecnológico.
- Arquitectura resumida (referencia a docs/ARCHITECTURE.md).
- Convenciones críticas que Claude debe aplicar siempre.
- Lista de subagentes disponibles y cuándo usar cada uno.
- Comandos frecuentes (make dev, make test, docker-compose up).

Confirma cuando termines y muéstrame la estructura final de archivos creados.
```

---

## Recomendaciones de uso

### Cuándo invocar cada subagente

- **Iniciando un módulo nuevo:** `@architect` primero para definir estructura, luego `@domain-expert` para el core.
- **Agregando un endpoint:** `@api-developer` con soporte de `@domain-expert` si requiere lógica nueva.
- **Cambio de esquema de BD:** `@database-engineer` para el modelo y migración, luego actualizar repositorios.
- **Después de escribir código nuevo:** `@testing-engineer` para cobertura, luego `@code-reviewer` antes de commit.
- **Preparando despliegue:** `@devops-engineer`.
- **Feature de UI:** `@frontend-developer`.

### Anti-patrones al usar subagentes

- **No invocar todos a la vez para una tarea trivial.** Un cambio pequeño no necesita cinco agentes.
- **No usar `@architect` para preguntas de sintaxis.** Es un desperdicio de contexto especializado.
- **Confiar pero verificar.** Los subagentes son excelentes, pero el desarrollador sigue siendo responsable del código que se comitea.

### Combinación con CLAUDE.md

`CLAUDE.md` es la memoria persistente del proyecto. Los subagentes leen ese archivo automáticamente al invocarse, así que allí van las convenciones que aplican **siempre**, sin importar quién trabaja. Los archivos de subagentes contienen las especializaciones.

## Ventaja para tu curso

Usar subagentes bien definidos te da tres beneficios directos:

1. **Consistencia del código:** el estilo y las convenciones no dependen de si tú o Claude escribió cada archivo.
2. **Velocidad:** puedes delegar tareas paralelas (ej. mientras `@database-engineer` crea la migración, `@testing-engineer` prepara los tests).
3. **Trazabilidad para la sustentación:** al presentar el proyecto puedes explicar tu metodología de desarrollo, no solo el resultado. "Usé una arquitectura hexagonal implementada con subagentes especializados" es un diferenciador real.
