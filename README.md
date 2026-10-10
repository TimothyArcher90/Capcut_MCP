# CapCut MCP

Servidor **MCP (Model Context Protocol)** para operar **CapCut escritorio** desde Claude.
Tú das las órdenes en el chat y Claude edita: cortes, silencios, muletillas, mejora de audio,
subtítulos editables, música, títulos, assets y la creación del proyecto dentro de CapCut,
con todo organizado automáticamente en `D:\CapCut_Studio`.

> **Importante (léelo):** CapCut **no tiene API pública oficial**. Este servidor trabaja
> escribiendo los archivos de proyecto (borradores) que CapCut lee, y procesando medios con
> ffmpeg. El formato de borrador no está documentado y puede cambiar con las actualizaciones de
> CapCut; algunas versiones recientes lo cifran. Ejecuta `capcut_status` para saber qué funciona
> en tu instalación. El render directo con ffmpeg funciona siempre. Ver [docs/COMPATIBILIDAD.md](docs/COMPATIBILIDAD.md).

## Qué hace

| Área | Herramientas |
|---|---|
| Diagnóstico y app | `capcut_status`, `capcut_app` (abrir/cerrar/reiniciar CapCut) |
| Workspace en D:\ | `capcut_project_create`, `capcut_project_list`, `capcut_project_info`, `capcut_import` |
| Assets | `capcut_download` (URL / yt-dlp), `capcut_save_generated` (SVG, SRT, LUT que crea Claude), `capcut_title_card`, `capcut_library` |
| Análisis | `capcut_probe`, `capcut_contact_sheet`, `capcut_thumbnail`, `capcut_detect_silences`, `capcut_loudness`, `capcut_transcribe`, `capcut_find_fillers` |
| Edición de medios | `capcut_cut`, `capcut_concat`, `capcut_remove_silences`, `capcut_enhance_audio`, `capcut_reframe`, `capcut_speed`, `capcut_extract_audio`, `capcut_mix_music`, `capcut_burn_subtitles` |
| Borradores CapCut | `capcut_draft_list`, `capcut_draft_inspect`, `capcut_draft_create`, `capcut_draft_add`, `capcut_draft_add_captions`, `capcut_draft_set_volume`, `capcut_draft_duplicate` |
| **Automático** | `capcut_auto_edit`: audio → silencios → transcripción → muletillas → subtítulos → hook → música → borrador en CapCut → render opcional |

Recurso `capcut://guide`: mapa de funciones de CapCut ↔ herramientas (Claude lo usa para “entender” CapCut).

## Estructura de carpetas (automática)

```
D:\CapCut_Studio\
├── _Library\  music  sfx  fonts  brand  templates  luts  drafts_backups
└── Projects\
    └── 2026-10-10_reel-lunes\
        ├── 00_Inbox\
        ├── 01_Raw\video  audio\          ← original intacto
        ├── 02_Assets\images broll music sfx fonts generated\
        ├── 03_Processed\audio cuts reframed\
        ├── 04_Subtitles\
        ├── 05_Drafts_Backup\
        ├── 06_Exports\
        ├── 07_Thumbnails\
        └── project.json                  ← manifiesto + historial
```

## Instalación (Windows)

1. **Python 3.10+** y **ffmpeg** en el PATH (`winget install Gyan.FFmpeg`).
2. Instalar:
   ```powershell
   git clone https://github.com/TimothyArcher90/Capcut_MCP.git D:\CapCut_Studio\_mcp
   cd D:\CapCut_Studio\_mcp
   python -m venv .venv
   .venv\Scripts\pip install -e ".[all]"
   ```
   `[all]` añade transcripción local (faster-whisper), yt-dlp y SVG→PNG. Sin extras: `pip install -e .`
3. Conectar con **Claude Desktop**: edita `%APPDATA%\Claude\claude_desktop_config.json`
   (ejemplo completo en [examples/claude_desktop_config.json](examples/claude_desktop_config.json)):
   ```json
   {
     "mcpServers": {
       "capcut": {
         "command": "D:\\CapCut_Studio\\_mcp\\.venv\\Scripts\\capcut-mcp.exe",
         "env": { "CAPCUT_STUDIO_ROOT": "D:\\CapCut_Studio" }
       }
     }
   }
   ```
   Con **Claude Code**: `claude mcp add capcut -- D:\CapCut_Studio\_mcp\.venv\Scripts\capcut-mcp.exe`
4. Reinicia Claude y pide: *“Ejecuta capcut_status”*.

### Variables de entorno

| Variable | Por defecto |
|---|---|
| `CAPCUT_STUDIO_ROOT` | `D:\CapCut_Studio` (si existe D:), si no `~/CapCut_Studio` |
| `CAPCUT_DRAFTS_DIR` | `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` (verifica en CapCut → Ajustes → Borradores) |
| `CAPCUT_EXE` | `%LOCALAPPDATA%\CapCut\Apps\CapCut.exe` |
| `FFMPEG_BIN`, `FFPROBE_BIN` | los del PATH |

## Ejemplos de órdenes a Claude

- *“Crea el proyecto ‘Reel lunes’, importa D:\Grabaciones\toma1.mp4 y hazle auto-edición 9:16 con subtítulos en mayúsculas, hook ‘3 errores que te cuestan dinero’ y la música de mi biblioteca.”*
- *“Quita todos los silencios de más de 0.3 s pero deja 0.15 s de aire.”*
- *“Hazme un lower-third SVG con mi nombre y cárgalo como overlay los primeros 4 segundos.”*
- *“Descarga este B-roll (URL) y ponlo como overlay del segundo 5 al 8.”*
- *“Duplica el borrador en versión 1:1 para LinkedIn.”*
- *“Renderiza el final en 06_Exports con música con ducking.”*

## Límites honestos

- **Efectos, transiciones, filtros, stickers, voces IA y plantillas de CapCut** usan IDs internos de la nube de CapCut no documentados: no se generan desde cero. Truco: crea un borrador plantilla con esos elementos y úsalo con `template=`.
- **Exportar dentro de CapCut** (botón Exportar) no está automatizado; usa `render=True` para el MP4 final por ffmpeg o exporta tú en CapCut tras revisar.
- CapCut debe **reiniciarse** para ver borradores creados mientras estaba abierto (`capcut_app action=restart`).
- Descarga sólo material propio o con licencia; respeta los términos de cada plataforma.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest -q          # requiere ffmpeg
```

Licencia MIT.
