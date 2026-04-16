#!/usr/bin/env python3
# ╔══════════════════════════════════════════════╗
#  ArgOS Opus Tag Studio  v1.0.0
#  Editor de etiquetas GTK4/libadwaita para Opus
#  ArgOs Platinum Edition
# ╚══════════════════════════════════════════════╝

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gst', '1.0')
gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Gtk, Adw, Gst, GLib, Gio, Gdk, GdkPixbuf
import os, sys, base64
from mutagen.oggopus import OggOpus
from mutagen.flac import Picture

Gst.init(None)

APP_ID  = "com.argos.opustageditor"
VERSION = "1.0.0"


# ═══════════════════════════════════════════════
#  GStreamer Player
# ═══════════════════════════════════════════════

class AudioPlayer:
    def __init__(self, on_tick=None, on_eos=None):
        self.pipeline = Gst.parse_launch("playbin")
        self.on_tick  = on_tick
        self.on_eos   = on_eos
        self._tid     = None
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_msg)

    def play(self, path):
        self.stop()
        self.pipeline.set_property("uri", f"file://{os.path.abspath(path)}")
        self.pipeline.set_state(Gst.State.PLAYING)
        self._tid = GLib.timeout_add(300, self._tick)

    def pause(self):
        self.pipeline.set_state(Gst.State.PAUSED)
        self._cancel()

    def resume(self):
        self.pipeline.set_state(Gst.State.PLAYING)
        self._tid = GLib.timeout_add(300, self._tick)

    def stop(self):
        self.pipeline.set_state(Gst.State.NULL)
        self._cancel()

    def seek(self, fraction):
        ok, dur = self.pipeline.query_duration(Gst.Format.TIME)
        if ok and dur > 0:
            self.pipeline.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                int(fraction * dur)
            )

    def get_state(self):
        _, state, _ = self.pipeline.get_state(0)
        return state

    def get_frac(self):
        ok_d, dur = self.pipeline.query_duration(Gst.Format.TIME)
        ok_p, pos = self.pipeline.query_position(Gst.Format.TIME)
        if ok_d and ok_p and dur > 0:
            return pos / dur, pos, dur
        return 0.0, 0, 0

    def _tick(self):
        if self.on_tick:
            self.on_tick()
        return True

    def _cancel(self):
        if self._tid:
            GLib.source_remove(self._tid)
            self._tid = None

    def _on_msg(self, bus, msg):
        if msg.type == Gst.MessageType.EOS:
            self.stop()
            if self.on_eos:
                GLib.idle_add(self.on_eos)
        elif msg.type == Gst.MessageType.ERROR:
            err, _ = msg.parse_error()
            print(f"[GStreamer] {err}")
            self.stop()


# ═══════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.set_title("Opus Tag Studio")
        self.set_default_size(1120, 720)
        self.set_icon_name("audio-x-generic")

        self.current_folder = None
        self.current_file   = None
        self.cover_data     = None
        self.cover_mime     = "image/jpeg"
        self._loading       = False

        self.player = AudioPlayer(
            on_tick=self._player_tick,
            on_eos=self._player_eos
        )
        self._build_ui()

    # ──────────────────────────────────────────
    #  UI assembly
    # ──────────────────────────────────────────

    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        tv = Adw.ToolbarView()
        self.toast_overlay.set_child(tv)
        tv.add_top_bar(self._build_headerbar())

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(300)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_start_child(self._build_sidebar())
        paned.set_end_child(self._build_editor())
        tv.set_content(paned)

        # Ctrl+S shortcut
        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self._on_key)
        self.add_controller(ctrl)

    def _build_headerbar(self):
        hb = Adw.HeaderBar()
        hb.set_centering_policy(Adw.CenteringPolicy.STRICT)

        # Left
        open_btn = Gtk.Button(icon_name="folder-open-symbolic",
                              tooltip_text="Abrir carpeta (Ctrl+O)")
        open_btn.add_css_class("flat")
        open_btn.connect("clicked", self.on_open_folder)
        hb.pack_start(open_btn)

        # Center
        wt = Adw.WindowTitle(title="Opus Tag Studio",
                             subtitle="ArgOs Platinum Edition")
        hb.set_title_widget(wt)

        # Right
        self.save_btn = Gtk.Button(icon_name="document-save-symbolic",
                                   tooltip_text="Guardar etiquetas (Ctrl+S)")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.set_sensitive(False)
        self.save_btn.connect("clicked", self.on_save)
        hb.pack_end(self.save_btn)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_btn.add_css_class("flat")
        menu_btn.set_menu_model(self._build_menu())
        hb.pack_end(menu_btn)

        return hb

    def _build_menu(self):
        menu = Gio.Menu()
        menu.append("Edición por lotes…", "win.batch")
        menu.append("Renombrar archivos…", "win.rename")
        menu.append("Acerca de Opus Tag Studio", "win.about")

        for name, cb in [
            ("batch",  self.on_batch),
            ("rename", self.on_rename),
            ("about",  self.on_about),
        ]:
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            self.add_action(a)
        return menu

    # ──────────────────────────────────────────
    #  Sidebar
    # ──────────────────────────────────────────

    def _build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(280, -1)

        self.search = Gtk.SearchEntry(placeholder_text="Buscar archivos…")
        self.search.set_margin_top(10)
        self.search.set_margin_bottom(6)
        self.search.set_margin_start(10)
        self.search.set_margin_end(10)
        self.search.connect("search-changed",
                            lambda *_: self.file_list.invalidate_filter())
        box.append(self.search)

        self.count_lbl = Gtk.Label(label="Sin carpeta abierta")
        self.count_lbl.add_css_class("caption")
        self.count_lbl.add_css_class("dim-label")
        self.count_lbl.set_halign(Gtk.Align.START)
        self.count_lbl.set_margin_start(12)
        self.count_lbl.set_margin_bottom(4)
        box.append(self.count_lbl)

        box.append(Gtk.Separator())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.file_list = Gtk.ListBox()
        self.file_list.add_css_class("navigation-sidebar")
        self.file_list.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.file_list.connect("row-activated", self.on_row_activated)
        self.file_list.set_filter_func(self._filter_row)
        scroll.set_child(self.file_list)
        box.append(scroll)

        self.sidebar_placeholder = Adw.StatusPage()
        self.sidebar_placeholder.set_icon_name("folder-music-symbolic")
        self.sidebar_placeholder.set_title("Sin archivos")
        self.sidebar_placeholder.set_description(
            "Abre una carpeta con archivos .opus")
        self.sidebar_placeholder.set_vexpand(True)
        box.append(self.sidebar_placeholder)

        return box

    # ──────────────────────────────────────────
    #  Editor panel
    # ──────────────────────────────────────────

    def _build_editor(self):
        self.editor_stack = Gtk.Stack()
        self.editor_stack.set_transition_type(
            Gtk.StackTransitionType.CROSSFADE)

        # Empty state
        empty = Adw.StatusPage()
        empty.set_icon_name("audio-x-generic-symbolic")
        empty.set_title("Selecciona un archivo")
        empty.set_description(
            "Elige un archivo .opus del panel izquierdo para editar sus etiquetas")
        self.editor_stack.add_named(empty, "empty")

        # Editor
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        vbox.set_margin_top(24)
        vbox.set_margin_bottom(32)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)

        # ── Top row: cover + title/artist ──
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        top.set_margin_bottom(4)

        # Cover widget
        cover_overlay = Gtk.Overlay()
        cover_overlay.set_size_request(160, 160)

        self.cover_img = Gtk.Picture()
        self.cover_img.set_size_request(160, 160)
        self.cover_img.set_content_fit(Gtk.ContentFit.COVER)
        cover_overlay.set_child(self.cover_img)

        cover_btns = Gtk.Box(spacing=4)
        cover_btns.set_halign(Gtk.Align.END)
        cover_btns.set_valign(Gtk.Align.END)
        cover_btns.set_margin_end(6)
        cover_btns.set_margin_bottom(6)
        for icon, tip, cb in [
            ("document-open-symbolic", "Cambiar portada", self.on_change_cover),
            ("edit-delete-symbolic",   "Quitar portada",  self.on_remove_cover),
        ]:
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.add_css_class("circular")
            b.add_css_class("osd")
            b.connect("clicked", cb)
            cover_btns.append(b)
        cover_overlay.add_overlay(cover_btns)

        cover_frame = Gtk.Frame()
        cover_frame.add_css_class("card")
        cover_frame.set_child(cover_overlay)
        top.append(cover_frame)

        # Right side: info + title + artist
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right.set_hexpand(True)
        right.set_valign(Gtk.Align.CENTER)

        self.file_info = Gtk.Label(label="")
        self.file_info.add_css_class("caption")
        self.file_info.add_css_class("dim-label")
        self.file_info.set_halign(Gtk.Align.START)
        right.append(self.file_info)

        top_group = Adw.PreferencesGroup()
        self.e_title = Adw.EntryRow(title="Título")
        self.e_title.connect("changed", self._mark_dirty)
        top_group.add(self.e_title)

        self.e_artist = Adw.EntryRow(title="Artista")
        self.e_artist.connect("changed", self._mark_dirty)
        top_group.add(self.e_artist)

        right.append(top_group)
        top.append(right)
        vbox.append(top)

        # ── Album group ──
        album_group = Adw.PreferencesGroup(title="Álbum")

        self.e_album = Adw.EntryRow(title="Álbum")
        self.e_album.connect("changed", self._mark_dirty)
        album_group.add(self.e_album)

        self.e_albumartist = Adw.EntryRow(title="Artista del álbum")
        self.e_albumartist.connect("changed", self._mark_dirty)
        album_group.add(self.e_albumartist)

        self.e_date = Adw.EntryRow(title="Año")
        self.e_date.connect("changed", self._mark_dirty)
        album_group.add(self.e_date)

        self.e_track = Adw.EntryRow(title="N° de pista")
        self.e_track.connect("changed", self._mark_dirty)
        album_group.add(self.e_track)

        self.e_disc = Adw.EntryRow(title="Disco")
        self.e_disc.connect("changed", self._mark_dirty)
        album_group.add(self.e_disc)

        self.e_genre = Adw.EntryRow(title="Género")
        self.e_genre.connect("changed", self._mark_dirty)
        album_group.add(self.e_genre)

        vbox.append(album_group)

        # ── Extras group ──
        extra_group = Adw.PreferencesGroup(title="Extras")

        self.e_comment = Adw.EntryRow(title="Comentario")
        self.e_comment.connect("changed", self._mark_dirty)
        extra_group.add(self.e_comment)

        vbox.append(extra_group)

        # ── Lyrics ──
        lyrics_group = Adw.PreferencesGroup(title="Letra")

        ly_scroll = Gtk.ScrolledWindow()
        ly_scroll.set_min_content_height(110)
        ly_scroll.set_max_content_height(200)
        ly_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.lyrics_buf = Gtk.TextBuffer()
        self.lyrics_buf.connect("changed", self._mark_dirty)

        tv_lyr = Gtk.TextView(buffer=self.lyrics_buf)
        tv_lyr.set_wrap_mode(Gtk.WrapMode.WORD)
        tv_lyr.set_left_margin(12)
        tv_lyr.set_right_margin(12)
        tv_lyr.set_top_margin(8)
        tv_lyr.set_bottom_margin(8)
        ly_scroll.set_child(tv_lyr)

        lyr_frame = Gtk.Frame()
        lyr_frame.add_css_class("card")
        lyr_frame.set_child(ly_scroll)
        lyrics_group.add(lyr_frame)
        vbox.append(lyrics_group)

        # ── Player ──
        player_group = Adw.PreferencesGroup(title="Vista previa de audio")
        player_group.add(self._build_player())
        vbox.append(player_group)

        scroll.set_child(vbox)
        self.editor_stack.add_named(scroll, "editor")
        return self.editor_stack

    def _build_player(self):
        card = Gtk.Frame()
        card.add_css_class("card")

        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pbox.set_margin_top(12)
        pbox.set_margin_bottom(14)
        pbox.set_margin_start(16)
        pbox.set_margin_end(16)

        self.player_name = Gtk.Label(label="Sin archivo seleccionado")
        self.player_name.add_css_class("caption")
        self.player_name.add_css_class("dim-label")
        self.player_name.set_halign(Gtk.Align.START)
        self.player_name.set_ellipsize(3)
        pbox.append(self.player_name)

        self.progress = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.progress.set_range(0, 1)
        self.progress.set_draw_value(False)
        self.progress.set_hexpand(True)
        self.progress.connect("change-value", self._on_seek)
        pbox.append(self.progress)

        time_row = Gtk.Box()
        self.lbl_pos = Gtk.Label(label="0:00")
        self.lbl_pos.add_css_class("caption")
        self.lbl_pos.add_css_class("numeric")
        time_row.append(self.lbl_pos)

        spc = Gtk.Box()
        spc.set_hexpand(True)
        time_row.append(spc)

        self.lbl_dur = Gtk.Label(label="0:00")
        self.lbl_dur.add_css_class("caption")
        self.lbl_dur.add_css_class("numeric")
        time_row.append(self.lbl_dur)
        pbox.append(time_row)

        ctrl = Gtk.Box(spacing=6)
        ctrl.set_halign(Gtk.Align.CENTER)

        self.play_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.play_btn.add_css_class("circular")
        self.play_btn.add_css_class("suggested-action")
        self.play_btn.set_size_request(44, 44)
        self.play_btn.connect("clicked", self.on_play_pause)
        ctrl.append(self.play_btn)

        stop_btn = Gtk.Button(icon_name="media-playback-stop-symbolic")
        stop_btn.add_css_class("circular")
        stop_btn.connect("clicked", self.on_stop)
        ctrl.append(stop_btn)

        pbox.append(ctrl)
        card.set_child(pbox)
        return card

    # ──────────────────────────────────────────
    #  File loading
    # ──────────────────────────────────────────

    def on_open_folder(self, *_):
        d = Gtk.FileDialog(title="Abrir carpeta con archivos Opus")
        d.select_folder(self, None, self._folder_cb)

    def _folder_cb(self, d, res):
        try:
            f = d.select_folder_finish(res)
            if f:
                self._load_folder(f.get_path())
        except Exception as e:
            print(e)

    def _load_folder(self, path):
        self.current_folder = path

        files = sorted(
            os.path.join(path, n)
            for n in os.listdir(path)
            if n.lower().endswith(".opus")
        )

        # Clear listbox
        while True:
            row = self.file_list.get_row_at_index(0)
            if row is None:
                break
            self.file_list.remove(row)

        if not files:
            self.sidebar_placeholder.set_visible(True)
            self.file_list.set_visible(False)
            self.count_lbl.set_label("Sin archivos .opus en esta carpeta")
            return

        self.sidebar_placeholder.set_visible(False)
        self.file_list.set_visible(True)
        self.count_lbl.set_label(f"{len(files)} archivos Opus")

        for fp in files:
            self.file_list.append(self._make_row(fp))

    def _make_row(self, fp):
        row = Gtk.ListBoxRow()
        row.fp = fp

        box = Gtk.Box(spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(10)
        box.set_margin_end(10)

        img = Gtk.Image(icon_name="audio-x-generic-symbolic")
        img.add_css_class("dim-label")
        box.append(img)

        lbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbox.set_hexpand(True)

        name_lbl = Gtk.Label(label=os.path.basename(fp))
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_ellipsize(3)
        name_lbl.set_max_width_chars(28)
        lbox.append(name_lbl)

        # Subtitle: artista - título
        try:
            tags   = OggOpus(fp)
            artist = tags.get("artist", [""])[0]
            title  = tags.get("title",  [""])[0]
            sub    = " — ".join(x for x in [artist, title] if x)
            if sub:
                sub_lbl = Gtk.Label(label=sub)
                sub_lbl.set_halign(Gtk.Align.START)
                sub_lbl.add_css_class("caption")
                sub_lbl.add_css_class("dim-label")
                sub_lbl.set_ellipsize(3)
                sub_lbl.set_max_width_chars(28)
                lbox.append(sub_lbl)
        except Exception:
            pass

        box.append(lbox)
        row.set_child(box)
        return row

    def _filter_row(self, row):
        q = self.search.get_text().lower()
        if not q:
            return True
        return q in os.path.basename(getattr(row, "fp", "")).lower()

    # ──────────────────────────────────────────
    #  Tag loading / saving
    # ──────────────────────────────────────────

    def on_row_activated(self, lb, row):
        self.current_file = row.fp
        self._load_tags(row.fp)
        self.editor_stack.set_visible_child_name("editor")
        self.player_name.set_label(os.path.basename(row.fp))

    def _load_tags(self, fp):
        try:
            tags = OggOpus(fp)
        except Exception as e:
            self._toast(f"Error al leer archivo: {e}")
            return

        self._loading = True

        def g(k):
            return tags.get(k, [""])[0]

        self.e_title.set_text(g("title"))
        self.e_artist.set_text(g("artist"))
        self.e_album.set_text(g("album"))
        self.e_albumartist.set_text(g("albumartist"))
        self.e_date.set_text(g("date"))
        self.e_track.set_text(g("tracknumber"))
        self.e_disc.set_text(g("discnumber"))
        self.e_genre.set_text(g("genre"))
        self.e_comment.set_text(g("comment"))
        self.lyrics_buf.set_text(g("lyrics"))

        # Cover art
        self.cover_data = None
        self.cover_img.set_paintable(None)
        if "metadata_block_picture" in tags:
            try:
                raw     = base64.b64decode(tags["metadata_block_picture"][0])
                pic     = Picture(raw)
                loader  = GdkPixbuf.PixbufLoader()
                loader.write(pic.data)
                loader.close()
                pb      = loader.get_pixbuf()
                texture = Gdk.Texture.new_for_pixbuf(pb)
                self.cover_img.set_paintable(texture)
                self.cover_data = pic.data
                self.cover_mime = pic.mime
            except Exception as e:
                print(f"[cover] {e}")

        # File info bar
        size_kb = os.path.getsize(fp) // 1024
        try:
            dur   = int(tags.info.length)
            dur_s = f"{dur // 60}:{dur % 60:02d}"
        except Exception:
            dur_s = "?"
        self.file_info.set_label(f"{size_kb} KB  ·  {dur_s}  ·  Opus")

        self._loading = False
        self.save_btn.set_sensitive(True)

    def _mark_dirty(self, *_):
        if not self._loading:
            self.save_btn.set_sensitive(True)

    def on_save(self, *_):
        rows = self.file_list.get_selected_rows()
        targets = [r.fp for r in rows] if rows else (
            [self.current_file] if self.current_file else [])
        if not targets:
            return
        saved = sum(1 for fp in targets if self._save_one(fp))
        self._toast(f"✓ Etiquetas guardadas ({saved} archivo{'s' if saved != 1 else ''})")
        # Refresh sidebar subtitles
        if self.current_folder:
            self._load_folder(self.current_folder)

    def _save_one(self, fp):
        try:
            tags = OggOpus(fp)
        except Exception as e:
            self._toast(f"Error al abrir {os.path.basename(fp)}: {e}")
            return False

        def s(k, v):
            if v:
                tags[k] = [v]
            elif k in tags:
                del tags[k]

        s("title",       self.e_title.get_text().strip())
        s("artist",      self.e_artist.get_text().strip())
        s("album",       self.e_album.get_text().strip())
        s("albumartist", self.e_albumartist.get_text().strip())
        s("date",        self.e_date.get_text().strip())
        s("tracknumber", self.e_track.get_text().strip())
        s("discnumber",  self.e_disc.get_text().strip())
        s("genre",       self.e_genre.get_text().strip())
        s("comment",     self.e_comment.get_text().strip())

        lyr = self.lyrics_buf.get_text(
            self.lyrics_buf.get_start_iter(),
            self.lyrics_buf.get_end_iter(), False
        ).strip()
        s("lyrics", lyr)

        if self.cover_data:
            pic      = Picture()
            pic.type = 3
            pic.mime = self.cover_mime
            pic.data = self.cover_data
            tags["metadata_block_picture"] = [
                base64.b64encode(pic.write()).decode("ascii")
            ]
        elif "metadata_block_picture" in tags:
            del tags["metadata_block_picture"]

        try:
            tags.save()
            return True
        except Exception as e:
            self._toast(f"Error al guardar: {e}")
            return False

    # ──────────────────────────────────────────
    #  Cover art
    # ──────────────────────────────────────────

    def on_change_cover(self, *_):
        d = Gtk.FileDialog(title="Seleccionar imagen de portada")
        flt = Gtk.FileFilter()
        flt.set_name("Imágenes (JPG, PNG)")
        flt.add_mime_type("image/jpeg")
        flt.add_mime_type("image/png")
        ls = Gio.ListStore.new(Gtk.FileFilter)
        ls.append(flt)
        d.set_filters(ls)
        d.open(self, None, self._cover_cb)

    def _cover_cb(self, d, res):
        try:
            file = d.open_finish(res)
            if not file:
                return
            path = file.get_path()
            with open(path, "rb") as fh:
                self.cover_data = fh.read()
            self.cover_mime = (
                "image/png"
                if path.lower().endswith(".png")
                else "image/jpeg"
            )
            loader = GdkPixbuf.PixbufLoader()
            loader.write(self.cover_data)
            loader.close()
            pb = loader.get_pixbuf()
            self.cover_img.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
            self._mark_dirty()
        except Exception as e:
            self._toast(f"Error al cargar imagen: {e}")

    def on_remove_cover(self, *_):
        self.cover_data = None
        self.cover_img.set_paintable(None)
        self._mark_dirty()

    # ──────────────────────────────────────────
    #  Audio player
    # ──────────────────────────────────────────

    def on_play_pause(self, *_):
        if not self.current_file:
            return
        state = self.player.get_state()
        if state == Gst.State.PLAYING:
            self.player.pause()
            self.play_btn.set_icon_name("media-playback-start-symbolic")
        elif state == Gst.State.PAUSED:
            self.player.resume()
            self.play_btn.set_icon_name("media-playback-pause-symbolic")
        else:
            self.player.play(self.current_file)
            self.play_btn.set_icon_name("media-playback-pause-symbolic")

    def on_stop(self, *_):
        self.player.stop()
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.progress.set_value(0)
        self.lbl_pos.set_label("0:00")
        self.lbl_dur.set_label("0:00")

    def _on_seek(self, scale, scroll_type, value):
        self.player.seek(max(0.0, min(1.0, value)))
        return False

    def _player_tick(self):
        frac, pos, dur = self.player.get_frac()
        self.progress.set_value(frac)
        p = pos // Gst.SECOND
        d = dur // Gst.SECOND
        self.lbl_pos.set_label(f"{p // 60}:{p % 60:02d}")
        self.lbl_dur.set_label(f"{d // 60}:{d % 60:02d}")

    def _player_eos(self):
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.progress.set_value(0)

    # ──────────────────────────────────────────
    #  Batch edit
    # ──────────────────────────────────────────

    def on_batch(self, *_):
        rows = self.file_list.get_selected_rows()
        if len(rows) < 2:
            self._toast("Selecciona 2 o más archivos para edición por lotes")
            return
        BatchDialog(self, [r.fp for r in rows]).present()

    def apply_batch(self, files, data):
        ok = 0
        for fp in files:
            try:
                tags = OggOpus(fp)
                for k, v in data.items():
                    if v:
                        tags[k] = [v]
                tags.save()
                ok += 1
            except Exception as e:
                print(f"[batch] {fp}: {e}")
        self._toast(f"✓ {ok}/{len(files)} archivos actualizados")
        if self.current_folder:
            self._load_folder(self.current_folder)

    # ──────────────────────────────────────────
    #  Rename
    # ──────────────────────────────────────────

    def on_rename(self, *_):
        rows = self.file_list.get_selected_rows()
        if not rows:
            self._toast("Selecciona archivos para renombrar")
            return
        RenameDialog(self, [r.fp for r in rows]).present()

    def apply_rename(self, files, pattern):
        ok = 0
        for fp in files:
            try:
                tags = OggOpus(fp)
                name = pattern
                for k in ("title", "artist", "album", "tracknumber", "date", "genre"):
                    val = "".join(
                        c for c in tags.get(k, [""])[0]
                        if c not in r'\/:*?"<>|'
                    )
                    name = name.replace(f"{{{k}}}", val)
                name = name.strip().strip(".")
                if not name:
                    continue
                new_fp = os.path.join(os.path.dirname(fp), name + ".opus")
                if new_fp != fp:
                    os.rename(fp, new_fp)
                    ok += 1
            except Exception as e:
                print(f"[rename] {fp}: {e}")
        self._toast(f"✓ {ok} archivo{'s' if ok != 1 else ''} renombrado{'s' if ok != 1 else ''}")
        if self.current_folder:
            self._load_folder(self.current_folder)

    # ──────────────────────────────────────────
    #  About
    # ──────────────────────────────────────────

    def on_about(self, *_):
        about = Adw.AboutWindow(transient_for=self)
        about.set_application_name("Opus Tag Studio")
        about.set_version(VERSION)
        about.set_developer_name("ArgOs Platinum Edition")
        about.set_application_icon("audio-x-generic")
        about.set_comments(
            "Editor de etiquetas exclusivo para archivos de audio Opus.\n"
            "Soporta todos los campos Vorbis Comment incluyendo portada,\n"
            "letra, edición por lotes y renombrado masivo."
        )
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://github.com/Tavo78ok")
        about.present()

    # ──────────────────────────────────────────
    #  Keyboard / utils
    # ──────────────────────────────────────────

    def _on_key(self, ctrl, keyval, keycode, mod):
        if mod & Gdk.ModifierType.CONTROL_MASK:
            if keyval == Gdk.KEY_s:
                self.on_save()
                return True
            if keyval == Gdk.KEY_o:
                self.on_open_folder()
                return True
        return False

    def _toast(self, msg):
        t = Adw.Toast.new(msg)
        t.set_timeout(3)
        self.toast_overlay.add_toast(t)


# ═══════════════════════════════════════════════
#  Batch Edit Dialog
# ═══════════════════════════════════════════════

class BatchDialog(Adw.Window):
    def __init__(self, parent, files):
        super().__init__(transient_for=parent, modal=True)
        self.parent_win = parent
        self.files      = files
        self.set_title("Edición por lotes")
        self.set_default_size(430, -1)
        self.set_resizable(False)

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(20)
        box.set_margin_start(16)
        box.set_margin_end(16)

        banner = Adw.Banner()
        banner.set_title(
            f"Editando {len(files)} archivos — "
            "solo se sobrescriben los campos con contenido"
        )
        banner.set_revealed(True)
        box.append(banner)

        group = Adw.PreferencesGroup()
        self.fields = {}
        for k, t in [
            ("artist",      "Artista"),
            ("album",       "Álbum"),
            ("albumartist", "Artista del álbum"),
            ("date",        "Año"),
            ("genre",       "Género"),
        ]:
            row = Adw.EntryRow(title=t)
            group.add(row)
            self.fields[k] = row
        box.append(group)

        btn = Gtk.Button(label="Aplicar a todos los archivos")
        btn.add_css_class("suggested-action")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect("clicked", self._apply)
        box.append(btn)

        tv.set_content(box)
        self.set_content(tv)

    def _apply(self, *_):
        data = {k: r.get_text().strip() for k, r in self.fields.items()}
        self.parent_win.apply_batch(self.files, data)
        self.close()


# ═══════════════════════════════════════════════
#  Rename Dialog
# ═══════════════════════════════════════════════

class RenameDialog(Adw.Window):
    def __init__(self, parent, files):
        super().__init__(transient_for=parent, modal=True)
        self.parent_win = parent
        self.files      = files
        self.set_title("Renombrar archivos")
        self.set_default_size(490, -1)
        self.set_resizable(False)

        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(20)
        box.set_margin_start(16)
        box.set_margin_end(16)

        group = Adw.PreferencesGroup(title="Patrón de nombre de archivo")
        group.set_description(
            "Tokens: {tracknumber}  {artist}  {title}  {album}  {date}  {genre}"
        )
        self.pat_row = Adw.EntryRow(title="Patrón")
        self.pat_row.set_text("{tracknumber} - {artist} - {title}")
        self.pat_row.connect("changed", self._update_preview)
        group.add(self.pat_row)
        box.append(group)

        preview_group = Adw.PreferencesGroup(title="Vista previa — primer archivo")
        self.preview_lbl = Gtk.Label(label="")
        self.preview_lbl.add_css_class("caption")
        self.preview_lbl.add_css_class("monospace")
        self.preview_lbl.set_wrap(True)
        self.preview_lbl.set_margin_top(6)
        self.preview_lbl.set_margin_bottom(6)
        preview_group.add(self.preview_lbl)
        box.append(preview_group)

        self._update_preview()

        btn = Gtk.Button(label=f"Renombrar {len(files)} archivos")
        btn.add_css_class("destructive-action")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect("clicked", self._apply)
        box.append(btn)

        tv.set_content(box)
        self.set_content(tv)

    def _update_preview(self, *_):
        if not self.files:
            return
        pat = self.pat_row.get_text()
        try:
            tags = OggOpus(self.files[0])
            name = pat
            for k in ("title", "artist", "album", "tracknumber", "date", "genre"):
                val = "".join(
                    c for c in tags.get(k, [""])[0]
                    if c not in r'\/:*?"<>|'
                )
                name = name.replace(f"{{{k}}}", val)
            self.preview_lbl.set_label(f"{name.strip()}.opus")
        except Exception:
            self.preview_lbl.set_label("(no se pudo leer el archivo)")

    def _apply(self, *_):
        pat = self.pat_row.get_text().strip()
        if pat:
            self.parent_win.apply_rename(self.files, pat)
        self.close()


# ═══════════════════════════════════════════════
#  Application entry point
# ═══════════════════════════════════════════════

class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self._activate)

    def _activate(self, _):
        MainWindow(application=self).present()


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
