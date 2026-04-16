## 🎵 ArgOS Opus Tag Studio

**Editor de etiquetas exclusivo para archivos de audio Opus**  
ArgOs Platinum Edition · GTK4 / libadwaita · v1.0.0

---

## Capturas

> Interfaz GTK4/libadwaita con panel lateral de archivos, editor completo de metadatos, portada y reproductor integrado.

---

## Características

| Función | Descripción |
|---|---|
| 📂 Explorador | Abre carpetas y lista todos los `.opus` con búsqueda en tiempo real |
| 🏷️ Metadatos completos | Título, Artista, Álbum, Artista del álbum, Año, N° pista, Disco, Género |
| 🖼️ Portada | Vista previa, cambio y eliminación de cover art (JPG/PNG) |
| 📝 Extras | Comentario y letra completa |
| 🎧 Reproductor | Play/pause/stop + barra de progreso con seek via GStreamer |
| 📦 Edición por lotes | Selecciona múltiples archivos y aplica campos comunes de una vez |
| ✏️ Renombrado masivo | Renombra archivos usando patrones como `{tracknumber} - {artist} - {title}` |
| ⌨️ Atajos | `Ctrl+S` guardar · `Ctrl+O` abrir carpeta |

---

## Instalación

### Desde el .deb (recomendado)

```bash
sudo dpkg -i argos-opus-tag-studio_1.0.0_all.deb
sudo apt-get install -f   # resuelve dependencias si es necesario
```

### Dependencias manuales (si es necesario)

```bash
sudo apt install python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 \
  gir1.2-gst-1.0 gir1.2-gdkpixbuf-2.0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  python3-mutagen
```

### Ejecutar directamente

```bash
python3 opus_tag_studio.py
```

---

## Patrones de renombrado

Los tokens disponibles en el diálogo de renombrado son:

| Token | Campo |
|---|---|
| `{title}` | Título |
| `{artist}` | Artista |
| `{album}` | Álbum |
| `{tracknumber}` | Número de pista |
| `{date}` | Año |
| `{genre}` | Género |

**Ejemplo:** `{tracknumber} - {artist} - {title}` → `05 - Artista - Canción.opus`

---

## Requisitos del sistema

- Python 3.10+
- GTK 4.0
- libadwaita 1.2+
- GStreamer 1.0 + plugins-base + plugins-good
- `python3-mutagen`

---

## Licencia

GPL-3.0 · ArgOs Platinum Edition · [github.com/Tavo78ok](https://github.com/Tavo78ok)
