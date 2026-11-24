"""Faux module « orca » pour tester le plugin hors d'OrcaSlicer."""
import io, json, sys, types, zipfile, threading

class FakeWindow:
    """Recoit les messages envoyes a la page (fenetre ou onglet) et permet de les attendre."""
    def __init__(self, **k):
        self.k = k; self.posts = []; self.open_ = True; self.cv = threading.Condition()
    def post(self, d):
        d = json.loads(json.dumps(d))
        with self.cv:
            self.posts.append(d); self.cv.notify_all()
    def is_open(self): return self.open_
    def close(self):
        self.open_ = False; cb = self.k.get("on_close"); cb and cb()
    def send(self, m): self.k["on_message"](m)
    def wait(self, cmd, n=1, timeout=60):
        import time
        end = time.time() + timeout
        with self.cv:
            while True:
                got = [p for p in self.posts if p.get("command") == cmd]
                if len(got) >= n: return got[n - 1]
                errs = [p for p in self.posts if p.get("command") == "error"]
                if errs: raise AssertionError("erreur : %s" % errs[-1]["text"])
                left = end - time.time()
                if left <= 0: raise AssertionError("pas de message %s (recus %s)" % (cmd, [p["command"] for p in self.posts]))
                self.cv.wait(left)

class FakePanel(FakeWindow):
    """Panneau d'Orca a cote du plateau (orca.host.ui.create_dock_panel) : montre, cache, ferme."""
    def __init__(self, **k):
        super().__init__(**k); self.shown = True
    def show(self): self.shown = True
    def hide(self): self.shown = False
    def close(self):
        if self.open_:
            self.open_ = False; self.shown = False; cb = self.k.get("on_close"); cb and cb()

def template_3mf_bytes(cfg):
    """Projet enregistre comme le fait OrcaSlicer 2.5.1 : application « BambuStudio-02.08.01.55 » et
    etiquette « OrcaSlicer »."""
    main = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
            ' <metadata name="Application">BambuStudio-02.08.01.55</metadata>\n <metadata name="OrcaSlicer">2.5.1</metadata>\n'
            ' <resources>\n </resources>\n <build/>\n</model>\n')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", main)
        z.writestr("Metadata/project_settings.config", json.dumps(cfg))
    return buf.getvalue()

def install(storage, template_cfg, current=None, dock=False):
    orca = types.ModuleType("orca")
    state = {"windows": [], "panels": [], "notes": [], "perms": [], "caps": [], "exports": 0, "language": "fr_FR", "presets": []}
    cur = dict(current or template_cfg)
    def ser(v):
        if isinstance(v, list):
            if v and all(isinstance(x, str) and (x.startswith("#") or not x.replace(".", "").replace("x", "").isdigit()) for x in v) and v and v[0].startswith("#"):
                return ";".join('"%s"' % x for x in v)
            if any(x == "" or "," in x for x in v):     # comme Orca : chaines entre guillemets
                return ";".join('"%s"' % x for x in v)
            return ",".join(v)
        return str(v)
    class Preset:
        def __init__(s, name, cfg): s.name = name; s._c = cfg
        def config_value(s, k): v = s._c.get(k); return None if v is None else ser(v)
    class Collection:
        """Comme PresetCollection d'Orca : prereglages de filament (state["presets"], FakePreset)."""
        def size(s): return len(state["presets"])
        def preset(s, i): return state["presets"][i]
        def find_preset(s, name): return next((p for p in state["presets"] if p.name == name), None)

    class Bundle:
        filaments = Collection()
        def current_printer_preset(s): return Preset(state.get("printer") or cur.get("printer_settings_id"), cur)
        def current_process_preset(s): return Preset(cur.get("print_settings_id"), cur)
        def current_filament_preset_names(s): return list(cur.get("filament_settings_id", []))
        def full_config_value(s, k):
            v = cur.get(k)
            if v is None: return None
            if k == "filament_settings_id": return ";".join('"%s"' % x for x in v)
            return ser(v)
    class Plater:
        def export_3mf_copy(s, path):
            state["exports"] += 1
            open(path, "wb").write(template_3mf_bytes(cur))
    ui = types.SimpleNamespace()
    def create_window(**k):
        w = FakeWindow(**k); state["windows"].append(w); return w
    ui.create_window = create_window
    if dock:   # OrcaSlicer 2.5.1 : panneaux a cote du plateau (sans : comme un Orca plus ancien)
        def create_dock_panel(**k):
            p = FakePanel(**k); state["panels"].append(p); return p
        ui.create_dock_panel = create_dock_panel
    ui.NotificationLevel = types.SimpleNamespace(ImportantNotificationLevel="Important", WarningNotificationLevel="Warning",
                                                 RegularNotificationLevel="Regular")
    ui.push_notification = lambda lvl, txt, hyper="", cb=None: state["notes"].append((lvl, txt, hyper, cb))
    orca.host = types.SimpleNamespace(ui=ui, preset_bundle=lambda: Bundle(), plater=lambda: Plater(),
                                      plugin=types.SimpleNamespace(storage=lambda: storage),
                                      # comme Orca : langue de l'interface (« fr_FR », « en_US »...)
                                      app_info=lambda: {"version": "2.5.1", "language": state["language"]})
    class Base: pass
    class ScriptBase: pass
    page = FakeWindow()
    state["page"] = page
    class PagesBase:
        """Comme orca.pages.PagesPluginCapabilityBase : post_message vers la page de l'onglet."""
        def post_message(self, data): page.post(data)
    orca.base = Base
    orca.script = types.SimpleNamespace(ScriptPluginCapabilityBase=ScriptBase)
    orca.pages = types.SimpleNamespace(PagesPluginCapabilityBase=PagesBase)
    orca.plugin = lambda cls: (state.__setitem__("plugin", cls), cls)[1]
    orca.register_capability = lambda c: state["caps"].append(c)
    orca.request_permissions = lambda **k: state["perms"].append(k)
    class ER:
        def __init__(s, kind, msg=""): s.kind = kind; s.msg = msg
        @staticmethod
        def success(m=""): return ER("success", m)
        @staticmethod
        def skipped(m=""): return ER("skipped", m)
    orca.ExecutionResult = ER
    orca.LifecycleEvent = types.SimpleNamespace(ProjectOpened="ProjectOpened", NewProject="NewProject")
    sys.modules["orca"] = orca
    return orca, state, cur


# --------------------------------------------------------------------------- prereglages de filament

STRINGS = {"filament_type", "filament_vendor", "default_filament_colour", "filament_settings_id", "filament_start_gcode",
           "filament_end_gcode", "filament_notes", "compatible_printers", "compatible_prints", "filament_extruder_variant",
           "filament_ramming_parameters", "filament_colour", "filament_multi_colour", "filament_colour_type"}


def orca_serialize(values, strings):
    """Comme ConfigOption::serialize d'Orca : textes separes par « ; » (entre guillemets si besoin),
    le reste par « , »."""
    if not strings:
        return ",".join(values)
    out = []
    for x in values:
        if (len(values) == 1 and x == "") or any(c in x for c in ' ;\t\\"\r\n'):
            x = '"' + x.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'
        out.append(x)
    return ";".join(out)


class FakePreset:
    """Comme un Preset d'Orca vu par un plugin."""

    def __init__(self, name, values, user=True, embedded=False, compatible=True, system=False, default=False):
        self.name = name
        self._v = dict(values)
        self.is_project_embedded = embedded
        self.is_compatible = compatible
        self.is_system = system
        self.is_default = default
        self._user = user

    def is_user(self):
        return self._user

    def config_keys(self):
        return list(self._v)

    def config_value(self, key):
        return self._v.get(key)


def preset_from(cfg, slot, name, variants=("Direct Drive Standard", "Direct Drive High Flow"), changes=None,
                inherits="", condition="", prints_condition="", filament_id=None):
    """Prereglage fait d'une case de reglages de projet (une valeur par variante de buse), modifie par
    changes {cle: liste de valeurs}."""
    import mange_3mf_any as m
    total = len(cfg["filament_colour"])
    rows = [r for r, fi in enumerate(cfg.get("filament_self_index", [])) if int(fi) == slot + 1]
    vals = {}
    for key, v in cfg.items():
        if not isinstance(v, list) or key in ("filament_self_index", "filament_colour", "filament_multi_colour",
                                                "filament_colour_type", "filament_settings_id", "filament_ids"):
            continue
        if key not in m.FILAMENT_PRESET_KEYS and not key.startswith("filament_"):
            continue
        if rows and len(v) == len(cfg["filament_self_index"]) and len(v) != total:
            got = [v[r] for r in rows][:len(variants)]
            got += [got[-1]] * (len(variants) - len(got))
        elif len(v) == total:
            got = [v[slot]]
        else:
            continue
        vals[key] = got
    vals["filament_extruder_variant"] = list(variants)
    for k, v in (changes or {}).items():
        vals[k] = list(v)
    raw = {k: orca_serialize(v, k in STRINGS or any("," in x or " " in x or "\n" in x for x in v)) for k, v in vals.items()}
    raw["filament_settings_id"] = orca_serialize([name], True)
    raw["inherits"] = inherits
    raw["compatible_printers_condition"] = condition
    raw["compatible_prints_condition"] = prints_condition
    if filament_id is not None:
        raw["filament_id"] = filament_id
    return raw
