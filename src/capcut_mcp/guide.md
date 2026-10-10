# Guía operativa: CapCut ↔ capcut-mcp

CapCut **no tiene API pública oficial**. Este servidor lo opera por tres vías:

| Vía | Qué hace | Fiabilidad |
|---|---|---|
| **A. Borradores** | Escribe/lee proyectos de CapCut escritorio (`draft_content.json`) en su carpeta de borradores. Al abrir CapCut aparecen como proyectos editables. | Depende de la versión de CapCut (ver `capcut_status`). |
| **B. Procesamiento ffmpeg** | Cortes, silencios, audio, reencuadre, música, subtítulos, render final. | Alta: no depende de CapCut. |
| **C. Control de la app** | Abrir, cerrar, reiniciar CapCut. | Alta (Windows/macOS). |

## Mapa de funciones de CapCut → herramienta

| Función en CapCut | Automatizado con | Notas |
|---|---|---|
| Importar medios | `capcut_import`, `capcut_download` | Clasifica en carpetas del proyecto. |
| Dividir / recortar / borrar tramos | `capcut_cut`, `capcut_draft_create` (`in`/`out`) | En borrador: no destructivo. |
| Eliminar silencios / pausas | `capcut_detect_silences`, `capcut_remove_silences`, `capcut_auto_edit` | Umbral `silence_db`, `min_silence`, `padding`. |
| Eliminar muletillas | `capcut_find_fillers`, `capcut_auto_edit(remove_fillers)` | Requiere transcripción. |
| Subtítulos automáticos | `capcut_transcribe` + `capcut_draft_add_captions` | Editables en CapCut (pista de texto). |
| Texto / títulos / hook | `texts` en timeline, `capcut_title_card` | Posición y: 0.55 arriba, -0.6 abajo. |
| Mejora de voz / reducir ruido / normalizar | `capcut_enhance_audio` | Presets voice, podcast, noisy, normalize, music. |
| Música de fondo, fades, ducking | `audio` en timeline (`loop`, `fade_out`, `volume`), `capcut_mix_music` | Ducking real sólo en render ffmpeg. |
| Velocidad | `speed` en segmento, `capcut_speed` | 0.25x–4x. |
| Formato 9:16 / 1:1 / 16:9 | `canvas`, `capcut_reframe` | `fit=fill` llena el lienzo. |
| Picture-in-picture / logo / overlays | `overlay` en timeline | `scale`, `x`, `y`, `alpha`. |
| Duplicar proyecto (versiones A/B) | `capcut_draft_duplicate` | |
| Exportar | `capcut_auto_edit(render=True)` o herramientas de render | El botón Exportar de CapCut no es automatizable sin control de UI. |
| Efectos, transiciones, filtros, stickers, plantillas, voces IA, auto-reframe IA de CapCut | Manual en CapCut | Son recursos de la nube de CapCut con IDs internos no documentados. Usa una plantilla (`template`) que ya los contenga. |

## Convenciones
* Tiempos en **segundos**.
* Coordenadas normalizadas: (0,0) centro del lienzo; x∈[-1,1] izquierda→derecha; y∈[-1,1] abajo→arriba.
* `scale` 1.0 = encajado al lienzo; para llenar 9:16 con un vídeo 16:9 usa ≈3.16 (lo calcula `fit=fill`).
* Tamaño de texto (`size`) ≈ 5–15; 8 para subtítulos, 11–13 para hooks.

## Flujo "editor automático"
1. `capcut_project_create(name="Reel Lunes")`
2. `capcut_import(project, ["D:/Grabaciones/toma1.mp4"])`
3. `capcut_auto_edit(project, source, hook_text="...", music="D:/CapCut_Studio/_Library/music/x.mp3")`
4. Reiniciar CapCut (`capcut_app action=restart`) → abrir el borrador → retoques finales y exportar.

## Si los borradores están cifrados
Algunas versiones recientes de CapCut cifran `draft_content.json`. Entonces:
* Prueba `capcut_draft_create` igualmente: puede que CapCut siga abriendo borradores en texto plano.
* Si no los abre, usa el render directo (`render=True`) — el resultado es un MP4 final.
* Alternativa: instalar una versión de CapCut que guarde en texto plano (bajo tu propio criterio).
