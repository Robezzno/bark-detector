# putosperros

> Detector acústico de ladridos con respuesta sonora automática y registro de eventos. Escucha por micrófono, distingue un ladrido del resto del ruido ambiente, y ante una **ráfaga** (varios ladridos en pocos segundos) dispara una 

> 📄 La documentación original del autor se conserva en [`README.orig.md`](README.orig.md).

## Qué es

Detector acústico de ladridos con respuesta sonora automática y registro de eventos. Escucha por micrófono, distingue un ladrido del resto del ruido ambiente, y ante una **ráfaga** (varios ladridos en pocos segundos) dispara una 

## Qué hace y cómo funciona

- **Punto(s) de entrada:** (ver estructura)
- **Stack detectado:** Python; Arduino/firmware;
- **Módulos/archivos principales:**
- `host/escucha.py`
- `host/generar_sonidos.py`

## Cómo ejecutar

Crear venv e instalar dependencias; ejecutar el punto de entrada.

## Estado

- **Último cambio (git local):** 2026-09-08 21:50:40 +0200 (hace 22 minutos)
- **Tests:** no se encontraron tests automatizados.
- **Señales de desarrollo:** sin marcadores evidentes de trabajo a medias.

## Posibles fallos

_Inferidos de señales estáticas del código, no de una auditoría en ejecución._

- **Sin tests:** cambios pueden introducir regresiones no detectadas.
- Dependencias no fijadas o entorno concreto (rutas absolutas, `local.properties`, servicios systemd) pueden romper la ejecución en otra máquina.

## Posibles mejoras

- Añadir tests automatizados y un pipeline de CI (GitHub Actions).
- Configurar CI/CD (no se detectó `.github/workflows`).
- Empaquetar con Docker para despliegue reproducible.
- Completar/actualizar la documentación funcional y fijar versiones de dependencias.

---
_README generado a partir de análisis estático del código el 2026-09-08. Las secciones «Posibles fallos» y «Posibles mejoras» son inferencias automáticas para orientar una revisión, no una auditoría exhaustiva._
