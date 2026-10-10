# Compatibilidad con versiones de CapCut

## Cómo funciona la vía "borradores"

CapCut escritorio guarda cada proyecto como una carpeta en su directorio de borradores
(por defecto en Windows `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`; se puede
cambiar en CapCut → Ajustes). Dentro hay un JSON con la línea de tiempo
(`draft_content.json` o `draft_info.json`, según versión/plataforma) y `draft_meta_info.json`.

capcut-mcp escribe ambos nombres del JSON de contenido para cubrir las dos variantes.

## Lo que NO está garantizado

- **El formato no es oficial.** La estructura implementada se basa en borradores reales observados
  y en proyectos open-source que lo han estudiado. Una actualización de CapCut puede añadir campos
  obligatorios o cambiar nombres.
- **Cifrado.** Hay reportes de que versiones recientes de CapCut (y de JianYing, su versión china)
  cifran el JSON de los borradores. No he podido confirmar qué versión exacta de CapCut
  internacional empezó a hacerlo ni si sigue aceptando borradores en texto plano: **verifícalo en tu
  equipo**.

## Procedimiento de verificación (5 minutos)

1. `capcut_status` → mira `drafts.status`:
   - `ok`: tus borradores son JSON legible. Todo disponible.
   - `borradores_cifrados`: no se pueden leer/editar los proyectos creados por CapCut.
2. Crea un borrador de prueba: *“crea un borrador ‘test_mcp’ con este vídeo y un texto HOLA”*.
3. `capcut_app action=restart` y busca `test_mcp` en la pantalla de inicio de CapCut.
   - Si abre con el vídeo y el texto → modo borradores operativo.
   - Si no aparece o falla → usa la **plantilla**: crea en CapCut un proyecto vacío llamado
     `plantilla_9x16`, ciérralo y pide `template="plantilla_9x16"`. Si tampoco funciona, usa
     `render=True` (MP4 final por ffmpeg, siempre disponible).

## Reportar incompatibilidades

Abre un issue con: versión de CapCut (Ajustes → Acerca de), sistema operativo, salida de
`capcut_status` y, si es posible, un `draft_content.json` de un proyecto vacío creado por CapCut
(sin material privado). Con eso se puede ajustar el generador a tu versión.
